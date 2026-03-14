/**
 * CitationChip — small pill showing [Source, p.N] with hover tooltip
 */
export default function CitationChip({ source, page, text }) {
  const label = page ? `${source}, p.${page}` : source;
  return (
    <span style={{ position: 'relative', display: 'inline-flex' }}>
      <span
        className="badge badge-accent"
        style={{
          cursor: 'default',
          fontSize: '11px',
          fontFamily: 'var(--font-mono)',
          borderRadius: 4,
          userSelect: 'none',
        }}
        title={text || label}
      >
        [{label}]
      </span>
    </span>
  );
}
