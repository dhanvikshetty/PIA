import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Building2, Briefcase, GraduationCap, BarChart3 } from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts';
import api from '../services/api';

const COLORS = ['#3b82f6', '#10b981', '#8b5cf6', '#f59e0b', '#f43f5e', '#06b6d4', '#ec4899', '#14b8a6'];

export default function CompanyDetailPage() {
  const { name } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getCompanyDetail(name).then(setData).catch(() => {}).finally(() => setLoading(false));
  }, [name]);

  if (loading) {
    return (
      <>
        <div className="page-header">
          <h1 className="page-title">{name}</h1>
        </div>
        <div className="page-body">
          <div className="loading-spinner"><div className="spinner"></div></div>
        </div>
      </>
    );
  }

  if (!data) {
    return (
      <>
        <div className="page-header">
          <h1 className="page-title">Company not found</h1>
        </div>
      </>
    );
  }

  const company = data.company || {};
  const topicData = Object.entries(data.topic_distribution || {}).map(([name, value]) => ({ name, value }));
  const diffData = Object.entries(data.difficulty_distribution || {}).map(([name, value]) => ({ name, value }));

  const diffColors = { Easy: '#10b981', Medium: '#f59e0b', Hard: '#f43f5e', Unknown: '#5a6478' };

  return (
    <>
      <div className="page-header">
        <button
          className="btn btn-secondary btn-sm"
          onClick={() => navigate('/companies')}
          style={{ marginBottom: 12 }}
        >
          <ArrowLeft size={16} /> Back to Companies
        </button>
        <h1 className="page-title">{company.company || name}</h1>
        <p className="page-subtitle">
          {company.role || 'Role not specified'} · {company.package || 'Package not specified'}
        </p>
      </div>

      <div className="page-body">
        {/* Stats */}
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-icon blue"><Building2 size={22} /></div>
            <div>
              <div className="stat-value">{data.total_questions || 0}</div>
              <div className="stat-label">Total Questions</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon purple"><Briefcase size={22} /></div>
            <div>
              <div className="stat-value">{company.rounds?.length || 0}</div>
              <div className="stat-label">Interview Rounds</div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-icon emerald"><GraduationCap size={22} /></div>
            <div>
              <div className="stat-value">{company.skills?.length || 0}</div>
              <div className="stat-label">Required Skills</div>
            </div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 24 }}>
          {/* Topic Distribution */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">Topic Distribution</h3>
              <BarChart3 size={18} style={{ color: 'var(--text-muted)' }} />
            </div>
            {topicData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie
                    data={topicData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={3}
                    dataKey="value"
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  >
                    {topicData.map((_, idx) => (
                      <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      background: 'var(--bg-secondary)',
                      border: '1px solid var(--border-color)',
                      borderRadius: 8,
                      color: 'var(--text-primary)',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>No topic data available</p>
            )}
          </div>

          {/* Difficulty Distribution */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">Difficulty Distribution</h3>
            </div>
            {diffData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={diffData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                  <XAxis dataKey="name" tick={{ fill: 'var(--text-secondary)', fontSize: 12 }} />
                  <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 12 }} />
                  <Tooltip
                    contentStyle={{
                      background: 'var(--bg-secondary)',
                      border: '1px solid var(--border-color)',
                      borderRadius: 8,
                      color: 'var(--text-primary)',
                    }}
                  />
                  <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                    {diffData.map((entry, idx) => (
                      <Cell key={idx} fill={diffColors[entry.name] || '#5a6478'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>No difficulty data available</p>
            )}
          </div>
        </div>

        {/* Skills and Rounds */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 24 }}>
          <div className="card">
            <h3 className="card-title" style={{ marginBottom: 16 }}>Required Skills</h3>
            <div className="company-skills">
              {(company.skills || []).map((skill, i) => (
                <span key={i} className="skill-tag">{skill}</span>
              ))}
              {(!company.skills || company.skills.length === 0) && (
                <span style={{ color: 'var(--text-muted)', fontSize: 14 }}>No skills data</span>
              )}
            </div>
          </div>

          <div className="card">
            <h3 className="card-title" style={{ marginBottom: 16 }}>Interview Rounds</h3>
            {(company.rounds || []).map((round, i) => (
              <div key={i} style={{
                padding: '8px 12px',
                background: 'var(--bg-glass)',
                borderRadius: 'var(--radius-sm)',
                marginBottom: 6,
                fontSize: 14,
                display: 'flex',
                alignItems: 'center',
                gap: 10,
              }}>
                <span style={{
                  width: 24, height: 24, borderRadius: '50%',
                  background: 'var(--accent-blue-dim)', color: 'var(--accent-blue)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 12, fontWeight: 700, flexShrink: 0,
                }}>{i + 1}</span>
                {round}
              </div>
            ))}
            {(!company.rounds || company.rounds.length === 0) && (
              <span style={{ color: 'var(--text-muted)', fontSize: 14 }}>No rounds data</span>
            )}
          </div>
        </div>

        {/* Questions Table */}
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Interview Questions ({data.total_questions})</h3>
          </div>
          {data.questions?.length > 0 ? (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
                    <th style={thStyle}>Question</th>
                    <th style={thStyle}>Round</th>
                    <th style={thStyle}>Topic</th>
                    <th style={thStyle}>Difficulty</th>
                  </tr>
                </thead>
                <tbody>
                  {data.questions.map((q, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid var(--border-color)' }}>
                      <td style={tdStyle}>{q.question}</td>
                      <td style={tdStyle}><span className="skill-tag">{q.round || 'Unknown'}</span></td>
                      <td style={tdStyle}><span className="skill-tag">{q.topic || 'General'}</span></td>
                      <td style={tdStyle}>
                        <span style={{
                          padding: '2px 8px',
                          borderRadius: 12,
                          fontSize: 12,
                          fontWeight: 600,
                          background: q.difficulty === 'Easy' ? 'var(--accent-emerald-dim)' :
                                     q.difficulty === 'Hard' ? 'var(--accent-rose-dim)' : 'var(--accent-amber-dim)',
                          color: q.difficulty === 'Easy' ? 'var(--accent-emerald)' :
                                 q.difficulty === 'Hard' ? 'var(--accent-rose)' : 'var(--accent-amber)',
                        }}>
                          {q.difficulty || 'Medium'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>
              No questions extracted yet. Run ingestion with structured extraction enabled.
            </p>
          )}
        </div>
      </div>
    </>
  );
}

const thStyle = {
  textAlign: 'left',
  padding: '10px 12px',
  fontSize: 12,
  fontWeight: 600,
  color: 'var(--text-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.5px',
};

const tdStyle = {
  padding: '12px',
  fontSize: 14,
  color: 'var(--text-primary)',
  verticalAlign: 'top',
};
