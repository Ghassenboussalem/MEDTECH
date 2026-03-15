
const API = '';

// ── Global State ──────────────────────────────────────────────────────────
let NODES = [];
let LESSON_TITLE = '';
let FILES = [];
let SESSION_ID = '';
let selectedNode = null;
let currentTutor = null;
let chatHistory = [];

// ── Load Graph from API ───────────────────────────────────────────────────
async function loadGraph() {
  const params = new URLSearchParams(window.location.search);
  const sessionId = params.get('id');
  if (!sessionId) { showLoadError('No session ID in URL. <a href="index.html">Go back</a>'); return; }

  setLdStage('Fetching graph data...', 30);

  try {
    const res = await fetch(`${API}/api/graph/${sessionId}`);
    if (res.status === 202) {
      // Still processing — poll
      setLdStage('Pipeline still running...', 50);
      await pollUntilReady(sessionId);
      return;
    }
    if (!res.ok) {
      const e = await res.json();
      throw new Error(e.error || 'Failed to load graph');
    }
    const data = await res.json();
    initGraph(data);
  } catch (err) {
    showLoadError('Error: ' + err.message);
  }
}

async function pollUntilReady(sessionId) {
  return new Promise((resolve, reject) => {
    const iv = setInterval(async () => {
      try {
        const res = await fetch(`${API}/api/status/${sessionId}`);
        const s = await res.json();
        setLdStage(s.stage, s.percent);
        if (s.status === 'done') {
          clearInterval(iv);
          const r = await fetch(`${API}/api/graph/${sessionId}`);
          const data = await r.json();
          initGraph(data);
          resolve();
        } else if (s.status === 'error') {
          clearInterval(iv);
          showLoadError('Pipeline error: ' + s.error);
          reject();
        }
      } catch (e) { clearInterval(iv); reject(e); }
    }, 2000);
  });
}

function setLdStage(text, pct) {
  document.getElementById('ld-stage').textContent = text;
  document.getElementById('ld-fill').style.width = (pct||0) + '%';
}

function showLoadError(html) {
  const err = document.getElementById('loading-error');
  err.innerHTML = html; err.style.display = 'block';
  document.querySelector('#loading-screen .ld-icon').textContent = '⚠️';
}

function initGraph(data) {
  NODES = data.nodes || [];
  LESSON_TITLE = data.lesson_title || 'My Lesson';
  FILES = data.files || [];
  // Grab session id from URL for node-content calls
  SESSION_ID = new URLSearchParams(window.location.search).get('id') || '';

  // Hide loading screen
  document.getElementById('loading-screen').style.display = 'none';

  // Populate top bar
  document.getElementById('badge-lesson').textContent = '📄 ' + LESSON_TITLE;

  // Populate source list
  const list = document.getElementById('source-list');
  list.innerHTML = FILES.map(f => `
    <div class="source-item">
      <span class="stype">📄</span>
      <span class="sname">${f}</span>
      <span class="sdone">✓</span>
    </div>
  `).join('');

  buildEdges();
  buildNodes();
  updateBadges();
}

// ── Graph Rendering ───────────────────────────────────────────────────────
function setViewBox() {
  const svg = document.getElementById('graph-svg');
  if (!NODES.length) return;
  let minX=Infinity, minY=Infinity, maxX=-Infinity, maxY=-Infinity;
  NODES.forEach(n => {
    minX = Math.min(minX, n.x - n.r - 80); minY = Math.min(minY, n.y - n.r - 80);
    maxX = Math.max(maxX, n.x + n.r + 80); maxY = Math.max(maxY, n.y + n.r + 80);
  });
  svg.setAttribute('viewBox', `${minX} ${minY} ${maxX-minX} ${maxY-minY}`);
  svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
}

function buildEdges() {
  setViewBox();
  const layer = document.getElementById('edges-layer');
  layer.innerHTML = '';
  const drawn = new Set();
  NODES.forEach(n => {
    (n.connections || []).forEach(cid => {
      const target = NODES.find(x => x.id === cid);
      if (!target) return;
      const key = [n.id, cid].sort().join('-');
      if (drawn.has(key)) return;
      drawn.add(key);
      const active = n.mastered || target.mastered;
      const bothUnlocked = n.unlocked && target.unlocked;
      const line = document.createElementNS('http://www.w3.org/2000/svg','line');
      line.setAttribute('x1', n.x); line.setAttribute('y1', n.y);
      line.setAttribute('x2', target.x); line.setAttribute('y2', target.y);
      line.setAttribute('stroke', active ? n.color : '#cbd5e1');
      line.setAttribute('class', `edge-line ${active?'active':''} ${!bothUnlocked?'locked':''}`);
      layer.appendChild(line);
    });
  });
}

function buildNodes() {
  const layer = document.getElementById('nodes-layer');
  layer.innerHTML = '';
  NODES.forEach(n => {
    const posG = document.createElementNS('http://www.w3.org/2000/svg','g');
    posG.setAttribute('transform', `translate(${n.x},${n.y})`);
    const actionG = document.createElementNS('http://www.w3.org/2000/svg','g');
    actionG.setAttribute('id', `node-${n.id}`);
    const g = document.createElementNS('http://www.w3.org/2000/svg','g');
    g.setAttribute('class', `node-group ${n.float||'float-a'}`);
    if (selectedNode && selectedNode.id === n.id) g.classList.add('active-node');
    g.addEventListener('click', () => selectNode(n.id));

    // Shadow
    const shadow = document.createElementNS('http://www.w3.org/2000/svg','circle');
    shadow.setAttribute('r', n.r + 6);
    shadow.setAttribute('fill', n.unlocked ? n.color : '#94a3b8');
    shadow.setAttribute('opacity', n.unlocked ? '0.15' : '0.1');
    g.appendChild(shadow);

    // Main circle
    const c = document.createElementNS('http://www.w3.org/2000/svg','circle');
    c.setAttribute('r', n.r);
    c.setAttribute('class', 'node-circle');
    if (n.unlocked) {
      c.setAttribute('fill', 'white');
      c.setAttribute('stroke', n.color);
      c.setAttribute('stroke-width', n.mastered ? '5' : '3');
    } else {
      c.setAttribute('fill', '#e2e8f0'); c.setAttribute('stroke', '#cbd5e1');
      c.setAttribute('stroke-width', '2.5'); c.setAttribute('stroke-dasharray', '6 5');
    }
    g.appendChild(c);

    // Tint
    if (n.unlocked) {
      const tint = document.createElementNS('http://www.w3.org/2000/svg','circle');
      tint.setAttribute('r', n.r - 3);
      tint.setAttribute('fill', n.color);
      tint.setAttribute('opacity', n.mastered ? '0.15' : '0.05');
      g.appendChild(tint);
    }

    // Emoji label
    const emojiSize = n.r > 70 ? '44' : n.r > 50 ? '30' : '22';
    const label = document.createElementNS('http://www.w3.org/2000/svg','text');
    label.setAttribute('y', n.sublabel ? '-10' : '0');
    label.setAttribute('font-size', emojiSize);
    label.setAttribute('class', 'node-label');
    label.setAttribute('fill', n.unlocked ? '#0f172a' : '#64748b');
    label.textContent = n.label || '📌';
    g.appendChild(label);

    // Sublabel
    if (n.sublabel) {
      n.sublabel.split('\n').forEach((line, i) => {
        const sl = document.createElementNS('http://www.w3.org/2000/svg','text');
        sl.setAttribute('y', (n.r > 70 ? 24 : n.r > 50 ? 16 : 14) + i * 16);
        sl.setAttribute('font-size', n.r > 70 ? '14' : n.r > 50 ? '12' : '10');
        sl.setAttribute('class', 'node-sublabel');
        sl.setAttribute('fill', n.unlocked ? '#334155' : '#94a3b8');
        sl.textContent = line;
        g.appendChild(sl);
      });
    }

    // Lock overlay
    if (!n.unlocked) {
      const lock = document.createElementNS('http://www.w3.org/2000/svg','text');
      lock.setAttribute('y', '8');
      lock.setAttribute('font-size', n.r > 70 ? '24' : '16');
      lock.setAttribute('class', 'node-label'); lock.setAttribute('fill', '#64748b');
      lock.textContent = '🔒';
      g.appendChild(lock);
    }

    // Mastered badge
    if (n.mastered) {
      const bx = n.r * 0.75, by = -n.r * 0.75;
      const badge = document.createElementNS('http://www.w3.org/2000/svg','circle');
      badge.setAttribute('cx', bx); badge.setAttribute('cy', by);
      badge.setAttribute('r', '12'); badge.setAttribute('fill', '#10b981');
      g.appendChild(badge);
      const check = document.createElementNS('http://www.w3.org/2000/svg','text');
      check.setAttribute('x', bx); check.setAttribute('y', by+4);
      check.setAttribute('font-size','12'); check.setAttribute('text-anchor','middle');
      check.setAttribute('fill','white'); check.setAttribute('font-weight','bold');
      check.textContent = '✓';
      g.appendChild(check);
    }

    actionG.appendChild(g);
    posG.appendChild(actionG);
    layer.appendChild(posG);
  });
}

// ── Node Selection ────────────────────────────────────────────────────────
function selectNode(id) {
  const n = NODES.find(x => x.id === id);
  if (!n) return;
  if (!n.unlocked) {
    const el = document.getElementById(`node-${id}`);
    if(el) { el.classList.add('shake'); setTimeout(() => el.classList.remove('shake'), 400); }
    return;
  }
  selectedNode = n;
  buildNodes();

  document.getElementById('empty-state').style.display = 'none';
  const detail = document.getElementById('node-detail');
  detail.classList.remove('hidden');

  const colors = {root:'#0ea5e9',chapter:'#7c3aed',section:'#3b82f6',sub:'#f59e0b'};
  const col = colors[n.type] || '#0ea5e9';
  document.getElementById('detail-icon').style.background = col + '22';
  document.getElementById('detail-icon').style.border = `2px solid ${col}55`;
  document.getElementById('detail-icon').textContent = n.label;
  document.getElementById('detail-title').textContent = (n.sublabel||'').replace('\n',' ') || n.label;
  document.getElementById('detail-type').textContent = `${(n.type||'node').toUpperCase()} · LEVEL ${n.level}`;

  // Render placeholder + start loading detailed content
  const scroll = document.getElementById('detail-scroll');
  scroll.innerHTML = `
    <div class="content-loading">
      <div class="content-spinner"></div>
      <span>Loading detailed explanation…</span>
    </div>
    <div class="node-connections-header">Connected Nodes</div>
    ${(n.connections||[]).map(cid => {
      const cn = NODES.find(x => x.id === cid);
      if (!cn) return '';
      return `<div style="display:flex;align-items:center;gap:10px;padding:12px;background:var(--surface2);border:1px solid var(--border);border-radius:8px;margin-bottom:8px;font-size:13px;font-weight:500;color:${cn.unlocked?'var(--text)':'var(--muted)'}">
        <div style="width:12px;height:12px;border-radius:50%;background:${cn.unlocked?(colors[cn.type]||'#ccc'):'#e2e8f0'}"></div>
        <div style="flex:1">${(cn.sublabel||cn.label||'').replace('\n',' ')}</div>
        <div style="font-size:10px;font-family:'Space Mono',monospace;font-weight:700;color:${cn.unlocked?'var(--success-dark)':'var(--muted)'}">${cn.unlocked?'OPEN':'LOCKED'}</div>
      </div>`;
    }).join('')}
  `;

  // Async: fetch and inject rich content
  loadNodeContent(n, scroll);

  const btn = document.getElementById('start-quiz-btn');
  if (n.mastered) {
    btn.style.background = 'var(--success)'; btn.textContent = '✓ Node Mastered'; btn.onclick = () => {};
  } else {
    btn.style.background = 'linear-gradient(135deg,var(--accent),var(--accent2))';
    btn.textContent = '🎯 Take Quiz to Unlock Path'; btn.onclick = openQuiz;
  }
}

/**
 * Fetch rich content from ContentAgent and inject it into the panel,
 * replacing the loading spinner.
 */
async function loadNodeContent(node, scrollEl) {
  const nodeTitle = (node.sublabel || '').replace('\n', ' ') || node.label;
  try {
    const res = await fetch(`${API}/api/node-content`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: SESSION_ID,
        node_title: nodeTitle,
        node_summary: node.summary || ''
      })
    });
    const data = await res.json();
    const richHTML = parseContent(data.content || '', node);
    // Replace only the spinner (first child) with rich HTML
    const spinner = scrollEl.querySelector('.content-loading');
    if (spinner) spinner.outerHTML = richHTML;
    else scrollEl.insertAdjacentHTML('afterbegin', richHTML);
  } catch (e) {
    const spinner = scrollEl.querySelector('.content-loading');
    if (spinner) spinner.outerHTML = `<div style="padding:14px;font-size:13px;color:var(--muted)">⚠️ Could not load content. Is the backend running?</div>`;
  }
}

/**
 * Parse the LLM's 4-section text into styled HTML blocks.
 * Sections are delimited by **Header Name** markers.
 */
function parseContent(text, node) {
  const sectionDefs = [
    { key: 'what',   label: 'What is it?',   icon: '📖', cls: 'cs-what'  },
    { key: 'facts',  label: 'Key Facts',     icon: '⚡', cls: 'cs-facts' },
    { key: 'why',    label: 'Why it matters', icon: '🎯', cls: 'cs-why'  },
    { key: 'deeper', label: 'Dig deeper',    icon: '🔭', cls: 'cs-deeper'},
  ];

  // Match each section heading
  const sectionRegex = /\*\*([^*]+)\*\*/g;
  const parts = text.split(sectionRegex);

  const sections = {};
  for (let i = 1; i < parts.length; i += 2) {
    const heading = parts[i].trim().toLowerCase();
    const body = (parts[i + 1] || '').trim();
    sectionDefs.forEach(def => {
      if (heading.includes(def.key)) sections[def.key] = body;
    });
  }

  // Fallback: put entire text as "what"
  if (!Object.keys(sections).length) {
    sections.what = text || node.summary || 'No detailed content available.';
  }

  let html = '';
  sectionDefs.forEach(def => {
    const body = sections[def.key];
    if (!body) return;

    let bodyHTML;
    if (def.key === 'facts') {
      const bullets = body.split(/\n/).map(l => l.replace(/^[•\-*]\s*/, '').trim()).filter(Boolean);
      bodyHTML = bullets.map(b => `
        <div class="fact-bullet">
          <span class="fact-dot">•</span>
          <span>${escHtml(b)}</span>
        </div>`).join('');
    } else {
      bodyHTML = `<p>${escHtml(body).replace(/\n/g, '<br>')}</p>`;
    }

    html += `
      <div class="content-section ${def.cls}">
        <div class="content-section-header">${def.icon} ${def.label}</div>
        <div class="content-section-body">${bodyHTML}</div>
      </div>`;
  });

  return html || `<div style="padding:14px;font-size:13px;color:var(--muted)">${escHtml(node.summary || 'No content available.')}</div>`;
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Quiz Flow ─────────────────────────────────────────────────────────────
function openQuiz() {
  if (!selectedNode || !selectedNode.quiz) { alert('No quiz available for this node.'); return; }
  document.getElementById('quiz-panel').classList.add('open');
  resetToMCQ();
}
function closeQuiz() { document.getElementById('quiz-panel').classList.remove('open'); }

function resetToMCQ() {
  const quiz = selectedNode.quiz;
  document.getElementById('q-text').textContent = quiz.question;
  const container = document.getElementById('mcq-options');
  container.innerHTML = '';

  // Shuffle options so correct answer (always at data index 0) appears randomly
  const correctAnswer = quiz.options[quiz.correct ?? 0];
  const shuffled = [...quiz.options]
    .map((opt, i) => ({ opt, isCorrect: i === (quiz.correct ?? 0) }))
    .sort(() => Math.random() - 0.5);

  shuffled.forEach(({ opt, isCorrect }) => {
    const label = document.createElement('label');
    label.className = 'mcq-option';
    const input = document.createElement('input');
    input.type = 'radio'; input.name = 'mcq'; input.value = opt;
    input.dataset.correct = isCorrect ? 'true' : 'false';
    label.appendChild(input);
    label.appendChild(document.createTextNode(' ' + opt));
    container.appendChild(label);
  });

  document.getElementById('quiz-mcq-view').style.display = 'block';
  document.getElementById('quiz-tutor-select').style.display = 'none';
  document.getElementById('quiz-interactive-chat').style.display = 'none';
  document.getElementById('quiz-success-view').style.display = 'none';
}

function scoreMCQ() {
  const selected = document.querySelector('input[name="mcq"]:checked');
  if (!selected) { alert('Please select an answer.'); return; }

  if (selected.dataset.correct === 'true') {
    selectedNode.mastered = true;
    unlockNeighbors(selectedNode.id);
    updateBadges();
    document.getElementById('quiz-mcq-view').style.display = 'none';
    document.getElementById('quiz-success-view').style.display = 'block';
    buildEdges(); buildNodes(); selectNode(selectedNode.id);
  } else {
    document.getElementById('quiz-mcq-view').style.display = 'none';
    document.getElementById('quiz-tutor-select').style.display = 'block';
  }
}

// ── Tutor Chat ────────────────────────────────────────────────────────────
function startChat(type) {
  currentTutor = type;
  chatHistory = [];
  const labels = { feynman:'🧒 Feynman Style', socratic:'🏛️ Socratic Method', devil:"😈 Devil's Advocate" };
  document.getElementById('chat-tutor-label').textContent = `Tutor: ${labels[type]}`;
  document.getElementById('quiz-tutor-select').style.display = 'none';
  document.getElementById('quiz-interactive-chat').style.display = 'flex';
  document.getElementById('chat-box').innerHTML = '';
  document.getElementById('chat-input-area').style.display = 'flex';
  document.getElementById('chat-retry-btn').style.display = 'none';
  document.getElementById('chat-input').value = '';

  // Opening greeting from tutor (real LLM)
  const greetings = {
    feynman: "🧒 Hey there! Let's make this super simple. Tell me — in your own words — what do you think this concept is about?",
    socratic: "🏛️ Welcome. Let us begin. What question first comes to your mind when you hear this topic?",
    devil: "😈 Interesting topic. Let me challenge you — convince me this concept actually matters. Why should anyone care?"
  };
  appendChat(greetings[type], 'tutor');
  chatHistory.push({ role: 'assistant', content: greetings[type] });
}

async function sendChatMessage() {
  const inputEl = document.getElementById('chat-input');
  const text = inputEl.value.trim();
  if (!text) return;

  appendChat(text, 'user');
  chatHistory.push({ role: 'user', content: text });
  inputEl.value = '';

  // Disable input while waiting
  document.getElementById('send-btn').disabled = true;
  const typingEl = appendChat('...', 'typing');

  try {
    const res = await fetch(`${API}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode: currentTutor,
        node_title: (selectedNode.sublabel || '').replace('\n', ' ') || selectedNode.label,
        node_summary: selectedNode.summary || '',
        message: text,
        history: chatHistory
      })
    });
    const data = await res.json();
    typingEl.remove();
    const reply = data.response || '(no response)';
    appendChat(reply, 'tutor');
    chatHistory.push({ role: 'assistant', content: reply });

    // After ≥ 2 exchanges, show retry button
    if (chatHistory.filter(m => m.role === 'user').length >= 2) {
      document.getElementById('chat-retry-btn').style.display = 'block';
    }
  } catch (e) {
    typingEl.remove();
    appendChat('(Could not reach Ollama. Is the backend running?)', 'tutor');
  } finally {
    document.getElementById('send-btn').disabled = false;
  }
}

function appendChat(text, sender) {
  const box = document.getElementById('chat-box');
  const div = document.createElement('div');
  div.className = sender === 'typing' ? 'chat-bubble chat-typing' : `chat-bubble chat-${sender}`;
  div.textContent = text;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return div;
}

// ── Unlock & Badges ───────────────────────────────────────────────────────
function unlockNeighbors(nodeId) {
  const n = NODES.find(x => x.id === nodeId);
  if (!n) return;
  (n.connections || []).forEach(cid => {
    const cn = NODES.find(x => x.id === cid);
    if (cn && !cn.unlocked) {
      cn.unlocked = true;
      const el = document.getElementById(`node-${cid}`);
      if (el) el.classList.add('unlock-flash');
    }
  });
}

function updateBadges() {
  const total = NODES.length;
  const unlocked = NODES.filter(n => n.unlocked).length;
  const mastered = NODES.filter(n => n.mastered).length;
  document.getElementById('badge-nodes').textContent = `${unlocked} / ${total} Unlocked`;
  document.getElementById('badge-progress').textContent = `${Math.round(mastered/total*100)}% Mastered`;
}

function resetGraph() {
  NODES.forEach(n => { n.unlocked = (n.id === 'root'); n.mastered = false; });
  selectedNode = null;
  document.getElementById('empty-state').style.display = 'flex';
  document.getElementById('node-detail').classList.add('hidden');
  buildEdges(); buildNodes(); updateBadges(); closeQuiz();
}

// ── Boot ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', loadGraph);
