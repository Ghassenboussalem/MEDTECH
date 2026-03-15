import React from 'react';
import useNotebookStore from '../store/useNotebookStore';

/**
 * Renders an embedded PDF or text chunk when a citation is clicked.
 */
export default function PDFModal({ notebookId }) {
  const selectedCitation = useNotebookStore((s) => s.selectedCitation);
  const setSelectedCitation = useNotebookStore((s) => s.setSelectedCitation);

  if (!selectedCitation) return null;

  // The backend serves files via a StaticFiles mount at /data/notebooks/
  // The citation has selectedCitation.source (the filename)
  const isPdf = selectedCitation.source.toLowerCase().endsWith('.pdf');
  
  // Construct the PDF URL with the page and search fragment to trigger native highlighting
  // Chromium supports the #search="urlEncodedText" fragment.
  const searchText = encodeURIComponent(selectedCitation.text.split(' ').slice(0, 5).join(' ')); // Take first 5 words for search to avoid long URL issues
  
  const fileUrl = isPdf
    ? `/data/notebooks/${notebookId}/sources/${encodeURIComponent(selectedCitation.source)}#page=${selectedCitation.page || 1}&search="${searchText}"`
    : null;

  return (
    <div style={{
      position: 'fixed',
      top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0, 0, 0, 0.5)',
      backdropFilter: 'blur(4px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 9999,
      animation: 'fade-in 0.2s ease',
      padding: '24px',
    }}>
      <div style={{
        background: 'var(--bg-card)',
        width: '100%',
        maxWidth: '900px',
        height: '90vh',
        borderRadius: 16,
        boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        border: '1px solid var(--border)',
      }}>
        {/* Header */}
        <div style={{
          padding: '16px 24px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: 'var(--bg-elevated)',
        }}>
          <div>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>{selectedCitation.source}</h3>
            {selectedCitation.page && (
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Page {selectedCitation.page}</span>
            )}
          </div>
          <button 
            onClick={() => setSelectedCitation(null)}
            style={{
              background: 'transparent',
              border: 'none',
              fontSize: 24,
              cursor: 'pointer',
              color: 'var(--text-secondary)',
              lineHeight: 1,
            }}
          >
            &times;
          </button>
        </div>

        {/* Content */}
        <div style={{ flex: 1, background: '#f5f5f5', overflow: 'hidden', position: 'relative' }}>
          {isPdf ? (
            <embed 
              src={fileUrl} 
              type="application/pdf"
              width="100%" 
              height="100%" 
              style={{ border: 'none' }}
            />
          ) : (
            <div style={{ padding: 40, overflowY: 'auto', height: '100%' }}>
              <div style={{
                background: '#fff',
                padding: 32,
                borderRadius: 8,
                boxShadow: '0 2px 8px rgba(0,0,0,0.05)',
                whiteSpace: 'pre-wrap',
                fontFamily: 'var(--font-serif)',
                fontSize: 16,
                lineHeight: 1.8,
                color: '#333',
              }}>
                {selectedCitation.text}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
