import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import useNotebookStore from '../store/useNotebookStore';
import SourcePanel from '../components/SourcePanel';
import ChatPanel from '../components/ChatPanel';
import GeneratePanel from '../components/GeneratePanel';
import PDFModal from '../components/PDFModal';

export default function NotebookDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { current, loading, error, fetchNotebook } = useNotebookStore();
  const [activeTab, setActiveTab] = useState('chat'); // 'chat' | 'generate'

  useEffect(() => { fetchNotebook(id); }, [id]);

  if (loading) return (
    <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <svg className="spin" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2">
        <path d="M21 12a9 9 0 1 1-6.219-8.56" />
      </svg>
    </div>
  );

  if (error) return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
      <p style={{ color: 'var(--danger)' }}>{error}</p>
      <button className="btn btn-ghost" onClick={() => navigate('/')}>← Back to notebooks</button>
    </div>
  );

  if (!current) return null;

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <PDFModal notebookId={id} />
      {/* ── Top bar ──────────────────────────────────────────────── */}
      <header style={{
        height: 58,
        borderBottom: '1px solid var(--border)',
        background: 'var(--bg-surface)',
        display: 'flex', alignItems: 'center',
        padding: '0 20px', gap: 16, flexShrink: 0,
      }}>
        <button className="btn btn-ghost btn-icon" onClick={() => navigate('/')}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M19 12H5" /><polyline points="12 19 5 12 12 5" />
          </svg>
        </button>
        <div style={{
          width: 28, height: 28, borderRadius: 8,
          background: 'var(--accent-dim)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.2" strokeLinecap="round">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          </svg>
        </div>
        <h1 style={{ fontWeight: 600, fontSize: '0.95rem', flex: 1 }} className="truncate">{current.name}</h1>
        <span className="badge badge-accent">{current.sources?.length ?? 0} sources</span>

        {/* Tab switcher */}
        <div style={{
          display: 'flex', gap: 4,
          background: 'var(--bg-elevated)',
          borderRadius: 'var(--radius-sm)',
          padding: 3,
        }}>
          {['chat', 'generate'].map((tab) => (
            <button key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                padding: '4px 12px',
                borderRadius: 4,
                fontSize: '13px', fontWeight: 500,
                background: activeTab === tab ? 'var(--accent)' : 'transparent',
                color: activeTab === tab ? '#fff' : 'var(--text-secondary)',
                transition: 'all var(--transition)',
              }}
            >
              {tab === 'chat' ? '💬 Chat' : '✨ Generate'}
            </button>
          ))}
        </div>
      </header>

      {/* ── Main two-panel layout ─────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Left: Sources */}
        <div style={{
          width: 280, flexShrink: 0,
          borderRight: '1px solid var(--border)',
          background: 'var(--bg-surface)',
          overflow: 'hidden', display: 'flex', flexDirection: 'column',
        }}>
          <SourcePanel notebookId={id} sources={current.sources ?? []} />
        </div>

        {/* Right: Chat or Generate — always mounted so cache survives tab switches */}
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <div style={{ flex: 1, overflow: 'hidden', flexDirection: 'column', display: activeTab === 'chat' ? 'flex' : 'none' }}>
            <ChatPanel notebookId={id} />
          </div>
          <div style={{ flex: 1, overflow: 'hidden', flexDirection: 'column', display: activeTab === 'generate' ? 'flex' : 'none' }}>
            <GeneratePanel notebookId={id} />
          </div>
        </div>
      </div>
    </div>
  );
}
