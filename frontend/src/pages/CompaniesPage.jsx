import { useState } from 'react';
import {
  Building2,
  Search,
  Loader2,
  ThumbsUp,
  ThumbsDown,
  IndianRupee,
  Scale,
  Link as LinkIcon,
  FileText,
  MapPin,
} from 'lucide-react';
import api from '../services/api';

// Quick-pick chips so the user isn't staring at an empty box
const SUGGESTIONS = ['Amazon', 'TCS', 'Infosys', 'Google', 'Deloitte', 'Accenture'];

export default function CompaniesPage() {
  const [input, setInput] = useState('');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function runSearch(name) {
    const company = (name ?? input).trim();
    if (!company || loading) return;

    setInput(company);
    setLoading(true);
    setError('');
    setReport(null);

    try {
      const data = await api.getCompanyAbout(company);
      setReport(data);
    } catch (err) {
      setError(err.message || 'Could not research that company.');
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    runSearch();
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">About the Company</h1>
        <p className="page-subtitle">
          Search any company for an India-focused breakdown — pros, cons,
          ₹ pay and work-life balance, backed by real sources.
        </p>
      </div>

      <div className="page-body">
        {/* Search bar */}
        <form onSubmit={handleSubmit} className="about-search">
          <Search size={18} className="about-search-icon" />
          <input
            className="about-search-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type a company name — e.g. Amazon, TCS, Google..."
            autoFocus
          />
          <button type="submit" className="btn btn-primary" disabled={!input.trim() || loading}>
            {loading ? <Loader2 size={16} className="about-spin" /> : 'Research'}
          </button>
        </form>

        {/* Suggestion chips */}
        {!report && !loading && (
          <div className="about-suggestions">
            {SUGGESTIONS.map((s) => (
              <button key={s} className="about-chip" onClick={() => runSearch(s)}>
                <Building2 size={14} />
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="about-loading">
            <Loader2 size={40} className="about-spin" />
            <p>Researching <strong>{input}</strong> across reviews, salary reports and recent news…</p>
            <span className="about-loading-hint">Reading real sources takes ~20 seconds — hang tight.</span>
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="about-error">
            <Building2 size={40} />
            <h3>Couldn't research that</h3>
            <p>{error}</p>
          </div>
        )}

        {/* Report */}
        {report && !loading && (
          <div className="about-report">
            <div className="about-company-name">{report.company}</div>

            {/* Overview */}
            <section className="about-section">
              <h2 className="about-section-title">Overview</h2>
              <p className="about-overview">{report.overview}</p>
            </section>

            {/* India presence */}
            {report.india_presence && (
              <section className="about-section">
                <h2 className="about-section-title">
                  <MapPin size={18} /> India presence
                </h2>
                <p className="about-overview">{report.india_presence}</p>
              </section>
            )}

            {/* Pros / Cons side by side */}
            <div className="about-proscons">
              <section className="about-section about-pros">
                <h2 className="about-section-title">
                  <ThumbsUp size={18} /> Pros
                </h2>
                <ul className="about-list">
                  {report.pros?.length
                    ? report.pros.map((p, i) => <li key={i}>{p}</li>)
                    : <li className="about-empty">No pros found.</li>}
                </ul>
              </section>

              <section className="about-section about-cons">
                <h2 className="about-section-title">
                  <ThumbsDown size={18} /> Cons
                </h2>
                <ul className="about-list">
                  {report.cons?.length
                    ? report.cons.map((c, i) => <li key={i}>{c}</li>)
                    : <li className="about-empty">No cons found.</li>}
                </ul>
              </section>
            </div>

            {/* Salaries */}
            <section className="about-section">
              <h2 className="about-section-title">
                <IndianRupee size={18} /> Salaries <span className="about-sal-label">(India · ₹ LPA)</span>
              </h2>
              <ul className="about-list">
                {report.salaries?.length
                  ? report.salaries.map((s, i) => <li key={i}>{s}</li>)
                  : <li className="about-empty">No salary data found.</li>}
              </ul>
              {report.salary_caveat && (
                <p className="about-sal-caveat">{report.salary_caveat}</p>
              )}
            </section>

            {/* Work-life balance */}
            <section className="about-section">
              <h2 className="about-section-title">
                <Scale size={18} /> Work-life balance
              </h2>
              <p className="about-overview">{report.work_life_balance}</p>
            </section>

            {/* Sources */}
            <section className="about-section">
              <h2 className="about-section-title">
                <LinkIcon size={18} /> Sources
              </h2>
              {report.sources?.length ? (
                <ul className="about-sources">
                  {report.sources.map((src, i) => (
                    <li key={i}>
                      <a href={src.url} target="_blank" rel="noopener noreferrer">
                        <FileText size={14} />
                        <span>{src.title}</span>
                      </a>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="about-empty">No sources returned.</p>
              )}
            </section>
          </div>
        )}
      </div>
    </>
  );
}
