import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import useNotebookStore from '../store/useNotebookStore';

const ACCEPTED = {
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
  'text/plain': ['.txt'],
  'text/markdown': ['.md'],
};

function FileStatus({ name, status, error }) {
  const icons = { uploading: '⏳', done: '✅', error: '❌' };
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '8px 12px',
      background: 'var(--bg-elevated)',
      borderRadius: 'var(--radius-sm)',
      border: `1px solid ${status === 'error' ? 'var(--danger)' : status === 'done' ? 'rgba(76,175,128,0.3)' : 'var(--border)'}`,
      fontSize: '13px',
      animation: 'slide-up .2s ease',
    }}>
      <span>{icons[status]}</span>
      <span className="truncate" style={{ flex: 1, color: 'var(--text-primary)' }}>{name}</span>
      {status === 'uploading' && (
        <svg className="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.5">
          <path d="M21 12a9 9 0 1 1-6.219-8.56" />
        </svg>
      )}
      {error && <span style={{ color: 'var(--danger)', fontSize: '11px' }}>{error}</span>}
    </div>
  );
}

export default function UploadZone({ notebookId }) {
  const { uploadFile } = useNotebookStore();
  const [queue, setQueue] = useState([]);

  const updateStatus = (name, patch) =>
    setQueue((q) => q.map((f) => (f.name === name ? { ...f, ...patch } : f)));

  const onDrop = useCallback(async (accepted) => {
    const newItems = accepted.map((f) => ({ name: f.name, status: 'uploading', error: null }));
    setQueue((q) => [...q, ...newItems]);

    for (const file of accepted) {
      try {
        await uploadFile(notebookId, file, (s) => updateStatus(file.name, { status: s }));
      } catch (e) {
        updateStatus(file.name, { status: 'error', error: e.message });
      }
    }
  }, [notebookId, uploadFile]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, accept: ACCEPTED, multiple: true });

  return (
    <div>
      <div
        {...getRootProps()}
        id="upload-dropzone"
        style={{
          border: `2px dashed ${isDragActive ? 'var(--accent)' : 'var(--border)'}`,
          borderRadius: 'var(--radius-md)',
          padding: '20px 16px',
          textAlign: 'center',
          cursor: 'pointer',
          background: isDragActive ? 'var(--accent-dim)' : 'transparent',
          transition: 'all var(--transition)',
        }}
      >
        <input {...getInputProps()} />
        <div style={{ fontSize: '1.6rem', marginBottom: 8 }}>📎</div>
        <p style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>
          {isDragActive ? 'Drop files here' : 'Drag & drop files'}
        </p>
        <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>PDF · DOCX · TXT · MD</p>
      </div>

      {queue.length > 0 && (
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {queue.map((f) => (
            <FileStatus key={f.name} name={f.name} status={f.status} error={f.error} />
          ))}
        </div>
      )}
    </div>
  );
}
