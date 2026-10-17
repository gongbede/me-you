import { Bell, BookOpen, Building2, Ellipsis, House, LogOut, MessageSquare, RotateCw, Settings2, UserRound, Users, X } from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import { Logo } from './Logo'
import { useAuth } from '../hooks/useAuth'
import { getTeachingCourses, listAdministeredInstitutions } from '../api/education'
import { NotificationBell } from './NotificationBell'
import { listConversations } from '../api/messaging'
import { getMyProfile } from '../api/profile'
import { getUnreadNotificationCount } from '../api/notifications'
import { ApiError } from '../api/client'
import { InstallPromptBanner } from './InstallPromptBanner'

const baseTabs = [
  { to: '/', label: 'Home', icon: House, end: true },
  { to: '/messages', label: 'Messages', icon: MessageSquare, end: false },
  { to: '/schools', label: 'Schools', icon: Building2, end: false },
  { to: '/my-courses', label: 'My Courses', icon: BookOpen, end: false },
  { to: '/profile', label: 'Profile', icon: UserRound, end: false },
]

const sidebarExtraTabs = [
  { to: '/classrooms', label: 'Classrooms', icon: Users, end: false },
  { to: '/notifications', label: 'Notifications', icon: Bell, end: false },
  { to: '/settings', label: 'Settings', icon: Settings2, end: false },
]

export function AppShell() {
  const { user } = useAuth()
  const location = useLocation()
  const [isVisible, setIsVisible] = useState(() => !document.hidden)
  const [isMoreOpen, setIsMoreOpen] = useState(false)
  const moreTriggerRef = useRef<HTMLButtonElement>(null)
  const moreSheetRef = useRef<HTMLElement>(null)
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
  const profileQuery = useQuery({
    queryKey: ['profile', 'me'],
    queryFn: async () => {
      try {
        return await getMyProfile()
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null
        throw error
      }
    },
    enabled: Boolean(user),
    retry: false,
  })
  const unreadMessages = messagesQuery.data?.reduce((total, conversation) => total + conversation.unread_count, 0) ?? 0
  const notificationUnreadQuery = useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: getUnreadNotificationCount,
    refetchInterval: isVisible ? 30_000 : false,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  })
  const unreadNotifications = notificationUnreadQuery.data?.unread_count ?? 0
  const tabs = [
    ...baseTabs.slice(0, 4),
    ...(teachingQuery.data?.length ? [{ to: '/teaching', label: 'Teaching', icon: BookOpen, end: false }] : []),
    ...(administrationQuery.data?.length ? [{ to: '/administration', label: 'Administration', icon: Settings2, end: false }] : []),
    ...sidebarExtraTabs,
    baseTabs[4],
  ]
  const learningPath = location.pathname.startsWith('/courses/') || location.pathname.startsWith('/lessons/')
  const isMorePath = ['/profile', '/teaching', '/administration', '/classrooms', '/notifications', '/settings', '/logout'].some((path) => location.pathname === path || location.pathname.startsWith(`${path}/`))
  const learningTabIsActive = (to: string, isActive: boolean) =>
    isActive || (to === '/my-courses' && learningPath) || (to === '/teaching' && location.pathname.startsWith('/teaching')) || (to === '/administration' && location.pathname.startsWith('/administration')) || (to === '/messages' && location.pathname.startsWith('/messages')) || (to === '/notifications' && location.pathname.startsWith('/notifications')) || (to === '/classrooms' && location.pathname.startsWith('/classrooms')) || (to === '/settings' && location.pathname.startsWith('/settings'))

  useEffect(() => {
    if (!isMoreOpen) return
    moreSheetRef.current?.querySelector<HTMLElement>('[data-more-first]')?.focus()
  }, [isMoreOpen])

  function closeMoreSheet() {
    setIsMoreOpen(false)
    moreTriggerRef.current?.focus()
  }

  function handleMoreKeyDown(event: ReactKeyboardEvent<HTMLElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      closeMoreSheet()
      return
    }
    if (event.key !== 'Tab') return
    const sheet = moreSheetRef.current
    if (!sheet) return
    const focusable = Array.from(sheet.querySelectorAll<HTMLElement>('a[href], button:not([disabled])'))
    const first = focusable[0]
    const last = focusable.at(-1)
    if (!first || !last) return
    if (event.shiftKey && (document.activeElement === first || !sheet.contains(document.activeElement))) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && (document.activeElement === last || !sheet.contains(document.activeElement))) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Main navigation">
        <Logo variant="horizontal-white" size={38} />
        <div className="sidebar__section-label">YOUR SPACE</div>
        <nav className="sidebar__nav">
          {tabs.map(({ to, label, icon: Icon, end }) => (
            <NavLink aria-label={label === 'Messages' && unreadMessages > 0 ? `Messages, ${unreadMessages} unread` : label === 'Notifications' && unreadNotifications > 0 ? `Notifications, ${unreadNotifications} unread` : undefined} className={({ isActive }) => `nav-link ${learningTabIsActive(to, isActive) ? 'is-active' : ''}`} end={end} key={to} to={to}>
              <Icon size={19} strokeWidth={2} aria-hidden="true" />
              <span>{label}{(label === 'Messages' && unreadMessages > 0) || (label === 'Notifications' && unreadNotifications > 0) ? <span className="nav-unread-badge">{(label === 'Messages' ? unreadMessages : unreadNotifications) > 99 ? '99+' : (label === 'Messages' ? unreadMessages : unreadNotifications)}</span> : null}</span>
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
          {notificationUnreadQuery.isError && (
            <button className="nav-link nav-link--retry" type="button" onClick={() => void notificationUnreadQuery.refetch()}>
              <RotateCw size={19} aria-hidden="true" />
              <span>Retry Notifications</span>
            </button>
          )}
        </nav>
        <div className="sidebar__bottom">
          <div className="sidebar__user">
            {profileQuery.isError ? (
              <button className="avatar-initial" type="button" aria-label="Retry loading avatar" onClick={() => void profileQuery.refetch()}>
                <RotateCw size={16} aria-hidden="true" />
              </button>
            ) : profileQuery.data?.profile_picture_url ? (
              <img className="avatar-initial sidebar__avatar-image" src={profileQuery.data.profile_picture_url} alt={`${profileQuery.data.display_name}'s avatar`} />
            ) : (
              <span className="avatar-initial" aria-hidden="true">{user?.username.slice(0, 1).toUpperCase()}</span>
            )}
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
        <InstallPromptBanner />
        <main className="app-main"><Outlet /></main>
      </div>

      <nav className="mobile-tabs" aria-label="Mobile navigation">
        {baseTabs.slice(0, 4).map(({ to, label, icon: Icon, end }) => (
          <NavLink aria-label={label === 'Messages' && unreadMessages > 0 ? `Messages, ${unreadMessages} unread` : undefined} className={({ isActive }) => `mobile-tab ${learningTabIsActive(to, isActive) ? 'is-active' : ''}`} end={end} key={to} to={to}>
            <Icon size={21} aria-hidden="true" />
            <span>{label}{label === 'Messages' && unreadMessages > 0 && <span className="mobile-unread-badge">{unreadMessages > 99 ? '99+' : unreadMessages}</span>}</span>
          </NavLink>
        ))}
        <button ref={moreTriggerRef} className={`mobile-tab${isMorePath ? ' is-active' : ''}`} type="button" aria-haspopup="dialog" aria-expanded={isMoreOpen} aria-controls="more-sheet" onClick={() => setIsMoreOpen(true)}>
          <Ellipsis size={21} aria-hidden="true" /><span>More</span>
        </button>
      </nav>

      {isMoreOpen && <>
        <button className="more-sheet-backdrop" type="button" aria-hidden="true" tabIndex={-1} onClick={closeMoreSheet} />
        <section id="more-sheet" ref={moreSheetRef} className="more-sheet" role="dialog" aria-modal="true" aria-labelledby="more-sheet-title" onKeyDown={handleMoreKeyDown}>
          <header className="more-sheet__header"><h2 id="more-sheet-title">More</h2><button className="icon-button" type="button" aria-label="Close More menu" onClick={closeMoreSheet}><X size={19} aria-hidden="true" /></button></header>
          <nav className="more-sheet__nav" aria-label="More navigation">
            <NavLink className={({ isActive }) => `more-sheet__link${isActive ? ' is-active' : ''}`} data-more-first to="/profile" onClick={closeMoreSheet}><UserRound size={19} aria-hidden="true" /><span>Profile</span></NavLink>
            {teachingQuery.data?.length ? <NavLink className={({ isActive }) => `more-sheet__link${isActive || location.pathname.startsWith('/teaching') ? ' is-active' : ''}`} to="/teaching" onClick={closeMoreSheet}><BookOpen size={19} aria-hidden="true" /><span>Teaching</span></NavLink> : null}
            {administrationQuery.data?.length ? <NavLink className={({ isActive }) => `more-sheet__link${isActive || location.pathname.startsWith('/administration') ? ' is-active' : ''}`} to="/administration" onClick={closeMoreSheet}><Settings2 size={19} aria-hidden="true" /><span>Administration</span></NavLink> : null}
            <NavLink className={({ isActive }) => `more-sheet__link${isActive ? ' is-active' : ''}`} to="/classrooms" onClick={closeMoreSheet}><Users size={19} aria-hidden="true" /><span>Classrooms</span></NavLink>
            <NavLink className={({ isActive }) => `more-sheet__link${isActive || location.pathname.startsWith('/notifications') ? ' is-active' : ''}`} to="/notifications" onClick={closeMoreSheet}><Bell size={19} aria-hidden="true" /><span>Notifications{unreadNotifications > 0 ? ` (${unreadNotifications})` : ''}</span></NavLink>
            <NavLink className={({ isActive }) => `more-sheet__link${isActive || location.pathname.startsWith('/settings') ? ' is-active' : ''}`} to="/settings" onClick={closeMoreSheet}><Settings2 size={19} aria-hidden="true" /><span>Settings</span></NavLink>
            <NavLink className={({ isActive }) => `more-sheet__link${isActive ? ' is-active' : ''}`} to="/logout" onClick={closeMoreSheet}><LogOut size={19} aria-hidden="true" /><span>Sign out</span></NavLink>
          </nav>
        </section>
      </>}
    </div>
  )
}