"""
chat.py — RAG pipeline: retrieve relevant chunks, then stream an answer from llama3.2.

`rag_stream()` is an async generator that yields text tokens.
`generate_artifact()` returns a single string for summaries / FAQ / study guides.
"""
import asyncio
import json
from collections.abc import AsyncGenerator

import ollama

from embeddings import query as vector_query
from guardrails import run_input_guards, output_safety_guard

CHAT_MODEL = "llama3.2:latest"

SYSTEM_PROMPT = """You are a meticulous research assistant. You answer questions \
ONLY using the provided source excerpts below. Every claim you make must be backed \
by one of the sources.

When citing a source, use ONLY the strict numeric format matching the provided Chunk IDs. \
For example: [1] or [3]. Never use the filename or page number in the citation.

If the answer cannot be found in the sources, say: \
"I could not find information about this in your uploaded documents."

Context:
{context}"""


def _build_context(chunks: list[dict]) -> tuple[str, list[dict]]:
    """Returns the formatted prompt context and the metadata mapping."""
    parts = []
    metadata = []
    for i, c in enumerate(chunks, 1):
        page_label = f" (Page {c['page']})" if c.get("page") else ""
        parts.append(f"Chunk [{i}]:\nSource: {c['source']}{page_label}\n{c['text']}")
        metadata.append({
            "id": i,
            "source": c["source"],
            "page": c.get("page", 0),
            "text": c["text"]
        })
    return "\n\n---\n\n".join(parts), metadata


def _build_messages(history: list[dict], system: str, question: str) -> list[dict]:
    messages = [{"role": "system", "content": system}]
    for msg in history:
        messages.append(msg)
    messages.append({"role": "user", "content": question})
    return messages


async def rag_stream(
    notebook_id: str,
    question: str,
    history: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """Async generator: yields text tokens for a grounded RAG answer.

    Flow:
      1. Run input guardrails (topic → safety → injection).
         If any fires, yield a [GUARDRAIL] prefixed refusal and return.
      2. Retrieve relevant chunks and build context.
      3. Stream the LLM response.
      4. Run output safety guard on the accumulated response.
    """
    history = history or []

    # ── 1. Input guardrails ───────────────────────────────────────────────────
    guard_result = await run_input_guards(question)
    if guard_result and guard_result.blocked:
        yield f"[GUARDRAIL:{guard_result.guard}] {guard_result.message}"
        return

    # ── 2. RAG retrieval ──────────────────────────────────────────────────────
    chunks = vector_query(notebook_id, question, k=5)
    
    if not chunks:
        context = "(No documents uploaded yet.)"
        metadata = []
    else:
        context, metadata = _build_context(chunks)
        
    system = SYSTEM_PROMPT.format(context=context)
    messages = _build_messages(history, system, question)

    # ── 3. Stream Metadata, then LLM response ─────────────────────────────────
    # Send the metadata block first so the frontend knows what [1] points to.
    # Yield as a single string without newlines to preserve SSE in main.py
    meta_json = json.dumps(metadata)
    yield f"[METADATA]{meta_json}[/METADATA]"

    accumulated = []
    stream = ollama.chat(model=CHAT_MODEL, messages=messages, stream=True)
    for part in stream:
        token = part["message"]["content"]
        if token:
            accumulated.append(token)
            yield token

    # ── 4. Output safety guard ────────────────────────────────────────────────
    full_response = "".join(accumulated)
    out_guard = await output_safety_guard(full_response)
    if out_guard.blocked:
        # We already streamed the harmful content — signal the frontend to replace it
        yield f"\n\n[GUARDRAIL:output_safety_guard] {out_guard.message}"


async def generate_welcome(notebook_id: str) -> dict:
    """Read a sample of the notebook's documents and generate a summary + 3 suggested questions."""
    chunks = vector_query(notebook_id, "overview main topics introduction", k=5)
    if not chunks:
        return {"summary": "Upload some documents to get started!", "questions": []}
    
    context = "\n".join(c["text"] for c in chunks)
    prompt = (
        "You are an energetic AI study assistant. Read the following document excerpts and generate:\n"
        "1. A proactive, encouraging 2-sentence summary of what the documents are about.\n"
        "2. Directly below that, exactly 3 highly relevant suggested questions the user could ask.\n\n"
        "Return ONLY a valid JSON object with the exact keys: 'summary' (string) and 'questions' (array of 3 strings).\n"
        "No markup, no markdown fences, no other text.\n\n"
        f"Excerpts:\n{context[:3000]}"
    )

    def _call():
        return ollama.chat(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
            options={"temperature": 0.3}
        )

    resp = await asyncio.to_thread(_call)
    text = resp["message"]["content"].strip()
    
    try:
        if text.startswith("```json"): text = text[7:]
        if text.endswith("```"): text = text[:-3]
        return json.loads(text.strip())
    except Exception:
        return {
            "summary": "I'm ready to help you study this material.",
            "questions": ["Can you summarize this?", "What are the key concepts?", "Generate a quiz for me."]
        }


async def validate_node(
    node_label: str,
    node_content: str,
    questions: list[dict],
) -> list[bool]:
    """
    Grade a list of {q, expected_answer, user_answer} dicts.
    Returns a list of booleans (True = correct).
    """
    results: list[bool] = []

    for item in questions:
        grading_prompt = (
            f"You are a fair and encouraging teacher grading a student's short answer.\n\n"
            f"Topic context:\n{node_content[:800]}\n\n"
            f"Question: {item['q']}\n"
            f"Expected key points: {item['expected_answer']}\n"
            f"Student answer: {item['user_answer']}\n\n"
            "Grading rules:\n"
            "1. Mark CORRECT if the student captures the core concept, even if phrased differently or with extra detail.\n"
            "2. Mark CORRECT if the answer is scientifically accurate and relevant, even using different words than the expected answer.\n"
            "3. Mark INCORRECT ONLY if the answer is clearly wrong, completely off-topic, or missing the essential point entirely.\n"
            "4. Never penalise a student for adding accurate extra information.\n"
            "5. Never require word-for-word matching.\n"
            "Reply with ONLY the single word CORRECT or INCORRECT."
        )

        def _grade():
            return ollama.chat(
                model=CHAT_MODEL,
                messages=[{"role": "user", "content": grading_prompt}],
                stream=False,
            )

        resp = await asyncio.to_thread(_grade)
        verdict = resp["message"]["content"].strip().upper()
        results.append(verdict.startswith("CORRECT"))

    return results


async def generate_artifact(notebook_id: str, artifact_type: str) -> str:
    """
    Generate a structured artifact from all notebook content.
    artifact_type: 'summary' | 'faq' | 'study_guide' | 'quiz' | 'learning_graph'
    """
    prompts = {
        "summary": (
            "Using ONLY the provided sources, write a concise executive summary "
            "(3–5 paragraphs) covering the main topics, arguments, and conclusions."
        ),
        "faq": (
            "Using ONLY the provided sources, generate a Frequently Asked Questions (FAQ) list. "
            "Format: **Q:** [question]\\n**A:** [answer with citation]. Include at least 8 Q&A pairs."
        ),
        "study_guide": (
            "Using ONLY the provided sources, create a structured study guide in Markdown with: "
            "## Key Concepts, ## Important Terms & Definitions, ## Summary Points."
        ),
        "quiz": (
            "Using ONLY the provided sources, generate exactly 8 multiple-choice quiz questions. "
            "Return ONLY a valid JSON array with no extra text, markdown, or explanation. "
            "Each element must be an object with these exact keys: "
            '{"question": "...", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], '
            '"answer": 0, "explanation": "..."} '
            "where 'answer' is the 0-based index of the correct option. "
            "Make questions challenging and directly grounded in the source material."
        ),
        "mind_map": (
            "Using ONLY the provided sources, create a highly detailed, interactive hierarchical mind map. "
            "Return ONLY a valid, perfectly formatted JSON object. Absolutely no extra text or markdown. "
            'The exact structure must have a "label" and a detailed "description" (1-3 sentences) for EVERY node: '
            '{"label": "Central Topic", "description": "High level overview of everything...", "children": ['
            '  {"label": "Branch 1", "description": "Key details about this branch...", "children": ['
            '    {"label": "Leaf A", "description": "Specific facts, stats, or definitions..."}'
            '  ]},'
            '  {"label": "Branch 2", "description": "..."}'
            "]} "
            "CRITICAL: Ensure all opening braces { have a closing brace } and brackets [ have ]. "
            "Do not leave trailing commas. "
            "Rules: 3-5 top-level branches, each with 2-4 sub-nodes, maximum 3 levels deep. "
            "Labels must be concise (max 5 words). Descriptions must be highly informative and use the source material."
        ),
        "learning_graph": (
            "Using ONLY the provided sources, design a learning graph (directed acyclic graph) "
            "that guides a student through the material layer by layer. "
            "Return ONLY a valid JSON object with no extra text or markdown. "
            "The JSON must follow this EXACT schema:\n"
            '{"title": "Short topic title", "nodes": [\n'
            '  {"id": "n0", "layer": 0, "label": "Introduction (max 5 words)",\n'
            '   "content": "2-3 paragraph lesson text teaching this node topic from the sources.",\n'
            '   "questions": [\n'
            '     {"q": "Open-ended question?", "answer": "Key points the student must mention"},\n'
            '     {"q": "...", "answer": "..."},\n'
            '     {"q": "...", "answer": "..."}\n'
            '   ],\n'
            '   "edges": ["n1", "n2"]},\n'
            '  {"id": "n1", "layer": 1, "label": "...", "content": "...", "questions": [...], "edges": ["n3"]},\n'
            '  ...\n'
            ']}\n'
            "Rules you MUST follow:\n"
            "1. Exactly 1 root node at layer 0 with no incoming edges.\n"
            "2. Total of 3-5 layers (layer 0 through layer 2-4).\n"
            "3. Layer 0 has exactly 1 node (the root). Other layers have 2-4 nodes each.\n"
            "4. Node IDs are simple strings: n0, n1, n2, etc.\n"
            "5. edges lists the IDs of direct children in the next layer only.\n"
            "6. Leaf nodes (last layer) have empty edges: [].\n"
            "7. Each node's content must be 2-3 informative paragraphs from the sources.\n"
            "8. Questions must be open-ended (not multiple choice). answers must list the key points.\n"
            "9. Labels are at most 5 words.\n"
            "CRITICAL: return only JSON, no markdown fences, no explanation."
        ),
    }
    user_prompt = prompts.get(artifact_type, prompts["summary"])

    # Use a broad query to retrieve as many chunks as possible
    chunks = vector_query(notebook_id, user_prompt, k=10)
    context = _build_context(chunks) if chunks else "(No documents uploaded yet.)"
    system = SYSTEM_PROMPT.format(context=context)

    def _call():
        return ollama.chat(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            stream=False,
        )

    response = await asyncio.to_thread(_call)
    return response["message"]["content"]
