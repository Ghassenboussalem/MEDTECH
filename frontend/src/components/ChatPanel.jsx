import { useState, useRef, useEffect } from 'react';
import CitationChip from './CitationChip';

/**
 * Parse AI response text and extract [Source, p.N] citations.
 * Returns an array of { type: 'text'|'citation', value, source, page }
 */
function parseMessage(text) {
  const parts = [];
  const re = /\[([^\]]+),\s*p\.(\d+)\]|\[([^\]]+)\]/g;
  let last = 0;
  let m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push({ type: 'text', value: text.slice(last, m.index) });
    if (m[1]) {
      parts.push({ type: 'citation', source: m[1].trim(), page: parseInt(m[2], 10) });
    } else {
      parts.push({ type: 'citation', source: m[3].trim(), page: null });
    }
    last = re.lastIndex;
  }
  if (last < text.length) parts.push({ type: 'text', value: text.slice(last) });
  return parts;
}

function AIMessage({ text }) {
  const parts = parseMessage(text);
  return (
    <div style={{
      display: 'flex', gap: 10, alignItems: 'flex-start',
      animation: 'slide-up .2s ease',
    }}>
      <div style={{
        width: 28, height: 28, borderRadius: 8, flexShrink: 0, marginTop: 2,
        background: 'var(--accent-dim)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: '13px',
      }}>🤖</div>
      <div style={{
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: '12px 16px',
        maxWidth: '80%',
        fontSize: '14px',
        lineHeight: 1.7,
        color: 'var(--text-primary)',
      }}>
        {parts.map((p, i) =>
          p.type === 'text'
            ? <span key={i}>{p.value}</span>
            : <CitationChip key={i} source={p.source} page={p.page} />
        )}
      </div>
    </div>
  );
}

function UserMessage({ text }) {
  return (
    <div style={{
      display: 'flex', gap: 10, alignItems: 'flex-start',
      justifyContent: 'flex-end',
      animation: 'slide-up .2s ease',
    }}>
      <div style={{
        background: 'var(--accent)',
        borderRadius: 'var(--radius-md)',
        padding: '10px 16px',
        maxWidth: '75%',
        fontSize: '14px',
        lineHeight: 1.6,
        color: '#fff',
      }}>
        {text}
      </div>
      <div style={{
        width: 28, height: 28, borderRadius: 8, flexShrink: 0, marginTop: 2,
        background: 'rgba(255,255,255,0.1)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: '13px',
      }}>👤</div>
    </div>
  );
}

function StreamingDot() {
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
      <div style={{
        width: 28, height: 28, borderRadius: 8, flexShrink: 0, marginTop: 2,
        background: 'var(--accent-dim)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '13px',
      }}>🤖</div>
      <div style={{
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: '12px 16px', display: 'flex', gap: 5, alignItems: 'center',
      }}>
        {[0, 1, 2].map((i) => (
          <div key={i} style={{
            width: 6, height: 6, borderRadius: '50%',
            background: 'var(--accent)',
            animation: `pulse-glow 1.2s ease-in-out ${i * 0.2}s infinite`,
          }} />
        ))}
      </div>
    </div>
  );
}

export default function ChatPanel({ notebookId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streaming]);

  const sendMessage = async () => {
    const q = input.trim();
    if (!q || streaming) return;
    setInput('');
    const userMsg = { role: 'user', content: q };
    setMessages((m) => [...m, userMsg]);
    setStreaming(true);

    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    let aiText = '';

    try {
      const res = await fetch(`/notebooks/${notebookId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, history }),
      });

      if (!res.ok) throw new Error('Chat request failed');

      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      setMessages((m) => [...m, { role: 'assistant', content: '' }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') continue;
            aiText += data;
            setMessages((m) => {
              const copy = [...m];
              copy[copy.length - 1] = { role: 'assistant', content: aiText };
              return copy;
            });
          }
        }
      }
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', content: `⚠️ Error: ${e.message}` }]);
    } finally {
      setStreaming(false);
    }
  };

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Messages */}
      <div className="overflow-y-auto" style={{ flex: 1, padding: '24px' }}>
        {messages.length === 0 && !streaming && (
          <div style={{
            height: '100%', display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', gap: 12,
            color: 'var(--text-muted)',
          }}>
            <div style={{ fontSize: '2.5rem' }}>💬</div>
            <p style={{ fontWeight: 500 }}>Chat with your documents</p>
            <p style={{ fontSize: '13px' }}>Ask anything about your uploaded sources</p>
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {messages.map((msg, i) =>
            msg.role === 'user'
              ? <UserMessage key={i} text={msg.content} />
              : <AIMessage key={i} text={msg.content} />
          )}
          {streaming && messages[messages.length - 1]?.role !== 'assistant' && <StreamingDot />}
        </div>
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{
        padding: '16px 20px',
        borderTop: '1px solid var(--border)',
        background: 'var(--bg-surface)',
      }}>
        <div style={{
          display: 'flex', gap: 10, alignItems: 'flex-end',
          background: 'var(--bg-elevated)',
          border: `1px solid ${streaming ? 'var(--border)' : 'var(--border)'}`,
          borderRadius: 'var(--radius-md)',
          padding: '8px 8px 8px 16px',
          transition: 'border-color var(--transition)',
        }}
          onFocusCapture={(e) => e.currentTarget.style.borderColor = 'var(--accent)'}
          onBlurCapture={(e) => e.currentTarget.style.borderColor = 'var(--border)'}
        >
          <textarea
            id="chat-input"
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask a question about your documents…"
            disabled={streaming}
            rows={1}
            style={{
              flex: 1, background: 'transparent', border: 'none', outline: 'none',
              color: 'var(--text-primary)', fontSize: '14px', lineHeight: 1.6,
              resize: 'none', maxHeight: 160, overflow: 'auto',
            }}
            onInput={(e) => {
              e.target.style.height = 'auto';
              e.target.style.height = e.target.scrollHeight + 'px';
            }}
          />
          <button
            id="chat-send-btn"
            className="btn btn-primary btn-icon"
            onClick={sendMessage}
            disabled={streaming || !input.trim()}
            style={{ flexShrink: 0 }}
          >
            {streaming
              ? <svg className="spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                </svg>
              : <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
            }
          </button>
        </div>
        <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 8, textAlign: 'center' }}>
          Shift+Enter for new line · Answers grounded in your uploaded documents
        </p>
      </div>
    </div>
  );
}
