import { useState, useRef, useEffect, useCallback } from 'react';

const API = '';  // relative — goes through Vite proxy

const BLOOM_ORDER = ['remember', 'understand', 'apply', 'analyze', 'evaluate', 'create'];
const BLOOM_LABELS = { remember: 'Remember', understand: 'Understand', apply: 'Apply', analyze: 'Analyze', evaluate: 'Evaluate', create: 'Create' };

const STATUS_STYLE = {
  UNKNOWN:    { bg: 'var(--bg-elevated)',        border: 'var(--border)',           dot: '#6b7280', label: '⚪ Unknown' },
  VISITED:    { bg: 'rgba(59,130,246,0.08)',     border: 'rgba(59,130,246,0.5)',    dot: '#3b82f6', label: '🔵 Visited' },
  CONFUSED:   { bg: 'rgba(239,68,68,0.08)',      border: 'rgba(239,68,68,0.55)',    dot: '#ef4444', label: '🔴 Confused' },
  UNDERSTOOD: { bg: 'rgba(234,179,8,0.08)',      border: 'rgba(234,179,8,0.55)',    dot: '#eab308', label: '🟡 Understood' },
  MASTERED:   { bg: 'rgba(39,169,108,0.09)',     border: 'rgba(39,169,108,0.55)',   dot: '#27a96c', label: '🟢 Mastered' },
};

const MODE_STYLE = {
  feynman:        { icon: '🧒', label: 'Feynman',          color: '#3b82f6' },
  socratic:       { icon: '🏛️', label: 'Socratic',          color: 'var(--accent)' },
  devil_advocate: { icon: '😈', label: "Devil's Advocate",  color: '#ef4444' },
};

/* ─── Bloom progress bar ───────────────────────────────────────────────────── */
function BloomBar({ reached, target }) {
  const ri = BLOOM_ORDER.indexOf(reached);
  const ti = BLOOM_ORDER.indexOf(target);
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
        <span>Bloom reached: <strong style={{ color: 'var(--text-primary)' }}>{BLOOM_LABELS[reached] || reached}</strong></span>
        <span>Target: <strong>{BLOOM_LABELS[target] || target}</strong></span>
      </div>
      <div style={{ display: 'flex', gap: 3 }}>
        {BLOOM_ORDER.map((level, i) => (
          <div key={level} title={BLOOM_LABELS[level]} style={{
            flex: 1, height: 6, borderRadius: 3,
            background: i <= ri ? (i >= ti ? 'var(--success)' : 'var(--accent)') : 'var(--bg-deep)',
            transition: 'background 0.3s',
          }} />
        ))}
      </div>
    </div>
  );
}

/* ─── Single concept node card ─────────────────────────────────────────────── */
function ConceptCard({ concept, onOpen, isActive }) {
  const st = STATUS_STYLE[concept.status] || STATUS_STYLE.UNKNOWN;
  const locked = concept.is_locked;
  const confused = concept.status === 'CONFUSED';

  return (
    <div
      onClick={() => !locked && onOpen(concept)}
      title={locked ? 'Complete prerequisite concepts first' : concept.name}
      style={{
        position: 'relative',
        background: st.bg,
        border: `1.5px solid ${st.border}`,
        borderRadius: 12,
        padding: '12px 16px',
        minWidth: 160, maxWidth: 220,
        cursor: locked ? 'not-allowed' : 'pointer',
        opacity: locked ? 0.45 : 1,
        transition: 'all 0.2s',
        boxShadow: isActive
          ? '0 0 0 3px rgba(99,102,241,0.35), 0 6px 20px rgba(0,0,0,0.35)'
          : confused
          ? '0 0 12px rgba(239,68,68,0.25)'
          : '0 2px 8px rgba(0,0,0,0.15)',
        animation: confused ? 'confusedPulse 2s ease-in-out infinite' : undefined,
      }}
      onMouseEnter={(e) => { if (!locked) e.currentTarget.style.transform = 'translateY(-2px)'; }}
      onMouseLeave={(e) => { e.currentTarget.style.transform = ''; }}
    >
      {/* Status dot */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: st.dot, flexShrink: 0 }} />
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.05em', color: st.dot, textTransform: 'uppercase' }}>
          {concept.status}
        </span>
        {locked && <span style={{ marginLeft: 'auto', fontSize: 12 }}>🔒</span>}
      </div>

      <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.3, marginBottom: 6 }}>
        {concept.name}
      </div>

      {/* Confidence bar */}
      <div style={{ height: 3, background: 'var(--bg-deep)', borderRadius: 99, overflow: 'hidden' }}>
        <div style={{
          height: '100%', borderRadius: 99,
          width: `${(concept.confidence_score || 0) * 100}%`,
          background: st.dot,
          transition: 'width 0.4s ease',
        }} />
      </div>

      {/* Bloom tag */}
      <div style={{ marginTop: 6, fontSize: 10, color: 'var(--text-muted)' }}>
        {BLOOM_LABELS[concept.bloom_level] || concept.bloom_level} target
      </div>
    </div>
  );
}

/* ─── SVG edges ────────────────────────────────────────────────────────────── */
function GraphEdges({ nodeRefs, edges, graphEl }) {
  const [lines, setLines] = useState([]);

  useEffect(() => {
    if (!graphEl) return;
    const newLines = [];
    edges.forEach((edge) => {
      const fromEl = nodeRefs.current[edge.from];
      const toEl   = nodeRefs.current[edge.to];
      if (!fromEl || !toEl) return;
      const containerRect = graphEl.getBoundingClientRect();
      const fr = fromEl.getBoundingClientRect();
      const tr = toEl.getBoundingClientRect();
      newLines.push({
        x1: fr.left + fr.width / 2 - containerRect.left,
        y1: fr.bottom - containerRect.top,
        x2: tr.left + tr.width / 2 - containerRect.left,
        y2: tr.top - containerRect.top,
        type: edge.edge_type,
        id: `${edge.from}-${edge.to}`,
      });
    });
    setLines(newLines);
  }, [edges, graphEl]);

  const edgeColor = (type) => {
    if (type === 'CONFUSED_WITH') return 'rgba(239,68,68,0.55)';
    if (type === 'RELATED_TO') return 'rgba(120,120,160,0.25)';
    return 'rgba(120,120,160,0.4)';
  };
  const edgeDash = (type) => type === 'RELATED_TO' ? '4,3' : type === 'CONFUSED_WITH' ? '6,3' : undefined;

  return (
    <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', overflow: 'visible' }}>
      <defs>
        <marker id="arrowPR" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L0,6 L6,3 z" fill="rgba(120,120,160,0.5)" /></marker>
        <marker id="arrowCW" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L0,6 L6,3 z" fill="rgba(239,68,68,0.6)" /></marker>
      </defs>
      {lines.map((l) => (
        <line key={l.id} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2}
          stroke={edgeColor(l.type)} strokeWidth={l.type === 'PREREQUISITE_OF' ? 1.5 : 1}
          strokeDasharray={edgeDash(l.type)}
          markerEnd={l.type === 'CONFUSED_WITH' ? 'url(#arrowCW)' : 'url(#arrowPR)'}
        />
      ))}
    </svg>
  );
}

/* ─── Main LucidityGraph component ────────────────────────────────────────── */
export default function LucidityGraph({ notebookId }) {
  const [graphState, setGraphState]   = useState(null);
  const [loading, setLoading]         = useState(false);
  const [building, setBuilding]       = useState(false);
  const [error, setError]             = useState(null);
  const [activeConceptId, setActiveCId] = useState(null);
  const [sessionId, setSessionId]     = useState(null);
  const nodeRefs  = useRef({});
  const graphElRef = useRef(null);

  const fetchGraph = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`/notebooks/${notebookId}/graph`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      if (data.concepts?.length > 0) setGraphState(data);
      else setGraphState(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [notebookId]);

  useEffect(() => { fetchGraph(); }, [fetchGraph]);

  const handleBuild = async () => {
    setBuilding(true);
    setError(null);
    try {
      const r = await fetch(`/notebooks/${notebookId}/build-graph`, { method: 'POST' });
      if (!r.ok) { const t = await r.text(); throw new Error(t); }
      const data = await r.json();
      setGraphState(data.graph);
      // Start session
      const sr = await fetch(`/notebooks/${notebookId}/start-session`, { method: 'POST' });
      if (sr.ok) { const sd = await sr.json(); setSessionId(sd.session_id); }
    } catch (e) {
      setError(e.message);
    } finally {
      setBuilding(false);
    }
  };

  const refreshGraph = useCallback(async () => {
    try {
      const r = await fetch(`/notebooks/${notebookId}/graph`);
      if (r.ok) setGraphState(await r.json());
    } catch { /* silent */ }
  }, [notebookId]);

  const activeConceptObj = graphState?.concepts?.find((c) => c.concept_id === activeConceptId) || null;

  // Group concepts by hierarchy
  const byLayer = { fundamental: [], intermediate: [], advanced: [] };
  (graphState?.concepts || []).forEach((c) => {
    const hl = c.hierarchy_level || 'intermediate';
    (byLayer[hl] || byLayer.intermediate).push(c);
  });

  const allEdges = (graphState?.edges || []).filter((e) =>
    e.edge_type === 'PREREQUISITE_OF' || e.edge_type === 'CONFUSED_WITH'
  );

  const totalNodes = graphState?.concepts?.length || 0;
  const masteredNodes = graphState?.concepts?.filter((c) => c.status === 'MASTERED').length || 0;
  const confusedNodes = graphState?.concepts?.filter((c) => c.status === 'CONFUSED').length || 0;

  return (
    <>
      <style>{`
        @keyframes confusedPulse {
          0%, 100% { box-shadow: 0 0 12px rgba(239,68,68,0.2); }
          50%       { box-shadow: 0 0 20px rgba(239,68,68,0.5); }
        }
        @keyframes slideInPanel {
          from { transform: translateX(40px); opacity: 0; }
          to   { transform: translateX(0);    opacity: 1; }
        }
      `}</style>

      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
        {/* ── Header ── */}
        <div style={{
          padding: '16px 22px', borderBottom: '1px solid var(--border)',
          background: 'var(--bg-surface)', flexShrink: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16,
        }}>
          <div>
            <h2 style={{ fontWeight: 700, fontSize: '1rem', marginBottom: 2 }}>🧠 Lucidity Graph</h2>
            <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Socratic AI co-pilot · never gives answers, only asks questions
            </p>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            {graphState && (
              <div style={{ display: 'flex', gap: 16, fontSize: 12, color: 'var(--text-muted)', alignItems: 'center' }}>
                <span>🟢 {masteredNodes}/{totalNodes} mastered</span>
                {confusedNodes > 0 && <span style={{ color: '#ef4444' }}>🔴 {confusedNodes} confused</span>}
              </div>
            )}
            <button
              className="btn btn-primary"
              onClick={handleBuild}
              disabled={building}
              style={{ fontSize: 13, padding: '7px 16px' }}
            >
              {building
                ? <><svg className="spin" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg> Analysing…</>
                : graphState ? '🔄 Rebuild Graph' : '🔬 Build Knowledge Graph'
              }
            </button>
          </div>
        </div>

        {/* ── Error ── */}
        {error && (
          <div style={{ padding: '10px 22px', background: 'rgba(239,68,68,0.07)', borderBottom: '1px solid rgba(239,68,68,0.2)', fontSize: 13, color: '#ef4444', flexShrink: 0 }}>
            ⚠️ {error}
          </div>
        )}

        {/* ── Body ── */}
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          {/* Graph canvas */}
          <div style={{ flex: 1, overflow: 'auto', padding: '20px 24px', position: 'relative' }}>
            {loading && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200, gap: 12, color: 'var(--text-muted)' }}>
                <svg className="spin" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
                Loading graph…
              </div>
            )}

            {!loading && !graphState && !building && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 300, gap: 16, textAlign: 'center', color: 'var(--text-muted)' }}>
                <div style={{ fontSize: '3rem' }}>🧠</div>
                <div style={{ fontWeight: 600, fontSize: 15, color: 'var(--text-primary)' }}>No knowledge graph yet</div>
                <p style={{ fontSize: 13, maxWidth: 340 }}>
                  Click <strong>Build Knowledge Graph</strong> to extract concepts from your uploaded sources and create a personalised Socratic learning journey.
                </p>
              </div>
            )}

            {building && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 300, gap: 16, color: 'var(--text-muted)' }}>
                <svg className="spin" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
                <p style={{ fontSize: 14 }}>Extracting concepts from your sources…<br /><span style={{ fontSize: 12 }}>This may take 30-60 seconds.</span></p>
              </div>
            )}

            {graphState && !building && (
              <>
                {/* Legend */}
                <div style={{ display: 'flex', gap: 14, marginBottom: 20, flexWrap: 'wrap' }}>
                  {Object.entries(STATUS_STYLE).map(([s, st]) => (
                    <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)' }}>
                      <div style={{ width: 8, height: 8, borderRadius: '50%', background: st.dot }} />
                      {s}
                    </div>
                  ))}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)' }}>
                    <div style={{ width: 18, height: 1, background: 'rgba(120,120,160,0.5)', borderTop: '1px dashed rgba(120,120,160,0.5)' }} />
                    Edge
                  </div>
                </div>

                {/* Graph */}
                <div
                  ref={graphElRef}
                  style={{ position: 'relative', minHeight: 300 }}
                >
                  <GraphEdges nodeRefs={nodeRefs} edges={allEdges} graphEl={graphElRef.current} />

                  {['fundamental', 'intermediate', 'advanced'].map((layer) => {
                    const nodes = byLayer[layer];
                    if (!nodes.length) return null;
                    return (
                      <div key={layer} style={{ marginBottom: 52 }}>
                        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 14 }}>
                          {layer === 'fundamental' ? '⬤ Fundamentals'
                            : layer === 'intermediate' ? '◎ Intermediate'
                            : '◇ Advanced'}
                        </div>
                        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
                          {nodes.map((c) => (
                            <div key={c.concept_id} ref={(el) => { nodeRefs.current[c.concept_id] = el; }}>
                              <ConceptCard
                                concept={c}
                                isActive={c.concept_id === activeConceptId}
                                onOpen={(concept) => setActiveCId(concept.concept_id)}
                              />
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}

                  {masteredNodes === totalNodes && totalNodes > 0 && (
                    <div style={{ marginTop: 20, padding: '20px 24px', background: 'rgba(39,169,108,0.09)', border: '1px solid rgba(39,169,108,0.35)', borderRadius: 12, textAlign: 'center', fontWeight: 700, color: 'var(--success)' }}>
                      🏆 All concepts mastered! Extraordinary work.
                    </div>
                  )}
                </div>
              </>
            )}
          </div>

          {/* Right panel */}
          {activeConceptId && activeConceptObj && (
            <SocraticSidePanel
              concept={activeConceptObj}
              notebookId={notebookId}
              sessionId={sessionId}
              onClose={() => setActiveCId(null)}
              onUpdated={refreshGraph}
            />
          )}
        </div>
      </div>
    </>
  );
}

/* ─── Socratic side panel ──────────────────────────────────────────────────── */
function SocraticSidePanel({ concept, notebookId, sessionId, onClose, onUpdated }) {
  const [history, setHistory]       = useState([]);
  const [input, setInput]           = useState('');
  const [streaming, setStreaming]   = useState(false);
  const [scoring, setScoring]       = useState(false);
  const [scoreResult, setScoreResult] = useState(null);
  const [mode, setMode]             = useState('');    // '' = auto
  const [error, setError]           = useState(null);
  const chatEndRef = useRef(null);
  const abortRef   = useRef(null);

  // Reset on concept change
  useEffect(() => {
    setHistory([]);
    setInput('');
    setScoreResult(null);
    setError(null);
    setMode('');
  }, [concept.concept_id]);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [history]);

  const currentMode = mode || (
    concept.bloom_reached && BLOOM_ORDER.indexOf(concept.bloom_reached) <= 1 ? 'feynman'
    : BLOOM_ORDER.indexOf(concept.bloom_reached) <= 3 ? 'socratic'
    : 'devil_advocate'
  );

  const handleSend = async () => {
    if (!input.trim() || streaming) return;
    const userMsg = { role: 'user', content: input.trim() };
    setHistory((h) => [...h, userMsg]);
    setInput('');
    setStreaming(true);
    setError(null);

    let aiText = '';
    setHistory((h) => [...h, { role: 'assistant', content: '' }]);

    try {
      abortRef.current = new AbortController();
      const resp = await fetch(`/notebooks/${notebookId}/socratic-chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          concept_id: concept.concept_id,
          message: userMsg.content,
          history: history.slice(-10),
          session_id: sessionId || '',
          mode,
        }),
        signal: abortRef.current.signal,
      });

      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = dec.decode(value);
        chunk.split('\n').forEach((line) => {
          if (line.startsWith('data: ') && line !== 'data: [DONE]') {
            aiText += line.slice(6);
            setHistory((h) => {
              const next = [...h];
              next[next.length - 1] = { role: 'assistant', content: aiText };
              return next;
            });
          }
        });
      }
    } catch (e) {
      if (e.name !== 'AbortError') setError(e.message);
    } finally {
      setStreaming(false);
    }
  };

  const handleScore = async () => {
    // Collect all student messages as a combined response
    const studentText = history
      .filter((m) => m.role === 'user')
      .map((m) => m.content)
      .join('\n\n');
    if (!studentText.trim()) {
      setError('Have a conversation first, then score your understanding.');
      return;
    }
    setScoring(true);
    setError(null);
    try {
      const r = await fetch(`/notebooks/${notebookId}/score-response`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          concept_id: concept.concept_id,
          student_response: studentText,
          session_id: sessionId || '',
        }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setScoreResult(data);
      onUpdated();
    } catch (e) {
      setError(e.message);
    } finally {
      setScoring(false);
    }
  };

  const st = STATUS_STYLE[concept.status] || STATUS_STYLE.UNKNOWN;
  const modeInfo = MODE_STYLE[currentMode] || MODE_STYLE.socratic;

  return (
    <div style={{
      width: 420, flexShrink: 0,
      borderLeft: '1px solid var(--border)',
      background: 'var(--bg-surface)',
      display: 'flex', flexDirection: 'column',
      animation: 'slideInPanel 0.2s ease-out',
      overflow: 'hidden',
    }}>
      {/* Panel header */}
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8, flexShrink: 0,
            background: st.bg, border: `1.5px solid ${st.border}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14,
          }}>
            {modeInfo.icon}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: '0.9rem', marginBottom: 1 }}>{concept.name}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{st.label}</div>
          </div>
          <button onClick={onClose} style={{
            background: 'var(--bg-elevated)', border: '1px solid var(--border)',
            borderRadius: 5, padding: '3px 9px', fontSize: 16, cursor: 'pointer', color: 'var(--text-secondary)',
          }}>×</button>
        </div>

        {/* Description */}
        {concept.description && (
          <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 10 }}>
            {concept.description}
          </p>
        )}

        {/* Bloom bar */}
        <BloomBar reached={concept.bloom_reached || 'remember'} target={concept.bloom_level || 'understand'} />

        {/* Mode selector */}
        <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
          {Object.entries(MODE_STYLE).map(([m, info]) => (
            <button key={m} onClick={() => setMode(mode === m ? '' : m)} style={{
              flex: 1, padding: '5px 0',
              background: currentMode === m ? 'var(--accent-dim)' : 'var(--bg-elevated)',
              border: `1px solid ${currentMode === m ? 'var(--accent)' : 'var(--border)'}`,
              borderRadius: 6, fontSize: 11, cursor: 'pointer',
              color: currentMode === m ? 'var(--accent)' : 'var(--text-muted)',
              fontWeight: currentMode === m ? 700 : 400,
            }} title={info.label}>
              {info.icon} {info.label.split("'")[0].trim()}
            </button>
          ))}
        </div>
      </div>

      {/* Chat thread */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {history.length === 0 && (
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 13, padding: '24px 0' }}>
            <div style={{ fontSize: '2rem', marginBottom: 8 }}>{modeInfo.icon}</div>
            <p><strong style={{ color: 'var(--text-primary)' }}>{modeInfo.label} Mode</strong></p>
            <p style={{ marginTop: 4, fontSize: 12 }}>
              {currentMode === 'feynman'
                ? "Explain the concept to me like I'm 8 years old. Go!"
                : currentMode === 'devil_advocate'
                ? "I'll make a wrong claim — your job is to catch and correct me."
                : "Ask me anything or tell me what you understand. I'll guide you."}
            </p>
          </div>
        )}

        {history.map((msg, i) => (
          <div key={i} style={{
            alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
            maxWidth: '88%',
          }}>
            <div style={{
              background: msg.role === 'user' ? 'var(--accent)' : 'var(--bg-elevated)',
              color: msg.role === 'user' ? '#fff' : 'var(--text-primary)',
              borderRadius: msg.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
              padding: '9px 13px', fontSize: 13, lineHeight: 1.55,
              border: msg.role === 'user' ? 'none' : '1px solid var(--border)',
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            }}>
              {msg.content || (streaming && i === history.length - 1 ? '▌' : '')}
            </div>
          </div>
        ))}

        {/* Score result */}
        {scoreResult && (
          <div style={{
            background: scoreResult.score >= 0.7 ? 'rgba(39,169,108,0.08)' : 'rgba(234,179,8,0.08)',
            border: `1px solid ${scoreResult.score >= 0.7 ? 'rgba(39,169,108,0.3)' : 'rgba(234,179,8,0.3)'}`,
            borderRadius: 10, padding: '14px 16px',
          }}>
            <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 6 }}>
              {scoreResult.score >= 0.85 ? '🌟' : scoreResult.score >= 0.6 ? '⭐' : '📚'} Score: {Math.round((scoreResult.score || 0) * 100)}%
              <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--text-muted)', marginLeft: 8 }}>
                Bloom: {BLOOM_LABELS[scoreResult.bloom_demonstrated] || scoreResult.bloom_demonstrated}
              </span>
            </div>
            {scoreResult.feedback_hint && (
              <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>
                💡 {scoreResult.feedback_hint}
              </p>
            )}
            {scoreResult.misconceptions_detected?.length > 0 && (
              <div style={{ fontSize: 11, color: '#ef4444' }}>
                ⚠️ Misconceptions detected: {scoreResult.misconceptions_detected.join('; ')}
              </div>
            )}
          </div>
        )}

        {error && (
          <div style={{ fontSize: 12, color: '#ef4444', padding: '6px 10px', background: 'rgba(239,68,68,0.07)', borderRadius: 6 }}>
            ⚠️ {error}
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Input area */}
      <div style={{ padding: '12px 14px', borderTop: '1px solid var(--border)', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            placeholder="Type your answer or explanation… (Enter to send)"
            rows={2}
            disabled={streaming}
            style={{
              flex: 1, background: 'var(--bg-deep)', border: '1px solid var(--border)',
              borderRadius: 8, padding: '8px 12px', fontSize: 13, color: 'var(--text-primary)',
              resize: 'none', outline: 'none', lineHeight: 1.5,
            }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || streaming}
            className="btn btn-primary"
            style={{ alignSelf: 'flex-end', padding: '8px 14px', fontSize: 13 }}
          >
            {streaming
              ? <svg className="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
              : '→'
            }
          </button>
        </div>
        <button
          onClick={handleScore}
          disabled={scoring || streaming || history.length === 0}
          style={{
            width: '100%', padding: '7px', fontSize: 12,
            background: 'var(--bg-elevated)', border: '1px solid var(--border)',
            borderRadius: 7, cursor: 'pointer', color: 'var(--text-secondary)',
          }}
        >
          {scoring
            ? <><svg className="spin" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg> Scoring…</>
            : '📊 Score my understanding & update graph'
          }
        </button>
      </div>
    </div>
  );
}
