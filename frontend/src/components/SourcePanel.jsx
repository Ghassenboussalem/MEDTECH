import { useState } from 'react';
import UploadZone from './UploadZone';
import useNotebookStore from '../store/useNotebookStore';

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export default function SourcePanel({ notebookId, sources }) {
  const [url, setUrl] = useState('');
  const [urlLoading, setUrlLoading] = useState(false);
  const [urlError, setUrlError] = useState('');
  const { uploadUrl } = useNotebookStore();

  const handleAddUrl = async (e) => {
    e.preventDefault();
    if (!url.trim()) return;
    setUrlLoading(true);
    setUrlError('');
    try {
      await uploadUrl(notebookId, url.trim());
      setUrl('');
    } catch (err) {
      setUrlError(err.message);
    } finally {
      setUrlLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{
        padding: '14px 16px',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <h2 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary)', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
          Sources
        </h2>
        <span className="badge badge-accent">{sources.length}</span>
      </div>

      {/* Upload zone & URL input */}
      <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <UploadZone notebookId={notebookId} />
        
        <form onSubmit={handleAddUrl} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              className="input"
              style={{ flex: 1, padding: '8px 12px', fontSize: 13 }}
              placeholder="Paste website URL..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={urlLoading}
            />
            <button
              type="submit"
              className="btn btn-primary"
              style={{ padding: '8px 12px', fontSize: 13 }}
              disabled={!url.trim() || urlLoading}
            >
              {urlLoading ? '...' : 'Add'}
            </button>
          </div>
          {urlError && <div style={{ color: 'var(--danger)', fontSize: 11 }}>{urlError}</div>}
        </form>
      </div>

      {/* Source list */}
      <div className="overflow-y-auto" style={{ flex: 1, padding: '8px 8px' }}>
        {sources.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '32px 16px' }}>
            <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>No sources yet.</p>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: 4 }}>Upload a document to get started.</p>
          </div>
        ) : (
          sources.map((s) => (
            <div key={s.name} style={{
              display: 'flex', alignItems: 'flex-start', gap: 10,
              padding: '10px 10px',
              borderRadius: 'var(--radius-sm)',
              transition: 'background var(--transition)',
            }}
              onMouseEnter={(e) => e.currentTarget.style.background = 'var(--bg-hover)'}
              onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
            >
              <span style={{ fontSize: '16px', lineHeight: 1.4, flexShrink: 0 }}>
                {s.name.endsWith('.pdf') ? '📕' : s.name.endsWith('.docx') ? '📘' : '📄'}
              </span>
              <div style={{ minWidth: 0 }}>
                <p className="truncate" style={{ fontSize: '13px', fontWeight: 500 }}>{s.name}</p>
                <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 2 }}>{formatDate(s.added_at)}</p>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
