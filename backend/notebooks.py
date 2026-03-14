"""
notebooks.py — Notebook CRUD using a simple JSON file at data/notebooks.json
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
NOTEBOOKS_FILE = DATA_DIR / "notebooks.json"


def _load() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not NOTEBOOKS_FILE.exists():
        return []
    return json.loads(NOTEBOOKS_FILE.read_text())


def _save(notebooks: list[dict]) -> None:
    NOTEBOOKS_FILE.write_text(json.dumps(notebooks, indent=2))


def list_notebooks() -> list[dict]:
    return _load()


def create_notebook(name: str) -> dict:
    notebooks = _load()
    nb = {
        "id": str(uuid.uuid4()),
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sources": [],
    }
    notebooks.append(nb)
    _save(notebooks)
    return nb


def get_notebook(notebook_id: str) -> dict | None:
    return next((n for n in _load() if n["id"] == notebook_id), None)


def delete_notebook(notebook_id: str) -> bool:
    notebooks = _load()
    new = [n for n in notebooks if n["id"] != notebook_id]
    if len(new) == len(notebooks):
        return False
    _save(new)
    return True


def add_source(notebook_id: str, source_name: str) -> dict | None:
    notebooks = _load()
    for nb in notebooks:
        if nb["id"] == notebook_id:
            entry = {"name": source_name, "added_at": datetime.now(timezone.utc).isoformat()}
            nb["sources"].append(entry)
            _save(notebooks)
            return nb
    return None
