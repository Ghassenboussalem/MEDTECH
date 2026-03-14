import { useState, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import useNotebookStore from '../store/useNotebookStore';
import LearningGraphView from './LearningGraphView';
import LucidityGraph from './LucidityGraph';

/* ─── Config ─────────────────────────────────────────────────────── */
const TYPES = [
  { id: 'summary',        label: 'Summary',         icon: '📋', desc: 'Concise overview of all sources' },
  { id: 'faq',            label: 'FAQ',              icon: '❓', desc: 'Q&A list extracted from sources' },
  { id: 'study_guide',    label: 'Study Guide',      icon: '📖', desc: 'Key concepts & definitions' },
  { id: 'quiz',           label: 'Quiz',             icon: '🧠', desc: 'Interactive multiple-choice quiz' },
  { id: 'mind_map',       label: 'Mind Map',         icon: '🗺️', desc: 'Hierarchical tree diagram of topics' },
  { id: 'learning_graph', label: 'Learning Graph',   icon: '🧩', desc: 'AI-validated graph-based lesson journey' },
  { id: 'lucidity_graph', label: 'Lucidity Graph',   icon: '🧠', desc: 'Socratic AI co-pilot — never gives answers', special: true },
];

/* ─── Interactive Quiz ───────────────────────────────────────────── */
function QuizView({ raw }) {
  const [answers, setAnswers] = useState({});  // { qIdx: optionIdx }
  const [revealed, setRevealed] = useState({});
  const [score, setScore] = useState(null);

  let questions = [];
  try {
    // Strip markdown fences if the LLM wrapped it
    const clean = raw.replace(/```json\n?|\n?```/g, '').trim();
    questions = JSON.parse(clean);
  } catch {
    return (
      <div style={{ padding: 20, color: 'var(--danger)', fontSize: 14 }}>
        ⚠️ Could not parse quiz. Try regenerating.
        <pre style={{ marginTop: 8, fontSize: 12, overflowX: 'auto', color: 'var(--text-muted)' }}>{raw}</pre>
      </div>
    );
  }

  const pick = (qi, oi) => {
    if (revealed[qi] !== undefined) return;
    setAnswers((a) => ({ ...a, [qi]: oi }));
  };

  const reveal = (qi) => {
    if (answers[qi] === undefined) return;
    setRevealed((r) => ({ ...r, [qi]: true }));
  };

  const submitAll = () => {
    const r = {};
    questions.forEach((_, i) => { if (answers[i] !== undefined) r[i] = true; });
    setRevealed(r);
    const correct = questions.filter((q, i) => answers[i] === q.answer).length;
    setScore(correct);
  };

  const reset = () => { setAnswers({}); setRevealed({}); setScore(null); };

  const allAnswered = questions.length > 0 && questions.every((_, i) => answers[i] !== undefined);

  return (
    <div>
      {score !== null && (
        <div style={{
          background: score >= questions.length * 0.7 ? 'rgba(39,169,108,0.1)' : 'rgba(214,59,78,0.08)',
          border: `1px solid ${score >= questions.length * 0.7 ? 'rgba(39,169,108,0.3)' : 'rgba(214,59,78,0.25)'}`,
          borderRadius: 'var(--radius-md)',
          padding: '16px 20px',
          marginBottom: 20,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: '1.1rem' }}>
              {score >= questions.length * 0.7 ? '🎉' : '📚'} {score}/{questions.length} correct
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
              {score >= questions.length * 0.7 ? 'Great job!' : 'Keep studying — review the explanations below.'}
            </div>
          </div>
          <button className="btn btn-ghost" onClick={reset} style={{ fontSize: 13 }}>Retry</button>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {questions.map((q, qi) => (
          <div key={qi} style={{
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            padding: '18px 20px',
            boxShadow: 'var(--shadow-card)',
          }}>
            <p style={{ fontWeight: 600, fontSize: 14, marginBottom: 12 }}>
              <span style={{
                display: 'inline-block', marginRight: 8,
                background: 'var(--accent-dim)', color: 'var(--accent)',
                borderRadius: 4, padding: '1px 7px', fontSize: 12, fontWeight: 700,
              }}>Q{qi + 1}</span>
              {q.question}
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {q.options.map((opt, oi) => {
                const isChosen = answers[qi] === oi;
                const isCorrect = q.answer === oi;
                const isRevealed = revealed[qi];

                let bg = 'var(--bg-elevated)';
                let border = 'var(--border)';
                let textColor = 'var(--text-primary)';

                if (isRevealed) {
                  if (isCorrect) { bg = 'rgba(39,169,108,0.12)'; border = 'rgba(39,169,108,0.4)'; textColor = 'var(--success)'; }
                  else if (isChosen && !isCorrect) { bg = 'rgba(214,59,78,0.08)'; border = 'rgba(214,59,78,0.3)'; textColor = 'var(--danger)'; }
                } else if (isChosen) {
                  bg = 'var(--accent-dim)'; border = 'var(--border-active)'; textColor = 'var(--accent)';
                }

                return (
                  <button key={oi} onClick={() => pick(qi, oi)} style={{
                    background: bg, border: `1px solid ${border}`,
                    borderRadius: 8, padding: '10px 14px',
                    textAlign: 'left', fontSize: 14, color: textColor,
                    cursor: isRevealed ? 'default' : 'pointer',
                    transition: 'all var(--transition)',
                    display: 'flex', alignItems: 'center', gap: 10,
                    fontWeight: isRevealed && isCorrect ? 600 : 400,
                  }}>
                    <span style={{
                      width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
                      background: isChosen || (isRevealed && isCorrect) ? (isRevealed && isCorrect ? 'var(--success)' : 'var(--accent)') : 'var(--border)',
                      color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 11, fontWeight: 700,
                      transition: 'all var(--transition)',
                    }}>
                      {isRevealed && isCorrect ? '✓' : isRevealed && isChosen && !isCorrect ? '✗' : String.fromCharCode(65 + oi)}
                    </span>
                    {opt.replace(/^[A-D]\.\s*/, '')}
                  </button>
                );
              })}
            </div>

            {/* Per-question reveal/explanation */}
            {!revealed[qi] && answers[qi] !== undefined && score === null && (
              <button className="btn btn-ghost" onClick={() => reveal(qi)}
                style={{ marginTop: 10, fontSize: 12, padding: '4px 10px' }}>
                Check answer
              </button>
            )}
            {revealed[qi] && q.explanation && (
              <div style={{
                marginTop: 12, padding: '10px 14px',
                background: 'var(--bg-deep)', borderRadius: 8,
                fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6,
                borderLeft: '3px solid var(--accent)',
              }}>
                💡 {q.explanation}
              </div>
            )}
          </div>
        ))}
      </div>

      {allAnswered && score === null && (
        <div style={{ marginTop: 20, textAlign: 'center' }}>
          <button className="btn btn-primary" onClick={submitAll}>
            Submit & See Score
          </button>
        </div>
      )}
    </div>
  );
}

/* ─── Mind Map ───────────────────────────────────────────────────── */
function MindMapNode({ node, depth = 0, isLast = true }) {
  if (!node) return null;
  const [expanded, setExpanded] = useState(depth < 2); // Auto-expand first 2 levels
  const hasChildren = node.children && node.children.length > 0;

  return (
    <div style={{ 
      marginLeft: depth === 0 ? 0 : 28,
      position: 'relative',
      marginTop: depth === 0 ? 0 : 12
    }}>
      {/* Tree drawing lines */}
      {depth > 0 && (
        <>
          {/* Horizontal line to node */}
          <div style={{ position: 'absolute', left: -20, top: 16, width: 16, height: 2, background: 'var(--border)' }} />
          {/* Vertical line connecting to parent */}
          <div style={{ position: 'absolute', left: -20, top: -12, width: 2, height: 28, background: 'var(--border)' }} />
          {/* If there are more siblings, continue vertical line down */}
          {!isLast && (
            <div style={{ position: 'absolute', left: -20, top: 16, width: 2, height: '100%', background: 'var(--border)' }} />
          )}
        </>
      )}

      {/* The Node Card */}
      <div 
        onClick={() => hasChildren && setExpanded(!expanded)}
        style={{
          display: 'inline-flex', flexDirection: 'column',
          background: depth === 0 ? 'var(--accent)' : 'var(--bg-elevated)',
          color: depth === 0 ? '#fff' : 'var(--text-primary)',
          border: `1px solid ${depth === 0 ? 'var(--accent)' : 'var(--border)'}`,
          borderRadius: 'var(--radius-sm)',
          padding: '12px 16px',
          boxShadow: depth === 0 ? 'var(--shadow-glow)' : '0 1px 3px rgba(0,0,0,0.02)',
          cursor: hasChildren ? 'pointer' : 'default',
          transition: 'all 0.2s',
          minWidth: 200, maxWidth: 600,
          userSelect: 'none',
        }}
        onMouseEnter={(e) => { if(hasChildren && depth > 0) e.currentTarget.style.borderColor = 'var(--border-active)' }}
        onMouseLeave={(e) => { if(hasChildren && depth > 0) e.currentTarget.style.borderColor = 'var(--border)' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <span style={{ fontSize: depth === 0 ? 16 : 14, fontWeight: depth === 0 ? 600 : 500 }}>
            {node.label}
          </span>
          {hasChildren && (
            <span style={{ 
              fontSize: 16, opacity: 0.6, width: 16, textAlign: 'center', 
              transform: expanded ? 'rotate(90deg)' : 'none', transition: 'transform 0.2s'
            }}>
              ›
            </span>
          )}
        </div>
        
        {node.description && (
          <div style={{ 
            marginTop: 8, fontSize: 13, lineHeight: 1.5, 
            color: depth === 0 ? 'rgba(255,255,255,0.85)' : 'var(--text-secondary)'
          }}>
            {node.description}
          </div>
        )}
      </div>

      {/* Children */}
      {hasChildren && expanded && (
        <div style={{ position: 'relative' }}>
          {/* Vertical line running down the left of all children */}
          <div style={{ position: 'absolute', left: 8, top: 0, width: 2, height: 'calc(100% - 20px)', background: 'var(--border)' }} />
          
          {node.children.map((child, i) => (
            <MindMapNode 
              key={i} 
              node={child} 
              depth={depth + 1} 
              isLast={i === node.children.length - 1} 
            />
          ))}
        </div>
      )}
    </div>
  );
}

function MindMapView({ raw }) {
  let root = null;
  
  const attemptParse = (str) => {
    try { return JSON.parse(str); } catch { return null; }
  };

  const clean = raw.replace(/```json\n?|\n?```/g, '').trim();
  root = attemptParse(clean);

  if (!root) {
    // Aggressive fixes: remove trailing commas, balance brackets
    let fixed = clean.replace(/,\s*([\]}])/g, '$1');
    root = attemptParse(fixed);
    
    if (!root) {
      // Often the LLM cuts off the end. Try appending common closures.
      root = attemptParse(fixed + ']}') || attemptParse(fixed + ']}]}') || attemptParse(fixed + '}');
    }
  }

  if (!root) {
    return (
      <div style={{ padding: 20, color: 'var(--danger)', fontSize: 14 }}>
        ⚠️ Could not parse mind map (invalid JSON from AI). Try regenerating.
        <pre style={{ marginTop: 8, fontSize: 12, overflowX: 'auto', color: 'var(--text-muted)' }}>{raw}</pre>
      </div>
    );
  }

  return (
    <div style={{
      background: 'var(--bg-surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)',
      padding: '24px',
      overflowX: 'auto',
      boxShadow: 'var(--shadow-card)',
    }}>
      <MindMapNode node={root} />
    </div>
  );
}

/* ─── Markdown result ────────────────────────────────────────────── */
function MarkdownResult({ content }) {
  return (
    <div style={{
      background: 'var(--bg-surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)',
      padding: '20px 24px',
      boxShadow: 'var(--shadow-card)',
    }}>
      <div className="prose">
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
    </div>
  );
}

/* ─── Main Generate Panel ────────────────────────────────────────── */
export default function GeneratePanel({ notebookId }) {
  const { generateArtifact } = useNotebookStore();

  // Cache: { summary: '...', faq: '...', study_guide: '...', quiz: '...' }
  const cache = useRef({});
  const [active, setActive] = useState(null);       // currently selected tab
  const [loading, setLoading] = useState(null);
  const [error, setError]   = useState(null);
  const [tick, setTick]     = useState(0);          // force re-render when cache updates

  const generate = async (type, force = false) => {
    setActive(type);
    setError(null);

    // Lucidity Graph manages its own state — no artifact API needed
    if (type === 'lucidity_graph') return;

    // Use cached result if available and not force-regenerating
    if (cache.current[type] && !force) return;

    setLoading(type);
    try {
      const data = await generateArtifact(notebookId, type);
      cache.current[type] = data.content;
      setTick((t) => t + 1);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(null);
    }
  };

  const current = active ? cache.current[active] : null;
  const isLoading = loading === active;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* ── Tab bar ──────────────────────────────────────────────── */}
      <div style={{
        padding: '0 24px',
        borderBottom: '1px solid var(--border)',
        background: 'var(--bg-surface)',
        display: 'flex', gap: 0, flexShrink: 0,
      }}>
        {TYPES.map((t) => {
          const isCached = !!cache.current[t.id];
          const isActive = active === t.id;
          return (
            <button key={t.id}
              onClick={() => generate(t.id)}
              disabled={loading === t.id}
              style={{
                padding: '14px 18px',
                fontSize: 13, fontWeight: 500,
                color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                borderBottom: `2px solid ${isActive ? 'var(--accent)' : 'transparent'}`,
                transition: 'all var(--transition)',
                display: 'flex', alignItems: 'center', gap: 6,
                whiteSpace: 'nowrap',
              }}
              onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.color = 'var(--text-primary)'; }}
              onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.color = 'var(--text-secondary)'; }}
            >
              {t.icon} {t.label}
              {isCached && (
                <span style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: 'var(--success)', display: 'inline-block',
                }} title="Cached" />
              )}
              {loading === t.id && (
                <svg className="spin" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.5">
                  <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                </svg>
              )}
            </button>
          );
        })}
      </div>

      {/* ── Content area ─────────────────────────────────────────── */}
      <div className="overflow-y-auto" style={{ flex: 1, padding: active === 'lucidity_graph' ? 0 : '20px 24px', overflow: active === 'lucidity_graph' ? 'hidden' : undefined, display: 'flex', flexDirection: 'column' }}>
        {/* ── Lucidity Graph (self-contained, full height) ── */}
        {active === 'lucidity_graph' && (
          <LucidityGraph notebookId={notebookId} />
        )}

        {active !== 'lucidity_graph' && !active && (
          <div style={{
            height: '100%', display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', gap: 16,
            color: 'var(--text-muted)', textAlign: 'center',
          }}>
            <div style={{ fontSize: '2.5rem' }}>✨</div>
            <p style={{ fontWeight: 500 }}>Pick a generation type above</p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, maxWidth: 380 }}>
              {TYPES.map((t) => (
                <button key={t.id} onClick={() => generate(t.id)}
                  className="card" style={{ padding: '14px 16px', textAlign: 'left', cursor: 'pointer' }}>
                  <div style={{ fontSize: '1.4rem', marginBottom: 6 }}>{t.icon}</div>
                  <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>{t.label}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>{t.desc}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        {active !== 'lucidity_graph' && active && isLoading && (
          <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-muted)' }}>
            <svg className="spin" style={{ margin: '0 auto 12px' }} width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2">
              <path d="M21 12a9 9 0 1 1-6.219-8.56" />
            </svg>
            <p style={{ fontSize: 13 }}>Generating from your sources… this may take ~30s</p>
          </div>
        )}

        {active !== 'lucidity_graph' && active && error && !isLoading && (
          <div style={{
            background: 'rgba(214,59,78,0.06)', border: '1px solid rgba(214,59,78,0.2)',
            borderRadius: 'var(--radius-md)', padding: '14px 18px', fontSize: 13, color: 'var(--danger)',
          }}>
            ⚠️ {error}
            <button className="btn btn-ghost" onClick={() => generate(active, true)}
              style={{ marginLeft: 12, fontSize: 12, padding: '3px 10px' }}>
              Retry
            </button>
          </div>
        )}

        {active !== 'lucidity_graph' && active && current && !isLoading && (
          <>
            {/* Regenerate button */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: '1.1rem' }}>{TYPES.find((t) => t.id === active)?.icon}</span>
                <span style={{ fontWeight: 600, fontSize: 15 }}>{TYPES.find((t) => t.id === active)?.label}</span>
                <span className="badge badge-success">Cached</span>
              </div>
              <button className="btn btn-ghost" onClick={() => generate(active, true)}
                style={{ fontSize: 12, padding: '5px 12px', gap: 5 }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                  <path d="M23 4v6h-6" /><path d="M1 20v-6h6" />
                  <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
                </svg>
                Regenerate
              </button>
            </div>

            {active === 'quiz'
              ? <QuizView raw={current} />
              : active === 'mind_map'
              ? <MindMapView raw={current} />
              : active === 'learning_graph'
              ? <LearningGraphView raw={current} notebookId={notebookId} />
              : <MarkdownResult content={current} />
            }
          </>
        )}
      </div>
    </div>
  );
}
