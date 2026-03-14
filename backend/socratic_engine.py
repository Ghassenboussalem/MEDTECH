"""
socratic_engine.py — Three AI teaching modes.
NEVER gives direct answers — only asks guiding questions and gives RAG-grounded hints.

Modes:
  feynman        — AI is a curious 8-year-old, student must explain simply
  socratic       — AI asks sub-questions guiding student to self-discover
  devil_advocate — AI presents a wrong claim, student must find and fix the error

Also provides score_response() to evaluate student understanding asynchronously.
"""
import asyncio
import json
import re
from collections.abc import AsyncGenerator

import ollama

from embeddings import query as vector_query

CHAT_MODEL = "llama3.2:latest"
BLOOM_ORDER = ["remember", "understand", "apply", "analyze", "evaluate", "create"]

_NO_ANSWER = (
    "ABSOLUTE RULE: You must NEVER state the answer, define the concept, or explain it "
    "yourself. Your only tools are questions, expressions of confusion, and single-word "
    "hints when the student is completely stuck. If you catch yourself about to give "
    "information, STOP and turn it into a question instead."
)

# ── System prompts ─────────────────────────────────────────────────────────────

_FEYNMAN_SYS = (
    f"{_NO_ANSWER}\n\n"
    "You are a curious, enthusiastic 8-year-old child who wants to understand everything. "
    "The student is trying to teach you the concept '{concept_name}'. Your behaviour:\n"
    "- Ask 'why?' and 'what does {word} mean?' whenever you hear jargon\n"
    "- Ask 'can you give me an example?' when the explanation is too abstract\n"
    "- Say 'I don't understand how A leads to B' when there is a logical gap\n"
    "- Express genuine delight when you understand something small\n"
    "- Keep each reply to 1-3 short sentences — you are a child, not a professor\n\n"
    "Context clue (do NOT reveal this directly): {context_hint}"
)

_SOCRATIC_SYS = (
    f"{_NO_ANSWER}\n\n"
    "You are a Socratic tutor helping a student discover '{concept_name}' themselves. "
    "Bloom's taxonomy target for this student: {bloom_target}.\n"
    "Your behaviour:\n"
    "- Break the concept into smaller sub-questions the student can answer step by step\n"
    "- When the student answers correctly, acknowledge briefly and ask the next sub-question\n"
    "- When the student is wrong or incomplete, ask a question that reveals the gap\n"
    "- If the student is stuck on an advanced point, check whether they grasp a prerequisite first\n"
    "- Ground every question in the actual course material below\n\n"
    "Relevant course material:\n{context}"
)

_DEVIL_SYS = (
    f"{_NO_ANSWER}\n\n"
    "You are playing Devil's Advocate on the topic '{concept_name}'. "
    "Present a plausible but WRONG or INCOMPLETE claim and challenge the student to correct you.\n"
    "Rules:\n"
    "- State your wrong claim confidently at the start\n"
    "- Known student misconception to target (if any): {misconception}\n"
    "- When the student challenges you, push back: 'Are you sure? Because...'\n"
    "- When the student's correction is right, reluctantly concede and probe deeper\n"
    "- If the student is also wrong, ask a follow-up question — never give the answer\n"
    "- Keep the deliberate error plausible, not obviously silly\n\n"
    "Relevant context (use to craft a believable wrong claim): {context_hint}"
)

_SCORING_PROMPT = (
    "You are an expert educational assessor. Evaluate the student's response.\n"
    "Return ONLY a valid JSON object — no markdown, no extra text.\n\n"
    "Concept: {concept_name}\n"
    "Bloom target: {bloom_level}\n"
    "Assessment indicators: {indicators}\n"
    "Student response: {response}\n"
    "Course context: {context}\n\n"
    'Return: {{"score":0.75,"bloom_demonstrated":"understand",'
    '"misconceptions_detected":["student said X which is wrong"],'
    '"feedback_hint":"One sentence hint — do NOT give the answer"}}\n\n'
    "Rules:\n"
    "- score 0.0 (completely wrong) → 1.0 (perfect)\n"
    "- bloom_demonstrated = highest Bloom level the response shows\n"
    "- misconceptions_detected = list of specific wrong beliefs (empty list [] if none)\n"
    "- Be generous: correct core concept = CORRECT even if imperfectly phrased\n"
    "- feedback_hint must not contain the answer — only a direction\n"
    "- RETURN ONLY JSON"
)


# ── Mode selection ─────────────────────────────────────────────────────────────

def select_mode(concept: dict, force_mode: str | None = None) -> str:
    if force_mode in ("feynman", "socratic", "devil_advocate"):
        return force_mode
    br = concept.get("bloom_reached", "remember")
    idx = BLOOM_ORDER.index(br) if br in BLOOM_ORDER else 0
    # Devil's Advocate if student has active misconceptions (caller checks externally)
    if idx <= 1:
        return "feynman"
    elif idx <= 3:
        return "socratic"
    return "devil_advocate"


# ── Streaming response ─────────────────────────────────────────────────────────

async def socratic_stream(
    notebook_id: str,
    concept: dict,
    history: list[dict],
    student_message: str,
    mode: str | None = None,
    active_misconception: str | None = None,
) -> AsyncGenerator[str, None]:
    """Async generator yielding token strings for the Socratic AI reply."""

    mode = select_mode(concept, mode)

    # RAG context
    chunks = vector_query(notebook_id, concept.get("name", "") + " " + student_message, k=4)
    context = "\n\n".join(c["text"] for c in chunks) if chunks else "(no course material loaded)"
    context_hint = context[:500]

    br = concept.get("bloom_reached", "remember")
    idx = BLOOM_ORDER.index(br) if br in BLOOM_ORDER else 0
    bloom_target = BLOOM_ORDER[min(idx + 1, len(BLOOM_ORDER) - 1)]

    # Build system prompt
    if mode == "feynman":
        system = _FEYNMAN_SYS.format(
            concept_name=concept.get("name", ""),
            context_hint=context_hint,
            word="{word}",
        )
    elif mode == "devil_advocate":
        mc = active_misconception or (
            concept.get("common_misconceptions", [""])[0]
            if concept.get("common_misconceptions") else ""
        )
        system = _DEVIL_SYS.format(
            concept_name=concept.get("name", ""),
            misconception=mc,
            context_hint=context_hint,
        )
    else:
        system = _SOCRATIC_SYS.format(
            concept_name=concept.get("name", ""),
            bloom_target=bloom_target,
            context=context_hint,
        )

    messages = [{"role": "system", "content": system}]
    for msg in history[-8:]:   # cap history to last 8 turns
        messages.append(msg)
    messages.append({"role": "user", "content": student_message})

    def _start_stream():
        return ollama.chat(model=CHAT_MODEL, messages=messages, stream=True)

    stream = await asyncio.to_thread(_start_stream)
    for part in stream:
        token = part["message"]["content"]
        if token:
            yield token


# ── Response scoring ────────────────────────────────────────────────────────────

async def score_response(
    notebook_id: str,
    concept: dict,
    student_response: str,
) -> dict:
    """Score the student's understanding. Returns score dict."""
    chunks = vector_query(notebook_id, concept.get("name", ""), k=3)
    context = "\n".join(c["text"] for c in chunks) if chunks else ""

    prompt = _SCORING_PROMPT.format(
        concept_name=concept.get("name", ""),
        bloom_level=concept.get("bloom_level", "understand"),
        indicators=", ".join(concept.get("assessment_indicators", [])) or "general understanding",
        response=student_response[:800],
        context=context[:600],
    )

    def _call():
        return ollama.chat(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )

    resp = await asyncio.to_thread(_call)
    raw = resp["message"]["content"]
    clean = re.sub(r"```json\n?|\n?```", "", raw).strip()
    clean = re.sub(r",\s*([\]}])", r"\1", clean)
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return {
            "score": 0.5,
            "bloom_demonstrated": "remember",
            "misconceptions_detected": [],
            "feedback_hint": "Keep exploring this concept!",
        }
