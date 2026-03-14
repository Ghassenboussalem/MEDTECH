import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import useNotebookStore from '../store/useNotebookStore';

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function NewNotebookModal({ onClose, onCreate }) {
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    try {
      await onCreate(name.trim());
      onClose();
    } catch { setLoading(false); }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2 style={{ fontSize: '1.2rem', marginBottom: 20 }}>New Notebook</h2>
        <form onSubmit={submit}>
          <input
            id="notebook-name-input"
            className="input"
            placeholder="e.g. Machine Learning Papers"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
            style={{ marginBottom: 20 }}
          />
          <div className="flex gap-2" style={{ justifyContent: 'flex-end' }}>
            <button className="btn btn-ghost" type="button" onClick={onClose}>Cancel</button>
            <button id="create-notebook-btn" className="btn btn-primary" type="submit" disabled={loading || !name.trim()}>
              {loading ? 'Creating…' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ConfirmModal({ message, onConfirm, onClose }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <p style={{ marginBottom: 24, color: 'var(--text-secondary)' }}>{message}</p>
        <div className="flex gap-2" style={{ justifyContent: 'flex-end' }}>
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-danger" onClick={onConfirm}>Delete</button>
        </div>
      </div>
    </div>
  );
}

export default function NotebookList() {
  const { notebooks, loading, fetchNotebooks, createNotebook, deleteNotebook } = useNotebookStore();
  const navigate = useNavigate();
  const [showNew, setShowNew] = useState(false);
  const [confirmId, setConfirmId] = useState(null);

  useEffect(() => { fetchNotebooks(); }, []);

  const handleCreate = async (name) => {
    const nb = await createNotebook(name);
    navigate(`/notebooks/${nb.id}`);
  };

  const handleDelete = async () => {
    await deleteNotebook(confirmId);
    setConfirmId(null);
  };

  return (
    <div style={{ minHeight: '100vh', padding: '0 20px 60px' }}>
      {/* Header */}
      <header style={{
        maxWidth: 1100, margin: '0 auto',
        padding: '32px 0 48px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between'
      }}>
        <div className="flex items-center gap-3">
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: 'var(--accent)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: 'var(--shadow-glow)',
          }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
            </svg>
          </div>
          <div>
            <h1 style={{ fontSize: '1.1rem', fontWeight: 700, lineHeight: 1 }}>NotebookLM Local</h1>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: 2 }}>Powered by llama3.2 · 100% local</p>
          </div>
        </div>
        <button id="new-notebook-btn" className="btn btn-primary" onClick={() => setShowNew(true)}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          New Notebook
        </button>
      </header>

      <main style={{ maxWidth: 1100, margin: '0 auto' }}>
        {loading && (
          <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-muted)' }}>
            <svg className="spin" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2">
              <path d="M21 12a9 9 0 1 1-6.219-8.56" />
            </svg>
          </div>
        )}

        {!loading && notebooks.length === 0 && (
          <div style={{
            textAlign: 'center', padding: '80px 0',
            border: '1px dashed var(--border)', borderRadius: 'var(--radius-xl)',
          }}>
            <div style={{ fontSize: '2.4rem', marginBottom: 12 }}>📚</div>
            <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: 8 }}>No notebooks yet</h2>
            <p style={{ color: 'var(--text-muted)', marginBottom: 24 }}>Create a notebook to start chatting with your documents</p>
            <button className="btn btn-primary" onClick={() => setShowNew(true)}>Create your first notebook</button>
          </div>
        )}

        {!loading && notebooks.length > 0 && (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: 20,
          }}>
            {notebooks.map((nb) => (
              <div key={nb.id} className="card" style={{ padding: 24, cursor: 'pointer' }}
                onClick={() => navigate(`/notebooks/${nb.id}`)}>
                <div className="flex items-center gap-2" style={{ marginBottom: 16 }}>
                  <div style={{
                    width: 38, height: 38, borderRadius: 10,
                    background: 'var(--accent-dim)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0,
                  }}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round">
                      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                    </svg>
                  </div>
                  <span className="truncate" style={{ fontWeight: 600, fontSize: '0.95rem' }}>{nb.name}</span>
                </div>

                <div className="flex items-center gap-2" style={{ marginBottom: 16 }}>
                  <span className="badge badge-accent">
                    {nb.sources?.length ?? 0} source{nb.sources?.length !== 1 ? 's' : ''}
                  </span>
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{formatDate(nb.created_at)}</span>
                </div>

                {nb.sources?.length > 0 && (
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                    {nb.sources.slice(0, 3).map((s) => (
                      <div key={s.name} className="truncate" style={{ marginBottom: 2 }}>📄 {s.name}</div>
                    ))}
                    {nb.sources.length > 3 && <div>+ {nb.sources.length - 3} more</div>}
                  </div>
                )}

                <div style={{ borderTop: '1px solid var(--border)', marginTop: 16, paddingTop: 12, display: 'flex', justifyContent: 'flex-end' }}>
                  <button className="btn btn-danger btn-icon" onClick={(e) => { e.stopPropagation(); setConfirmId(nb.id); }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                      <polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14H6L5 6" /><path d="M10 11v6" /><path d="M14 11v6" /><path d="M9 6V4h6v2" />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {showNew && <NewNotebookModal onClose={() => setShowNew(false)} onCreate={handleCreate} />}
      {confirmId && (
        <ConfirmModal
          message="Delete this notebook? All sources and vectors will be permanently removed."
          onConfirm={handleDelete}
          onClose={() => setConfirmId(null)}
        />
      )}
    </div>
  );
}
