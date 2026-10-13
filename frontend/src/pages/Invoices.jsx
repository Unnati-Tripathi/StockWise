import React, { useEffect, useState } from 'react';
import { invoicesApi, medicinesApi } from '../api';
import { Upload, FileText, CheckCircle, AlertTriangle, XCircle, ChevronRight, Save } from 'lucide-react';

const Invoices = () => {
  const [invoices, setInvoices] = useState([]);
  const [selectedInvoice, setSelectedInvoice] = useState(null);
  const [medicines, setMedicines] = useState([]);
  
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState(null);
  
  // For editing a line item
  const [editingLine, setEditingLine] = useState(null);
  const [editFormData, setEditFormData] = useState({});

  const loadData = async () => {
    setLoading(true);
    try {
      const [invData, medData] = await Promise.all([
        invoicesApi.getInvoices(),
        medicinesApi.getMedicines(0, 500)
      ]);
      setInvoices(invData);
      setMedicines(medData.items);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    setUploading(true);
    setError(null);
    try {
      await invoicesApi.upload(file);
      await loadData();
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleSelect = async (id) => {
    setLoading(true);
    try {
      const data = await invoicesApi.getInvoice(id);
      setSelectedInvoice(data);
      setEditingLine(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    setActionLoading(true);
    try {
      await invoicesApi.approve(selectedInvoice.id);
      await handleSelect(selectedInvoice.id);
      await loadData();
    } catch (err) {
      alert(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handlePost = async () => {
    setActionLoading(true);
    try {
      await invoicesApi.postToInventory(selectedInvoice.id);
      await handleSelect(selectedInvoice.id);
      await loadData();
    } catch (err) {
      alert(err.message);
    } finally {
      setActionLoading(false);
    }
  };
  
  const handleEditClick = (line) => {
    setEditingLine(line.id);
    setEditFormData({
      medicine_id: line.medicine_id || '',
      quantity: line.quantity || '',
      batch_number: line.batch_number || '',
      unit_cost: line.unit_cost || '',
      expiry_date: line.expiry_date || '',
    });
  };

  const handleSaveLine = async () => {
    try {
      const payload = {
        ...editFormData,
        medicine_id: editFormData.medicine_id ? parseInt(editFormData.medicine_id) : null,
        quantity: editFormData.quantity ? parseInt(editFormData.quantity) : null,
        unit_cost: editFormData.unit_cost ? parseFloat(editFormData.unit_cost) : null,
      };
      await invoicesApi.updateLineItem(selectedInvoice.id, editingLine, payload);
      setEditingLine(null);
      await handleSelect(selectedInvoice.id);
    } catch (err) {
      alert(err.message);
    }
  };

  if (loading && !selectedInvoice && invoices.length === 0) return <div className="page-content">Loading...</div>;

  const getStatusBadge = (status) => {
    switch(status) {
      case 'UPLOADED':
      case 'PROCESSING': return <span className="badge badge-info">{status}</span>;
      case 'NEEDS_REVIEW': return <span className="badge badge-warning">{status}</span>;
      case 'APPROVED': return <span className="badge badge-primary" style={{backgroundColor: 'var(--primary-color)', color: 'white'}}>{status}</span>;
      case 'POSTED': return <span className="badge badge-success">{status}</span>;
      case 'FAILED': return <span className="badge badge-danger">{status}</span>;
      default: return <span className="badge">{status}</span>;
    }
  };

  return (
    <>
      <header className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 className="page-title">AI Invoice Processing</h1>
        <div>
          <input 
            type="file" 
            id="invoice-upload" 
            style={{ display: 'none' }} 
            accept=".pdf,image/*" 
            onChange={handleUpload}
          />
          <label htmlFor="invoice-upload" className="btn btn-primary" style={{ cursor: 'pointer' }}>
            <Upload size={18} /> {uploading ? 'Uploading...' : 'Upload Invoice'}
          </label>
        </div>
      </header>
      
      <div className="page-content" style={{ display: 'flex', gap: '2rem', alignItems: 'flex-start' }}>
        {/* Left Side: Invoice List */}
        <div className="card" style={{ flex: '1', padding: 0 }}>
          <h3 className="card-title" style={{ padding: '1.5rem 1.5rem 0' }}>Recent Invoices</h3>
          <div className="table-container" style={{ marginTop: '1rem' }}>
            <table>
              <tbody>
                {invoices.map(inv => (
                  <tr 
                    key={inv.id} 
                    onClick={() => handleSelect(inv.id)}
                    style={{ 
                      cursor: 'pointer', 
                      backgroundColor: selectedInvoice?.id === inv.id ? '#f1f5f9' : 'transparent' 
                    }}
                  >
                    <td>
                      <div style={{ fontWeight: 'bold' }}>{inv.invoice_number || `Invoice #${inv.id}`}</div>
                      <div className="text-muted" style={{ fontSize: '0.875rem' }}>{inv.extracted_supplier_name || 'Unknown Supplier'}</div>
                    </td>
                    <td>{getStatusBadge(inv.status)}</td>
                    <td><ChevronRight size={18} className="text-muted" /></td>
                  </tr>
                ))}
                {invoices.length === 0 && (
                  <tr>
                    <td colSpan="3" style={{ textAlign: 'center', padding: '2rem' }}>No invoices found.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right Side: Invoice Detail */}
        {selectedInvoice && (
          <div className="card" style={{ flex: '2' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.5rem' }}>
              <div>
                <h2 style={{ fontSize: '1.5rem', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <FileText className="text-primary" /> {selectedInvoice.invoice_number || `Invoice #${selectedInvoice.id}`}
                </h2>
                <p className="text-muted">{selectedInvoice.extracted_supplier_name}</p>
                <div style={{ marginTop: '0.5rem' }}>{getStatusBadge(selectedInvoice.status)}</div>
              </div>
              
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button 
                  className="btn btn-primary" 
                  style={{ backgroundColor: '#f59e0b' }}
                  disabled={selectedInvoice.status !== 'NEEDS_REVIEW' || actionLoading}
                  onClick={handleApprove}
                >
                  <CheckCircle size={18} /> Approve
                </button>
                <button 
                  className="btn btn-primary"
                  disabled={selectedInvoice.status !== 'APPROVED' || actionLoading}
                  onClick={handlePost}
                >
                  <Save size={18} /> Post to Inventory
                </button>
              </div>
            </div>

            {selectedInvoice.error_message && (
              <div className="alert alert-error">
                <strong>Processing Error:</strong> {selectedInvoice.error_message}
              </div>
            )}

            <div className="grid grid-cols-2" style={{ marginBottom: '2rem', gap: '1rem' }}>
              <div>
                <label className="text-muted" style={{ fontSize: '0.875rem' }}>Date</label>
                <div>{selectedInvoice.invoice_date || '-'}</div>
              </div>
              <div>
                <label className="text-muted" style={{ fontSize: '0.875rem' }}>Total</label>
                <div>{selectedInvoice.currency} {selectedInvoice.total || '-'}</div>
              </div>
            </div>

            <h3 className="card-title">Extracted Line Items</h3>
            <div className="table-container">
              <table style={{ fontSize: '0.875rem' }}>
                <thead>
                  <tr>
                    <th>Medicine & Code</th>
                    <th>Batch</th>
                    <th>Qty</th>
                    <th>Cost</th>
                    <th>Expiry</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedInvoice.line_items.map(line => (
                    <tr key={line.id}>
                      {editingLine === line.id ? (
                        <>
                          <td colSpan="6">
                            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                              <select 
                                className="form-control" 
                                value={editFormData.medicine_id}
                                onChange={e => setEditFormData({...editFormData, medicine_id: e.target.value})}
                                style={{ flex: '1', minWidth: '150px' }}
                              >
                                <option value="">Select Medicine...</option>
                                {medicines.map(m => (
                                  <option key={m.id} value={m.id}>{m.name} ({m.code})</option>
                                ))}
                              </select>
                              <input 
                                className="form-control" placeholder="Batch" value={editFormData.batch_number}
                                onChange={e => setEditFormData({...editFormData, batch_number: e.target.value})}
                                style={{ width: '100px' }}
                              />
                              <input 
                                className="form-control" placeholder="Qty" type="number" value={editFormData.quantity}
                                onChange={e => setEditFormData({...editFormData, quantity: e.target.value})}
                                style={{ width: '80px' }}
                              />
                              <input 
                                className="form-control" placeholder="Cost" type="number" step="0.01" value={editFormData.unit_cost}
                                onChange={e => setEditFormData({...editFormData, unit_cost: e.target.value})}
                                style={{ width: '80px' }}
                              />
                              <input 
                                className="form-control" placeholder="YYYY-MM-DD" type="date" value={editFormData.expiry_date}
                                onChange={e => setEditFormData({...editFormData, expiry_date: e.target.value})}
                                style={{ width: '130px' }}
                              />
                            </div>
                          </td>
                          <td>
                            <button className="btn btn-primary" style={{ padding: '0.25rem 0.5rem' }} onClick={handleSaveLine}>Save</button>
                            <button className="btn" style={{ padding: '0.25rem 0.5rem', marginLeft: '0.5rem' }} onClick={() => setEditingLine(null)}>Cancel</button>
                          </td>
                        </>
                      ) : (
                        <>
                          <td>
                            <div><strong>{line.extracted_medicine_name}</strong></div>
                            <div className="text-muted">{line.extracted_code}</div>
                          </td>
                          <td>{line.batch_number}</td>
                          <td>{line.quantity}</td>
                          <td>{line.unit_cost}</td>
                          <td>{line.expiry_date}</td>
                          <td>
                            {line.has_error ? (
                              <div title={line.validation_message} style={{ color: 'var(--danger-color)' }}>
                                <AlertTriangle size={16} /> Error
                              </div>
                            ) : (
                              <div style={{ color: 'var(--primary-color)' }}>
                                <CheckCircle size={16} /> OK
                              </div>
                            )}
                          </td>
                          <td>
                            {selectedInvoice.status === 'NEEDS_REVIEW' || selectedInvoice.status === 'FAILED' ? (
                              <button 
                                onClick={() => handleEditClick(line)}
                                style={{ background: 'none', border: 'none', color: 'var(--info-color)', cursor: 'pointer', textDecoration: 'underline' }}
                              >
                                Edit
                              </button>
                            ) : null}
                          </td>
                        </>
                      )}
                    </tr>
                  ))}
                  {selectedInvoice.line_items.length === 0 && (
                    <tr>
                      <td colSpan="7" style={{ textAlign: 'center', padding: '1rem' }}>No line items extracted.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            
            {/* Validation Message Summary */}
            {selectedInvoice.line_items.some(l => l.has_error) && (
              <div className="alert alert-error" style={{ marginTop: '1rem' }}>
                <h4 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <XCircle size={18} /> Validation Errors
                </h4>
                <ul style={{ paddingLeft: '1.5rem', fontSize: '0.875rem' }}>
                  {selectedInvoice.line_items.filter(l => l.has_error).map(l => (
                    <li key={l.id}><strong>{l.extracted_medicine_name}:</strong> {l.validation_message}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
};

export default Invoices;
