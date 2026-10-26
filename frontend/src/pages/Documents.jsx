import React, { useState, useEffect } from 'react';
import { documentsApi } from '../api';
import {
  Upload,
  FileText,
  Search,
  Trash2,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  Clock,
  Layers,
  FileSearch,
} from 'lucide-react';

const Documents = () => {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  // Upload Form State
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState('');
  const [docType, setDocType] = useState('supplier_policy');

  // Search State
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [topK, setTopK] = useState(5);

  const fetchDocuments = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await documentsApi.list();
      setDocuments(data.items || []);
    } catch (err) {
      setError(`Failed to load documents: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      const selected = e.target.files[0];
      setFile(selected);
      if (!title) {
        setTitle(selected.name.replace(/\.[^/.]+$/, ''));
      }
    }
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file) return;

    setUploading(true);
    setError(null);
    setSuccessMsg(null);
    try {
      await documentsApi.upload(file, title, docType);
      setSuccessMsg(`Document "${file.name}" uploaded successfully. Ingestion triggered.`);
      setFile(null);
      setTitle('');
      // Reset input element
      const fileInput = document.getElementById('doc-file-input');
      if (fileInput) fileInput.value = '';
      await fetchDocuments();
    } catch (err) {
      setError(`Upload failed: ${err.message}`);
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (id, docTitle) => {
    if (!window.confirm(`Are you sure you want to delete "${docTitle}"?`)) return;
    try {
      await documentsApi.delete(id);
      setDocuments((prev) => prev.filter((d) => d.id !== id));
      if (searchResults) {
        setSearchResults((prev) => prev ? prev.filter((r) => r.document_id !== id) : null);
      }
    } catch (err) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setSearching(true);
    try {
      const res = await documentsApi.search(searchQuery.trim(), parseInt(topK, 10));
      setSearchResults(res.results || []);
    } catch (err) {
      alert(`Search failed: ${err.message}`);
    } finally {
      setSearching(false);
    }
  };

  const renderStatusBadge = (status) => {
    switch (status) {
      case 'ready':
        return (
          <span className="badge badge-success" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <CheckCircle2 size={13} /> Ready
          </span>
        );
      case 'processing':
      case 'pending':
        return (
          <span className="badge badge-warning" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <Clock size={13} /> {status}
          </span>
        );
      case 'failed':
        return (
          <span className="badge badge-danger" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <AlertCircle size={13} /> Failed
          </span>
        );
      default:
        return <span className="badge badge-neutral">{status}</span>;
    }
  };

  return (
    <>
      <header className="page-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 className="page-title">Pharmacy Knowledge & SOPs (RAG)</h1>
            <p className="text-muted">
              Ingest supplier contracts, SOPs, and medicine monographs into pgvector for hybrid retrieval.
            </p>
          </div>
          <button className="btn btn-neutral" onClick={fetchDocuments} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'spin' : ''} /> Refresh
          </button>
        </div>
      </header>

      <div className="page-content" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        {error && (
          <div className="alert alert-danger" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertCircle size={18} /> {error}
          </div>
        )}
        {successMsg && (
          <div className="alert alert-success" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CheckCircle2 size={18} /> {successMsg}
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1.5rem' }}>
          {/* Upload Card */}
          <div className="card">
            <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: 0 }}>
              <Upload size={18} className="text-primary" /> Upload Knowledge Document
            </h3>
            <p className="text-muted" style={{ fontSize: '0.875rem' }}>
              Supported formats: PDF, DOCX, TXT. Documents are chunked (500 tokens) and embedded.
            </p>

            <form onSubmit={handleUpload} style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '4px' }}>
                  Select File
                </label>
                <input
                  id="doc-file-input"
                  type="file"
                  accept=".pdf,.docx,.txt"
                  onChange={handleFileChange}
                  className="form-control"
                  required
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '4px' }}>
                  Document Title
                </label>
                <input
                  type="text"
                  placeholder="e.g. MedCorp Delivery Policy 2024"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="form-control"
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: '4px' }}>
                  Document Type
                </label>
                <select
                  value={docType}
                  onChange={(e) => setDocType(e.target.value)}
                  className="form-control"
                >
                  <option value="supplier_policy">Supplier Policy / SLA</option>
                  <option value="sop">Standard Operating Procedure (SOP)</option>
                  <option value="medicine_ref">Medicine Reference / Monograph</option>
                  <option value="regulatory">Regulatory & Compliance</option>
                  <option value="other">Other Document</option>
                </select>
              </div>

              <button
                type="submit"
                className="btn btn-primary"
                disabled={!file || uploading}
                style={{ marginTop: '0.5rem' }}
              >
                {uploading ? 'Ingesting Document...' : 'Upload & Process Vector Index'}
              </button>
            </form>
          </div>

          {/* RAG Search Sandbox */}
          <div className="card">
            <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: 0 }}>
              <FileSearch size={18} className="text-primary" /> Hybrid RAG Search Test
            </h3>
            <p className="text-muted" style={{ fontSize: '0.875rem' }}>
              Test Reciprocal Rank Fusion (lexical PostgreSQL tsvector + pgvector cosine similarity).
            </p>

            <form onSubmit={handleSearch} style={{ display: 'flex', gap: '8px', marginTop: '1rem' }}>
              <input
                type="text"
                placeholder="Query policies, storage conditions, lead times..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="form-control"
                style={{ flex: 1 }}
              />
              <select
                value={topK}
                onChange={(e) => setTopK(e.target.value)}
                className="form-control"
                style={{ width: '80px' }}
                title="Top K Chunks"
              >
                <option value="3">Top 3</option>
                <option value="5">Top 5</option>
                <option value="10">Top 10</option>
              </select>
              <button type="submit" className="btn btn-primary" disabled={searching || !searchQuery.trim()}>
                {searching ? 'Searching...' : <Search size={16} />}
              </button>
            </form>

            {/* Results Preview */}
            <div style={{ marginTop: '1rem', maxHeight: '280px', overflowY: 'auto' }}>
              {searchResults && searchResults.length === 0 && (
                <p className="text-muted" style={{ textAlign: 'center', padding: '1rem' }}>
                  No matching chunks found. Try broader keywords.
                </p>
              )}
              {searchResults && searchResults.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {searchResults.map((res, i) => (
                    <div
                      key={i}
                      style={{
                        padding: '0.75rem',
                        background: '#f8fafc',
                        borderRadius: '0.375rem',
                        border: '1px solid var(--border-color)',
                        fontSize: '0.825rem',
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          marginBottom: '4px',
                          fontWeight: 600,
                          color: '#334155',
                        }}
                      >
                        <span>
                          {res.document_filename} {res.page_number ? `(p. ${res.page_number})` : ''}
                        </span>
                        <span className="badge badge-neutral" style={{ textTransform: 'uppercase', fontSize: '0.7rem' }}>
                          {res.match_type} | score: {res.score?.toFixed(4)}
                        </span>
                      </div>
                      <div style={{ color: '#475569', lineHeight: 1.4 }}>
                        {res.content.length > 250 ? `${res.content.slice(0, 250)}...` : res.content}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Documents Table */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Layers size={18} className="text-primary" /> Indexed Knowledge Corpus ({documents.length})
            </h3>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table className="table" style={{ width: '100%' }}>
              <thead>
                <tr>
                  <th>Title / Filename</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Chunks</th>
                  <th>Model</th>
                  <th>Created At</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {documents.length === 0 ? (
                  <tr>
                    <td colSpan="7" style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                      No documents ingested yet. Upload an SOP or supplier contract above to enable RAG.
                    </td>
                  </tr>
                ) : (
                  documents.map((doc) => (
                    <tr key={doc.id}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{doc.title || doc.filename}</div>
                        <div className="text-muted" style={{ fontSize: '0.75rem' }}>
                          {doc.filename}
                        </div>
                      </td>
                      <td>
                        <span className="badge badge-neutral" style={{ textTransform: 'capitalize' }}>
                          {(doc.doc_type || 'other').replace('_', ' ')}
                        </span>
                      </td>
                      <td>{renderStatusBadge(doc.status)}</td>
                      <td>
                        <strong>{doc.chunk_count || 0}</strong>
                      </td>
                      <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        {doc.embedding_model || '—'}
                      </td>
                      <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        {new Date(doc.created_at).toLocaleDateString()}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          className="btn btn-neutral"
                          onClick={() => handleDelete(doc.id, doc.title || doc.filename)}
                          style={{ padding: '4px 8px', color: '#ef4444' }}
                          title="Delete document"
                        >
                          <Trash2 size={15} />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
};

export default Documents;

