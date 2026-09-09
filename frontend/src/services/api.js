/**
 * PIA API Service — handles all backend communication.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

// Token storage — access + refresh tokens live in localStorage. Auth is
// optional (feature routes are public), so an absent token just means no
// Authorization header is sent.
const ACCESS_KEY = 'pia_access_token';
const REFRESH_KEY = 'pia_refresh_token';

export const auth = {
  getAccess: () => localStorage.getItem(ACCESS_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_KEY),
  set: ({ access_token, refresh_token }) => {
    if (access_token) localStorage.setItem(ACCESS_KEY, access_token);
    if (refresh_token) localStorage.setItem(REFRESH_KEY, refresh_token);
  },
  clear: () => {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
  isLoggedIn: () => !!localStorage.getItem(ACCESS_KEY),
};

class APIService {
  async request(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const token = auth.getAccess();
    const config = {
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
      ...options,
    };

    // Don't set Content-Type for FormData
    if (options.body instanceof FormData) {
      delete config.headers['Content-Type'];
    }

    const response = await fetch(url, config);

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `Request failed: ${response.status}`);
    }

    return response.json();
  }

  // Query
  async query(queryText, company = null, docType = null) {
    return this.request('/query', {
      method: 'POST',
      body: JSON.stringify({
        query: queryText,
        company: company || null,
        doc_type: docType || null,
      }),
    });
  }

  // Ingestion
  async ingest(dataDir = null, skipExtraction = false, force = false) {
    const formData = new FormData();
    if (dataDir) formData.append('data_dir', dataDir);
    formData.append('skip_extraction', skipExtraction);
    formData.append('force', force);

    return this.request('/ingest', {
      method: 'POST',
      body: formData,
    });
  }

  async uploadAndIngest(files, docType, company, skipExtraction = false) {
    const formData = new FormData();
    files.forEach(file => formData.append('files', file));
    formData.append('doc_type', docType);
    formData.append('company', company);
    formData.append('skip_extraction', skipExtraction);

    return this.request('/ingest/upload', {
      method: 'POST',
      body: formData,
    });
  }

  // Companies
  async getCompanies() {
    return this.request('/companies');
  }

  async getCompanyDetail(name) {
    return this.request(`/companies/${encodeURIComponent(name)}`);
  }

  // About the Company — grounded web report (overview/pros/cons/salaries/WLB/sources)
  async getCompanyAbout(company) {
    return this.request('/company/about', {
      method: 'POST',
      body: JSON.stringify({ company }),
    });
  }

  // Resume — ATS analysis: requires both resume PDF and JD PDF
  async analyzeResume(resumeFile, jdFile) {
    const formData = new FormData();
    formData.append('resume_file', resumeFile);
    formData.append('jd_file', jdFile);

    return this.request('/resume/analyze', {
      method: 'POST',
      body: formData,
    });
  }

  // Resume — streaming ATS analysis (SSE over POST). Calls:
  //   onStage({ stage, message })  as progress frames arrive
  //   onResult(report)             once with the final scorecard
  //   onError(message)             on failure (server error frame or transport)
  // EventSource can't POST multipart, so we read the response body manually.
  async analyzeResumeStream(resumeFile, jdFile, { onStage, onResult, onError } = {}) {
    const formData = new FormData();
    formData.append('resume_file', resumeFile);
    formData.append('jd_file', jdFile);

    let response;
    try {
      response = await fetch(`${API_BASE}/resume/analyze/stream`, {
        method: 'POST',
        body: formData,
      });
    } catch (err) {
      onError?.(err.message || 'Network error');
      return;
    }

    if (!response.ok || !response.body) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      onError?.(error.detail || `Request failed: ${response.status}`);
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    // Parse a single SSE block ("event: X\ndata: {...}") and dispatch it.
    const dispatch = (block) => {
      const lines = block.split('\n');
      let event = 'message';
      let data = '';
      for (const line of lines) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        else if (line.startsWith('data:')) data += line.slice(5).trim();
      }
      if (!data) return;
      let payload;
      try {
        payload = JSON.parse(data);
      } catch {
        return;
      }
      if (event === 'stage') onStage?.(payload);
      else if (event === 'result') onResult?.(payload);
      else if (event === 'error') onError?.(payload.error || 'Analysis failed');
    };

    try {
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const block = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          if (block.trim()) dispatch(block);
        }
      }
      if (buffer.trim()) dispatch(buffer);
    } catch (err) {
      onError?.(err.message || 'Stream interrupted');
    }
  }

  // Fast Prep — company and/or JD PDF + days left + level → day-by-day study plan
  async getFastPrepPlan({ company = '', daysLeft, level = 'medium', jdFile = null }) {
    const formData = new FormData();
    formData.append('company', company || '');
    formData.append('days_left', daysLeft);
    formData.append('level', level);
    if (jdFile) formData.append('jd_file', jdFile);

    return this.request('/fast-prep/plan', {
      method: 'POST',
      body: formData,
    });
  }

  // Fast Prep — web-grounded Top Asked questions (DSA + core), lazy-loaded
  async getTopAsked({ company, role = '' }) {
    return this.request('/fast-prep/questions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ company, role }),
    });
  }

  // Evaluation
  async runEval(modes = ['dense_only', 'hybrid', 'hybrid_reranked'], includeFaithfulness = false) {
    return this.request('/eval/run', {
      method: 'POST',
      body: JSON.stringify({
        modes,
        include_faithfulness: includeFaithfulness,
      }),
    });
  }

  async getEvalResults() {
    return this.request('/eval/results');
  }

  // Stats
  async getStats() {
    return this.request('/stats');
  }

  // Health
  async healthCheck() {
    const response = await fetch('/api/health');
    return response.json();
  }

  // ── Auth ──────────────────────────────────────────────────────────────
  // Feature routes are public; auth is optional. On success we persist both
  // tokens so subsequent request() calls send the Bearer header automatically.

  async register({ email, password, name = '' }) {
    const data = await this.request('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, name }),
    });
    auth.set(data);
    return data;
  }

  async login({ email, password }) {
    const data = await this.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    auth.set(data);
    return data;
  }

  async logout() {
    const refresh_token = auth.getRefresh();
    try {
      if (refresh_token) {
        await fetch(`${API_BASE}/auth/logout`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token }),
        });
      }
    } finally {
      auth.clear();
    }
  }

  async me() {
    return this.request('/auth/me');
  }
}

export const api = new APIService();
export default api;
