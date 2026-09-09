import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Building2,
  FileText,
  HelpCircle,
  Database,
  ArrowRight,
  TrendingUp,
  Sparkles,
} from 'lucide-react';
import api from '../services/api';

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      const [statsData, companiesData] = await Promise.all([
        api.getStats().catch(() => ({ vector_store_chunks: 0, structured_store: {}, ingested_files: 0 })),
        api.getCompanies().catch(() => ({ companies: [], total: 0 })),
      ]);
      setStats(statsData);
      setCompanies(companiesData.companies || []);
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
    } finally {
      setLoading(false);
    }
  }

  const quickQueries = [
    { text: 'What SQL questions were asked in ProcDNA?', company: 'ProcDNA' },
    { text: 'Give all DSA questions asked by Walmart', company: 'Walmart' },
    { text: 'What topics should I study for Amazon?', company: 'Amazon' },
    { text: 'Compare ProcDNA and Walmart interview difficulty', company: null },
  ];

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">Your placement preparation command center</p>
      </div>

      <div className="page-body">
        {/* Hero section */}
        <div className="card" style={{
          background: 'var(--gradient-hero)',
          marginBottom: 24,
          position: 'relative',
          overflow: 'hidden',
        }}>
          <div style={{ position: 'relative', zIndex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <Sparkles size={20} style={{ color: 'var(--accent-amber)' }} />
              <span style={{ color: 'var(--accent-amber)', fontSize: 13, fontWeight: 600 }}>AI-Powered</span>
            </div>
            <h2 style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>
              Welcome to Placement Buddy Puddy
            </h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: 14, maxWidth: 600, marginBottom: 16 }}>
              Analyze job descriptions, retrieve interview experiences with source citations,
              compare your resume against JDs, and prepare with data-driven insights.
            </p>
            <button className="btn btn-primary" onClick={() => navigate('/query')}>
              <MessageSquareIcon /> Start Asking Questions
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-icon blue"><Building2 size={22} /></div>
            <div>
              <div className="stat-value">{companies.length}</div>
              <div className="stat-label">Companies</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon emerald"><Database size={22} /></div>
            <div>
              <div className="stat-value">{stats?.vector_store_chunks || 0}</div>
              <div className="stat-label">Document Chunks</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon purple"><HelpCircle size={22} /></div>
            <div>
              <div className="stat-value">{stats?.structured_store?.interview_questions || 0}</div>
              <div className="stat-label">Interview Questions</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon amber"><FileText size={22} /></div>
            <div>
              <div className="stat-value">{stats?.ingested_files || 0}</div>
              <div className="stat-label">Ingested Files</div>
            </div>
          </div>
        </div>

        {/* Two columns */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
          {/* Quick Queries */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">Quick Queries</h3>
              <TrendingUp size={18} style={{ color: 'var(--text-muted)' }} />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {quickQueries.map((q, i) => (
                <button
                  key={i}
                  className="btn btn-secondary"
                  style={{ justifyContent: 'space-between', textAlign: 'left' }}
                  onClick={() => navigate('/query', { state: { query: q.text, company: q.company } })}
                >
                  <span style={{ fontSize: 13 }}>{q.text}</span>
                  <ArrowRight size={16} style={{ opacity: 0.5, flexShrink: 0 }} />
                </button>
              ))}
            </div>
          </div>

          {/* Companies */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">Companies</h3>
              <button className="btn btn-sm btn-secondary" onClick={() => navigate('/companies')}>
                View All
              </button>
            </div>
            {companies.length === 0 ? (
              <div className="empty-state" style={{ padding: 24 }}>
                <p className="empty-state-text">
                  No companies ingested yet. Go to Admin to upload documents.
                </p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {companies.slice(0, 5).map((c, i) => (
                  <div
                    key={i}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '10px 12px',
                      background: 'var(--bg-glass)',
                      borderRadius: 'var(--radius-sm)',
                      cursor: 'pointer',
                      transition: 'background 0.15s',
                    }}
                    onClick={() => navigate(`/companies/${c.company}`)}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-glass-hover)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'var(--bg-glass)'}
                  >
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 14 }}>{c.company}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{c.role}</div>
                    </div>
                    <span className="company-package" style={{ marginBottom: 0 }}>{c.package}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function MessageSquareIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>;
}
