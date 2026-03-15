import { create } from 'zustand';

const API = '';  // proxied by Vite → localhost:8000

const useNotebookStore = create((set, get) => ({
  notebooks: [],
  current: null,
  loading: false,
  error: null,
  selectedCitation: null,

  setSelectedCitation: (meta) => set({ selectedCitation: meta }),

  // ── Notebook CRUD ───────────────────────────────────────────────────────
  fetchNotebooks: async () => {
    set({ loading: true, error: null });
    try {
      const res = await fetch(`${API}/notebooks`);
      if (!res.ok) throw new Error('Failed to load notebooks');
      const data = await res.json();
      set({ notebooks: data, loading: false });
    } catch (e) {
      set({ error: e.message, loading: false });
    }
  },

  createNotebook: async (name) => {
    const res = await fetch(`${API}/notebooks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (!res.ok) throw new Error('Failed to create notebook');
    const nb = await res.json();
    set((s) => ({ notebooks: [...s.notebooks, nb] }));
    return nb;
  },

  deleteNotebook: async (id) => {
    const res = await fetch(`${API}/notebooks/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete notebook');
    set((s) => ({ notebooks: s.notebooks.filter((n) => n.id !== id) }));
  },

  // ── Current notebook ────────────────────────────────────────────────────
  fetchNotebook: async (id) => {
    set({ loading: true, error: null, current: null });
    try {
      const res = await fetch(`${API}/notebooks/${id}`);
      if (!res.ok) throw new Error('Notebook not found');
      const data = await res.json();
      set({ current: data, loading: false });
    } catch (e) {
      set({ error: e.message, loading: false });
    }
  },

  // ── Upload ──────────────────────────────────────────────────────────────
  uploadFile: async (notebookId, file, onProgress) => {
    const form = new FormData();
    form.append('file', file);
    onProgress('uploading');
    const res = await fetch(`${API}/notebooks/${notebookId}/upload`, {
      method: 'POST',
      body: form,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(err.detail || 'Upload failed');
    }
    const data = await res.json();
    onProgress('done');
    // Refresh current notebook metadata
    const nb = await fetch(`${API}/notebooks/${notebookId}`).then((r) => r.json());
    set({ current: nb });
    return data;
  },

  uploadUrl: async (notebookId, url) => {
    const res = await fetch(`${API}/notebooks/${notebookId}/upload-url`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Failed to fetch URL' }));
      throw new Error(err.detail || 'Failed to fetch URL');
    }
    const data = await res.json();
    // Refresh current notebook metadata
    const nb = await fetch(`${API}/notebooks/${notebookId}`).then((r) => r.json());
    set({ current: nb });
    return data;
  },

  // ── Generate artifacts ──────────────────────────────────────────────────
  generateArtifact: async (notebookId, type) => {
    const res = await fetch(`${API}/notebooks/${notebookId}/generate/${type}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Generation failed');
    return res.json();
  },
}));

export default useNotebookStore;
