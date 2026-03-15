"""
Quiz Agent — v2
---------------
Generates a 4-option MCQ for each node.
Key improvements:
- Correct answer is ALWAYS at options[0] in the data
- Frontend shuffles before display so the user never knows which position is correct
- Prompt explicitly instructs LLM to derive the correct answer from the summary
- Includes the full summary as context so facts are accurate
"""
import json
import re
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2:latest"

QUIZ_PROMPT = """\
You are a quiz writer. Create EXACTLY 3 multiple-choice questions to test understanding of the following concept. The questions should progressively get harder or cover different aspects.

CONCEPT: "{title}"

SUMMARY (read carefully — the correct answers must come from this):
---
{summary}
---

Output ONLY this JSON format — no markdown, no explanation, nothing else:
{{
  "quizzes": [
    {{
      "question": "A specific question about the concept above?",
      "options": ["The correct answer (a fact from the summary)", "A wrong option", "Another wrong option", "Another wrong option"],
      "correct": 0
    }},
    {{
      "question": "A different specific question about the concept?",
      "options": ["The correct answer", "Wrong", "Wrong", "Wrong"],
      "correct": 0
    }},
    {{
      "question": "A third specific question about the concept?",
      "options": ["The correct answer", "Wrong", "Wrong", "Wrong"],
      "correct": 0
    }}
  ]
}}

RULES:
- You MUST output exactly 3 distinct questions.
- For EVERY question, options[0] is ALWAYS the correct answer — it MUST be directly supported by the summary.
- The 3 wrong options for each question must be plausible but clearly wrong.
- Keep all options under 12 words.
- Output raw JSON only."""


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


def _validate_quiz(q: dict) -> bool:
    return (
        isinstance(q.get("question"), str) and len(q["question"]) > 10
        and isinstance(q.get("options"), list) and len(q["options"]) >= 4
        and q.get("correct") == 0  # We always expect correct at index 0
    )


def _default_quiz(title: str, summary: str) -> list:
    """Fallback 3 MCQs that are at least somewhat sensible from available text."""
    sentences = [s.strip() for s in re.split(r'[.!?]', summary) if len(s.strip()) > 20]
    ans1 = sentences[0][:80] if len(sentences) > 0 else f"A core aspect of {title}"
    ans2 = sentences[1][:80] if len(sentences) > 1 else f"Another detail about {title}"
    ans3 = sentences[2][:80] if len(sentences) > 2 else f"A final point about {title}"
    
    return [
        {
            "question": f"What is the primary focus of '{title}'?",
            "options": [ans1, "An unrelated historical event", "A mathematical equation", "A geographic location"],
            "correct": 0,
        },
        {
            "question": f"Which of the following is true about '{title}'?",
            "options": [ans2, "It does not apply here", "It is an outdated theory", "Nobody knows"],
            "correct": 0,
        },
        {
            "question": f"What is another key point regarding '{title}'?",
            "options": [ans3, "It was discovered by aliens", "It is only relevant in space", "It is a myth"],
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
            summary = context[:500]

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
                        # Normalize — sometimes LLM doesn't put correct at 0
                        correct_idx = q.get("correct", 0)
                        options = q.get("options", [])
                        if isinstance(options, list) and len(options) >= 4:
                            if correct_idx != 0 and 0 <= correct_idx < len(options):
                                options[0], options[correct_idx] = options[correct_idx], options[0]
                            q["options"] = options[:4]
                            q["correct"] = 0
                            if isinstance(q.get("question"), str) and len(q["question"]) > 5:
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
