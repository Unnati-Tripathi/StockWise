import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Inventory from './pages/Inventory';
import Replenishment from './pages/Replenishment';
import StockMovements from './pages/StockMovements';

import Invoices from './pages/Invoices';
import Assistant from './pages/Assistant';
import Documents from './pages/Documents';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="inventory" element={<Inventory />} />
          <Route path="replenishment" element={<Replenishment />} />
          <Route path="movements" element={<StockMovements />} />
          <Route path="invoices" element={<Invoices />} />
          <Route path="assistant" element={<Assistant />} />
          <Route path="documents" element={<Documents />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
