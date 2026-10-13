import React, { useEffect, useState } from 'react';
import { replenishmentApi } from '../api';

const Replenishment = () => {
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filterRisk, setFilterRisk] = useState('');

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      try {
        const data = await replenishmentApi.getRecommendations(0, 100);
        setRecommendations(data.items);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    
    loadData();
  }, []);

  if (loading) return <div className="page-content">Loading recommendations...</div>;
  if (error) return <div className="page-content"><div className="alert alert-error">Error: {error}</div></div>;

  const filteredItems = filterRisk 
    ? recommendations.filter(r => r.risk_level === filterRisk) 
    : recommendations;

  const getRiskBadge = (level) => {
    switch (level) {
      case 'CRITICAL': return 'badge-danger';
      case 'HIGH': return 'badge-warning';
      case 'MEDIUM': return 'badge-info';
      case 'LOW': return 'badge-success';
      default: return 'badge-neutral';
    }
  };

  return (
    <>
      <header className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 className="page-title">Replenishment Engine</h1>
        <select 
          className="form-control" 
          style={{ width: '200px' }} 
          value={filterRisk} 
          onChange={(e) => setFilterRisk(e.target.value)}
        >
          <option value="">All Risk Levels</option>
          <option value="CRITICAL">Critical Risk</option>
          <option value="HIGH">High Risk</option>
          <option value="MEDIUM">Medium Risk</option>
          <option value="LOW">Low Risk</option>
          <option value="UNKNOWN">Unknown</option>
        </select>
      </header>
      
      <div className="page-content">
        <div className="card" style={{ padding: 0 }}>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Medicine</th>
                  <th>Risk Level</th>
                  <th>Stock</th>
                  <th>Avg Daily Demand</th>
                  <th>Days Cover</th>
                  <th>Supplier</th>
                  <th>Reorder Qty</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.length > 0 ? filteredItems.map(item => (
                  <tr key={item.medicine_id}>
                    <td>
                      <div><strong>{item.medicine_name}</strong></div>
                      <div className="text-muted" style={{ fontSize: '0.8rem' }}>{item.medicine_code}</div>
                    </td>
                    <td>
                      <span className={`badge ${getRiskBadge(item.risk_level)}`}>
                        {item.risk_level}
                      </span>
                    </td>
                    <td>{item.usable_stock}</td>
                    <td>{item.average_daily_demand ? item.average_daily_demand.toFixed(2) : '-'}</td>
                    <td>{item.days_of_stock_cover ? item.days_of_stock_cover.toFixed(1) : '-'}</td>
                    <td>
                      {item.preferred_supplier_name ? (
                        <div>
                          <div>{item.preferred_supplier_name}</div>
                          <div className="text-muted" style={{ fontSize: '0.8rem' }}>Lead time: {item.supplier_lead_time_days}d</div>
                        </div>
                      ) : <span className="text-muted">None</span>}
                    </td>
                    <td style={{ fontWeight: 'bold', color: item.recommended_reorder_quantity > 0 ? 'var(--primary-color)' : 'inherit' }}>
                      {item.recommended_reorder_quantity || 0}
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan="7" style={{ textAlign: 'center', padding: '2rem' }}>No recommendations match the criteria.</td>
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

export default Replenishment;
