import { House, LogOut, UserRound } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { Logo } from './Logo'
import { useAuth } from '../hooks/useAuth'

const tabs = [
  { to: '/', label: 'Home', icon: House, end: true },
  { to: '/profile', label: 'Profile', icon: UserRound, end: false },
]

export function AppShell() {
  const { user } = useAuth()

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Main navigation">
        <Logo variant="horizontal-white" size={38} />
        <div className="sidebar__section-label">YOUR SPACE</div>
        <nav className="sidebar__nav">
          {tabs.map(({ to, label, icon: Icon, end }) => (
            <NavLink className={({ isActive }) => `nav-link ${isActive ? 'is-active' : ''}`} end={end} key={to} to={to}>
              <Icon size={19} strokeWidth={2} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar__bottom">
          <div className="sidebar__user">
            <span className="avatar-initial" aria-hidden="true">{user?.username.slice(0, 1).toUpperCase()}</span>
            <span className="sidebar__user-copy"><strong>{user?.username}</strong><small>{user?.email}</small></span>
          </div>
          <NavLink className="nav-link nav-link--quiet" to="/logout">
            <LogOut size={18} aria-hidden="true" /><span>Sign out</span>
          </NavLink>
        </div>
      </aside>

      <div className="app-column">
        <header className="topbar">
          <div className="topbar__mobile-brand"><Logo variant="mark" size={36} /></div>
          <span className="topbar__greeting">A brighter day to learn something.</span>
          <span className="topbar__spark" aria-hidden="true">✦</span>
        </header>
        <main className="app-main"><Outlet /></main>
      </div>

      <nav className="mobile-tabs" aria-label="Mobile navigation">
        {tabs.map(({ to, label, icon: Icon, end }) => (
          <NavLink className={({ isActive }) => `mobile-tab ${isActive ? 'is-active' : ''}`} end={end} key={to} to={to}>
            <Icon size={21} aria-hidden="true" />
            <span>{label}</span>
          </NavLink>
        ))}
        <NavLink className="mobile-tab" to="/logout"><LogOut size={21} aria-hidden="true" /><span>Sign out</span></NavLink>
      </nav>
    </div>
  )
}