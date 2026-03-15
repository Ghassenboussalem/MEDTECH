"""
concept_extractor.py — Multi-pass LLM pipeline.

Strategy to overcome llama3.2 context-window limitations and produce MANY concepts:
  1. Split context into overlapping chunks of ~1500 chars.
  2. For each chunk, extract 3-5 micro-concepts.
  3. Merge & deduplicate micro-concepts by semantic similarity (edit distance).
  4. Pass 2: Build course structure (modules) from all merged concepts.
"""
import asyncio
import json
import re
from difflib import SequenceMatcher

import ollama

CHAT_MODEL = "llama3.2:latest"
CHUNK_SIZE = 1500        # chars per extraction chunk
CHUNK_OVERLAP = 200      # overlap to catch concepts split across chunks
MAX_CONCEPTS = 35        # safety ceiling (raised to get richer graphs)
MIN_CONCEPTS_PER_CHUNK = 2  # minimum candidates to accept from each chunk


def _clean_json(raw: str) -> str:
    """Strip markdown fences and trailing commas before closing brackets."""
    clean = re.sub(r"```json\n?|\n?```", "", raw).strip()
    clean = re.sub(r",\s*([\]}])", r"\1", clean)
    return clean


def _repair_json(raw: str) -> dict | None:
    """Attempt to salvage truncated or malformed JSON from the LLM."""
    clean = _clean_json(raw)

    # 1. Direct parse
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    # 2. Close unclosed brackets / braces
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
    patched = re.sub(r",\s*([\]}])", r"\1", patched)
    try:
        result = json.loads(patched)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # 3. Regex extraction of individual concept objects
    concept_pattern = re.compile(
        r'\{[^{}]*"concept_id"\s*:\s*"([^"]+)"[^{}]*(?:\{[^{}]*\}[^{}]*)?\}',
        re.DOTALL,
    )
    concepts = []
    for m in concept_pattern.finditer(clean):
        blob = re.sub(r",\s*([\]}])", r"\1", m.group(0))
        try:
            obj = json.loads(blob)
            if isinstance(obj, dict) and "concept_id" in obj:
                concepts.append(obj)
        except json.JSONDecodeError:
            pass

    if concepts:
        return {"concepts": concepts}
    return None


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _deduplicate(concepts: list[dict]) -> list[dict]:
    """Remove near-duplicate concepts (same name or very similar).
    Threshold lowered to 0.65 so only truly identical names are merged,
    allowing more distinct concepts to survive.
    """
    unique = []
    for c in concepts:
        name_c = c.get("name", "").lower().strip()
        is_dup = False
        for u in unique:
            if _similar(name_c, u.get("name", "").lower().strip()) > 0.65:
                is_dup = True
                break
        if not is_dup:
            unique.append(c)
    return unique


def _assign_hierarchy(concepts: list[dict]) -> dict:
    """
    Assign hierarchy based on bloom_level.
    remember/understand → fundamental
    apply/analyze → intermediate
    evaluate/create → advanced
    """
    hierarchy = {"fundamental": [], "intermediate": [], "advanced": []}
    bloom_map = {
        "remember": "fundamental", "understand": "fundamental",
        "apply": "intermediate", "analyze": "intermediate",
        "evaluate": "advanced", "create": "advanced",
    }
    for c in concepts:
        hl = bloom_map.get(c.get("bloom_level", "understand"), "intermediate")
        # Also factor in importance
        if c.get("importance") == "critique" and hl == "intermediate":
            hl = "fundamental"
        c["hierarchy_level"] = hl
        hierarchy[hl].append(c["concept_id"])
    return hierarchy


async def _extract_chunk(context_chunk: str, chunk_idx: int) -> list[dict]:
    """Extract 5 concepts from a single context chunk."""
    prompt = (
        "You are an expert educational content analyst.\n"
        "Extract EXACTLY 5 distinct, specific concepts from the text below.\n"
        "Each concept must be a concrete idea, NOT a vague category.\n"
        "Return ONLY a valid JSON object with ONE key 'concepts' containing an array of 5 items.\n"
        "NO markdown. NO extra text. NO explanations.\n\n"
        '{"concepts":['
        '{"concept_id":"short_snake_case_id",'
        '"name":"Human Readable Concept Name",'
        '"importance":"critique|importante|utile",'
        '"bloom_level":"remember|understand|apply|analyze|evaluate|create",'
        '"description":"2-3 sentence definition with specific details.",'
        '"mastery_criteria":["Student can ...","Student can ..."],'
        '"common_misconceptions":["Students often think ..."],'
        '"application_examples":["Real-world usage example"]}]}\n\n'
        "Rules:\n"
        "- concept_id must be unique snake_case (add _2, _3 suffixes if needed)\n"
        "- Prefer concrete, specific sub-concepts over broad abstractions\n"
        "- bloom_level reflects the TARGET cognitive level\n"
        "- VALID JSON ONLY — close ALL brackets\n\n"
        f"Text chunk:\n{context_chunk}"
    )

    def _call():
        return ollama.chat(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
            format="json",
            options={"num_predict": 2048, "temperature": 0.1},
        )

    try:
        resp = await asyncio.to_thread(_call)
        raw = resp["message"]["content"]
        result = _repair_json(raw)
        if result:
            # Handle both {"concepts": [...]} and {"essential_concepts": [...]}
            candidates = result.get("concepts") or result.get("essential_concepts") or []
            if isinstance(candidates, list):
                # Ensure each concept has required fields
                valid = []
                for c in candidates:
                    if isinstance(c, dict) and c.get("concept_id") and c.get("name"):
                        # Add chunk suffix to avoid ID collisions across chunks
                        c["concept_id"] = f"{c['concept_id']}_c{chunk_idx}"
                        valid.append(c)
                return valid
    except Exception as e:
        print(f"Chunk {chunk_idx} extraction failed: {e}")
    return []


async def extract_concepts(context: str) -> dict:
    """
    Multi-chunk extraction to get many more concepts from large documents.
    Splits the context into overlapping windows and extracts 4 concepts per window,
    then deduplicates and merges into a unified concept list.
    """
    # Split into overlapping chunks
    chunks = []
    start = 0
    while start < len(context):
        end = min(start + CHUNK_SIZE, len(context))
        chunks.append(context[start:end])
        if end == len(context):
            break
        start += CHUNK_SIZE - CHUNK_OVERLAP

    # Limit to avoid too many API calls with small models
    chunks = chunks[:10]  # max 10 chunks × 5 concepts = up to 50 raw concepts

    # Run all chunks in parallel for speed
    tasks = [_extract_chunk(chunk, i) for i, chunk in enumerate(chunks)]
    results = await asyncio.gather(*tasks)

    # Merge all concepts
    all_concepts = []
    for chunk_concepts in results:
        all_concepts.extend(chunk_concepts)

    # Deduplicate
    unique_concepts = _deduplicate(all_concepts)

    # Cap at MAX_CONCEPTS
    unique_concepts = unique_concepts[:MAX_CONCEPTS]

    if not unique_concepts:
        # Save raw for debugging
        try:
            with open("failed_concepts.json", "w", encoding="utf-8") as f:
                f.write(json.dumps({"chunks": len(chunks), "extracted": len(all_concepts)}))
        except Exception:
            pass
        return {
            "essential_concepts": [],
            "concept_hierarchy": {"fundamental": [], "intermediate": [], "advanced": []},
            "total_concepts": 0,
            "_parse_error": f"Extracted 0 concepts from {len(chunks)} chunks",
        }

    # Assign hierarchy
    hierarchy = _assign_hierarchy(unique_concepts)

    # Ensure at least some fundamentals exist
    if not hierarchy["fundamental"] and hierarchy["intermediate"]:
        # Promote first 2 intermediates to fundamental
        for cid in hierarchy["intermediate"][:2]:
            hierarchy["fundamental"].append(cid)
            for c in unique_concepts:
                if c["concept_id"] == cid:
                    c["hierarchy_level"] = "fundamental"
        hierarchy["intermediate"] = hierarchy["intermediate"][2:]

    return {
        "essential_concepts": unique_concepts,
        "concept_hierarchy": hierarchy,
        "total_concepts": len(unique_concepts),
    }


async def extract_course_structure(context: str, concepts_json: dict) -> dict:
    """Pass 2: design modular course structure around extracted concepts."""
    concepts = concepts_json.get("essential_concepts", [])
    concept_list = "\n".join(
        f"- {c['concept_id']}: {c['name']} ({c.get('importance','importante')}, bloom:{c.get('bloom_level','understand')})"
        for c in concepts[:12]  # limit to avoid token overflow
    )

    prompt = (
        "You are an expert curriculum designer.\n"
        "Design a structured course plan for the following course material.\n"
        "Return ONLY a single valid JSON object — NO markdown, NO extra text.\n\n"
        f"Extracted concepts ({len(concepts)} total):\n{concept_list}\n\n"
        "Required schema:\n"
        '{"course_title":"Title","course_description":"Brief description.",'
        '"target_audience":"Who this is for.",'
        '"modules":[{"module_number":1,"title":"Module Title","duration_minutes":45,'
        '"prerequisites":[],"learning_outcomes":["Student will be able to ..."],'
        '"concepts_covered":["concept_id_1","concept_id_2"],'
        '"teaching_strategies":["Feynman","Worked examples"],'
        '"assessment_methods":["Oral explanation","Problem solving"]}],'
        '"total_duration_hours":3,"progression_path":"Linear description of learning path"}\n\n'
        "Rules:\n"
        "- Group concepts into 4-8 modules by topic similarity\n"
        "- concepts_covered must use concept_ids from the list above\n"
        "- prerequisites = list of module_numbers that come before\n"
        "- RETURN ONLY VALID COMPLETE JSON — close ALL brackets and braces\n\n"
        f"Course material excerpt:\n{context[:1500]}"
    )

    def _call():
        return ollama.chat(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
            format="json",
            options={"num_predict": 3000},
        )

    resp = await asyncio.to_thread(_call)
    raw = resp["message"]["content"]

    result = _repair_json(raw)
    if result and "modules" in result:
        return result

    # Fallback: auto-group by hierarchy_level
    fundamentals = [c for c in concepts if c.get("hierarchy_level") == "fundamental"]
    intermediates = [c for c in concepts if c.get("hierarchy_level") == "intermediate"]
    advanced_c = [c for c in concepts if c.get("hierarchy_level") == "advanced"]

    modules = []
    if fundamentals:
        modules.append({
            "module_number": 1,
            "title": "Foundations",
            "concepts_covered": [c["concept_id"] for c in fundamentals],
            "prerequisites": [],
            "learning_outcomes": ["Understand foundational concepts"],
        })
    if intermediates:
        modules.append({
            "module_number": 2,
            "title": "Core Concepts",
            "concepts_covered": [c["concept_id"] for c in intermediates],
            "prerequisites": [1] if fundamentals else [],
            "learning_outcomes": ["Apply intermediate knowledge"],
        })
    if advanced_c:
        modules.append({
            "module_number": 3,
            "title": "Advanced Topics",
            "concepts_covered": [c["concept_id"] for c in advanced_c],
            "prerequisites": [2] if intermediates else [1] if fundamentals else [],
            "learning_outcomes": ["Synthesize and evaluate advanced concepts"],
        })

    return {
        "course_title": "Generated Course",
        "modules": modules,
        "_fallback": True,
    }


async def run_pipeline(notebook_id: str, context: str) -> tuple[dict, dict]:
    """Run both passes. Returns (concepts_json, course_json)."""
    concepts_json = await extract_concepts(context)
    course_json = await extract_course_structure(context, concepts_json)
    return concepts_json, course_json
