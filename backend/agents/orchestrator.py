"""
Orchestrator Agent
------------------
Coordinates the full multi-agent pipeline:
  1. PDFExtractorAgent  — extract text from each PDF
  2. StructureAgent     — LLM: extract knowledge hierarchy
  3. QuizAgent          — LLM: generate MCQs for each node
  4. GraphLayoutAgent   — compute positions and build NODES list

Updates the shared sessions dict with live progress so the frontend
can display a real-time progress bar.
"""
import threading

from agents.pdf_extractor import PDFExtractorAgent
from agents.structure_agent import StructureAgent
from agents.quiz_agent import QuizAgent
from agents.graph_layout import GraphLayoutAgent


class OrchestratorAgent:
    """
    Coordinates the full pipeline for a single upload session.
    Designed to run inside a background thread.
    """

    def __init__(self, sessions: dict, lock: threading.Lock,
                 contexts: dict = None, contexts_lock: threading.Lock = None):
        self.sessions = sessions
        self.lock = lock
        self.contexts = contexts or {}
        self.contexts_lock = contexts_lock or threading.Lock()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _update(self, session_id: str, stage: str, percent: int, status: str = "running"):
        with self.lock:
            self.sessions[session_id]["stage"] = stage
            self.sessions[session_id]["percent"] = percent
            self.sessions[session_id]["status"] = status
        print(f"[Orchestrator] [{percent:3d}%] {stage}")

    # ── Main entry point ──────────────────────────────────────────────────────

    def run(
        self,
        file_paths: list,
        file_names: list,
        lesson_title: str,
        session_id: str,
        extra_docs: list | None = None,
    ):
        """
        Execute the full pipeline in order.

        Args:
            file_paths: Absolute paths to uploaded PDF files.
            file_names: Original filenames (for the graph sidebar).
            lesson_title: Human-readable lesson title entered by user.
            session_id: UUID used to update the shared sessions dict.
        """
        try:
            # ── Step 1: Source Extraction ──────────────────────────────────
            self._update(session_id, "📄 Extracting source content...", 10)
            extractor = PDFExtractorAgent()
            extracted_docs = []

            if file_paths:
                for idx, path in enumerate(file_paths):
                    fname = file_names[idx] if idx < len(file_names) else f"file_{idx}.pdf"
                    self._update(
                        session_id,
                        f"📄 Reading {fname} ({idx+1}/{len(file_paths)})...",
                        10 + int((idx / max(1, len(file_paths))) * 15),
                    )
                    result = extractor.extract(path)
                    extracted_docs.append(result)
                    print(f"[Orchestrator] Extracted {result['page_count']} pages from {fname}")

            if extra_docs:
                extracted_docs.extend(extra_docs)

            if not extracted_docs:
                raise ValueError("No source text could be extracted from uploaded files.")

            # Merge all texts
            combined_text = "\n\n---\n\n".join(
                f"[Source: {doc['filename']}]\n{doc['text']}" for doc in extracted_docs
            )

            # Store the FULL text in contexts for on-demand content generation
            with self.contexts_lock:
                self.contexts[session_id] = combined_text

            # Trim to ~14 000 chars for LLM structure/quiz calls
            if len(combined_text) > 14000:
                combined_text = combined_text[:14000] + "\n...[truncated]"

            # ── Step 2: Structure Extraction ───────────────────────────────
            self._update(session_id, "🧠 Analyzing knowledge structure with LLM...", 30)
            structure_agent = StructureAgent()
            structure = structure_agent.extract(combined_text, lesson_title)
            # Inject lesson title so root node can use it
            structure.setdefault("title", lesson_title)
            print(f"[Orchestrator] Structure: {len(structure.get('chapters', []))} chapters")

            # ── Step 3: Quiz Generation ────────────────────────────────────
            self._update(session_id, "📝 Generating quizzes for each concept...", 50)
            quiz_agent = QuizAgent()

            # Count total nodes for progress reporting
            total_nodes = 1  # root
            for ch in structure.get("chapters", []):
                total_nodes += 1
                for sec in ch.get("sections", []):
                    total_nodes += 1
                    total_nodes += len(sec.get("subsections", []))

            # Annotate entire tree with quiz questions
            # We override the default annotate_tree to emit progress
            done_nodes = [0]

            def _quiz_with_progress(node_title, node_summary, context):
                quiz = quiz_agent.generate(node_title, node_summary, context)
                done_nodes[0] += 1
                pct = 50 + int((done_nodes[0] / total_nodes) * 30)
                short = node_title[:28] + ("…" if len(node_title) > 28 else "")
                self._update(session_id, f"📝 Quiz {done_nodes[0]}/{total_nodes}: {short}", pct)
                return quiz

            ctx = combined_text[:3000]

            # Root quiz
            structure["quiz"] = _quiz_with_progress(
                structure.get("title", lesson_title), structure.get("summary", ""), ctx
            )
            # Chapter / Section / Sub quizzes
            for chapter in structure.get("chapters", []):
                chapter["quiz"] = _quiz_with_progress(
                    chapter["title"], chapter.get("summary", ""), ctx
                )
                for section in chapter.get("sections", []):
                    section["quiz"] = _quiz_with_progress(
                        section["title"], section.get("summary", ""), ctx
                    )
                    for sub in section.get("subsections", []):
                        sub["quiz"] = _quiz_with_progress(
                            sub["title"], sub.get("summary", ""), ctx
                        )

            # ── Step 4: Graph Layout ───────────────────────────────────────
            self._update(session_id, "🗺️ Building neural graph layout...", 85)
            layout_agent = GraphLayoutAgent()
            graph_data = layout_agent.build(structure, lesson_title, file_names)
            print(f"[Orchestrator] Graph: {len(graph_data['nodes'])} nodes")

            # ── Done ───────────────────────────────────────────────────────
            with self.lock:
                self.sessions[session_id]["graph"] = graph_data
                self.sessions[session_id]["status"] = "done"
                self.sessions[session_id]["stage"] = "✅ Graph ready!"
                self.sessions[session_id]["percent"] = 100

        except Exception as exc:
            import traceback
            traceback.print_exc()
            with self.lock:
                self.sessions[session_id]["status"] = "error"
                self.sessions[session_id]["stage"] = f"❌ Error: {exc}"
                self.sessions[session_id]["percent"] = 0
