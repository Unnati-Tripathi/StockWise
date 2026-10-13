import React, { useEffect, useState } from 'react';
import { medicinesApi, replenishmentApi } from '../api';
import { Search } from 'lucide-react';

const Inventory = () => {
  const [medicines, setMedicines] = useState([]);
  const [replenishments, setReplenishments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      try {
        const [medsData, repData] = await Promise.all([
          medicinesApi.getMedicines(0, 100),
          replenishmentApi.getRecommendations(0, 100) // Getting usable_stock from here
        ]);
        setMedicines(medsData.items);
        setReplenishments(repData.items);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    
    loadData();
  }, []);

  if (loading) return <div className="page-content">Loading inventory...</div>;
  if (error) return <div className="page-content"><div className="alert alert-error">Error: {error}</div></div>;

  const filteredMeds = medicines.filter(m => 
    m.name.toLowerCase().includes(search.toLowerCase()) || 
    m.code.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <>
      <header className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 className="page-title">Inventory</h1>
        <div style={{ position: 'relative' }}>
          <Search size={18} style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input 
            type="text" 
            className="form-control" 
            placeholder="Search medicines..." 
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ paddingLeft: '2.5rem', width: '300px' }}
          />
        </div>
      </header>
      
      <div className="page-content">
        <div className="card" style={{ padding: 0 }}>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Name</th>
                  <th>Category</th>
                  <th>Unit</th>
                  <th>Usable Stock</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredMeds.length > 0 ? filteredMeds.map(med => {
                  const rep = replenishments.find(r => r.medicine_id === med.id);
                  const stock = rep ? rep.usable_stock : 0;
                  
                  let badge = <span className="badge badge-neutral">Unknown</span>;
                  if (med.is_active) {
                    badge = <span className="badge badge-success">Active</span>;
                  } else {
                    badge = <span className="badge badge-danger">Inactive</span>;
                  }

                  return (
                    <tr key={med.id}>
                      <td style={{ fontFamily: 'monospace', fontWeight: 600 }}>{med.code}</td>
                      <td>{med.name}</td>
                      <td>{med.category || '-'}</td>
                      <td>{med.base_unit}</td>
                      <td style={{ fontWeight: 600 }}>{stock}</td>
                      <td>{badge}</td>
                    </tr>
                  );
                }) : (
                  <tr>
                    <td colSpan="6" style={{ textAlign: 'center', padding: '2rem' }}>No medicines found.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
};

export default Inventory;
