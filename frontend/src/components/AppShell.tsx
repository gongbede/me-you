import { Bell, BookOpen, Building2, ChevronDown, Ellipsis, House, LogOut, MessageSquare, RotateCw, Search, Settings2, UserRound, Users, X } from 'lucide-react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
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
import { getPlatformAdminAccess } from '../api/moderation'

const baseTabs = [
  { to: '/', label: 'Home', icon: House, end: true },
  { to: '/messages', label: 'Messages', icon: MessageSquare, end: false },
  { to: '/schools', label: 'Schools', icon: Building2, end: false },
  { to: '/my-courses', label: 'My Courses', icon: BookOpen, end: false },
  { to: '/profile', label: 'Profile', icon: UserRound, end: false },
]

const desktopPrimaryTabs = baseTabs.slice(0, 4)

const moreTabs = [
  { to: '/classrooms', label: 'Classrooms', icon: Users, end: false },
  { to: '/search', label: 'Search', icon: Search, end: false },
  { to: '/notifications', label: 'Notifications', icon: Bell, end: false },
  { to: '/settings', label: 'Settings', icon: Settings2, end: false },
  baseTabs[4],
]

export function AppShell() {
  const { user } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [searchText, setSearchText] = useState('')
  const [isVisible, setIsVisible] = useState(() => !document.hidden)
  const [isMoreOpen, setIsMoreOpen] = useState(false)
  const [isDesktopMoreOpen, setIsDesktopMoreOpen] = useState(false)
  const [isAvatarMenuOpen, setIsAvatarMenuOpen] = useState(false)
  const moreTriggerRef = useRef<HTMLButtonElement>(null)
  const moreSheetRef = useRef<HTMLElement>(null)
  const desktopMoreRef = useRef<HTMLDivElement>(null)
  const avatarMenuRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const update = () => setIsVisible(!document.hidden)
    document.addEventListener('visibilitychange', update)
    return () => document.removeEventListener('visibilitychange', update)
  }, [])
  const teachingQuery = useQuery({ queryKey: ['teaching', 'courses'], queryFn: getTeachingCourses })
  const administrationQuery = useQuery({ queryKey: ['administration', 'institutions'], queryFn: listAdministeredInstitutions })
  const platformAdminQuery = useQuery({ queryKey: ['platform-admin', 'access'], queryFn: getPlatformAdminAccess, enabled: Boolean(user), retry: false })
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
  const learningPath = location.pathname.startsWith('/courses/') || location.pathname.startsWith('/lessons/')
  const isMorePath = ['/profile', '/teaching', '/administration', '/classrooms', '/notifications', '/settings', '/logout', '/search', '/admin'].some((path) => location.pathname === path || location.pathname.startsWith(`${path}/`))
  const learningTabIsActive = (to: string, isActive: boolean) =>
    isActive || (to === '/my-courses' && learningPath) || (to === '/teaching' && location.pathname.startsWith('/teaching')) || (to === '/administration' && location.pathname.startsWith('/administration')) || (to === '/messages' && location.pathname.startsWith('/messages')) || (to === '/notifications' && location.pathname.startsWith('/notifications')) || (to === '/classrooms' && location.pathname.startsWith('/classrooms')) || (to === '/settings' && location.pathname.startsWith('/settings'))

  useEffect(() => {
    if (!isMoreOpen) return
    moreSheetRef.current?.querySelector<HTMLElement>('[data-more-first]')?.focus()
  }, [isMoreOpen])

  useEffect(() => {
    if (!isDesktopMoreOpen && !isAvatarMenuOpen) return
    const closeOnOutsideClick = (event: MouseEvent) => {
      const target = event.target
      if (!(target instanceof Node)) return
      if (!desktopMoreRef.current?.contains(target)) setIsDesktopMoreOpen(false)
      if (!avatarMenuRef.current?.contains(target)) setIsAvatarMenuOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setIsDesktopMoreOpen(false)
      setIsAvatarMenuOpen(false)
    }
    document.addEventListener('mousedown', closeOnOutsideClick)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('mousedown', closeOnOutsideClick)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [isDesktopMoreOpen, isAvatarMenuOpen])

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
      <div className="app-column">
        <header className="topbar">
          <div className="topbar__mobile-brand"><Logo variant="mark" size={36} /></div>
          <NavLink className="topbar__brand" to="/" aria-label="Me&You home"><Logo variant="horizontal" size={36} /></NavLink>
          <nav className="topbar__primary-nav" aria-label="Main navigation">
            {desktopPrimaryTabs.map(({ to, label, icon: Icon, end }) => (
              <NavLink aria-label={label === 'Messages' && unreadMessages > 0 ? `Messages, ${unreadMessages} unread` : label} className={({ isActive }) => `topbar__nav-link ${learningTabIsActive(to, isActive) ? 'is-active' : ''}`} end={end} key={to} to={to}>
                <Icon size={17} aria-hidden="true" /><span>{label}</span>
                {label === 'Messages' && unreadMessages > 0 && <span className="nav-unread-badge">{unreadMessages > 99 ? '99+' : unreadMessages}</span>}
              </NavLink>
            ))}
            {moreTabs.map(({ to, label, icon: Icon, end }) => (
              <NavLink aria-label={label === 'Notifications' && unreadNotifications > 0 ? `Notifications, ${unreadNotifications} unread` : label} className={({ isActive }) => `topbar__nav-link topbar__nav-link--collapsible ${learningTabIsActive(to, isActive) ? 'is-active' : ''}`} end={end} key={to} to={to}>
                <Icon size={17} aria-hidden="true" /><span>{label}</span>
                {label === 'Notifications' && unreadNotifications > 0 && <span className="nav-unread-badge">{unreadNotifications > 99 ? '99+' : unreadNotifications}</span>}
              </NavLink>
            ))}
            <div className="topbar-menu" ref={desktopMoreRef}>
              <button className="topbar__nav-link topbar__menu-trigger" type="button" aria-label="More navigation" aria-haspopup="true" aria-controls="topbar-more-menu" aria-expanded={isDesktopMoreOpen} onClick={() => { setIsDesktopMoreOpen(!isDesktopMoreOpen); setIsAvatarMenuOpen(false) }}>
                <Ellipsis size={18} aria-hidden="true" /><span>More</span><ChevronDown size={14} aria-hidden="true" />
              </button>
              {isDesktopMoreOpen && <nav id="topbar-more-menu" className="topbar-dropdown" aria-label="More navigation">
                {moreTabs.map(({ to, label, icon: Icon }) => (
                  <NavLink className={({ isActive }) => `topbar-dropdown__link topbar-dropdown__link--collapsible${learningTabIsActive(to, isActive) ? ' is-active' : ''}`} key={to} to={to} onClick={() => setIsDesktopMoreOpen(false)}>
                    <Icon size={18} aria-hidden="true" /><span>{label}{label === 'Notifications' && unreadNotifications > 0 ? ` (${unreadNotifications})` : ''}</span>
                  </NavLink>
                ))}
                {teachingQuery.data?.length ? <NavLink className={({ isActive }) => `topbar-dropdown__link${isActive || location.pathname.startsWith('/teaching') ? ' is-active' : ''}`} to="/teaching" onClick={() => setIsDesktopMoreOpen(false)}><BookOpen size={18} aria-hidden="true" /><span>Teaching</span></NavLink> : null}
                {administrationQuery.data?.length ? <NavLink className={({ isActive }) => `topbar-dropdown__link${isActive || location.pathname.startsWith('/administration') ? ' is-active' : ''}`} to="/administration" onClick={() => setIsDesktopMoreOpen(false)}><Settings2 size={18} aria-hidden="true" /><span>Administration</span></NavLink> : null}
                {platformAdminQuery.data?.is_platform_admin && <NavLink className={({ isActive }) => `topbar-dropdown__link${isActive ? ' is-active' : ''}`} to="/admin/reports" onClick={() => setIsDesktopMoreOpen(false)}><Bell size={18} aria-hidden="true" /><span>Reports</span></NavLink>}
                {teachingQuery.isError && <button className="topbar-dropdown__link" type="button" onClick={() => void teachingQuery.refetch()}><RotateCw size={18} aria-hidden="true" /><span>Retry Teaching</span></button>}
                {administrationQuery.isError && <button className="topbar-dropdown__link" type="button" onClick={() => void administrationQuery.refetch()}><RotateCw size={18} aria-hidden="true" /><span>Retry Administration</span></button>}
              </nav>}
            </div>
          </nav>
          <form className="topbar-search" role="search" onSubmit={(event) => { event.preventDefault(); navigate(`/search${searchText.trim() ? `?q=${encodeURIComponent(searchText.trim())}` : ''}`) }}>
            <label className="sr-only" htmlFor="topbar-search-input">Search</label>
            <Search size={17} aria-hidden="true" />
            <input id="topbar-search-input" value={searchText} maxLength={100} onChange={(event) => setSearchText(event.currentTarget.value)} placeholder="Search people, posts, schools" />
          </form>
          <div className="topbar__actions"><NotificationBell />
            <div className="topbar-menu" ref={avatarMenuRef}>
              <button className="topbar-avatar-trigger" type="button" aria-label="Open profile menu" aria-haspopup="true" aria-controls="topbar-profile-menu" aria-expanded={isAvatarMenuOpen} onClick={() => { setIsAvatarMenuOpen(!isAvatarMenuOpen); setIsDesktopMoreOpen(false) }}>
                {profileQuery.isError ? <RotateCw size={16} aria-hidden="true" /> : profileQuery.data?.profile_picture_url ? <img src={profileQuery.data.profile_picture_url} alt={`${profileQuery.data.display_name}'s avatar`} /> : <span aria-hidden="true">{user?.username.slice(0, 1).toUpperCase()}</span>}
              </button>
              {isAvatarMenuOpen && <nav id="topbar-profile-menu" className="topbar-dropdown topbar-dropdown--right" aria-label="Profile menu">
                <NavLink className="topbar-dropdown__link" to="/profile" onClick={() => setIsAvatarMenuOpen(false)}><UserRound size={18} aria-hidden="true" /><span>Profile</span></NavLink>
                <NavLink className="topbar-dropdown__link" to="/settings" onClick={() => setIsAvatarMenuOpen(false)}><Settings2 size={18} aria-hidden="true" /><span>Settings</span></NavLink>
                <NavLink className="topbar-dropdown__link" to="/logout" onClick={() => setIsAvatarMenuOpen(false)}><LogOut size={18} aria-hidden="true" /><span>Sign out</span></NavLink>
              </nav>}
            </div>
          </div>
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
            <NavLink className={({ isActive }) => `more-sheet__link${isActive ? ' is-active' : ''}`} to="/search" onClick={closeMoreSheet}><Search size={19} aria-hidden="true" /><span>Search</span></NavLink>
            {moreTabs.filter(({ to }) => to !== '/profile' && to !== '/search').map(({ to, label, icon: Icon }) => <NavLink key={to} className={({ isActive }) => `more-sheet__link${learningTabIsActive(to, isActive) ? ' is-active' : ''}`} to={to} onClick={closeMoreSheet}><Icon size={19} aria-hidden="true" /><span>{label}{label === 'Notifications' && unreadNotifications > 0 ? ` (${unreadNotifications})` : ''}</span></NavLink>)}
            <NavLink className={({ isActive }) => `more-sheet__link${isActive || location.pathname.startsWith('/search') ? ' is-active' : ''}`} to="/search" onClick={closeMoreSheet}><Search size={19} aria-hidden="true" /><span>Search</span></NavLink>
            {platformAdminQuery.data?.is_platform_admin && <NavLink className={({ isActive }) => `more-sheet__link${isActive ? ' is-active' : ''}`} to="/admin/reports" onClick={closeMoreSheet}><Bell size={19} aria-hidden="true" /><span>Reports</span></NavLink>}
            {teachingQuery.data?.length ? <NavLink className={({ isActive }) => `more-sheet__link${isActive || location.pathname.startsWith('/teaching') ? ' is-active' : ''}`} to="/teaching" onClick={closeMoreSheet}><BookOpen size={19} aria-hidden="true" /><span>Teaching</span></NavLink> : null}
            {administrationQuery.data?.length ? <NavLink className={({ isActive }) => `more-sheet__link${isActive || location.pathname.startsWith('/administration') ? ' is-active' : ''}`} to="/administration" onClick={closeMoreSheet}><Settings2 size={19} aria-hidden="true" /><span>Administration</span></NavLink> : null}
            <NavLink className={({ isActive }) => `more-sheet__link${isActive ? ' is-active' : ''}`} to="/logout" onClick={closeMoreSheet}><LogOut size={19} aria-hidden="true" /><span>Sign out</span></NavLink>
          </nav>
        </section>
      </>}
    </div>
  )
}