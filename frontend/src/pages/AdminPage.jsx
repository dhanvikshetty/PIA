import { useState, useEffect, useRef } from 'react';
import { Upload, Database, RefreshCw, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import api from '../services/api';

export default function AdminPage() {
  const [stats, setStats] = useState(null);
  const [ingesting, setIngesting] = useState(false);
  const [ingestResult, setIngestResult] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [error, setError] = useState('');
  const [backendStatus, setBackendStatus] = useState('checking');
  const fileInputRef = useRef(null);

  // Upload form state
  const [uploadDocType, setUploadDocType] = useState('interview_experience');
  const [uploadCompany, setUploadCompany] = useState('');

  useEffect(() => {
    checkBackend();
    loadStats();
  }, []);

  async function checkBackend() {
    try {
      await api.healthCheck();
      setBackendStatus('healthy');
    } catch {
      setBackendStatus('offline');
    }
  }

  async function loadStats() {
    try {
      const data = await api.getStats();
      setStats(data);
    } catch {}
  }

  async function handleIngest(force = false) {
    setIngesting(true);
    setError('');
    setIngestResult(null);
    try {
      const result = await api.ingest(null, false, force);
      setIngestResult(result);
      loadStats();
    } catch (err) {
      setError(err.message);
    } finally {
      setIngesting(false);
    }
  }

  async function handleUpload(e) {
    const files = Array.from(e.target.files);
    if (!files.length) return;
    if (!uploadCompany) { setError('Please enter a company name'); return; }

    setUploading(true);
    setError('');
    setUploadResult(null);
    try {
      const result = await api.uploadAndIngest(files, uploadDocType, uploadCompany);
      setUploadResult(result);
      loadStats();
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Admin</h1>
        <p className="page-subtitle">Upload documents, run ingestion, and monitor system health</p>
      </div>

      <div className="page-body">
        {/* Backend Status */}
        <div className="card" style={{ marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {backendStatus === 'healthy' ? (
              <CheckCircle2 size={20} style={{ color: 'var(--accent-emerald)' }} />
            ) : backendStatus === 'offline' ? (
              <AlertCircle size={20} style={{ color: 'var(--accent-rose)' }} />
            ) : (
              <Loader2 size={20} style={{ animation: 'spin 1s linear infinite', color: 'var(--text-muted)' }} />
            )}
            <div>
              <div style={{ fontWeight: 600, fontSize: 14 }}>
                Backend: {backendStatus === 'healthy' ? 'Connected' : backendStatus === 'offline' ? 'Offline' : 'Checking...'}
              </div>
              {backendStatus === 'offline' && (
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  Run: <code style={{ color: 'var(--accent-blue)' }}>python -m backend.main</code> from the project root
                </div>
              )}
            </div>
            <button className="btn btn-sm btn-secondary" style={{ marginLeft: 'auto' }} onClick={checkBackend}>
              <RefreshCw size={14} /> Refresh
            </button>
          </div>
        </div>

        <div className="admin-grid">
          {/* Ingestion */}
          <div className="card">
            <h3 className="card-title" style={{ marginBottom: 16 }}>
              <Database size={18} style={{ display: 'inline', marginRight: 8 }} />
              Ingestion Pipeline
            </h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 16 }}>
              Process all PDFs in the <code>./data</code> directory through the pipeline:
              PDF → Chunk → Embed → Store
            </p>

            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              <button className="btn btn-primary" onClick={() => handleIngest(false)} disabled={ingesting}>
                {ingesting ? <><Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> Processing...</> : 'Run Ingestion'}
              </button>
              <button className="btn btn-secondary" onClick={() => handleIngest(true)} disabled={ingesting}>
                Force Re-ingest
              </button>
            </div>

            {ingestResult && (
              <div style={{
                padding: 16,
                background: 'var(--accent-emerald-dim)',
                borderRadius: 'var(--radius-sm)',
                marginBottom: 16,
              }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--accent-emerald)', marginBottom: 8 }}>
                  ✓ Ingestion Complete
                </div>
                <div className="metric-row"><span className="metric-label">Files Processed</span><span className="metric-value">{ingestResult.files_processed}</span></div>
                <div className="metric-row"><span className="metric-label">Pages Loaded</span><span className="metric-value">{ingestResult.pages_loaded}</span></div>
                <div className="metric-row"><span className="metric-label">Chunks Created</span><span className="metric-value">{ingestResult.chunks_created}</span></div>
                <div className="metric-row"><span className="metric-label">Questions Extracted</span><span className="metric-value">{ingestResult.questions_extracted}</span></div>
              </div>
            )}
          </div>

          {/* Upload */}
          <div className="card">
            <h3 className="card-title" style={{ marginBottom: 16 }}>
              <Upload size={18} style={{ display: 'inline', marginRight: 8 }} />
              Upload Documents
            </h3>

            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 13, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Document Type</label>
              <select className="filter-select" value={uploadDocType} onChange={e => setUploadDocType(e.target.value)} style={{ width: '100%' }}>
                <option value="interview_experience">Interview Experience</option>
                <option value="job_description">Job Description</option>
                <option value="aptitude_material">Aptitude Material</option>
              </select>
            </div>

            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 13, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>Company Name</label>
              <input
                type="text"
                className="chat-input-field"
                value={uploadCompany}
                onChange={e => setUploadCompany(e.target.value)}
                placeholder="e.g., ProcDNA"
                style={{ minHeight: 40 }}
              />
            </div>

            <button
              className="btn btn-primary"
              style={{ width: '100%', marginBottom: 16 }}
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? <><Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> Uploading...</> : <><Upload size={16} /> Select PDF Files</>}
            </button>
            <input ref={fileInputRef} type="file" accept=".pdf" multiple onChange={handleUpload} style={{ display: 'none' }} />

            {uploadResult && (
              <div style={{ padding: 12, background: 'var(--accent-emerald-dim)', borderRadius: 'var(--radius-sm)', fontSize: 13 }}>
                ✓ {uploadResult.files_saved?.length || 0} files uploaded and ingested
              </div>
            )}
          </div>
        </div>

        {/* System Stats */}
        {stats && (
          <div className="card" style={{ marginTop: 24 }}>
            <h3 className="card-title" style={{ marginBottom: 16 }}>System Statistics</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
              <div className="metric-row">
                <span className="metric-label">Vector Store Chunks</span>
                <span className="metric-value">{stats.vector_store_chunks}</span>
              </div>
              <div className="metric-row">
                <span className="metric-label">Ingested Files</span>
                <span className="metric-value">{stats.ingested_files}</span>
              </div>
              {Object.entries(stats.structured_store || {}).map(([key, value]) => (
                <div key={key} className="metric-row">
                  <span className="metric-label">{key.replace(/_/g, ' ')}</span>
                  <span className="metric-value">{value}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {error && (
          <div style={{
            marginTop: 16, padding: '12px 16px',
            background: 'var(--accent-rose-dim)', color: 'var(--accent-rose)',
            borderRadius: 'var(--radius-sm)', fontSize: 13,
          }}>
            Error: {error}
          </div>
        )}
      </div>
    </>
  );
}
