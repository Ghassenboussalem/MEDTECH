# MEDTECH - Local NotebookLM + Lucidity Graph

A fully local, privacy-first AI learning assistant inspired by NotebookLM.
Everything runs on your machine with Ollama models. No cloud API is required.

## Core Features

- Upload lesson sources: PDF, DOCX, TXT/MD, URL, and image files.
- Ask grounded questions over your notebook sources.
- Streamed chat responses with source references.
- Generate artifacts: Summary, Study Guide, Mind Map (plus additional internal artifact types).
- Lucidity Graph learning flow with node quizzes and adaptive tutoring.

## Lucidity Highlights

- Lucidity starts from notebook sources (no separate re-upload required in normal flow).
- First chapter node is always unlocked for a clean starting point.
- Quiz flow uses node-specific MCQs and non-generic validation rules.
- If a learner fails, tutoring method is selected adaptively from 3 modes:
  - Feynman
  - Socratic
  - Devil's Advocate
- Method selection uses a lightweight online reinforcement policy (bandit-style) per session/node.

## Models Used

- `llama3.2:latest` - generation/chat/quiz/content
- `nomic-embed-text` - embeddings for retrieval
- `llava:latest` - image-to-text description for image sources

## Tech Stack

- Backend: FastAPI, Python
- Frontend: React + Vite + Zustand
- Vector store: ChromaDB
- Graph: NetworkX + custom Lucidity rendering

## Prerequisites

1. Install Ollama and pull models:

```bash
ollama pull llama3.2:latest
ollama pull nomic-embed-text
ollama pull llava:latest
```

2. Install Python 3.11+ and Node.js 18+.

## Run Locally

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open: `http://localhost:5173`

## Main Endpoints (selected)

- `POST /notebooks/{id}/upload` - upload notebook source file
- `POST /notebooks/{id}/chat` - RAG chat streaming
- `POST /notebooks/{id}/generate/{artifact_type}` - artifact generation
- `POST /api/from-notebook/{notebook_id}` - bootstrap Lucidity session from notebook sources
- `GET /api/status/{session_id}` - Lucidity build progress
- `GET /api/graph/{session_id}` - Lucidity graph payload
- `POST /api/tutor-method/select` - adaptive tutor method selection
- `POST /api/tutor-method/feedback` - reinforcement feedback update

## Project Layout

```text
medtech/
  backend/
    main.py
    ingest.py
    embeddings.py
    chat.py
    guardrails.py
    agents/
  frontend/
    src/
      components/
      pages/
      store/
    public/lucidity/
  data/
```

## Notes

- The app is designed for local/private operation.
- If frontend/backend fail to start, verify Ollama is running and models are available.
