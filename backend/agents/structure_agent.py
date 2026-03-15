"""
Structure Agent — v2
--------------------
Two-step extraction for better quality with small LLMs like llama3.2:

  Step 1: Extract 4-6 chapter titles + rich summaries (simple flat JSON)
  Step 2: For each chapter, extract 3-4 sections + optional subsections

Splitting the big nested JSON into smaller calls is far more reliable.
"""
import json
import re
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2:latest"

# ── Prompt 1: Top-level Chapters ─────────────────────────────────────────────
CHAPTER_PROMPT = """\
You are analyzing educational text about: "{title}"

Read the text carefully and identify the MAIN TOPICS covered. \
Then output ONLY the following JSON — no markdown, no explanation, nothing else:

{{"summary": "Write 2-3 sentences summarizing the entire lesson.", \
"emoji": "📚", \
"chapters": [\
{{"title": "Chapter Title", "emoji": "📖", \
"summary": "Write 2-3 informative sentences describing what this chapter covers, \
using specific facts from the text."}}\
]}}

STRICT RULES:
- Create EXACTLY 4 to 6 chapters — no more, no less
- Each chapter summary MUST be 2-3 sentences with specific facts from the text
- Emoji must be relevant to the chapter topic
- Output raw JSON only — absolutely nothing before or after the JSON

TEXT:
{text}"""

# ── Prompt 2: Sections for one Chapter ───────────────────────────────────────
SECTION_PROMPT = """\
You are breaking down the chapter "{chapter_title}" \
(from a lesson on "{lesson_title}") into sections.

Chapter context: {chapter_summary}

Read the text and extract the main sub-topics for this chapter. \
Output ONLY this JSON — no markdown, no explanation:

{{"sections": [\
{{"title": "Section Title", "emoji": "🔍", \
"summary": "2-3 informative sentences with specific facts.", \
"subsections": [\
{{"title": "Subsection Title", "emoji": "📌", \
"summary": "1-2 sentences with a specific fact or concept."}}\
]}}\
]}}

STRICT RULES:
- Create EXACTLY 3 sections
- Each section summary MUST be 2-3 complete sentences with real facts
- Each section should have 0 to 2 subsections — only add them if the text supports it
- Use [] for subsections if none apply
- Output raw JSON only

TEXT (focus on areas relevant to "{chapter_title}"):
{text}"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _call_ollama(prompt: str, num_predict: int = 1500, timeout: int = 120) -> str:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,      # Very low — we want factual, structured output
            "num_predict": num_predict,
            "top_p": 0.9,
        },
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json().get("response", "")


def _extract_json(text: str):
    """Try multiple strategies to pull JSON from LLM output."""
    # 1. Direct parse
    try:
        return json.loads(text.strip())
    except Exception:
        pass
    # 2. Strip markdown fences
    cleaned = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"```\s*$", "", cleaned.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned.strip())
    except Exception:
        pass
    # 3. Grab first { ... } block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return None


def _safe_call(prompt: str, validate_fn, fallback, retries: int = 3, **kw):
    """Call Ollama with retries; return fallback if all fail."""
    for attempt in range(1, retries + 1):
        try:
            raw = _call_ollama(prompt, **kw)
            result = _extract_json(raw)
            if result and validate_fn(result):
                return result
            print(f"[StructureAgent] Attempt {attempt} — validation failed. Raw: {raw[:120]}")
        except Exception as e:
            print(f"[StructureAgent] Attempt {attempt} error: {e}")
    return fallback


# ── Agent ─────────────────────────────────────────────────────────────────────

class StructureAgent:
    """Two-step LLM extraction: chapters first, then sections per chapter."""

    def extract(self, text: str, lesson_title: str) -> dict:
        # Keep at most 14 000 chars — roughly 3 500 tokens for llama3.2
        chunk = text[:14000]

        # ── Step 1: Extract chapters ──────────────────────────────────────
        print("[StructureAgent] Step 1 — extracting chapters...")
        chapter_prompt = CHAPTER_PROMPT.format(title=lesson_title, text=chunk)

        top_level = _safe_call(
            chapter_prompt,
            validate_fn=lambda r: isinstance(r.get("chapters"), list) and len(r["chapters"]) >= 2,
            fallback=self._fallback_chapters(lesson_title),
            retries=3,
            num_predict=1200,
        )

        chapters = top_level.get("chapters", [])
        print(f"[StructureAgent] Got {len(chapters)} chapters")

        # ── Step 2: Extract sections for each chapter ─────────────────────
        for i, chapter in enumerate(chapters):
            ch_title = chapter.get("title", f"Chapter {i+1}")
            ch_summary = chapter.get("summary", "")
            print(f"[StructureAgent] Step 2.{i+1} — sections for: {ch_title}")

            section_prompt = SECTION_PROMPT.format(
                chapter_title=ch_title,
                lesson_title=lesson_title,
                chapter_summary=ch_summary,
                text=chunk,
            )

            sections_data = _safe_call(
                section_prompt,
                validate_fn=lambda r: isinstance(r.get("sections"), list) and len(r["sections"]) >= 1,
                fallback={"sections": self._fallback_sections(ch_title)},
                retries=3,
                num_predict=1500,
            )

            chapter["sections"] = sections_data.get("sections", self._fallback_sections(ch_title))
            # Ensure each section has subsections key
            for sec in chapter["sections"]:
                sec.setdefault("subsections", [])

        return {
            "summary": top_level.get("summary", f"A lesson on {lesson_title}."),
            "emoji": top_level.get("emoji", "📚"),
            "chapters": chapters,
        }

    # ── Fallbacks ─────────────────────────────────────────────────────────

    @staticmethod
    def _fallback_chapters(lesson_title: str) -> dict:
        return {
            "summary": f"An educational overview of {lesson_title}.",
            "emoji": "📚",
            "chapters": [
                {"title": "Introduction", "emoji": "📖",
                 "summary": f"Foundational introduction to {lesson_title}."},
                {"title": "Core Concepts", "emoji": "💡",
                 "summary": f"The key concepts and principles of {lesson_title}."},
                {"title": "Applications", "emoji": "🔧",
                 "summary": f"How {lesson_title} concepts are applied in practice."},
                {"title": "Advanced Topics", "emoji": "🚀",
                 "summary": f"Deeper and more specialized aspects of {lesson_title}."},
            ],
        }

    @staticmethod
    def _fallback_sections(chapter_title: str) -> list:
        return [
            {"title": "Overview", "emoji": "🔍",
             "summary": f"A broad overview of {chapter_title}.", "subsections": []},
            {"title": "Key Details", "emoji": "📌",
             "summary": f"Important details and specifics about {chapter_title}.", "subsections": []},
            {"title": "Summary", "emoji": "✅",
             "summary": f"Key takeaways from {chapter_title}.", "subsections": []},
        ]
