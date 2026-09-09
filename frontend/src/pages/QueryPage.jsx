import { useState, useRef, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { Send, FileText, Bot, User, Loader2, Construction } from 'lucide-react';
import api from '../services/api';

// Ask Puddy is live. Flip to true to show the "work in progress" banner and
// disable the chat end-to-end (input, submit, and handleSubmit all key off this).
const WIP = false;

export default function QueryPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [company, setCompany] = useState('');
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const location = useLocation();

  useEffect(() => {
    api.getCompanies().then(data => {
      setCompanies(data.companies || []);
    }).catch(() => {});
  }, []);

  // Handle pre-filled query from dashboard
  useEffect(() => {
    if (location.state?.query) {
      setInput(location.state.query);
      if (location.state.company) setCompany(location.state.company);
      // Auto-submit after a short delay
      setTimeout(() => {
        handleSubmit(null, location.state.query, location.state.company);
      }, 300);
      // Clear location state
      window.history.replaceState({}, document.title);
    }
  }, [location.state]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function handleSubmit(e, queryOverride = null, companyOverride = null) {
    if (e) e.preventDefault();
    if (WIP) return;  // Ask Puddy temporarily closed — see banner
    const query = queryOverride || input;
    const comp = companyOverride || company;
    if (!query.trim() || loading) return;

    const userMessage = {
      role: 'user',
      content: query,
      company: comp,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await api.query(query, comp || null);
      const assistantMessage = {
        role: 'assistant',
        content: response.answer,
        sources: response.sources || [],
        intent: response.intent,
        chunks_used: response.chunks_used,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, assistantMessage]);
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${err.message}. Make sure the backend service is running and accessible.`,
        sources: [],
        timestamp: new Date(),
        error: true,
      }]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Ask Puddy</h1>
        <p className="page-subtitle">Get cited answers from interview experiences and job descriptions</p>
      </div>

      <div className="page-body">
        {WIP && (
          <div className="query-wip">
            <Construction size={18} />
            <span>Ask Puddy is temporarily closed — work in progress. Try Quick Prep and About the Company in the meantime.</span>
          </div>
        )}
        <div className="chat-container">
          {/* Messages */}
          <div className="chat-messages">
            {messages.length === 0 && (
              <div className="empty-state">
                <Bot size={64} />
                <h3 className="empty-state-title">Ask me anything about placements</h3>
                <p className="empty-state-text">
                  I can answer questions about interview experiences, job descriptions,
                  and help you prepare with data-driven insights. Every answer includes source citations.
                </p>
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i} className="chat-message">
                <div className={`chat-avatar ${msg.role}`}>
                  {msg.role === 'user' ? <User size={18} /> : <Bot size={18} />}
                </div>
                <div className="chat-bubble">
                  {msg.role === 'user' && msg.company && (
                    <div style={{
                      fontSize: 11,
                      color: 'var(--accent-blue)',
                      marginBottom: 4,
                      textTransform: 'uppercase',
                      letterSpacing: '0.5px',
                    }}>
                      Company: {msg.company}
                    </div>
                  )}
                  <div className="chat-bubble-content" style={msg.error ? { color: 'var(--accent-rose)' } : {}}>
                    {msg.content.split('\n').map((line, j) => (
                      <p key={j}>{line}</p>
                    ))}
                  </div>

                  {msg.sources && msg.sources.length > 0 && (
                    <div className="chat-sources">
                      <div className="chat-sources-title">Sources</div>
                      {msg.sources.map((source, j) => (
                        <div key={j} className="chat-source-item">
                          <FileText size={14} />
                          <span>{source.file}, Page {source.page}</span>
                          <span style={{ color: 'var(--text-muted)', marginLeft: 'auto' }}>
                            {source.company}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {msg.intent && (
                    <div style={{
                      marginTop: 8,
                      fontSize: 11,
                      color: 'var(--text-muted)',
                    }}>
                      Intent: {msg.intent} · {msg.chunks_used} chunks used
                    </div>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="chat-message">
                <div className="chat-avatar assistant"><Bot size={18} /></div>
                <div className="chat-bubble">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)' }}>
                    <Loader2 size={16} className="spinner" style={{ border: 'none', animation: 'spin 1s linear infinite' }} />
                    Searching documents and generating answer...
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="chat-input-container">
            <div className="chat-filters">
              <select
                className="filter-select"
                value={company}
                onChange={(e) => setCompany(e.target.value)}
              >
                <option value="">All Companies</option>
                {companies.map(c => (
                  <option key={c.company} value={c.company}>{c.company}</option>
                ))}
              </select>
            </div>
            <form onSubmit={handleSubmit} className="chat-input-wrapper">
              <textarea
                ref={inputRef}
                className="chat-input-field"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={WIP ? 'Ask Puddy is temporarily closed — work in progress.' : 'Ask about interview experiences, JD requirements, preparation tips...'}
                rows={1}
                disabled={WIP}
              />
              <button
                type="submit"
                className="btn btn-primary btn-icon"
                disabled={WIP || !input.trim() || loading}
              >
                <Send size={18} />
              </button>
            </form>
          </div>
        </div>
      </div>
    </>
  );
}
