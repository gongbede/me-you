import { BookOpen, Building2, House, LogOut, MessageSquare, RotateCw, Settings2, UserRound } from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Logo } from './Logo'
import { useAuth } from '../hooks/useAuth'
import { getTeachingCourses, listAdministeredInstitutions } from '../api/education'
import { NotificationBell } from './NotificationBell'
import { listConversations } from '../api/messaging'

const baseTabs = [
  { to: '/', label: 'Home', icon: House, end: true },
  { to: '/messages', label: 'Messages', icon: MessageSquare, end: false },
  { to: '/schools', label: 'Schools', icon: Building2, end: false },
  { to: '/my-courses', label: 'My Courses', icon: BookOpen, end: false },
  { to: '/profile', label: 'Profile', icon: UserRound, end: false },
]

export function AppShell() {
  const { user } = useAuth()
  const location = useLocation()
  const [isVisible, setIsVisible] = useState(() => !document.hidden)
  useEffect(() => {
    const update = () => setIsVisible(!document.hidden)
    document.addEventListener('visibilitychange', update)
    return () => document.removeEventListener('visibilitychange', update)
  }, [])
  const teachingQuery = useQuery({ queryKey: ['teaching', 'courses'], queryFn: getTeachingCourses })
  const administrationQuery = useQuery({ queryKey: ['administration', 'institutions'], queryFn: listAdministeredInstitutions })
  const messagesQuery = useQuery({
    queryKey: ['messages', 'conversations'],
    queryFn: listConversations,
    refetchInterval: isVisible ? 20_000 : false,
    refetchIntervalInBackground: false,
  })
  const unreadMessages = messagesQuery.data?.reduce((total, conversation) => total + conversation.unread_count, 0) ?? 0
  const tabs = [
    ...baseTabs.slice(0, 4),
    ...(teachingQuery.data?.length ? [{ to: '/teaching', label: 'Teaching', icon: BookOpen, end: false }] : []),
    ...(administrationQuery.data?.length ? [{ to: '/administration', label: 'Administration', icon: Settings2, end: false }] : []),
    baseTabs[4],
  ]
  const learningPath = location.pathname.startsWith('/courses/') || location.pathname.startsWith('/lessons/')
  const learningTabIsActive = (to: string, isActive: boolean) =>
    isActive || (to === '/my-courses' && learningPath) || (to === '/teaching' && location.pathname.startsWith('/teaching')) || (to === '/administration' && location.pathname.startsWith('/administration')) || (to === '/messages' && location.pathname.startsWith('/messages'))

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Main navigation">
        <Logo variant="horizontal-white" size={38} />
        <div className="sidebar__section-label">YOUR SPACE</div>
        <nav className="sidebar__nav">
          {tabs.map(({ to, label, icon: Icon, end }) => (
            <NavLink aria-label={label === 'Messages' && unreadMessages > 0 ? `Messages, ${unreadMessages} unread` : undefined} className={({ isActive }) => `nav-link ${learningTabIsActive(to, isActive) ? 'is-active' : ''}`} end={end} key={to} to={to}>
              <Icon size={19} strokeWidth={2} aria-hidden="true" />
              <span>{label}{label === 'Messages' && unreadMessages > 0 && <span className="nav-unread-badge">{unreadMessages > 99 ? '99+' : unreadMessages}</span>}</span>
            </NavLink>
          ))}
          {teachingQuery.isError && (
            <button className="nav-link nav-link--retry" type="button" onClick={() => void teachingQuery.refetch()}>
              <RotateCw size={19} aria-hidden="true" />
              <span>Retry Teaching</span>
            </button>
          )}
          {administrationQuery.isError && (
            <button className="nav-link nav-link--retry" type="button" onClick={() => void administrationQuery.refetch()}>
              <RotateCw size={19} aria-hidden="true" />
              <span>Retry Administration</span>
            </button>
          )}
          {messagesQuery.isError && (
            <button className="nav-link nav-link--retry" type="button" onClick={() => void messagesQuery.refetch()}>
              <RotateCw size={19} aria-hidden="true" />
              <span>Retry Messages</span>
            </button>
          )}
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
          <div className="topbar__actions"><span className="topbar__spark" aria-hidden="true">✦</span><NotificationBell /></div>
        </header>
        <main className="app-main"><Outlet /></main>
      </div>

      <nav className="mobile-tabs" aria-label="Mobile navigation" style={{ gridTemplateColumns: `repeat(${tabs.length + 1 + Number(teachingQuery.isError) + Number(administrationQuery.isError) + Number(messagesQuery.isError)}, minmax(0, 1fr))` }}>
        {tabs.map(({ to, label, icon: Icon, end }) => (
          <NavLink aria-label={label === 'Messages' && unreadMessages > 0 ? `Messages, ${unreadMessages} unread` : undefined} className={({ isActive }) => `mobile-tab ${learningTabIsActive(to, isActive) ? 'is-active' : ''}`} end={end} key={to} to={to}>
            <Icon size={21} aria-hidden="true" />
            <span>{label}{label === 'Messages' && unreadMessages > 0 && <span className="mobile-unread-badge">{unreadMessages > 99 ? '99+' : unreadMessages}</span>}</span>
          </NavLink>
        ))}
        {teachingQuery.isError && (
          <button className="mobile-tab mobile-tab--retry" type="button" onClick={() => void teachingQuery.refetch()}>
            <RotateCw size={21} aria-hidden="true" />
            <span>Retry Teaching</span>
          </button>
        )}
        {administrationQuery.isError && (
          <button className="mobile-tab mobile-tab--retry" type="button" onClick={() => void administrationQuery.refetch()}>
            <RotateCw size={21} aria-hidden="true" />
            <span>Retry Admin</span>
          </button>
        )}
        {messagesQuery.isError && (
          <button className="mobile-tab mobile-tab--retry" type="button" onClick={() => void messagesQuery.refetch()}>
            <RotateCw size={21} aria-hidden="true" />
            <span>Retry Messages</span>
          </button>
        )}
        <NavLink className="mobile-tab" to="/logout"><LogOut size={21} aria-hidden="true" /><span>Sign out</span></NavLink>
      </nav>
    </div>
  )
}