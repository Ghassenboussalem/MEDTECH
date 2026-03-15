"""
Content Agent
-------------
Generates a rich, structured explanation for a single knowledge node on demand.
Called when the user clicks a node — keeps graph generation fast while
delivering deep content lazily.

Returns structured markdown-like text with sections:
  • What is it?
  • Key Facts (bullet points)
  • Why it matters
  • Historical context (if relevant)
"""
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2:latest"

CONTENT_PROMPT = """\
You are an expert educator writing a detailed lesson entry for a student.

TOPIC: "{title}"

BASE SUMMARY (use this as your primary source — expand on it):
{summary}

ADDITIONAL CONTEXT FROM THE LESSON:
{context}

Write a thorough, detailed explanation of this topic. Structure your output \
using EXACTLY these four sections, each with the exact header shown:

**What is it?**
Write 3-4 sentences clearly defining and explaining this concept. \
Be specific, use real terms and facts from the summary.

**Key Facts**
• Write 4-5 bullet points with specific, interesting facts about this topic.
• Each bullet should contain one concrete fact, date, name, or number.
• Do not be vague — use actual data from the summary and context.

**Why it matters**
Write 2-3 sentences explaining the significance and real-world impact of this topic.

**Dig deeper**
Write 2-3 sentences connecting this topic to related concepts or \
what a student should explore next.

RULES:
- Use ONLY information from the summary and context provided above.
- Do NOT make up facts not present in the source material.
- Be specific — avoid generic statements like "this is important".
- Output only the four sections above, nothing else."""


class ContentAgent:
    """Generates detailed node content on demand via Ollama."""

    def generate(self, node_title: str, node_summary: str, context: str = "") -> str:
        """
        Args:
            node_title: Name of the concept.
            node_summary: Short summary from StructureAgent.
            context: First few KB of source PDF text for extra detail.

        Returns:
            Formatted string with four content sections.
        """
        # Trim context to fit in prompt
        ctx = context[:3000] if context else node_summary

        prompt = CONTENT_PROMPT.format(
            title=node_title,
            summary=node_summary or node_title,
            context=ctx,
        )
        try:
            payload = {
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 800,
                    "top_p": 0.9,
                },
            }
            resp = requests.post(OLLAMA_URL, json=payload, timeout=90)
            resp.raise_for_status()
            content = resp.json().get("response", "").strip()
            return content if content else self._fallback(node_title, node_summary)
        except Exception as e:
            print(f"[ContentAgent] Error for '{node_title}': {e}")
            return self._fallback(node_title, node_summary)

    @staticmethod
    def _fallback(title: str, summary: str) -> str:
        return f"""**What is it?**
{summary or f"An important concept: {title}."}

**Key Facts**
• This concept is a key part of the lesson.
• Review the source material for more detail.
• Connect this to the neighboring nodes in the graph.

**Why it matters**
Understanding {title} is essential for mastering the broader topic. \
It connects to several other key concepts in this lesson.

**Dig deeper**
Explore the connected nodes in the graph to understand how {title} \
relates to the bigger picture of this lesson."""
