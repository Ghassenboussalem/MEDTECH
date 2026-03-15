"""
Tutor Agent
-----------
Live interactive chat powered by llama3.2:latest via Ollama.
Supports three teaching modes: Feynman, Socratic, Devil's Advocate.
"""
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2:latest"

SYSTEM_PROMPTS = {
    "feynman": (
        "You are a Feynman-style tutor. Your goal is to help the student deeply understand "
        "the concept '{title}' through simple analogies and plain everyday language. "
        "Never give away the quiz answer directly — guide the student to discover it. "
        "Keep each response to 2-3 sentences maximum. Be warm, encouraging and concise."
    ),
    "socratic": (
        "You are a Socratic tutor. Help the student understand '{title}' by asking one "
        "thoughtful guiding question that leads them toward the key insight. "
        "Do NOT explain directly — only ask questions. One short question per reply."
    ),
    "devil": (
        "You are a Devil's Advocate tutor. Challenge the student's understanding of '{title}' "
        "by raising provocative counter-arguments they must defend. Force critical thinking. "
        "Keep each challenge to 2 sentences. Be intellectually playful, not hostile."
    ),
}


def _build_prompt(mode: str, node_title: str, node_summary: str, history: list, user_message: str) -> str:
    system = SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPTS["feynman"]).format(title=node_title)

    lines = [
        f"[SYSTEM] {system}",
        f"[CONTEXT] Node: {node_title}. Summary: {node_summary}",
        "",
    ]
    for turn in history[-6:]:  # Keep last 3 exchanges (6 messages)
        role = "Student" if turn["role"] == "user" else "Tutor"
        lines.append(f"{role}: {turn['content']}")

    lines.append(f"Student: {user_message}")
    lines.append("Tutor:")
    return "\n".join(lines)


class TutorAgent:
    """Agent that handles live tutoring conversations."""

    def chat(
        self,
        mode: str,
        node_title: str,
        node_summary: str,
        user_message: str,
        history: list,
    ) -> str:
        """
        Args:
            mode: 'feynman' | 'socratic' | 'devil'
            node_title: The concept being tutored.
            node_summary: LLM-generated summary for context.
            user_message: The student's latest message.
            history: List of {role, content} dicts (prior turns).

        Returns:
            The tutor's reply string.
        """
        prompt = _build_prompt(mode, node_title, node_summary, history, user_message)
        try:
            payload = {
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 300},
            }
            resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
            resp.raise_for_status()
            reply = resp.json().get("response", "").strip()
            # Strip any accidental "Tutor:" prefix
            if reply.startswith("Tutor:"):
                reply = reply[6:].strip()
            return reply or "Hmm, let me think... Can you rephrase your question?"
        except Exception as e:
            return f"(Connection error: {e}. Is Ollama running?)"
