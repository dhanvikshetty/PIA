import { useState, useEffect } from 'react';
import { LogIn, UserPlus, Loader2, LogOut, CheckCircle2 } from 'lucide-react';
import api, { auth } from '../services/api';

export default function LoginPage() {
  const [mode, setMode] = useState('login'); // 'login' | 'register'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [user, setUser] = useState(null);

  useEffect(() => {
    if (auth.isLoggedIn()) {
      api.me().then(setUser).catch(() => auth.clear());
    }
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = mode === 'login'
        ? await api.login({ email, password })
        : await api.register({ email, password, name });
      setUser(data.user);
      setPassword('');
    } catch (err) {
      setError(err.message || 'Something went wrong');
    } finally {
      setLoading(false);
    }
  }

  async function handleLogout() {
    await api.logout();
    setUser(null);
    setEmail('');
  }

  if (user) {
    return (
      <>
        <div className="page-header">
          <h1 className="page-title">Account</h1>
          <p className="page-subtitle">You're signed in.</p>
        </div>
        <div className="page-body">
          <div className="auth-card">
            <div className="auth-signed-in">
              <CheckCircle2 size={40} style={{ color: 'var(--accent-emerald)' }} />
              <div>
                <div className="auth-user-name">{user.name || user.email}</div>
                <div className="auth-user-email">{user.email}</div>
              </div>
            </div>
            <button className="btn btn-secondary" onClick={handleLogout} style={{ width: '100%' }}>
              <LogOut size={16} /> Sign out
            </button>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">{mode === 'login' ? 'Sign in' : 'Create account'}</h1>
        <p className="page-subtitle">
          {mode === 'login'
            ? 'Sign in to your Puddy account.'
            : 'Register a new Puddy account.'}
        </p>
      </div>
      <div className="page-body">
        <form className="auth-card" onSubmit={handleSubmit}>
          {mode === 'register' && (
            <label className="auth-field">
              <span>Name</span>
              <input
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="Your name"
                autoComplete="name"
              />
            </label>
          )}
          <label className="auth-field">
            <span>Email</span>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              required
            />
          </label>
          <label className="auth-field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder={mode === 'register' ? 'At least 8 characters' : '••••••••'}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              minLength={8}
              required
            />
          </label>

          {error && <div className="auth-error">{error}</div>}

          <button className="btn btn-primary" type="submit" disabled={loading} style={{ width: '100%' }}>
            {loading ? <Loader2 size={16} className="spin" /> : (mode === 'login' ? <LogIn size={16} /> : <UserPlus size={16} />)}
            {mode === 'login' ? 'Sign in' : 'Create account'}
          </button>

          <div className="auth-switch">
            {mode === 'login' ? "Don't have an account?" : 'Already have an account?'}
            <button
              type="button"
              className="auth-switch-btn"
              onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }}
            >
              {mode === 'login' ? 'Register' : 'Sign in'}
            </button>
          </div>
        </form>
      </div>
    </>
  );
}
