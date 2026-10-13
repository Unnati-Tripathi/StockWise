import React, { useEffect, useState } from 'react';
import { inventoryApi, replenishmentApi, demoApi } from '../api';
import { Activity, AlertTriangle, Package, RefreshCw, Database } from 'lucide-react';
import { Link } from 'react-router-dom';

const Dashboard = () => {
  const [summary, setSummary] = useState(null);
  const [recommendations, setRecommendations] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [demoLoading, setDemoLoading] = useState(false);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [sumData, recData] = await Promise.all([
        inventoryApi.getSummary(),
        replenishmentApi.getRecommendations()
      ]);
      setSummary(sumData);
      setRecommendations(recData);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleDemoReset = async () => {
    setDemoLoading(true);
    try {
      await demoApi.resetData();
      await loadData();
    } catch (err) {
      alert("Failed to reset demo data: " + err.message);
    } finally {
      setDemoLoading(false);
    }
  };

  if (loading) return <div className="page-content">Loading dashboard...</div>;
  if (error) return <div className="page-content"><div className="alert alert-error">Error: {error}</div></div>;
  if (!summary) return null;

  const highRiskCount = recommendations?.items.filter(
    r => r.risk_level === 'CRITICAL' || r.risk_level === 'HIGH'
  ).length || 0;

  const isDatabaseEmpty = summary.total_active_medicines === 0;

  return (
    <>
      <header className="page-header">
        <h1 className="page-title">Dashboard Overview</h1>
      </header>
      
      <div className="page-content">
        {isDatabaseEmpty && (
          <div className="card" style={{ backgroundColor: '#fef2f2', borderColor: '#fca5a5' }}>
            <h2 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Database className="text-danger" /> Database is empty
            </h2>
            <p style={{ marginBottom: '1rem' }}>There are no medicines in the system. You can load synthetic demo data to test the dashboard.</p>
            <button 
              className="btn btn-primary" 
              onClick={handleDemoReset}
              disabled={demoLoading}
            >
              {demoLoading ? 'Loading...' : 'Load Synthetic Demo Data'}
            </button>
          </div>
        )}

        <div className="grid grid-cols-4">
          <div className="card stat-card">
            <div className="stat-label">Total Medicines</div>
            <div className="stat-value">{summary.total_active_medicines}</div>
          </div>
          
          <div className="card stat-card">
            <div className="stat-label">Units in Stock</div>
            <div className="stat-value">{summary.total_units_in_stock}</div>
          </div>
          
          <div className="card stat-card">
            <div className="stat-label">High Risk Alerts</div>
            <div className="stat-value" style={{ color: highRiskCount > 0 ? 'var(--danger-color)' : 'var(--primary-color)' }}>
              {highRiskCount}
            </div>
          </div>
          
          <div className="card stat-card">
            <div className="stat-label">Expiring Soon</div>
            <div className="stat-value" style={{ color: summary.expiring_soon_batches > 0 ? 'var(--warning-color)' : 'inherit' }}>
              {summary.expiring_soon_batches}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2" style={{ marginTop: '1.5rem' }}>
          <div className="card">
            <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <AlertTriangle size={20} style={{ color: 'var(--warning-color)' }} />
              Priority Replenishments
            </h3>
            {highRiskCount > 0 ? (
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>Medicine</th>
                      <th>Risk</th>
                      <th>Stock</th>
                      <th>Reorder</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recommendations.items
                      .filter(r => r.risk_level === 'CRITICAL' || r.risk_level === 'HIGH')
                      .slice(0, 5)
                      .map(item => (
                        <tr key={item.medicine_id}>
                          <td>{item.medicine_name}</td>
                          <td>
                            <span className={`badge ${item.risk_level === 'CRITICAL' ? 'badge-danger' : 'badge-warning'}`}>
                              {item.risk_level}
                            </span>
                          </td>
                          <td>{item.usable_stock}</td>
                          <td>{item.recommended_reorder_quantity || '-'}</td>
                        </tr>
                      ))
                    }
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-muted">No high risk replenishments needed at this time.</p>
            )}
            <div style={{ marginTop: '1rem' }}>
              <Link to="/replenishment" className="btn btn-primary" style={{ fontSize: '0.875rem' }}>View All Recommendations</Link>
            </div>
          </div>
          
          <div className="card">
            <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Activity size={20} style={{ color: 'var(--info-color)' }} />
              Inventory Health
            </h3>
            <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <li style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '0.5rem', borderBottom: '1px solid var(--border-color)' }}>
                <span>Total Batches Tracked</span>
                <strong>{summary.total_batches}</strong>
              </li>
              <li style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '0.5rem', borderBottom: '1px solid var(--border-color)' }}>
                <span>Already Expired Batches</span>
                <strong style={{ color: summary.expired_batches > 0 ? 'var(--danger-color)' : 'inherit' }}>
                  {summary.expired_batches}
                </strong>
              </li>
              <li style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: '0.5rem' }}>
                <span>System Status</span>
                <span className="badge badge-success">Operational</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </>
  );
};

export default Dashboard;
