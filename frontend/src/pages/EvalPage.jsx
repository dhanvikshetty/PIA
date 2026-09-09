import { useState, useEffect } from 'react';
import { BarChart3, Play, Loader2, TrendingUp, TrendingDown } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import api from '../services/api';

export default function EvalPage() {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [runningEval, setRunningEval] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    loadResults();
  }, []);

  async function loadResults() {
    try {
      setLoading(true);
      const data = await api.getEvalResults();
      setResults(data);
    } catch {
      // No results yet
    } finally {
      setLoading(false);
    }
  }

  async function runEval(includeFaithfulness = false) {
    setRunningEval(true);
    setError('');
    try {
      const data = await api.runEval(
        ['dense_only', 'hybrid', 'hybrid_reranked'],
        includeFaithfulness
      );
      setResults(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setRunningEval(false);
    }
  }

  const modes = results ? Object.keys(results.modes) : [];
  const metricKeys = [
    { key: 'avg_precision@5', label: 'Precision@5', format: v => (v * 100).toFixed(1) + '%' },
    { key: 'avg_recall@5', label: 'Recall@5', format: v => (v * 100).toFixed(1) + '%' },
    { key: 'avg_mrr', label: 'MRR', format: v => v.toFixed(4) },
    { key: 'avg_retrieval_time_ms', label: 'Retrieval Time', format: v => v.toFixed(0) + 'ms' },
  ];

  // Build chart data
  const chartData = metricKeys.filter(m => m.key !== 'avg_retrieval_time_ms').map(metric => {
    const row = { name: metric.label };
    modes.forEach(mode => {
      const val = results?.modes[mode]?.aggregated?.[metric.key];
      row[mode] = val ? parseFloat((val * 100).toFixed(1)) : 0;
    });
    return row;
  });

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Evaluation Dashboard</h1>
        <p className="page-subtitle">Quantitative proof the RAG pipeline works — before/after comparisons</p>
      </div>

      <div className="page-body">
        {/* Run Eval */}
        <div className="card" style={{ marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
            <div>
              <h3 className="card-title">Run Evaluation</h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
                Compares dense-only → hybrid → hybrid+reranked across 30 Q&A pairs
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                className="btn btn-primary"
                onClick={() => runEval(false)}
                disabled={runningEval}
              >
                {runningEval ? (
                  <><Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> Running...</>
                ) : (
                  <><Play size={16} /> Run Retrieval Eval</>
                )}
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => runEval(true)}
                disabled={runningEval}
              >
                + Faithfulness (slower)
              </button>
            </div>
          </div>
          {error && (
            <div style={{
              marginTop: 12, padding: '8px 12px',
              background: 'var(--accent-rose-dim)', color: 'var(--accent-rose)',
              borderRadius: 'var(--radius-sm)', fontSize: 13,
            }}>
              {error}
            </div>
          )}
        </div>

        {results ? (
          <>
            {/* Comparison Chart */}
            <div className="card" style={{ marginBottom: 24 }}>
              <div className="card-header">
                <h3 className="card-title">Retrieval Quality Comparison (%)</h3>
              </div>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={chartData} barGap={4}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                  <XAxis dataKey="name" tick={{ fill: 'var(--text-secondary)', fontSize: 12 }} />
                  <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 12 }} domain={[0, 100]} />
                  <Tooltip
                    contentStyle={{
                      background: 'var(--bg-secondary)',
                      border: '1px solid var(--border-color)',
                      borderRadius: 8,
                      color: 'var(--text-primary)',
                    }}
                    formatter={(value) => `${value}%`}
                  />
                  <Legend wrapperStyle={{ fontSize: 12, color: 'var(--text-secondary)' }} />
                  {modes.map((mode, i) => (
                    <Bar
                      key={mode}
                      dataKey={mode}
                      fill={['#5a6478', '#f59e0b', '#10b981'][i] || '#3b82f6'}
                      radius={[4, 4, 0, 0]}
                      name={mode.replace(/_/g, ' ')}
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Metrics Table */}
            <div className="card" style={{ marginBottom: 24 }}>
              <div className="card-header">
                <h3 className="card-title">Detailed Metrics</h3>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
                      <th style={thStyle}>Metric</th>
                      {modes.map(m => (
                        <th key={m} style={thStyle}>{m.replace(/_/g, ' ')}</th>
                      ))}
                      <th style={thStyle}>Improvement</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metricKeys.map(metric => {
                      const values = modes.map(m =>
                        results.modes[m]?.aggregated?.[metric.key] || 0
                      );
                      const baseline = values[0];
                      const best = values[values.length - 1];
                      const improvement = baseline > 0
                        ? (((best - baseline) / baseline) * 100).toFixed(1)
                        : 'N/A';

                      return (
                        <tr key={metric.key} style={{ borderBottom: '1px solid var(--border-color)' }}>
                          <td style={tdStyle}>{metric.label}</td>
                          {values.map((v, i) => (
                            <td key={i} style={{ ...tdStyle, fontFamily: 'monospace' }}>
                              {metric.format(v)}
                            </td>
                          ))}
                          <td style={tdStyle}>
                            {improvement !== 'N/A' && parseFloat(improvement) > 0 ? (
                              <span style={{ color: 'var(--accent-emerald)', display: 'flex', alignItems: 'center', gap: 4 }}>
                                <TrendingUp size={14} /> +{improvement}%
                              </span>
                            ) : improvement !== 'N/A' && parseFloat(improvement) < 0 ? (
                              <span style={{ color: 'var(--accent-rose)', display: 'flex', alignItems: 'center', gap: 4 }}>
                                <TrendingDown size={14} /> {improvement}%
                              </span>
                            ) : (
                              <span style={{ color: 'var(--text-muted)' }}>—</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Last evaluated: {results.timestamp} · {results.eval_set_size} questions
            </div>
          </>
        ) : !loading && (
          <div className="card">
            <div className="empty-state">
              <BarChart3 size={64} />
              <h3 className="empty-state-title">No evaluation results yet</h3>
              <p className="empty-state-text">
                Run the evaluation to see precision, recall, and MRR comparisons
                across dense-only, hybrid, and hybrid+reranked retrieval modes.
              </p>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

const thStyle = {
  textAlign: 'left', padding: '10px 12px', fontSize: 12, fontWeight: 600,
  color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px',
};

const tdStyle = {
  padding: '12px', fontSize: 14, color: 'var(--text-primary)',
};
