"""
main.py — FastAPI application: all REST endpoints for the NotebookLM clone.
"""
import asyncio
import base64
import math
import random
import threading
import uuid
from typing import Literal

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
import os
from pathlib import Path

import notebooks as nb_store
import ingest as ingester
import embeddings as vec_store
import chat as rag
from chat import validate_node
import graph as kg_store
import concept_extractor as extractor
import socratic_engine as socratic
from graph_storage import GraphStorage
import ollama
from agents.orchestrator import OrchestratorAgent
from agents.tutor_agent import TutorAgent
from agents.content_agent import ContentAgent

app = FastAPI(title="NotebookLM Local Clone", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure data dir exists
DATA_DIR = Path(__file__).parent / "data" / "notebooks"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Mount the entire notebooks data directory to serve uploaded files statically
app.mount("/data/notebooks", StaticFiles(directory=str(DATA_DIR)), name="notebook_data")

# Lucidity session data (copied flow from standalone Lucidity project)
UPLOAD_FOLDER = Path(__file__).parent / "uploads"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

sessions: dict = {}
sessions_lock = threading.Lock()
contexts: dict = {}
contexts_lock = threading.Lock()
notebook_lucidity_sessions: dict[str, str] = {}
tutor_bandit_state: dict[str, dict] = {}


def _get_lucidity_session(session_id: str):
    with sessions_lock:
        return sessions.get(session_id)


def _is_image_filename(name: str) -> bool:
    ext = Path(name).suffix.lower()
    return ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def _describe_image_with_llava(image_bytes: bytes, filename: str) -> str:
    """Generate a study-oriented description from an image using llava:latest."""
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    prompt = (
        "Describe this image for a study knowledge graph. "
        "Focus on concrete objects, concepts, labels, numbers, and relationships. "
        "Return one concise paragraph followed by 3-5 bullet points of key facts."
    )
    response = ollama.chat(
        model="llava:latest",
        messages=[
            {
                "role": "user",
                "content": prompt,
                "images": [b64_image],
            }
        ],
        stream=False,
        options={"temperature": 0.2, "num_predict": 512},
    )
    return response["message"]["content"].strip()


# ── Lucidity API ─────────────────────────────────────────────────────────────

@app.post("/api/upload")
async def lucidity_upload(
    lesson_title: str = Form("My Lesson"),
    pdfs: list[UploadFile] = File(...),
):
    lesson_title = lesson_title.strip() or "My Lesson"

    if not pdfs or all((f.filename or "").strip() == "" for f in pdfs):
        raise HTTPException(400, "No PDF files were provided.")

    session_id = str(uuid.uuid4())
    session_dir = UPLOAD_FOLDER / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    file_paths: list[str] = []
    file_names: list[str] = []
    extra_docs: list[dict] = []

    for f in pdfs:
        filename = (f.filename or "").strip()
        safe_name = os.path.basename(filename)
        dest = session_dir / safe_name
        content = await f.read()
        dest.write_bytes(content)

        if filename.lower().endswith(".pdf"):
            file_paths.append(str(dest))
            file_names.append(safe_name)
            continue

        if _is_image_filename(filename):
            try:
                description = await asyncio.to_thread(_describe_image_with_llava, content, safe_name)
            except Exception as exc:
                description = f"Image analysis failed for {safe_name}: {exc}"

            extra_docs.append(
                {
                    "filename": safe_name,
                    "text": description,
                    "page_count": 1,
                }
            )
            file_names.append(safe_name)

    if not file_paths and not extra_docs:
        raise HTTPException(
            400,
            "No valid files found. Upload PDF files and/or images (png, jpg, jpeg, webp, bmp, gif).",
        )

    with sessions_lock:
        sessions[session_id] = {
            "status": "queued",
            "stage": "⏳ Queued...",
            "percent": 0,
            "graph": None,
            "error": None,
            "lesson_title": lesson_title,
            "files": file_names,
        }

    def _run_pipeline():
        agent = OrchestratorAgent(sessions, sessions_lock, contexts, contexts_lock)
        agent.run(file_paths, file_names, lesson_title, session_id, extra_docs=extra_docs)

    threading.Thread(target=_run_pipeline, daemon=True).start()
    return {"session_id": session_id, "files": file_names}


@app.get("/api/status/{session_id}")
def lucidity_status(session_id: str):
    session = _get_lucidity_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found.")
    return {
        "status": session["status"],
        "stage": session["stage"],
        "percent": session["percent"],
        "error": session.get("error"),
    }


@app.get("/api/graph/{session_id}")
def lucidity_graph(session_id: str):
    session = _get_lucidity_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found.")
    if session["status"] == "error":
        raise HTTPException(500, session.get("error", "Pipeline failed."))
    if session["status"] != "done":
        return JSONResponse(
            status_code=202,
            content={"error": "Graph not ready yet.", "status": session["status"]},
        )
    return session["graph"]


class LucidityNodeContentRequest(BaseModel):
    session_id: str = ""
    node_title: str
    node_summary: str = ""


@app.post("/api/node-content")
def lucidity_node_content(body: LucidityNodeContentRequest):
    with contexts_lock:
        context = contexts.get(body.session_id, "")

    content = ContentAgent().generate(body.node_title, body.node_summary, context)
    return {"content": content}


class LucidityChatRequest(BaseModel):
    mode: str = "feynman"
    node_title: str = "this concept"
    node_summary: str = ""
    message: str
    history: list[dict] = []


def _bandit_key(session_id: str, node_id: str) -> str:
    return f"{session_id}:{node_id}"


def _default_method_stats() -> dict:
    return {
        "feynman": {"trials": 0, "reward": 0.0},
        "socratic": {"trials": 0, "reward": 0.0},
        "devil": {"trials": 0, "reward": 0.0},
    }


def _choose_tutor_method(stats: dict, fail_count: int) -> str:
    methods = ["feynman", "socratic", "devil"]
    untried = [m for m in methods if stats[m]["trials"] == 0]
    if untried:
        # Mild curriculum bias during exploration by fail stage.
        if fail_count <= 1 and "feynman" in untried:
            return "feynman"
        if fail_count == 2 and "socratic" in untried:
            return "socratic"
        if fail_count >= 3 and "devil" in untried:
            return "devil"
        return random.choice(untried)

    total_trials = sum(stats[m]["trials"] for m in methods)
    c = 1.15

    # Difficulty stage prior bonus to keep progression coherent.
    stage_bonus = {
        "feynman": 0.08 if fail_count <= 1 else 0.0,
        "socratic": 0.08 if fail_count == 2 else 0.0,
        "devil": 0.08 if fail_count >= 3 else 0.0,
    }

    best_method = "socratic"
    best_score = -1e9
    for m in methods:
        t = stats[m]["trials"]
        avg = (stats[m]["reward"] / t) if t else 0.0
        ucb = avg + c * math.sqrt(math.log(total_trials + 1) / t)
        score = ucb + stage_bonus[m]
        if score > best_score:
            best_score = score
            best_method = m
    return best_method


class TutorMethodSelectRequest(BaseModel):
    session_id: str
    node_id: str
    fail_count: int = 1


class TutorMethodFeedbackRequest(BaseModel):
    session_id: str
    node_id: str
    method: str
    reward: float


@app.post("/api/tutor-method/select")
def tutor_method_select(body: TutorMethodSelectRequest):
    key = _bandit_key(body.session_id, body.node_id)
    with sessions_lock:
        stats = tutor_bandit_state.setdefault(key, _default_method_stats())
        method = _choose_tutor_method(stats, body.fail_count)
        snapshot = {
            m: {
                "trials": stats[m]["trials"],
                "avg_reward": round((stats[m]["reward"] / stats[m]["trials"]) if stats[m]["trials"] else 0.0, 3),
            }
            for m in ("feynman", "socratic", "devil")
        }
    return {"method": method, "stats": snapshot}


@app.post("/api/tutor-method/feedback")
def tutor_method_feedback(body: TutorMethodFeedbackRequest):
    method = (body.method or "").strip().lower()
    if method not in {"feynman", "socratic", "devil"}:
        raise HTTPException(400, "Invalid method. Use feynman|socratic|devil")

    reward = max(0.0, min(1.0, float(body.reward)))
    key = _bandit_key(body.session_id, body.node_id)

    with sessions_lock:
        stats = tutor_bandit_state.setdefault(key, _default_method_stats())
        stats[method]["trials"] += 1
        stats[method]["reward"] += reward

        return {
            "ok": True,
            "method": method,
            "trials": stats[method]["trials"],
            "avg_reward": round(stats[method]["reward"] / stats[method]["trials"], 3),
        }


@app.post("/api/chat")
def lucidity_chat(body: LucidityChatRequest):
    user_message = body.message.strip()
    if not user_message:
        raise HTTPException(400, "message is required")

    reply = TutorAgent().chat(
        mode=body.mode,
        node_title=body.node_title,
        node_summary=body.node_summary,
        user_message=user_message,
        history=body.history,
    )
    return {"response": reply}


@app.get("/api/health")
def lucidity_health():
    return {"status": "ok", "model": "llama3.2:latest"}


@app.post("/api/from-notebook/{notebook_id}")
def lucidity_from_notebook(notebook_id: str):
    """Create or reuse a Lucidity session using already uploaded notebook sources."""
    nb = nb_store.get_notebook(notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")

    # Reuse an active/completed Lucidity session for this notebook when possible.
    with sessions_lock:
        existing_session_id = notebook_lucidity_sessions.get(notebook_id)
        existing_session = sessions.get(existing_session_id) if existing_session_id else None
        if existing_session and existing_session.get("status") in {"queued", "running", "done"}:
            return {
                "session_id": existing_session_id,
                "status": existing_session.get("status"),
                "reused": True,
            }

    source_dir = DATA_DIR / notebook_id / "sources"
    if not source_dir.exists():
        raise HTTPException(400, "No uploaded sources found for this notebook.")

    source_files = sorted([p for p in source_dir.iterdir() if p.is_file()])
    pdf_files = [p for p in source_files if p.suffix.lower() == ".pdf"]
    image_files = [p for p in source_files if _is_image_filename(p.name)]

    if not pdf_files and not image_files:
        raise HTTPException(
            400,
            "This notebook has no supported sources. Upload PDF and/or image files in Sources first.",
        )

    lesson_title = nb.get("name", "My Lesson")
    file_paths = [str(p) for p in pdf_files]
    file_names = [p.name for p in pdf_files]
    extra_docs: list[dict] = []

    for image_file in image_files:
        try:
            image_bytes = image_file.read_bytes()
            description = _describe_image_with_llava(image_bytes, image_file.name)
        except Exception as exc:
            description = f"Image analysis failed for {image_file.name}: {exc}"

        extra_docs.append(
            {
                "filename": image_file.name,
                "text": description,
                "page_count": 1,
            }
        )
        file_names.append(image_file.name)
    session_id = str(uuid.uuid4())

    with sessions_lock:
        sessions[session_id] = {
            "status": "queued",
            "stage": "⏳ Queued...",
            "percent": 0,
            "graph": None,
            "error": None,
            "lesson_title": lesson_title,
            "files": file_names,
        }
        notebook_lucidity_sessions[notebook_id] = session_id

    def _run_pipeline():
        agent = OrchestratorAgent(sessions, sessions_lock, contexts, contexts_lock)
        agent.run(file_paths, file_names, lesson_title, session_id, extra_docs=extra_docs)

    threading.Thread(target=_run_pipeline, daemon=True).start()

    return {
        "session_id": session_id,
        "status": "queued",
        "reused": False,
        "files": file_names,
    }

# ── Notebooks ────────────────────────────────────────────────────────────────

class NotebookCreate(BaseModel):
    name: str


@app.get("/notebooks")
def list_notebooks():
    return nb_store.list_notebooks()


@app.post("/notebooks", status_code=201)
def create_notebook(body: NotebookCreate):
    return nb_store.create_notebook(body.name)


@app.get("/notebooks/{notebook_id}")
def get_notebook(notebook_id: str):
    nb = nb_store.get_notebook(notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")
    return nb


@app.delete("/notebooks/{notebook_id}", status_code=204)
def delete_notebook(notebook_id: str):
    deleted = nb_store.delete_notebook(notebook_id)
    if not deleted:
        raise HTTPException(404, "Notebook not found")
    vec_store.delete_collection(notebook_id)


# ── Sources ──────────────────────────────────────────────────────────────────

@app.get("/notebooks/{notebook_id}/sources")
def list_sources(notebook_id: str):
    nb = nb_store.get_notebook(notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")
    return nb.get("sources", [])


@app.post("/notebooks/{notebook_id}/upload", status_code=201)
async def upload_source(notebook_id: str, file: UploadFile = File(...)):
    nb = nb_store.get_notebook(notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")

    file_bytes = await file.read()

    # Save the file to disk so the frontend can display it in the citation viewer
    nb_dir = DATA_DIR / notebook_id / "sources"
    nb_dir.mkdir(parents=True, exist_ok=True)
    file_path = nb_dir / file.filename
    file_path.write_bytes(file_bytes)

    chunks = ingester.ingest_file(file_bytes, file.filename)

    if not chunks:
        # If extraction completely fails, clean up the saved file
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(422, "Could not extract text from the uploaded file.")

    # Run embedding in a thread to avoid blocking the event loop
    await asyncio.to_thread(vec_store.add_chunks, notebook_id, chunks)
    nb_store.add_source(notebook_id, file.filename)

    return {"filename": file.filename, "chunks_indexed": len(chunks)}


class UrlUpload(BaseModel):
    url: str


@app.post("/notebooks/{notebook_id}/upload-url", status_code=201)
async def upload_url(notebook_id: str, body: UrlUpload):
    nb = nb_store.get_notebook(notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")

    try:
        chunks = await asyncio.to_thread(ingester.parse_url, body.url)
    except ValueError as e:
        raise HTTPException(422, str(e))

    if not chunks:
        raise HTTPException(422, "Could not extract text from URL.")

    source_name = chunks[0]["source"] if chunks else body.url
    await asyncio.to_thread(vec_store.add_chunks, notebook_id, chunks)
    nb_store.add_source(notebook_id, source_name)
    return {"url": body.url, "source_name": source_name, "chunks_indexed": len(chunks)}


# ── Chat ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str
    history: list[dict] = []


@app.post("/notebooks/{notebook_id}/chat")
async def chat(notebook_id: str, body: ChatRequest):
    nb = nb_store.get_notebook(notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")

    async def event_stream():
        async for token in rag.rag_stream(notebook_id, body.question, body.history):
            # SSE format: data: <token>\n\n
            yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/notebooks/{notebook_id}/welcome")
async def get_welcome_message(notebook_id: str):
    """Generate a proactive summary and 3 suggested questions for an empty chat."""
    nb = nb_store.get_notebook(notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")
    
    # Check if there are sources before generating a welcome
    sources = nb.get("sources", [])
    if not sources:
        return {"summary": "Upload some documents to get started!", "questions": []}

    result = await rag.generate_welcome(notebook_id)
    return result


# ── Artifact Generation ───────────────────────────────────────────────────────

ArtifactType = Literal["summary", "faq", "study_guide", "quiz", "mind_map", "learning_graph"]


@app.post("/notebooks/{notebook_id}/generate/{artifact_type}")
async def generate_artifact(notebook_id: str, artifact_type: ArtifactType):
    nb = nb_store.get_notebook(notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")

    result = await rag.generate_artifact(notebook_id, artifact_type)
    return {"type": artifact_type, "content": result}


# ── Node Validation ─────────────────────────────────────────────────────────

class ValidateQuestion(BaseModel):
    q: str
    expected_answer: str
    user_answer: str


class ValidateNodeRequest(BaseModel):
    node_id: str
    node_label: str
    node_content: str
    questions: list[ValidateQuestion]


@app.post("/notebooks/{notebook_id}/validate-node")
async def validate_node_endpoint(notebook_id: str, body: ValidateNodeRequest):
    nb = nb_store.get_notebook(notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")

    qs = [q.model_dump() for q in body.questions]
    results = await validate_node(
        node_label=body.node_label,
        node_content=body.node_content,
        questions=qs,
    )
    passed = all(results)
    return {"node_id": body.node_id, "results": results, "passed": passed}


# ── Knowledge Graph (MAÏEUTICA) ─────────────────────────────────────────────────────────

@app.post("/notebooks/{notebook_id}/build-graph")
async def build_graph(notebook_id: str):
    """Extract concepts from uploaded sources and build the knowledge graph."""
    nb = nb_store.get_notebook(notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")

    # Pull all text from the vector store
    from embeddings import query as vec_query
    chunks = vec_query(notebook_id, "overview introduction main concepts", k=20)
    context = "\n\n".join(c["text"] for c in chunks) if chunks else ""
    if not context:
        raise HTTPException(422, "No sources uploaded yet — upload documents first.")

    concepts_json, course_json = await extractor.run_pipeline(notebook_id, context)

    if not concepts_json.get("essential_concepts"):
        error_msg = concepts_json.get("_parse_error", "Failed to extract concepts from sources.")
        raise HTTPException(500, f"Graph generation failed: The AI could not extract valid concepts. Parse error: {error_msg}")

    graph = kg_store.get_graph(notebook_id)
    graph.build_graph(concepts_json, course_json)  # GraphBuilder API

    return {
        "status": "built",
        "concepts_extracted": concepts_json.get("total_concepts", 0),
        "modules": len(course_json.get("modules", [])),
        "course_title": course_json.get("course_title", ""),
        "graph": graph.get_state(),
    }


@app.get("/notebooks/{notebook_id}/graph")
def get_graph(notebook_id: str):
    """Return the current knowledge graph state."""
    nb = nb_store.get_notebook(notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")
    graph = kg_store.get_graph(notebook_id)
    return graph.get_state()


class ExportGraphRequest(BaseModel):
    storage_type: str = "neo4j"   # "neo4j" | "memgraph"


@app.post("/notebooks/{notebook_id}/export-graph")
async def export_graph(notebook_id: str, body: ExportGraphRequest):
    """Optional: persist the knowledge graph to Neo4j or Memgraph."""
    nb = nb_store.get_notebook(notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")
    graph = kg_store.get_graph(notebook_id)
    storage = GraphStorage(storage_type=body.storage_type)
    result = await asyncio.to_thread(storage.save_graph, graph, notebook_id)
    if not result.get("success"):
        raise HTTPException(500, result.get("error", "Export failed"))
    return result


class SocraticChatRequest(BaseModel):
    concept_id: str
    message: str
    history: list[dict] = []
    session_id: str = ""
    mode: str = ""  # feynman | socratic | devil_advocate | "" (auto)


@app.post("/notebooks/{notebook_id}/socratic-chat")
async def socratic_chat(notebook_id: str, body: SocraticChatRequest):
    """Streaming Socratic AI response — never gives direct answers."""
    nb = nb_store.get_notebook(notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")

    graph = kg_store.get_graph(notebook_id)
    concept = graph.get_concept(body.concept_id)
    if not concept:
        raise HTTPException(404, f"Concept '{body.concept_id}' not found in graph.")

    # Pick first active misconception as hint for Devil mode
    active_mcs = graph.get_active_misconceptions(body.concept_id)
    mc_hint = active_mcs[0]["wrong_statement"] if active_mcs else None

    force_mode = body.mode if body.mode in ("feynman", "socratic", "devil_advocate") else None

    async def event_stream():
        async for token in socratic.socratic_stream(
            notebook_id=notebook_id,
            concept=concept,
            history=body.history,
            student_message=body.message,
            mode=force_mode,
            active_misconception=mc_hint,
        ):
            yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class ScoreRequest(BaseModel):
    concept_id: str
    student_response: str
    session_id: str = ""


@app.post("/notebooks/{notebook_id}/score-response")
async def score_response_endpoint(notebook_id: str, body: ScoreRequest):
    """Score a student summary response, update the knowledge graph node."""
    nb = nb_store.get_notebook(notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")

    graph = kg_store.get_graph(notebook_id)
    concept = graph.get_concept(body.concept_id)
    if not concept:
        raise HTTPException(404, "Concept not found")

    result = await socratic.score_response(
        notebook_id=notebook_id,
        concept=concept,
        student_response=body.student_response,
    )

    # Update graph with score
    mode = graph.get_recommended_mode(body.concept_id)
    graph.update_concept(
        concept_id=body.concept_id,
        score=result.get("score", 0.5),
        bloom_achieved=result.get("bloom_demonstrated", "remember"),
        misconceptions_detected=result.get("misconceptions_detected", []),
        mode=mode,
    )

    return {"concept_id": body.concept_id, **result, "updated_node": graph.get_concept(body.concept_id)}


@app.get("/notebooks/{notebook_id}/next-concept")
def next_concept(notebook_id: str):
    """Return the next recommended concept_id for the student."""
    nb = nb_store.get_notebook(notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")
    graph = kg_store.get_graph(notebook_id)
    cid = graph.get_next_concept()
    if not cid:
        return {"concept_id": None, "message": "All concepts mastered!"}
    concept = graph.get_concept(cid)
    mode = graph.get_recommended_mode(cid)
    return {"concept_id": cid, "concept": concept, "recommended_mode": mode}


class NodeQuizRequest(BaseModel):
    concept_id: str


@app.post("/notebooks/{notebook_id}/node-quiz")
async def generate_node_quiz(notebook_id: str, body: NodeQuizRequest):
    """Generate 3 MCQ questions for a specific concept node."""
    nb = nb_store.get_notebook(notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")

    graph = kg_store.get_graph(notebook_id)
    concept = graph.get_concept(body.concept_id)
    if not concept:
        raise HTTPException(404, f"Concept '{body.concept_id}' not found in graph.")

    # Fetch relevant context from RAG
    from embeddings import query as vec_query
    chunks = vec_query(notebook_id, concept.get("name", ""), k=4)
    context = "\n\n".join(c["text"] for c in chunks) if chunks else concept.get("description", "")

    concept_name = concept.get("name", body.concept_id)
    concept_desc = concept.get("description", "")

    prompt = (
        "You are an educational assessment expert.\n"
        f"Create exactly 3 multiple-choice questions to test understanding of:\n"
        f"Concept: {concept_name}\n"
        f"Description: {concept_desc}\n\n"
        f"Context from the course material:\n{context[:1500]}\n\n"
        "Return ONLY valid JSON in this exact format:\n"
        '{"questions":['
        '{"q":"Question text?","options":["Option A","Option B","Option C","Option D"],"answer_index":0,"explanation":"Why this is correct."},'
        '{"q":"Question 2?","options":["A","B","C","D"],"answer_index":2,"explanation":"Reason."},'
        '{"q":"Question 3?","options":["A","B","C","D"],"answer_index":1,"explanation":"Reason."}'
        "]}\n\n"
        "Rules:\n"
        "- answer_index is 0-based (0=A, 1=B, 2=C, 3=D)\n"
        "- Make distractors plausible but clearly wrong to an expert\n"
        "- Questions must be specific to the concept above\n"
        "- NO markdown, NO extra text, ONLY the JSON object"
    )

    import ollama
    import json
    import re

    def _call():
        return ollama.chat(
            model="llama3.2:latest",
            messages=[{"role": "user", "content": prompt}],
            stream=False,
            format="json",
            options={"num_predict": 2048, "temperature": 0.2},
        )

    try:
        resp = await asyncio.to_thread(_call)
        raw = resp["message"]["content"]

        # Clean and parse
        clean = re.sub(r"```json\n?|\n?```", "", raw).strip()
        clean = re.sub(r",\s*([\]}])", r"\1", clean)
        data = json.loads(clean)
        questions = data.get("questions", [])

        # Validate structure
        valid_qs = []
        for q in questions:
            if (isinstance(q, dict) and q.get("q") and
                    isinstance(q.get("options"), list) and len(q["options"]) >= 2 and
                    isinstance(q.get("answer_index"), int)):
                valid_qs.append(q)

        if not valid_qs:
            # Fallback: generate a simple free-text question
            raise ValueError("No valid questions parsed")

        return {"concept_id": body.concept_id, "concept_name": concept_name, "questions": valid_qs[:3]}

    except Exception as e:
        # Fallback hard-coded questions from concept data
        fallback = [
            {
                "q": f"Which of the following best describes '{concept_name}'?",
                "options": [
                    concept_desc[:80] if concept_desc else "Correct definition",
                    "An unrelated process",
                    "The opposite concept",
                    "A method, not a concept",
                ],
                "answer_index": 0,
                "explanation": f"{concept_name}: {concept_desc}",
            }
        ]
        return {"concept_id": body.concept_id, "concept_name": concept_name, "questions": fallback}


@app.post("/notebooks/{notebook_id}/start-session")
def start_session(notebook_id: str):
    nb = nb_store.get_notebook(notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")
    graph = kg_store.get_graph(notebook_id)
    return {"session_id": graph.start_session()}


@app.post("/notebooks/{notebook_id}/end-session/{session_id}")
def end_session(notebook_id: str, session_id: str):
    nb = nb_store.get_notebook(notebook_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")
    graph = kg_store.get_graph(notebook_id)
    return graph.end_session(session_id)


# ── Dev entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
