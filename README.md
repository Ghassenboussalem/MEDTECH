# NotebookLM Local Clone 🤖📚

A fully **local, privacy-first** AI research assistant — a self-hosted clone of Google NotebookLM powered by **llama3.2** via Ollama. No cloud APIs, no data leaving your machine.

## Features

- 📄 Upload PDFs, DOCX, TXT/MD documents, or **paste website URLs**
- 💬 Chat with an AI grounded **exclusively** in your uploaded sources
- 📎 Inline **[source citations]** in every answer
- ✨ Generate **Summary**, **FAQ**, **Study Guide**, **Quiz**, and **Mind Map** from your documents
- 🗂️ Multiple isolated notebooks
- 🌙 Beautiful dark UI with streaming responses

## Tech Stack

| Layer | Tech |
|---|---|
| LLM | Ollama + llama3.2:latest |
| Embeddings | nomic-embed-text (via Ollama) |
| Vector store | ChromaDB |
| Backend | FastAPI + Python |
| Frontend | Vite + React + Zustand |

## Prerequisites

1. **Install [Ollama](https://ollama.com)** and pull the required models:
   ```bash
   ollama pull llama3.2:latest
   ollama pull nomic-embed-text
   ```

2. **Python 3.11+** and **Node.js 18+**

## Quick Start

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 2. Frontend (new terminal)

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

> [!IMPORTANT]
> Make sure `ollama serve` is running before starting the backend.

## Project Structure

```
medtech/
├── backend/
│   ├── main.py          # FastAPI REST API
│   ├── notebooks.py     # Notebook CRUD (JSON file)
│   ├── ingest.py        # Document parsing & chunking
│   ├── embeddings.py    # ChromaDB + nomic-embed-text
│   ├── chat.py          # RAG pipeline + streaming
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── pages/       # NotebookList, NotebookDetail
│       ├── components/  # ChatPanel, SourcePanel, UploadZone, CitationChip, GeneratePanel
│       └── store/       # Zustand store
└── data/                # Auto-created: notebooks.json + ChromaDB files
```

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/notebooks` | List all notebooks |
| POST | `/notebooks` | Create notebook |
| DELETE | `/notebooks/{id}` | Delete notebook |
| POST | `/notebooks/{id}/upload` | Upload & index document |
| GET | `/notebooks/{id}/sources` | List sources |
| POST | `/notebooks/{id}/chat` | SSE streaming RAG chat |
| POST | `/notebooks/{id}/generate/{type}` | Generate summary/faq/study_guide |
