import React, { useState, useEffect } from 'react';
import { inventoryApi, medicinesApi } from '../api';

const StockMovements = () => {
  const [medicines, setMedicines] = useState([]);
  const [batches, setBatches] = useState([]);
  
  const [formData, setFormData] = useState({
    medicine_id: '',
    batch_id: '',
    movement_type: 'RECEIPT',
    quantity_change: '',
    reference: '',
    notes: ''
  });
  
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null);

  useEffect(() => {
    const fetchSelectData = async () => {
      try {
        const [medRes, batchRes] = await Promise.all([
          medicinesApi.getMedicines(0, 500),
          inventoryApi.getBatches(0, 500)
        ]);
        setMedicines(medRes.items);
        setBatches(batchRes.items);
      } catch (err) {
        console.error("Failed to load options", err);
      }
    };
    fetchSelectData();
  }, []);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const filteredBatches = batches.filter(b => b.medicine_id.toString() === formData.medicine_id);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setFeedback(null);
    
    try {
      let qty = parseInt(formData.quantity_change, 10);
      if (isNaN(qty)) throw new Error("Invalid quantity");
      
      const payload = {
        medicine_id: parseInt(formData.medicine_id, 10),
        movement_type: formData.movement_type,
        quantity_change: qty,
        reference: formData.reference || null,
        notes: formData.notes || null,
      };
      
      if (formData.batch_id) {
        payload.batch_id = parseInt(formData.batch_id, 10);
      }

      await inventoryApi.recordMovement(payload);
      
      setFeedback({ type: 'success', message: 'Stock movement recorded successfully.' });
      setFormData(prev => ({ ...prev, quantity_change: '', reference: '', notes: '' }));
      
    } catch (err) {
      setFeedback({ type: 'error', message: err.message });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <header className="page-header">
        <h1 className="page-title">Record Stock Movement</h1>
      </header>
      
      <div className="page-content">
        <div className="card" style={{ maxWidth: '600px', margin: '0 auto' }}>
          {feedback && (
            <div className={`alert ${feedback.type === 'success' ? 'alert-success' : 'alert-error'}`}>
              {feedback.message}
            </div>
          )}
          
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">Movement Type</label>
              <select 
                className="form-control" 
                name="movement_type" 
                value={formData.movement_type} 
                onChange={handleChange}
                required
              >
                <option value="RECEIPT">Receipt (+)</option>
                <option value="SALE">Sale (-)</option>
                <option value="CUSTOMER_RETURN">Customer Return (+)</option>
                <option value="DAMAGE">Damage (-)</option>
                <option value="ADJUSTMENT">Adjustment</option>
              </select>
            </div>
            
            <div className="form-group">
              <label className="form-label">Medicine</label>
              <select 
                className="form-control" 
                name="medicine_id" 
                value={formData.medicine_id} 
                onChange={handleChange}
                required
              >
                <option value="">Select a medicine...</option>
                {medicines.map(m => (
                  <option key={m.id} value={m.id}>{m.name} ({m.code})</option>
                ))}
              </select>
            </div>
            
            {formData.medicine_id && (
              <div className="form-group">
                <label className="form-label">Inventory Batch {formData.movement_type !== 'ADJUSTMENT' && '*'}</label>
                <select 
                  className="form-control" 
                  name="batch_id" 
                  value={formData.batch_id} 
                  onChange={handleChange}
                  required={formData.movement_type !== 'ADJUSTMENT'}
                >
                  <option value="">Select a batch...</option>
                  {filteredBatches.map(b => (
                    <option key={b.id} value={b.id}>{b.batch_number} (Stock: {b.quantity_on_hand})</option>
                  ))}
                </select>
                {filteredBatches.length === 0 && <small className="text-danger">No batches found for this medicine.</small>}
              </div>
            )}
            
            <div className="form-group">
              <label className="form-label">Quantity Change</label>
              <input 
                type="number" 
                className="form-control" 
                name="quantity_change" 
                value={formData.quantity_change} 
                onChange={handleChange}
                placeholder={['SALE', 'DAMAGE'].includes(formData.movement_type) ? "-10" : "10"}
                required 
              />
              <small className="text-muted">Use negative numbers for sales/damages, positive for receipts.</small>
            </div>
            
            <div className="form-group">
              <label className="form-label">Reference (Optional)</label>
              <input 
                type="text" 
                className="form-control" 
                name="reference" 
                value={formData.reference} 
                onChange={handleChange}
                placeholder="e.g. PO-12345 or INV-9876"
              />
            </div>
            
            <button 
              type="submit" 
              className="btn btn-primary" 
              style={{ width: '100%', marginTop: '1rem' }}
              disabled={submitting}
            >
              {submitting ? 'Recording...' : 'Record Movement'}
            </button>
          </form>
        </div>
      </div>
    </>
  );
};

export default StockMovements;
