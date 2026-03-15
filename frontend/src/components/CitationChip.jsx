import useNotebookStore from '../store/useNotebookStore';

/**
 * CitationChip — small numerical pill showing [1] with hover tooltip 
 * and click handler to open the PDF viewer.
 */
export default function CitationChip({ metadata }) {
  const setSelectedCitation = useNotebookStore((s) => s.setSelectedCitation);

  if (!metadata) return null;

  return (
    <span style={{ position: 'relative', display: 'inline-flex', margin: '0 2px' }}>
      <button
        onClick={() => setSelectedCitation(metadata)}
        className="badge badge-accent citation-badge"
        style={{
          cursor: 'pointer',
          fontSize: '11px',
          fontWeight: 600,
          fontFamily: 'var(--font-sans)',
          borderRadius: '50%',
          width: '18px',
          height: '18px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 0,
          border: '1px solid var(--accent)',
          background: 'var(--accent-glow)',
          color: 'var(--accent)',
          userSelect: 'none',
          transition: 'all 0.2s ease',
        }}
        title={`Source: ${metadata.source}${metadata.page ? ` (Page ${metadata.page})` : ''}\n\n"${metadata.text}"`}
        onMouseOver={(e) => {
          e.currentTarget.style.background = 'var(--accent)';
          e.currentTarget.style.color = '#fff';
        }}
        onMouseOut={(e) => {
          e.currentTarget.style.background = 'var(--accent-glow)';
          e.currentTarget.style.color = 'var(--accent)';
        }}
      >
        {metadata.id}
      </button>
    </span>
  );
}
