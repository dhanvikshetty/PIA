import { useState, useRef } from 'react';
import {
  Upload, FileText, CheckCircle2, XCircle, AlertTriangle,
  Loader2, TrendingUp, Award, Zap, BookOpen, User, GraduationCap,
  LayoutTemplate, Tag, ChevronDown, ChevronUp, Info,
} from 'lucide-react';
import api from '../services/api';

// ─── helpers ─────────────────────────────────────────────────────────────────

function scoreColor(score) {
  if (score >= 75) return 'var(--accent-emerald)';
  if (score >= 50) return 'var(--accent-amber)';
  return 'var(--accent-rose)';
}

function scoreLabel(score) {
  if (score >= 75) return 'Strong';
  if (score >= 50) return 'Moderate';
  return 'Weak';
}

function scoreBg(score) {
  if (score >= 75) return 'rgba(16,185,129,0.08)';
  if (score >= 50) return 'rgba(245,158,11,0.08)';
  return 'rgba(239,68,68,0.08)';
}

// ─── sub-components ───────────────────────────────────────────────────────────

function DropZone({ label, subLabel, file, onFile, accept = '.pdf', dragColor }) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

  function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f && f.name.toLowerCase().endsWith('.pdf')) onFile(f);
  }

  return (
    <div
      onClick={() => inputRef.current?.click()}
      onDragOver={e => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      style={{
        border: `2px dashed ${dragOver ? dragColor : (file ? dragColor : 'var(--border-color)')}`,
        borderRadius: 'var(--radius)',
        padding: '28px 20px',
        textAlign: 'center',
        cursor: 'pointer',
        background: dragOver ? `${dragColor}12` : (file ? `${dragColor}08` : 'var(--bg-glass)'),
        transition: 'all 0.2s',
        minHeight: 130,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
      }}
    >
      {file ? (
        <>
          <FileText size={36} style={{ color: dragColor }} />
          <div style={{ fontWeight: 600, fontSize: 14, color: dragColor }}>{file.name}</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            {(file.size / 1024).toFixed(1)} KB · click to replace
          </div>
        </>
      ) : (
        <>
          <Upload size={36} style={{ color: 'var(--text-muted)' }} />
          <div style={{ fontWeight: 600, fontSize: 14 }}>{label}</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{subLabel}</div>
        </>
      )}
      <input ref={inputRef} type="file" accept={accept} style={{ display: 'none' }}
        onChange={e => { if (e.target.files[0]) onFile(e.target.files[0]); }} />
    </div>
  );
}

function ScoreRing({ score, size = 120 }) {
  const color = scoreColor(score);
  const r = 46;
  const circ = 2 * Math.PI * r;
  const dash = (score / 100) * circ;

  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} viewBox="0 0 100 100" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx="50" cy="50" r={r} fill="none" stroke="var(--border-color)" strokeWidth="8" />
        <circle
          cx="50" cy="50" r={r} fill="none"
          stroke={color} strokeWidth="8"
          strokeDasharray={`${dash} ${circ - dash}`}
          strokeLinecap="round"
          style={{ transition: 'stroke-dasharray 0.6s ease' }}
        />
      </svg>
      <div style={{
        position: 'absolute', inset: 0,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
      }}>
        <span style={{ fontSize: size * 0.22, fontWeight: 800, color, lineHeight: 1 }}>{score}</span>
        <span style={{ fontSize: size * 0.1, color: 'var(--text-muted)', marginTop: 2 }}>/100</span>
      </div>
    </div>
  );
}

function SectionBar({ label, score, icon: Icon, weight }) {
  const color = scoreColor(score);
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 13 }}>
          <Icon size={14} style={{ color }} />
          <span style={{ fontWeight: 600 }}>{label}</span>
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>({weight})</span>
        </div>
        <span style={{ fontSize: 13, fontWeight: 700, color }}>{score}</span>
      </div>
      <div style={{ height: 6, borderRadius: 99, background: 'var(--border-color)', overflow: 'hidden' }}>
        <div style={{
          height: '100%', width: `${score}%`,
          background: color, borderRadius: 99,
          transition: 'width 0.6s ease',
        }} />
      </div>
    </div>
  );
}

function SkillPill({ label, variant }) {
  const styles = {
    matched: { bg: 'rgba(16,185,129,0.12)', color: 'var(--accent-emerald)', border: 'rgba(16,185,129,0.3)' },
    missing: { bg: 'rgba(239,68,68,0.10)', color: 'var(--accent-rose)', border: 'rgba(239,68,68,0.3)' },
    preferred: { bg: 'rgba(99,102,241,0.10)', color: '#818cf8', border: 'rgba(99,102,241,0.3)' },
    keyword_hit: { bg: 'rgba(16,185,129,0.08)', color: 'var(--accent-emerald)', border: 'rgba(16,185,129,0.2)' },
    keyword_miss: { bg: 'rgba(245,158,11,0.10)', color: 'var(--accent-amber)', border: 'rgba(245,158,11,0.3)' },
  };
  const s = styles[variant] || styles.matched;
  return (
    <span style={{
      display: 'inline-block',
      padding: '3px 10px',
      borderRadius: 99,
      fontSize: 12,
      fontWeight: 600,
      background: s.bg,
      color: s.color,
      border: `1px solid ${s.border}`,
      margin: '3px 4px 3px 0',
    }}>
      {label}
    </span>
  );
}

function Collapsible({ title, icon: Icon, iconColor, count, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{
      border: '1px solid var(--border-color)',
      borderRadius: 'var(--radius)',
      overflow: 'hidden',
      marginBottom: 12,
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 16px', background: 'var(--bg-glass)',
          border: 'none', cursor: 'pointer', color: 'var(--text-primary)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Icon size={15} style={{ color: iconColor }} />
          <span style={{ fontWeight: 600, fontSize: 14 }}>{title}</span>
          {count !== undefined && (
            <span style={{
              fontSize: 11, fontWeight: 700, padding: '1px 7px',
              borderRadius: 99, background: `${iconColor}20`, color: iconColor,
            }}>{count}</span>
          )}
        </div>
        {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
      </button>
      {open && (
        <div style={{ padding: '12px 16px', background: 'var(--bg-card)', borderTop: '1px solid var(--border-color)' }}>
          {children}
        </div>
      )}
    </div>
  );
}

// ─── main page ────────────────────────────────────────────────────────────────

export default function ResumePage() {
  const [resumeFile, setResumeFile] = useState(null);
  const [jdFile, setJdFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  async function handleAnalyze() {
    if (!resumeFile) { setError('Upload your resume PDF first'); return; }
    if (!jdFile) { setError('Upload the Job Description PDF first'); return; }
    setLoading(true);
    setError('');
    setResult(null);
    setStage('Starting analysis...');
    await api.analyzeResumeStream(resumeFile, jdFile, {
      onStage: ({ message }) => setStage(message),
      onResult: (data) => {
        setResult(data);
        setLoading(false);
        setStage('');
      },
      onError: (message) => {
        setError(message || 'Analysis failed. Please try again.');
        setLoading(false);
        setStage('');
      },
    });
  }

  function reset() {
    setResult(null);
    setError('');
    setStage('');
    setResumeFile(null);
    setJdFile(null);
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">ATS Resume Analyzer</h1>
        <p className="page-subtitle">
          Drop your resume and the job description — we'll score your resume like an ATS and tell you exactly what's missing
        </p>
      </div>

      <div className="page-body">

        {/* ── Upload Panel ── */}
        {!result && (
          <div style={{ maxWidth: 760, margin: '0 auto' }}>
            <div className="card" style={{ marginBottom: 16 }}>
              <h3 className="card-title" style={{ marginBottom: 6 }}>Step 1 — Upload your files</h3>
              <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 20 }}>
                No company selection needed. We extract everything — role, skills, keywords — directly from your JD PDF.
              </p>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Your Resume
                  </div>
                  <DropZone
                    label="Drop Resume PDF"
                    subLabel="or click to browse"
                    file={resumeFile}
                    onFile={setResumeFile}
                    dragColor="var(--accent-emerald)"
                  />
                </div>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Job Description
                  </div>
                  <DropZone
                    label="Drop JD PDF"
                    subLabel="the job you're applying for"
                    file={jdFile}
                    onFile={setJdFile}
                    dragColor="#818cf8"
                  />
                </div>
              </div>

              {error && (
                <div style={{
                  padding: '10px 14px', marginBottom: 16,
                  background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)',
                  color: 'var(--accent-rose)', borderRadius: 'var(--radius-sm)', fontSize: 13,
                }}>
                  {error}
                </div>
              )}

              <button
                className="btn btn-primary"
                style={{ width: '100%', height: 44, fontSize: 15 }}
                onClick={handleAnalyze}
                disabled={loading || !resumeFile || !jdFile}
              >
                {loading
                  ? <><Loader2 size={16} style={{ animation: 'spin 1s linear infinite', marginRight: 8 }} />{stage || 'Analyzing...'}</>
                  : <><Zap size={16} style={{ marginRight: 8 }} />Run ATS Analysis</>
                }
              </button>
            </div>

            <div style={{
              display: 'flex', gap: 8, alignItems: 'flex-start',
              padding: '10px 14px', borderRadius: 'var(--radius-sm)',
              background: 'var(--bg-glass)', border: '1px solid var(--border-color)',
              fontSize: 12, color: 'var(--text-muted)',
            }}>
              <Info size={14} style={{ flexShrink: 0, marginTop: 1 }} />
              <span>Your resume and JD are processed in-memory only and are <strong style={{ color: 'var(--text-secondary)' }}>never stored</strong>. Typical analysis time is 10–20 seconds.</span>
            </div>
          </div>
        )}

        {/* ── Results ── */}
        {result && (
          <div>
            {/* Header bar */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              marginBottom: 20, flexWrap: 'wrap', gap: 12,
            }}>
              <div>
                <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 2 }}>ATS analysis for</div>
                <h2 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>
                  {result.role}
                  {result.company !== 'Unknown' && <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}> @ {result.company}</span>}
                </h2>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 3 }}>
                  {result.industry_domain} · {result.seniority_level} level
                  {result.required_experience_years && ` · ${result.required_experience_years}+ yrs required`}
                  {result.required_degree && ` · ${result.required_degree}`}
                </div>
              </div>
              <button className="btn btn-secondary" onClick={reset} style={{ fontSize: 13 }}>
                ← Analyze Another
              </button>
            </div>

            {/* Top row: score ring + section bars + verdict */}
            <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 20, marginBottom: 20 }}>

              {/* Score ring card */}
              <div className="card" style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center',
                justifyContent: 'center', gap: 12, minWidth: 190, padding: '24px 20px',
              }}>
                <ScoreRing score={result.ats_score} size={130} />
                <div style={{ textAlign: 'center' }}>
                  <div style={{
                    fontSize: 15, fontWeight: 700,
                    color: scoreColor(result.ats_score),
                  }}>
                    {scoreLabel(result.ats_score)} Match
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 3 }}>ATS Score</div>
                </div>
                <div style={{
                  width: '100%', padding: '8px 12px', borderRadius: 'var(--radius-sm)',
                  background: scoreBg(result.ats_score),
                  fontSize: 11, color: scoreColor(result.ats_score),
                  textAlign: 'center', fontWeight: 600,
                }}>
                  {result.ats_score >= 75 ? '✓ Likely to pass ATS' : result.ats_score >= 50 ? '⚠ May get filtered out' : '✗ High risk of rejection'}
                </div>
              </div>

              {/* Section score bars */}
              <div className="card">
                <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 14 }}>Score Breakdown</div>
                <SectionBar label="Skills Match"          score={result.section_scores.skills_match}         icon={TrendingUp}     weight="35%" />
                <SectionBar label="Keyword Density"       score={result.section_scores.keyword_density}      icon={Tag}            weight="25%" />
                <SectionBar label="Experience Alignment"  score={result.section_scores.experience_alignment} icon={User}           weight="15%" />
                <SectionBar label="Education Match"       score={result.section_scores.education_match}      icon={GraduationCap}  weight="10%" />
                <SectionBar label="Section Completeness"  score={result.section_scores.section_completeness} icon={LayoutTemplate} weight="10%" />
                <SectionBar label="ATS Formatting"        score={result.section_scores.formatting}           icon={FileText}       weight="5%"  />
              </div>
            </div>

            {/* Verdict + Strengths */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
              <div className="card">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <Info size={15} style={{ color: 'var(--accent-amber)' }} />
                  <span style={{ fontWeight: 700, fontSize: 14 }}>Overall Verdict</span>
                </div>
                <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, margin: 0 }}>
                  {result.overall_verdict}
                </p>
              </div>
              <div className="card">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <Award size={15} style={{ color: 'var(--accent-emerald)' }} />
                  <span style={{ fontWeight: 700, fontSize: 14 }}>Your Strengths</span>
                </div>
                {result.strengths.length > 0
                  ? result.strengths.map((s, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 6 }}>
                      <CheckCircle2 size={13} style={{ color: 'var(--accent-emerald)', marginTop: 2, flexShrink: 0 }} />
                      <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{s}</span>
                    </div>
                  ))
                  : <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>No clear strengths detected for this JD.</p>
                }
              </div>
            </div>

            {/* Priority Recommendations */}
            {result.priority_recommendations?.length > 0 && (
              <div className="card" style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                  <Zap size={15} style={{ color: 'var(--accent-amber)' }} />
                  <span style={{ fontWeight: 700, fontSize: 14 }}>Priority Improvements</span>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>— ordered by impact</span>
                </div>
                {result.priority_recommendations.map((r, i) => (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'flex-start', gap: 10,
                    padding: '8px 12px', borderRadius: 'var(--radius-sm)',
                    background: i === 0 ? 'rgba(245,158,11,0.07)' : 'var(--bg-glass)',
                    marginBottom: 6,
                  }}>
                    <span style={{
                      fontSize: 11, fontWeight: 800, minWidth: 20, height: 20,
                      borderRadius: '50%', background: i < 3 ? 'var(--accent-amber)' : 'var(--border-color)',
                      color: i < 3 ? '#000' : 'var(--text-muted)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                    }}>{i + 1}</span>
                    <span style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{r}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Collapsible detail sections */}
            <Collapsible
              title="Required Skills"
              icon={TrendingUp}
              iconColor="var(--accent-emerald)"
              count={`${result.matched_required_skills.length}/${result.total_required_skills}`}
              defaultOpen
            >
              {result.matched_required_skills.length > 0 && (
                <div style={{ marginBottom: 10 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent-emerald)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    ✓ Found in your resume
                  </div>
                  {result.matched_required_skills.map((s, i) => <SkillPill key={i} label={s} variant="matched" />)}
                </div>
              )}
              {result.missing_required_skills.length > 0 && (
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent-rose)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    ✗ Missing — ranked by importance
                  </div>
                  {result.missing_required_skills.map((s, i) => <SkillPill key={i} label={s} variant="missing" />)}
                </div>
              )}
              {result.matched_required_skills.length === 0 && result.missing_required_skills.length === 0 && (
                <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>No required skills extracted from this JD.</p>
              )}
            </Collapsible>

            <Collapsible
              title="Preferred Skills"
              icon={BookOpen}
              iconColor="#818cf8"
              count={`${result.matched_preferred_skills.length} matched`}
            >
              {result.matched_preferred_skills.length > 0 && (
                <div style={{ marginBottom: 10 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: '#818cf8', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    ✓ Found
                  </div>
                  {result.matched_preferred_skills.map((s, i) => <SkillPill key={i} label={s} variant="preferred" />)}
                </div>
              )}
              {result.missing_preferred_skills.length > 0 && (
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Not Found
                  </div>
                  {result.missing_preferred_skills.map((s, i) => <SkillPill key={i} label={s} variant="keyword_miss" />)}
                </div>
              )}
            </Collapsible>

            <Collapsible
              title="ATS Keywords"
              icon={Tag}
              iconColor="var(--accent-amber)"
              count={`${result.matched_keywords.length}/${result.total_keywords} hit`}
            >
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10 }}>
                ATS systems scan for exact keyword matches. Missing keywords significantly reduce your score even if you have the skills.
              </p>
              {result.matched_keywords.length > 0 && (
                <div style={{ marginBottom: 10 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent-emerald)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Matched keywords</div>
                  {result.matched_keywords.map((k, i) => <SkillPill key={i} label={k} variant="keyword_hit" />)}
                </div>
              )}
              {result.missing_keywords.length > 0 && (
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent-amber)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Missing keywords — add these exact phrases to your resume</div>
                  {result.missing_keywords.map((k, i) => <SkillPill key={i} label={k} variant="keyword_miss" />)}
                </div>
              )}
            </Collapsible>

            <Collapsible
              title="ATS Formatting Checks"
              icon={LayoutTemplate}
              iconColor={scoreColor(result.section_scores.formatting)}
              count={`${result.formatting_issues.length} issue${result.formatting_issues.length !== 1 ? 's' : ''}`}
            >
              {result.formatting_positives.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  {result.formatting_positives.map((p, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 6 }}>
                      <CheckCircle2 size={13} style={{ color: 'var(--accent-emerald)', marginTop: 2, flexShrink: 0 }} />
                      <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{p}</span>
                    </div>
                  ))}
                </div>
              )}
              {result.formatting_issues.length > 0 && (
                <div>
                  {result.formatting_issues.map((iss, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 6 }}>
                      <XCircle size={13} style={{ color: 'var(--accent-rose)', marginTop: 2, flexShrink: 0 }} />
                      <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{iss}</span>
                    </div>
                  ))}
                </div>
              )}
              {result.formatting_issues.length === 0 && result.formatting_positives.length === 0 && (
                <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>No formatting data available.</p>
              )}
            </Collapsible>

          </div>
        )}

      </div>
    </>
  );
}
