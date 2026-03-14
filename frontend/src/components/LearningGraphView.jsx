import { useState, useCallback, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';

/* ─── Helpers ──────────────────────────────────────────────────────────────── */
function parseSafe(raw) {
  const clean = raw.replace(/```json\n?|\n?```/g, '').trim();
  try { return JSON.parse(clean); } catch { /* ignore */ }
  const fixed = clean.replace(/,\s*([\]}])/g, '$1');
  try { return JSON.parse(fixed); } catch { return null; }
}

function buildNodeMap(nodes) {
  const map = {};
  nodes.forEach((n) => { map[n.id] = n; });
  return map;
}

function groupByLayer(nodes) {
  const layers = {};
  nodes.forEach((n) => {
    if (!layers[n.layer]) layers[n.layer] = [];
    layers[n.layer].push(n);
  });
  return layers;
}

/* ─── Colours ──────────────────────────────────────────────────────────────── */
const COLOR = {
  unlocked: { bg: '#1e1e2e', border: 'var(--accent)',           text: 'var(--accent)' },
  passed:   { bg: 'rgba(39,169,108,0.08)', border: 'rgba(39,169,108,0.55)', text: 'var(--success)' },
  visible:  { bg: 'var(--bg-elevated)',    border: 'var(--border)',          text: 'var(--text-muted)' },
};

/* ─── Question input row ───────────────────────────────────────────────────── */
function QuestionRow({ idx, question, value, onChange, result, submitted }) {
  let borderColor = 'var(--border)';
  if (submitted && result === true)  borderColor = 'var(--success)';
  if (submitted && result === false) borderColor = 'rgba(214,59,78,0.6)';

  return (
    <div style={{ marginBottom: 18 }}>
      <p style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, color: 'var(--text-primary)' }}>
        <span style={{
          display: 'inline-block', marginRight: 8,
          background: 'var(--accent-dim)', color: 'var(--accent)',
          borderRadius: 4, padding: '1px 7px', fontSize: 11, fontWeight: 700,
        }}>Q{idx + 1}</span>
        {question.q}
      </p>
      <div style={{ position: 'relative' }}>
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={submitted && result === true}
          placeholder="Type your answer here…"
          rows={3}
          style={{
            width: '100%', boxSizing: 'border-box',
            background: 'var(--bg-deep)', border: `1px solid ${borderColor}`,
            borderRadius: 8, padding: '10px 12px',
            fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.6,
            resize: 'vertical', outline: 'none',
            transition: 'border-color 0.2s',
          }}
        />
        {submitted && (
          <span style={{ position: 'absolute', top: 8, right: 10, fontSize: 16 }}>
            {result ? '✅' : '❌'}
          </span>
        )}
      </div>
      {submitted && result === false && (
        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 6, paddingLeft: 4 }}>
          💡 Hint: <em>{question.answer}</em>
        </p>
      )}
    </div>
  );
}

/* ─── Node lesson panel (right drawer) ────────────────────────────────────── */
function NodePanel({ node, passed, onClose, onPassed, notebookId }) {
  const qCount = node?.questions?.length ?? 0;

  // Dynamically size answer array to match actual question count
  const [answers, setAnswers]  = useState(() => Array(qCount).fill(''));
  const [results, setResults]  = useState(null);  // bool[] | null
  const [loading, setLoading]  = useState(false);
  const [error, setError]      = useState(null);
  const [retryKey, setRetryKey] = useState(0);

  // Reset when node changes
  useEffect(() => {
    setAnswers(Array(node?.questions?.length ?? 0).fill(''));
    setResults(null);
    setError(null);
  }, [node?.id]);

  if (!node) return null;

  const questions = node.questions || [];
  const allFilled = answers.length > 0 && answers.every((a) => a.trim().length > 0);
  const allPassed = results && results.every(Boolean);
  const someFailed = results && !results.every(Boolean);

  const setAnswer = (i, v) =>
    setAnswers((prev) => { const next = [...prev]; next[i] = v; return next; });

  const handleSubmit = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`/notebooks/${notebookId}/validate-node`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          node_id: node.id,
          node_label: node.label,
          node_content: node.content,
          questions: questions.map((q, i) => ({
            q: q.q,
            expected_answer: q.answer,
            user_answer: answers[i] ?? '',
          })),
        }),
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(`Server error ${resp.status}: ${text}`);
      }
      const data = await resp.json();
      setResults(data.results);
      if (data.passed) setTimeout(() => onPassed(node.id), 700);
    } catch (e) {
      setError(e.message || 'Validation failed — check the backend is running.');
      console.error('[LearningGraph] validate-node error:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleRetry = () => {
    // Keep correct answers, clear wrong ones
    setAnswers((prev) => prev.map((a, i) => (results && results[i] ? a : '')));
    setResults(null);
    setError(null);
    setRetryKey((k) => k + 1);
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      display: 'flex', alignItems: 'stretch',
    }}>
      {/* Backdrop */}
      <div onClick={onClose} style={{ flex: 1, background: 'rgba(0,0,0,0.55)', cursor: 'pointer' }} />

      {/* Slide-in panel */}
      <div style={{
        width: 520, maxWidth: '90vw',
        background: 'var(--bg-surface)',
        borderLeft: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column',
        overflowY: 'auto',
        animation: 'slideInRight 0.25s ease-out',
      }}>
        {/* Header */}
        <div style={{
          padding: '20px 24px 16px', borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'flex-start', gap: 12, flexShrink: 0,
        }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10, flexShrink: 0,
            background: passed ? 'rgba(39,169,108,0.15)' : 'var(--accent-dim)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18,
          }}>
            {passed ? '✅' : '📖'}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 style={{ fontWeight: 700, fontSize: '1rem', marginBottom: 2 }}>{node.label}</h2>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {passed ? 'Completed — read only' : `Layer ${node.layer}`}
            </span>
          </div>
          <button onClick={onClose} style={{
            background: 'var(--bg-elevated)', border: '1px solid var(--border)',
            borderRadius: 6, padding: '4px 10px', fontSize: 18, lineHeight: 1,
            color: 'var(--text-secondary)', cursor: 'pointer',
          }}>×</button>
        </div>

        {/* Lesson content */}
        <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8 }} className="prose">
            <ReactMarkdown>{node.content}</ReactMarkdown>
          </div>
        </div>

        {/* Quiz or completed */}
        <div style={{ padding: '20px 24px', flex: 1 }}>
          {passed ? (
            <div style={{
              background: 'rgba(39,169,108,0.08)', border: '1px solid rgba(39,169,108,0.3)',
              borderRadius: 10, padding: '14px 18px', textAlign: 'center',
              color: 'var(--success)', fontWeight: 600,
            }}>
              🎉 You already passed this node!
            </div>
          ) : (
            <>
              <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 16 }}>
                ✏️ Answer {questions.length > 0 ? `all ${questions.length}` : 'the'} questions to unlock next nodes
              </h3>

              {questions.length === 0 && (
                <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
                  No questions found for this node. Try regenerating the graph.
                </div>
              )}

              {questions.map((q, i) => (
                <QuestionRow
                  key={`${node.id}-${retryKey}-${i}`}
                  idx={i}
                  question={q}
                  value={answers[i] ?? ''}
                  onChange={(v) => setAnswer(i, v)}
                  result={results ? results[i] : null}
                  submitted={results !== null}
                />
              ))}

              {error && (
                <div style={{
                  background: 'rgba(214,59,78,0.07)', border: '1px solid rgba(214,59,78,0.25)',
                  borderRadius: 8, padding: '10px 14px', fontSize: 13,
                  color: 'var(--danger)', marginBottom: 14,
                }}>
                  ⚠️ {error}
                </div>
              )}

              {allPassed && (
                <div style={{
                  background: 'rgba(39,169,108,0.08)', border: '1px solid rgba(39,169,108,0.3)',
                  borderRadius: 10, padding: '14px 18px', textAlign: 'center',
                  color: 'var(--success)', fontWeight: 600, marginBottom: 16,
                }}>
                  🎉 All correct! Adjacent nodes are now unlocked.
                </div>
              )}

              <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
                {!results && questions.length > 0 && (
                  <button
                    className="btn btn-primary"
                    onClick={handleSubmit}
                    disabled={!allFilled || loading}
                    style={{ flex: 1 }}
                  >
                    {loading
                      ? <><svg className="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg> Grading…</>
                      : '✅ Submit Answers'
                    }
                  </button>
                )}
                {someFailed && !allPassed && (
                  <button className="btn btn-ghost" onClick={handleRetry} style={{ flex: 1 }}>
                    🔄 Retry wrong answers
                  </button>
                )}
              </div>

              {!allFilled && !results && questions.length > 0 && (
                <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8, textAlign: 'center' }}>
                  Fill in all {questions.length} answers to enable submit
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── Single graph node card ───────────────────────────────────────────────── */
function GraphNode({ node, state, onClick }) {
  const col = COLOR[state] || COLOR.visible;
  const [burst, setBurst] = useState(false);

  useEffect(() => {
    if (state === 'passed') { setBurst(true); setTimeout(() => setBurst(false), 700); }
  }, [state]);

  const clickable = (state === 'unlocked' || state === 'passed');

  return (
    <div
      onClick={() => clickable && onClick(node)}
      title={state === 'visible' ? 'Complete the parent node first to unlock this.' : node.label}
      style={{
        position: 'relative',
        background: col.bg,
        border: `1.5px solid ${col.border}`,
        borderRadius: 12,
        padding: '14px 18px',
        minWidth: 150, maxWidth: 200,
        cursor: clickable ? 'pointer' : 'not-allowed',
        transition: 'all 0.2s',
        boxShadow: state === 'unlocked'
          ? '0 0 0 2px rgba(99,102,241,0.18), 0 4px 12px rgba(0,0,0,0.3)'
          : state === 'passed'
          ? '0 0 0 2px rgba(39,169,108,0.15)'
          : '0 2px 6px rgba(0,0,0,0.12)',
        userSelect: 'none',
        opacity: state === 'visible' ? 0.5 : 1,
      }}
      onMouseEnter={(e) => {
        if (state === 'unlocked') {
          e.currentTarget.style.transform = 'translateY(-2px)';
          e.currentTarget.style.boxShadow = '0 0 0 2px rgba(99,102,241,0.35), 0 8px 20px rgba(0,0,0,0.4)';
        }
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = '';
        e.currentTarget.style.boxShadow = state === 'unlocked'
          ? '0 0 0 2px rgba(99,102,241,0.18), 0 4px 12px rgba(0,0,0,0.3)'
          : '';
      }}
    >
      {burst && (
        <div style={{
          position: 'absolute', inset: 0, borderRadius: 12, pointerEvents: 'none',
          animation: 'unlockRipple 0.6s ease-out forwards',
          background: 'radial-gradient(circle, rgba(99,102,241,0.3) 0%, transparent 70%)',
        }} />
      )}

      <div style={{
        fontSize: 10, fontWeight: 700, letterSpacing: '0.05em',
        color: col.text, marginBottom: 6, textTransform: 'uppercase',
      }}>
        {state === 'passed' ? '✓ Completed' : state === 'unlocked' ? '▶ Open' : '🔒 Locked'}
      </div>

      <div style={{ fontWeight: 600, fontSize: 13, color: state === 'unlocked' ? 'var(--text-primary)' : col.text, lineHeight: 1.3 }}>
        {node.label}
      </div>

      {state === 'unlocked' && (
        <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-muted)' }}>Click to study →</div>
      )}
    </div>
  );
}

/* ─── SVG edge lines ───────────────────────────────────────────────────────── */
function EdgeLines({ nodeRefs, edges, nodeMap, passedIds, visibleLayerMax }) {
  const [lines, setLines] = useState([]);

  useEffect(() => {
    const newLines = [];
    edges.forEach(([fromId, toId]) => {
      const fromEl = nodeRefs.current[fromId];
      const toEl   = nodeRefs.current[toId];
      const toNode = nodeMap[toId];
      if (!fromEl || !toEl || !toNode) return;
      if (toNode.layer > visibleLayerMax) return;

      const containerRect = fromEl.closest('[data-graph-container]')?.getBoundingClientRect();
      if (!containerRect) return;

      const fr = fromEl.getBoundingClientRect();
      const tr = toEl.getBoundingClientRect();

      newLines.push({
        x1: fr.left + fr.width / 2 - containerRect.left,
        y1: fr.bottom - containerRect.top,
        x2: tr.left + tr.width / 2 - containerRect.left,
        y2: tr.top - containerRect.top,
        isPassed: passedIds.has(fromId),
        id: `${fromId}-${toId}`,
      });
    });
    setLines(newLines);
  }); // intentionally no deps — re-calculates when DOM changes

  return (
    <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', overflow: 'visible' }}>
      <defs>
        <marker id="arrowG" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <path d="M0,0 L0,6 L6,3 z" fill="rgba(39,169,108,0.7)" />
        </marker>
        <marker id="arrowD" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <path d="M0,0 L0,6 L6,3 z" fill="rgba(120,120,160,0.45)" />
        </marker>
      </defs>
      {lines.map((l) => (
        <line
          key={l.id} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2}
          stroke={l.isPassed ? 'rgba(39,169,108,0.55)' : 'rgba(120,120,160,0.3)'}
          strokeWidth={l.isPassed ? 2 : 1.5}
          strokeDasharray={l.isPassed ? undefined : '5,4'}
          markerEnd={l.isPassed ? 'url(#arrowG)' : 'url(#arrowD)'}
        />
      ))}
    </svg>
  );
}

/* ─── Main export ──────────────────────────────────────────────────────────── */
export default function LearningGraphView({ raw, notebookId }) {
  const graphData = parseSafe(raw);

  if (!graphData || !Array.isArray(graphData.nodes) || graphData.nodes.length === 0) {
    return (
      <div style={{ padding: 20, color: 'var(--danger)', fontSize: 14 }}>
        ⚠️ Could not parse learning graph (invalid JSON from AI). Try regenerating.
        <pre style={{ marginTop: 8, fontSize: 11, overflowX: 'auto', color: 'var(--text-muted)' }}>{raw}</pre>
      </div>
    );
  }

  const nodeMap   = buildNodeMap(graphData.nodes);
  const layerMap  = groupByLayer(graphData.nodes);
  const layerNums = Object.keys(layerMap).map(Number).sort((a, b) => a - b);
  const rootNode  = graphData.nodes.find((n) => n.layer === 0);

  const allEdges = [];
  graphData.nodes.forEach((n) => (n.edges || []).forEach((c) => allEdges.push([n.id, c])));

  return (
    <InnerGraph
      graphData={graphData}
      nodeMap={nodeMap}
      layerMap={layerMap}
      layerNums={layerNums}
      allEdges={allEdges}
      rootNode={rootNode}
      notebookId={notebookId}
    />
  );
}

/* ─── Stateful inner graph ─────────────────────────────────────────────────── */
function InnerGraph({ graphData, nodeMap, layerMap, layerNums, allEdges, rootNode, notebookId }) {
  const nodeRefs = useRef({});

  // passedIds: truly completed nodes (answered correctly)
  const [passedIds,   setPassedIds]   = useState(() => new Set());
  // unlockedIds: nodes eligible to be opened (start = root)
  const [unlockedIds, setUnlockedIds] = useState(() => new Set(rootNode ? [rootNode.id] : []));
  const [activeNode,  setActiveNode]  = useState(null);

  // highest layer that has been passed
  const maxPassedLayer = [...passedIds].reduce((mx, id) => {
    const layer = nodeMap[id]?.layer ?? 0;
    return layer > mx ? layer : mx;
  }, -1);

  // users can SEE nodes up to (maxPassedLayer + 1).
  // Before anything is passed, only layer 0 is visible.
  const visibleLayerMax = Math.max(maxPassedLayer + 1, 0);

  const getNodeState = (node) => {
    if (passedIds.has(node.id))   return 'passed';
    if (unlockedIds.has(node.id)) return 'unlocked';
    if (node.layer <= visibleLayerMax) return 'visible';
    return null; // fully hidden
  };

  const handlePassed = useCallback((nodeId) => {
    const node = nodeMap[nodeId];
    if (!node) return;
    setPassedIds((prev) => new Set([...prev, nodeId]));
    setUnlockedIds((prev) => new Set([...prev, ...(node.edges || [])]));
    setActiveNode(null);
  }, [nodeMap]);

  const progressTotal  = graphData.nodes.length;
  const progressPassed = passedIds.size;

  return (
    <>
      <style>{`
        @keyframes unlockRipple {
          0%   { opacity: 1; transform: scale(0.8); }
          100% { opacity: 0; transform: scale(1.6); }
        }
        @keyframes slideInRight {
          from { transform: translateX(40px); opacity: 0; }
          to   { transform: translateX(0);    opacity: 1; }
        }
      `}</style>

      {/* Header + progress */}
      <div style={{
        background: 'var(--bg-surface)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)', padding: '16px 22px', marginBottom: 20,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        boxShadow: 'var(--shadow-card)',
      }}>
        <div>
          <h2 style={{ fontWeight: 700, fontSize: '1.05rem', marginBottom: 4 }}>
            🧩 {graphData.title}
          </h2>
          <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Complete each node to unlock the next layer · non-sequential paths available
          </p>
        </div>
        <div style={{ textAlign: 'right', minWidth: 150 }}>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>
            {progressPassed} / {progressTotal} completed
          </div>
          <div style={{ height: 6, background: 'var(--bg-deep)', borderRadius: 99, overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: 99,
              width: `${progressTotal > 0 ? (progressPassed / progressTotal) * 100 : 0}%`,
              background: 'linear-gradient(90deg, var(--accent), var(--success))',
              transition: 'width 0.4s ease',
            }} />
          </div>
        </div>
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        {[
          { color: COLOR.unlocked.border, label: 'Open — click to study' },
          { color: COLOR.passed.border,   label: 'Completed' },
          { color: 'var(--border)',        label: 'Locked (next layer preview)' },
        ].map(({ color, label }) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-muted)' }}>
            <div style={{ width: 10, height: 10, borderRadius: 3, border: `2px solid ${color}` }} />
            {label}
          </div>
        ))}
      </div>

      {/* Graph canvas */}
      <div
        data-graph-container
        style={{
          position: 'relative',
          background: 'var(--bg-surface)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)', padding: '28px 24px',
          boxShadow: 'var(--shadow-card)', overflowX: 'auto', minHeight: 300,
        }}
      >
        <EdgeLines
          nodeRefs={nodeRefs}
          edges={allEdges}
          nodeMap={nodeMap}
          passedIds={passedIds}
          visibleLayerMax={visibleLayerMax}
        />

        {layerNums.map((layerNum) => {
          const nodesInLayer  = layerMap[layerNum] || [];
          const visibleNodes  = nodesInLayer.filter((n) => getNodeState(n) !== null);
          if (visibleNodes.length === 0) return null;

          return (
            <div key={layerNum} style={{ marginBottom: 48 }}>
              <div style={{
                fontSize: 11, fontWeight: 700, letterSpacing: '0.08em',
                color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 16,
              }}>
                {layerNum === 0 ? '⬤  Start' : `Layer ${layerNum}`}
              </div>
              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                {visibleNodes.map((node) => (
                  <div key={node.id} ref={(el) => { nodeRefs.current[node.id] = el; }}>
                    <GraphNode node={node} state={getNodeState(node)} onClick={setActiveNode} />
                  </div>
                ))}
              </div>
            </div>
          );
        })}

        {progressPassed === progressTotal && progressTotal > 0 && (
          <div style={{
            marginTop: 20, padding: '18px 24px',
            background: 'rgba(39,169,108,0.09)', border: '1px solid rgba(39,169,108,0.35)',
            borderRadius: 12, textAlign: 'center',
            fontSize: 15, fontWeight: 700, color: 'var(--success)',
          }}>
            🏆 You've completed all nodes! Great work!
          </div>
        )}
      </div>

      {/* Node drawer */}
      {activeNode && (
        <NodePanel
          node={activeNode}
          passed={passedIds.has(activeNode.id)}
          onClose={() => setActiveNode(null)}
          onPassed={handlePassed}
          notebookId={notebookId}
        />
      )}
    </>
  );
}
