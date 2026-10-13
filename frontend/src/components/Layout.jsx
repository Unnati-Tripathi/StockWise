import React from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { LayoutDashboard, Package, RefreshCw, ArrowRightLeft, FileText, Bot } from 'lucide-react';

const Layout = () => {
  return (
    <div className="app-container">
      <aside className="sidebar">
        <div className="sidebar-header">
          <Package className="text-primary" />
          StockWise
        </div>
        <nav className="sidebar-nav">
          <NavLink to="/" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <LayoutDashboard size={20} />
            Dashboard
          </NavLink>
          <NavLink to="/inventory" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <Package size={20} />
            Inventory
          </NavLink>
          <NavLink to="/replenishment" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <RefreshCw size={20} />
            Replenishment
          </NavLink>
          <NavLink to="/invoices" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <FileText size={20} />
            Invoices (AI)
          </NavLink>
          <NavLink to="/assistant" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <Bot size={20} />
            Assistant (AI)
          </NavLink>
          <NavLink to="/movements" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <ArrowRightLeft size={20} />
            Stock Movements
          </NavLink>
        </nav>
      </aside>
      
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
};

export default Layout;
