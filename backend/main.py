"""
main.py — FastAPI application: all REST endpoints for the NotebookLM clone.
"""
import asyncio
from typing import Literal

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import notebooks as nb_store
import ingest as ingester
import embeddings as vec_store
import chat as rag
from chat import validate_node
import graph as kg_store
import concept_extractor as extractor
import socratic_engine as socratic
from graph_storage import GraphStorage

app = FastAPI(title="NotebookLM Local Clone", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    chunks = ingester.ingest_file(file_bytes, file.filename)

    if not chunks:
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
