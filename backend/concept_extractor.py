"""
concept_extractor.py — Two-pass LLM pipeline.

Pass 1: extracts ConceptNodes JSON (names, bloom, hierarchy, misconceptions…)
Pass 2: extracts CourseStructure JSON (modules, prerequisites, outcomes…)
"""
import asyncio
import json
import re

import ollama

CHAT_MODEL = "llama3.2:latest"


def _clean_json(raw: str) -> str:
    """Strip markdown fences and trailing commas before closing brackets."""
    clean = re.sub(r"```json\n?|\n?```", "", raw).strip()
    clean = re.sub(r",\s*([\]}])", r"\1", clean)
    return clean


def _repair_json(raw: str) -> dict | None:
    """
    Attempt to salvage truncated or malformed JSON from the LLM.

    Strategy:
    1. Strip markdown + trailing commas.
    2. Try a direct parse (cheap path).
    3. Try to close open brackets/braces one by one and re-parse.
    4. As a last resort: manually extract all complete concept objects
       using regex and build a minimal valid dict from them.
    """
    clean = _clean_json(raw)

    # ── 1. Direct parse ────────────────────────────────────────────────────────
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    # ── 2. Close unclosed brackets / braces ────────────────────────────────────
    # Walk the string, track what's open, then append closing chars.
    stack = []
    in_string = False
    escape = False
    for ch in clean:
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack:
            stack.pop()

    patched = clean + "".join(reversed(stack))
    # Remove trailing commas that might be just before the newly added closers
    patched = re.sub(r",\s*([\]}])", r"\1", patched)
    try:
        result = json.loads(patched)
        # Only accept if it looks like a concepts dict
        if isinstance(result, dict) and "essential_concepts" in result:
            return result
    except json.JSONDecodeError:
        pass

    # ── 3. Regex extraction of individual concept objects ─────────────────────
    # Find all JSON objects inside the essential_concepts array, even if the outer
    # structure is broken. A concept block starts with {"concept_id": ...}.
    concept_pattern = re.compile(
        r'\{[^{}]*"concept_id"\s*:\s*"([^"]+)"[^{}]*(?:\{[^{}]*\}[^{}]*)?\}',
        re.DOTALL,
    )
    concepts = []
    concept_ids = []
    for m in concept_pattern.finditer(clean):
        blob = m.group(0)
        # Ensure the object is closed
        blob = re.sub(r",\s*([\]}])", r"\1", blob)
        try:
            obj = json.loads(blob)
            if isinstance(obj, dict) and "concept_id" in obj:
                concepts.append(obj)
                concept_ids.append(obj["concept_id"])
        except json.JSONDecodeError:
            pass

    if concepts:
        return {
            "essential_concepts": concepts,
            "concept_hierarchy": {
                "fundamental": concept_ids[:max(1, len(concept_ids) // 3)],
                "intermediate": concept_ids[max(1, len(concept_ids) // 3): max(2, 2 * len(concept_ids) // 3)],
                "advanced": concept_ids[max(2, 2 * len(concept_ids) // 3):],
            },
            "total_concepts": len(concepts),
            "_repaired": True,
        }

    return None


async def extract_concepts(context: str) -> dict:
    """Pass 1: extract ConceptNodes from course text."""
    prompt = (
        "You are an expert educational content analyst.\n"
        "Analyse the following course material and extract the essential concepts.\n"
        "Return ONLY a single valid JSON object — NO markdown, NO extra text.\n\n"
        "Required schema:\n"
        '{"essential_concepts":[{"concept_id":"short_snake_case_id","name":"Concept Name",'
        '"importance":"critique|importante|utile","bloom_level":"remember|understand|apply|analyze|evaluate|create",'
        '"description":"1-2 sentence definition.",'
        '"mastery_criteria":["Student can ..."],'
        '"common_misconceptions":["Students often think ..."],'
        '"application_examples":["Example 1"],'
        '"assessment_indicators":["Can explain without jargon"]}],'
        '"concept_hierarchy":{"fundamental":["concept_id"],"intermediate":["concept_id"],"advanced":["concept_id"]},'
        '"total_concepts":5}\n\n'
        "Rules:\n"
        "- importance: critique=must master, importante=should master, utile=nice-to-know\n"
        "- bloom_level = TARGET level for this course (not current student level)\n"
        "- Extract EXACTLY 3 concepts total (no more, no less)\n"
        "- fundamental = no prerequisites; intermediate = needs fundamentals; advanced = needs intermediates\n"
        "- CRITICAL: concept_ids in concept_hierarchy must exactly match concept_id fields above\n"
        "- RETURN ONLY VALID COMPLETE JSON — close ALL brackets and braces\n\n"
        f"Course material:\n{context[:3000]}"
    )

    def _call():
        return ollama.chat(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
            format="json",
            options={"num_predict": 4096},
        )

    resp = await asyncio.to_thread(_call)
    raw = resp["message"]["content"]

    # Try direct parse first, then repair
    result = _repair_json(raw)
    if result and result.get("essential_concepts"):
        return result

    # Save raw for debugging
    try:
        with open("failed_concepts.json", "w", encoding="utf-8") as f:
            f.write(raw)
    except Exception:
        pass

    return {
        "essential_concepts": [],
        "concept_hierarchy": {"fundamental": [], "intermediate": [], "advanced": []},
        "total_concepts": 0,
        "_parse_error": raw[:300],
    }


async def extract_course_structure(context: str, concepts_json: dict) -> dict:
    """Pass 2: design modular course structure around extracted concepts."""
    concept_list = ", ".join(
        f"{c['concept_id']} ({c['name']})"
        for c in concepts_json.get("essential_concepts", [])
    )

    prompt = (
        "You are an expert curriculum designer.\n"
        "Design a structured course plan for the following course material.\n"
        "Return ONLY a single valid JSON object — NO markdown, NO extra text.\n\n"
        f"Extracted concepts: {concept_list}\n\n"
        "Required schema:\n"
        '{"course_title":"Title","course_description":"Brief description.",'
        '"target_audience":"Who this is for.",'
        '"modules":[{"module_number":1,"title":"Module Title","duration_minutes":45,'
        '"prerequisites":[],"learning_outcomes":["Student will be able to ..."],'
        '"concepts_covered":["concept_id_1"],'
        '"teaching_strategies":["Feynman","Worked examples"],'
        '"assessment_methods":["Oral explanation","Problem solving"]}],'
        '"total_duration_hours":3,"progression_path":"Linear description of learning path"}\n\n'
        "Rules:\n"
        "- concepts_covered must use exact concept_ids from the list above\n"
        "- 2-3 modules total (keep it short)\n"
        "- prerequisites = list of module titles that come before this one\n"
        "- RETURN ONLY VALID COMPLETE JSON — close ALL brackets and braces\n\n"
        f"Course material:\n{context[:2000]}"
    )

    def _call():
        return ollama.chat(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
            format="json",
            options={"num_predict": 4096},
        )

    resp = await asyncio.to_thread(_call)
    raw = resp["message"]["content"]

    # Try repair
    result = _repair_json(raw)
    if result and "modules" in result:
        return result

    return {
        "course_title": "Course",
        "modules": [],
        "_parse_error": raw[:300],
    }


async def run_pipeline(notebook_id: str, context: str) -> tuple[dict, dict]:
    """Run both passes. Returns (concepts_json, course_json)."""
    concepts_json = await extract_concepts(context)
    course_json = await extract_course_structure(context, concepts_json)
    return concepts_json, course_json
