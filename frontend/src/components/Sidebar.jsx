import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  MessageSquare,
  Building2,
  Zap,
  Users,
  FileText,
  Settings,
  BarChart3,
  Brain,
  ChevronLeft,
  ChevronRight,
  LogIn,
} from 'lucide-react';

export default function Sidebar({ isCollapsed, onToggle, isOpen, onClose }) {
  return (
    <>
      {isOpen && <div className="sidebar-overlay" onClick={onClose} />}

      <aside className={`sidebar ${isCollapsed ? 'collapsed' : ''} ${isOpen ? 'open' : ''}`}>
        <button className="sidebar-toggle" onClick={onToggle} aria-label="Toggle Sidebar">
          {isCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>

        <div className="sidebar-header">
          <div className="sidebar-logo">
            <div className="sidebar-logo-icon">
              <Brain size={22} />
            </div>
          </div>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-section-label">Main</div>
          <NavLink to="/" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} onClick={onClose} end>
            <LayoutDashboard size={18} />
            <span className="nav-link-text">Dashboard</span>
          </NavLink>
          <NavLink to="/query" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} onClick={onClose}>
            <MessageSquare size={18} />
            <span className="nav-link-text">Ask Puddy</span>
          </NavLink>
          <NavLink to="/companies" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} onClick={onClose}>
            <Building2 size={18} />
            <span className="nav-link-text">About Company</span>
          </NavLink>
          <NavLink to="/fast-prep" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} onClick={onClose}>
            <Zap size={18} />
            <span className="nav-link-text">Fast Prep</span>
          </NavLink>
          <NavLink to="/hr-questions" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} onClick={onClose}>
            <Users size={18} />
            <span className="nav-link-text">HR Qss</span>
          </NavLink>

          <div className="nav-section-label">Tools</div>
          <NavLink to="/resume" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} onClick={onClose}>
            <FileText size={18} />
            <span className="nav-link-text">Resume Analyzer</span>
          </NavLink>
          <NavLink to="/eval" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} onClick={onClose}>
            <BarChart3 size={18} />
            <span className="nav-link-text">Eval Dashboard</span>
          </NavLink>

          <div className="nav-section-label">System</div>
          <NavLink to="/login" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} onClick={onClose}>
            <LogIn size={18} />
            <span className="nav-link-text">Account</span>
          </NavLink>
          <NavLink to="/admin" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} onClick={onClose}>
            <Settings size={18} />
            <span className="nav-link-text">Admin</span>
          </NavLink>
        </nav>
      </aside>
    </>
  );
}
