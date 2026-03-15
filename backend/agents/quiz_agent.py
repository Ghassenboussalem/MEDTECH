"""Quiz Agent
-------------
Generates realistic, node-specific 3-question MCQ sets for each concept.
"""
import json
import re
from collections import Counter
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2:latest"

QUIZ_PROMPT = """\
You are an expert assessment designer for technical education.

Create EXACTLY 3 high-quality multiple-choice questions for this node.
The 3 questions must target different cognitive levels:
1) factual understanding,
2) mechanism/relationship understanding,
3) application or diagnosis.

NODE TITLE: "{title}"

NODE SUMMARY (all correct answers must be grounded in this content):
---
{summary}
---

Return ONLY valid JSON in this exact schema:
{{
    "quizzes": [
        {{
            "question": "Specific, concrete question about the node content?",
            "options": ["Correct answer", "Plausible distractor", "Plausible distractor", "Plausible distractor"],
            "correct": 0
        }},
        {{"question": "...", "options": ["...", "...", "...", "..."], "correct": 0}},
        {{"question": "...", "options": ["...", "...", "...", "..."], "correct": 0}}
    ]
}}

STRICT RULES:
- Exactly 3 questions.
- options[0] MUST be correct for each question.
- Questions must reference concrete node details (terms, properties, constraints, numbers, examples).
- Avoid generic stems such as "What is the primary focus...".
- Distractors must be realistic and domain-plausible, not joke answers.
- Keep each option concise (<= 14 words).
- Output ONLY raw JSON.
"""

STOPWORDS = {
        "the", "and", "for", "that", "with", "this", "from", "are", "was", "were", "into",
        "have", "has", "had", "about", "what", "when", "where", "which", "their", "there",
        "your", "you", "will", "can", "could", "should", "would", "than", "then", "they",
        "them", "these", "those", "using", "used", "also", "such", "only", "over", "under",
}


def _keywords(text: str, limit: int = 12) -> list[str]:
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", text.lower())
        filtered = [t for t in tokens if t not in STOPWORDS]
        ranked = [w for w, _ in Counter(filtered).most_common(limit)]
        return ranked


def _call_ollama(prompt: str, timeout: int = 60) -> str:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 400, "top_p": 0.9},
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json().get("response", "")


def _extract_json(text: str):
    try:
        return json.loads(text.strip())
    except Exception:
        pass
    cleaned = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"```\s*$", "", cleaned.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned.strip())
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return None


def _validate_quiz(q: dict, title: str, summary_keywords: list[str]) -> bool:
    if not isinstance(q, dict):
        return False
    question = q.get("question") or q.get("q")
    options = q.get("options")
    if not isinstance(question, str) or len(question.strip()) < 14:
        return False
    if not isinstance(options, list) or len(options) < 4:
        return False
    if not isinstance(q.get("correct", 0), int):
        return False

    generic_phrases = [
        "primary focus",
        "which of the following is true",
        "another key point",
    ]
    ql = question.lower()
    if any(g in ql for g in generic_phrases):
        return False

    # Ensure node-specific grounding: title token or summary keyword appears in question/options.
    node_tokens = [t for t in re.findall(r"[a-zA-Z0-9\-]+", title.lower()) if len(t) > 2]
    corpus = " ".join([question] + [str(o) for o in options]).lower()
    has_title = any(t in corpus for t in node_tokens)
    has_kw = any(k in corpus for k in summary_keywords[:8]) if summary_keywords else False

    return (
        has_title or has_kw
    )


def _default_quiz(title: str, summary: str) -> list:
    """Fallback 3 node-grounded MCQs based on summary sentences."""
    sentences = [s.strip() for s in re.split(r"[.!?]", summary) if len(s.strip()) > 24]
    if not sentences:
        sentences = [
            f"{title} is explained in this lesson as a concrete concept with operational details",
            f"{title} has relationships, constraints, and practical implications",
            f"{title} can be applied to analyze realistic cases",
        ]

    ans1 = sentences[0][:110]
    ans2 = sentences[1][:110] if len(sentences) > 1 else sentences[0][:110]
    ans3 = sentences[2][:110] if len(sentences) > 2 else sentences[-1][:110]

    kws = _keywords(summary)
    d1 = kws[0] if kws else "an unrelated factor"
    d2 = kws[1] if len(kws) > 1 else "a contradictory mechanism"
    d3 = kws[2] if len(kws) > 2 else "an unsupported assumption"

    return [
        {
            "question": f"Which statement best matches the lesson's explanation of {title}?",
            "options": [ans1, f"It is mainly defined by {d1} alone", f"It excludes {d2} entirely", f"It is unrelated to {d3}"],
            "correct": 0,
        },
        {
            "question": f"According to the node content, which mechanism of {title} is accurate?",
            "options": [ans2, "It works without any constraints", "It is purely random and structure-free", "It has no practical implications"],
            "correct": 0,
        },
        {
            "question": f"In a realistic application, which use of {title} aligns with the lesson?",
            "options": [ans3, "Use it without checking assumptions", "Apply it where evidence is absent", "Treat it as universally optimal"],
            "correct": 0,
        }
    ]


class QuizAgent:
    """Generates 3 MCQs for every node. Correct answer always at index 0."""

    def generate(self, node_title: str, node_summary: str, context: str = "") -> list:
        """
        Args:
            node_title: Concept name.
            node_summary: LLM-generated summary for this node.
            context: Optional extra text (ignored if summary is rich enough).

        Returns:
            list: List of 3 dicts: [{question, options[4], correct=0}, ...]
        """
        # Use summary if rich, otherwise supplement with context
        summary = node_summary.strip()
        if len(summary) < 40 and context:
            summary = context[:1200]

        summary_keywords = _keywords(summary)

        prompt = QUIZ_PROMPT.format(title=node_title, summary=summary)

        for attempt in range(1, 4):
            try:
                raw = _call_ollama(prompt, timeout=90) # slightly longer timeout for 3 questions
                result = _extract_json(raw)
                
                quizzes = []
                if result and "quizzes" in result and isinstance(result["quizzes"], list):
                    quizzes = result["quizzes"]
                elif result and isinstance(result, list):
                    quizzes = result
                
                if len(quizzes) >= 1:
                    valid_quizzes = []
                    for q in quizzes:
                        if not isinstance(q, dict):
                            continue
                        if "q" in q and "question" not in q:
                            q["question"] = q["q"]

                        # Normalize — sometimes LLM doesn't put correct at 0
                        correct_idx = q.get("correct", 0)
                        options = q.get("options", [])
                        if isinstance(options, list) and len(options) >= 4:
                            if correct_idx != 0 and 0 <= correct_idx < len(options):
                                options[0], options[correct_idx] = options[correct_idx], options[0]
                            q["options"] = [str(o).strip()[:120] for o in options[:4]]
                            q["correct"] = 0
                            if _validate_quiz(q, node_title, summary_keywords):
                                valid_quizzes.append(q)
                    
                    if len(valid_quizzes) > 0:
                        # If we have at least 1 valid quiz, pad it up to 3 if necessary
                        while len(valid_quizzes) < 3:
                            valid_quizzes.append(_default_quiz(node_title, summary)[len(valid_quizzes) % 3])
                        
                        return valid_quizzes[:3]

            except Exception as e:
                print(f"[QuizAgent] Attempt {attempt} error for '{node_title}': {e}")

        return _default_quiz(node_title, summary)

    def annotate_tree(self, structure: dict, context_text: str = "") -> dict:
        """Walk the tree and add quiz to every node (mutates in-place)."""
        root_title = str(structure.get("title", "Root"))
        root_summary = str(structure.get("summary", ""))
        print("[QuizAgent] Root quiz...")
        structure["quiz"] = self.generate(root_title, root_summary, context_text[:2000])

        chapters = structure.get("chapters", [])
        if isinstance(chapters, list):
            for chapter in chapters:
                if not isinstance(chapter, dict): continue
                print(f"[QuizAgent] Chapter: {chapter.get('title', 'Unknown')}")
                chapter["quiz"] = self.generate(str(chapter.get("title", "")), str(chapter.get("summary", "")), context_text[:2000])
                
                sections = chapter.get("sections", [])
                if isinstance(sections, list):
                    for section in sections:
                        if not isinstance(section, dict): continue
                        print(f"[QuizAgent]   Section: {section.get('title', 'Unknown')}")
                        section["quiz"] = self.generate(str(section.get("title", "")), str(section.get("summary", "")), context_text[:2000])
                        
                        subs = section.get("subsections", [])
                        if isinstance(subs, list):
                            for sub in subs:
                                if not isinstance(sub, dict): continue
                                print(f"[QuizAgent]     Sub: {sub.get('title', 'Unknown')}")
                                sub["quiz"] = self.generate(str(sub.get("title", "")), str(sub.get("summary", "")), context_text[:2000])

        return structure
