const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export async function fetchApi(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    let errorDetail = 'API request failed';
    try {
      const errorData = await response.json();
      errorDetail = errorData.detail || errorDetail;
    } catch (e) {
      // Ignore JSON parse error on non-JSON response
    }
    throw new Error(errorDetail);
  }
  
  return response.json();
}

export const inventoryApi = {
  getSummary: () => fetchApi('/inventory/summary'),
  getBatches: (skip = 0, limit = 100) => fetchApi(`/inventory/batches?skip=${skip}&limit=${limit}`),
  recordMovement: (data) => fetchApi('/inventory/movements', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
};

export const medicinesApi = {
  getMedicines: (skip = 0, limit = 100) => fetchApi(`/medicines/?skip=${skip}&limit=${limit}`),
  getMedicine: (id) => fetchApi(`/medicines/${id}`),
};

export const replenishmentApi = {
  getRecommendations: (skip = 0, limit = 50) => fetchApi(`/replenishment/recommendations?skip=${skip}&limit=${limit}`),
};

export const demoApi = {
  resetData: () => fetchApi('/demo/reset', { method: 'POST' }),
};

export const invoicesApi = {
  upload: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch(`${API_BASE}/invoices/`, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || 'Upload failed');
    }
    return response.json();
  },
  getInvoices: (skip = 0, limit = 50) => fetchApi(`/invoices/?skip=${skip}&limit=${limit}`),
  getInvoice: (id) => fetchApi(`/invoices/${id}`),
  updateLineItem: (invoiceId, lineId, data) => fetchApi(`/invoices/${invoiceId}/lines/${lineId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  approve: (id) => fetchApi(`/invoices/${id}/approve`, { method: 'POST' }),
  postToInventory: (id) => fetchApi(`/invoices/${id}/post`, { method: 'POST' }),
};

export const assistantApi = {
  chat: (query, sessionHistory = []) => fetchApi('/assistant/chat', {
    method: 'POST',
    body: JSON.stringify({ query, session_history: sessionHistory })
  })
};

export const documentsApi = {
  upload: async (file, title = '', docType = 'supplier_policy') => {
    const formData = new FormData();
    formData.append('file', file);
    if (title) formData.append('title', title);
    if (docType) formData.append('doc_type', docType);

    const response = await fetch(`${API_BASE}/documents/`, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || 'Document upload failed');
    }
    return response.json();
  },
  list: (skip = 0, limit = 50) => fetchApi(`/documents/?skip=${skip}&limit=${limit}`),
  get: (id) => fetchApi(`/documents/${id}`),
  delete: (id) => fetchApi(`/documents/${id}`, { method: 'DELETE' }),
  search: (query, topK = 5) => fetchApi('/documents/search', {
    method: 'POST',
    body: JSON.stringify({ query, top_k: topK })
  }),
};
