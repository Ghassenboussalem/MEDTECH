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
    clean = re.sub(r"```json\n?|\n?```", "", raw).strip()
    clean = re.sub(r",\s*([\]}])", r"\1", clean)
    return clean


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
        "- Extract 4-10 concepts total\n"
        "- fundamental = no prerequisites; intermediate = needs fundamentals; advanced = needs intermediates\n"
        "- CRITICAL: concept_ids in concept_hierarchy must exactly match concept_id fields above\n"
        "- RETURN ONLY JSON\n\n"
        f"Course material:\n{context[:4000]}"
    )

    def _call():
        return ollama.chat(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )

    resp = await asyncio.to_thread(_call)
    raw = resp["message"]["content"]
    try:
        return json.loads(_clean_json(raw))
    except json.JSONDecodeError:
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
        "- 2-4 modules total\n"
        "- prerequisites = list of module titles that come before this one\n"
        "- RETURN ONLY JSON\n\n"
        f"Course material:\n{context[:2000]}"
    )

    def _call():
        return ollama.chat(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )

    resp = await asyncio.to_thread(_call)
    raw = resp["message"]["content"]
    try:
        return json.loads(_clean_json(raw))
    except json.JSONDecodeError:
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
