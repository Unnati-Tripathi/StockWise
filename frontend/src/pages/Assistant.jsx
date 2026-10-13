import React, { useState, useRef, useEffect } from 'react';
import { assistantApi } from '../api';
import { Send, Bot, User, Code, FileText, ChevronRight, ChevronDown } from 'lucide-react';

const Assistant = () => {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Hello! I am the StockWise AI Assistant. I can help you with inventory lookups, stockout risks, supplier comparisons, and replenishment proposals.' }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const suggestedQuestions = [
    "Which medicines are at critical risk of stockout?",
    "Which batches are approaching expiry?",
    "Compare the available suppliers for medicines.",
    "Prepare a draft replenishment proposal for high-risk items."
  ];

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async (queryText = input) => {
    if (!queryText.trim()) return;
    
    const userMsg = { role: 'user', content: queryText };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      // Create session history (excluding tool payloads for simpler API)
      const sessionHistory = messages.map(m => ({ role: m.role, content: m.content }));
      
      const response = await assistantApi.chat(queryText, sessionHistory);
      
      setMessages(prev => [
        ...prev, 
        { 
          role: 'assistant', 
          content: response.reply,
          evidence: response.evidence 
        }
      ]);
    } catch (err) {
      setMessages(prev => [
        ...prev, 
        { role: 'assistant', content: `Error: ${err.message}` }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const EvidenceBlock = ({ evidence }) => {
    const [expanded, setExpanded] = useState(false);
    
    if (!evidence) return null;
    
    return (
      <div style={{ marginTop: '1rem', border: '1px solid var(--border-color)', borderRadius: '0.5rem', overflow: 'hidden' }}>
        <button 
          onClick={() => setExpanded(!expanded)}
          style={{ 
            display: 'flex', alignItems: 'center', width: '100%', padding: '0.5rem 1rem', 
            background: 'var(--surface-color)', border: 'none', cursor: 'pointer',
            fontSize: '0.875rem', fontWeight: 'bold', color: 'var(--text-muted)'
          }}
        >
          {expanded ? <ChevronDown size={16} style={{ marginRight: '0.5rem' }}/> : <ChevronRight size={16} style={{ marginRight: '0.5rem' }}/>}
          <Code size={16} style={{ marginRight: '0.5rem' }} /> 
          Grounded Evidence Tool: {evidence.tool_name}
        </button>
        {expanded && (
          <div style={{ padding: '1rem', background: '#f8fafc', overflowX: 'auto' }}>
            <pre style={{ margin: 0, fontSize: '0.75rem', color: '#334155' }}>
              {JSON.stringify(evidence.data, null, 2)}
            </pre>
          </div>
        )}
      </div>
    );
  };

  return (
    <>
      <header className="page-header">
        <h1 className="page-title">AI Inventory Assistant</h1>
        <p className="text-muted">Chat with real-time data grounded by StockWise deterministic engines.</p>
      </header>
      
      <div className="page-content" style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 200px)', maxWidth: '1000px', margin: '0 auto' }}>
        
        {/* Suggested Questions */}
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
          {suggestedQuestions.map((q, idx) => (
            <button 
              key={idx} 
              className="badge badge-neutral" 
              style={{ cursor: 'pointer', padding: '0.5rem 1rem', background: 'white', border: '1px solid var(--border-color)' }}
              onClick={() => handleSend(q)}
              disabled={loading}
            >
              {q}
            </button>
          ))}
        </div>

        {/* Chat Area */}
        <div className="card" style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: 0, overflow: 'hidden' }}>
          
          <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            {messages.map((msg, idx) => (
              <div key={idx} style={{ 
                display: 'flex', 
                gap: '1rem', 
                flexDirection: msg.role === 'user' ? 'row-reverse' : 'row' 
              }}>
                <div style={{ 
                  width: '36px', height: '36px', borderRadius: '50%', 
                  background: msg.role === 'user' ? 'var(--primary-color)' : '#e2e8f0',
                  color: msg.role === 'user' ? 'white' : 'var(--text-color)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0
                }}>
                  {msg.role === 'user' ? <User size={20} /> : <Bot size={20} />}
                </div>
                <div style={{ 
                  maxWidth: '75%', 
                  background: msg.role === 'user' ? 'var(--primary-color)' : 'white',
                  color: msg.role === 'user' ? 'white' : 'inherit',
                  padding: '1rem', 
                  borderRadius: '0.5rem',
                  border: msg.role === 'user' ? 'none' : '1px solid var(--border-color)',
                  boxShadow: msg.role === 'user' ? 'none' : '0 1px 3px rgba(0,0,0,0.05)'
                }}>
                  <div style={{ lineHeight: '1.5' }}>{msg.content}</div>
                  
                  {msg.evidence && <EvidenceBlock evidence={msg.evidence} />}
                </div>
              </div>
            ))}
            {loading && (
              <div style={{ display: 'flex', gap: '1rem' }}>
                <div style={{ width: '36px', height: '36px', borderRadius: '50%', background: '#e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Bot size={20} />
                </div>
                <div style={{ padding: '1rem', borderRadius: '0.5rem', border: '1px solid var(--border-color)' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Thinking...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input Area */}
          <div style={{ padding: '1rem', borderTop: '1px solid var(--border-color)', background: '#f8fafc' }}>
            <form 
              onSubmit={(e) => { e.preventDefault(); handleSend(); }}
              style={{ display: 'flex', gap: '0.5rem' }}
            >
              <input
                type="text"
                className="form-control"
                style={{ flex: 1 }}
                placeholder="Ask about stockouts, expiry, or suppliers..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={loading}
              />
              <button 
                type="submit" 
                className="btn btn-primary"
                disabled={!input.trim() || loading}
              >
                <Send size={18} /> Send
              </button>
            </form>
          </div>

        </div>
      </div>
    </>
  );
};

export default Assistant;
