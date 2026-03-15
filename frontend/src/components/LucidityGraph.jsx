import { useEffect, useMemo, useState } from 'react';

export default function LucidityGraph({ notebookId, initialSessionId = '' }) {
  const [loading, setLoading] = useState(!initialSessionId);
  const [error, setError] = useState('');
  const [sessionId, setSessionId] = useState(initialSessionId);

  const graphSrc = useMemo(() => {
    if (!sessionId) return '';
    return `/lucidity/graph.html?id=${encodeURIComponent(sessionId)}`;
  }, [sessionId]);

  useEffect(() => {
    if (initialSessionId) {
      setSessionId(initialSessionId);
      setLoading(false);
      setError('');
    }
  }, [initialSessionId]);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      if (!notebookId) {
        setError('Notebook ID is missing.');
        setLoading(false);
        return;
      }

      if (sessionId) {
        setLoading(false);
        return;
      }

      setLoading(true);
      setError('');

      try {
        const res = await fetch(`/api/from-notebook/${notebookId}`, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data?.detail || 'Failed to initialize Lucidity session.');
        }

        if (!cancelled) {
          setSessionId(data.session_id);
          setLoading(false);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e.message || 'Failed to initialize Lucidity session.');
          setLoading(false);
        }
      }
    }

    bootstrap();
    return () => { cancelled = true; };
  }, [notebookId, sessionId]);

  if (loading) {
    return (
      <div style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'var(--text-muted)',
        fontSize: 14,
      }}>
        Preparing Lucidity graph from notebook sources...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexDirection: 'column',
        gap: 10,
        color: 'var(--text-muted)',
        padding: 20,
        textAlign: 'center',
      }}>
        <div style={{ color: 'var(--danger)', fontWeight: 600 }}>Lucidity initialization failed</div>
        <div>{error}</div>
      </div>
    );
  }

  return (
    <iframe
      src={graphSrc}
      title="Lucidity Graph"
      style={{
        width: '100%',
        height: '100%',
        border: 'none',
        background: 'transparent',
      }}
      allow="clipboard-read; clipboard-write"
    />
  );
}
