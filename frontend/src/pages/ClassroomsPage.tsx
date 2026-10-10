import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, CalendarClock, Check, Clock3, LoaderCircle, MessageCircle, Megaphone, Plus, Send, Users, Video } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { ApiError, getFriendlyErrorMessage } from '../api/client'
import {
  changeClassSessionState,
  createClassSession,
  getClassSessionAttendance,
  getCourse,
  getTeachingCourses,
  joinClassSession,
  listClassSessions,
  listClassSessionMessages,
  markClassSessionAttendance,
  sendClassSessionMessage,
  type ClassSession,
  type ClassSessionAttendance,
  type ClassSessionMessageType,
} from '../api/education'

function classroomError(error: unknown): string {
  if (error instanceof ApiError && error.status === 403) return 'You need an active teacher assignment or course enrollment to access this classroom.'
  if (error instanceof ApiError && error.status === 404) return 'This classroom or course is no longer available.'
  return getFriendlyErrorMessage(error)
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

function sessionStateLabel(status: ClassSession['status']): string {
  return {
    SCHEDULED: 'Upcoming',
    LIVE: 'Live now',
    ENDED: 'Ended',
    CANCELLED: 'Cancelled',
  }[status]
}

export function ClassroomScheduleForm({
  isSaving,
  onCancel,
  onSave,
}: {
  isSaving: boolean
  onCancel: () => void
  onSave: (input: Pick<ClassSession, 'title' | 'description' | 'starts_at' | 'ends_at'>) => Promise<void>
}) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [startsAt, setStartsAt] = useState('')
  const [endsAt, setEndsAt] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const cleanTitle = title.trim()
    const start = new Date(startsAt)
    const end = new Date(endsAt)
    if (!cleanTitle || !startsAt || !endsAt || !Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start) {
      setError('Choose a title and an end time after the start time.')
      return
    }
    setError(null)
    try {
      await onSave({ title: cleanTitle, description: description.trim() || null, starts_at: start.toISOString(), ends_at: end.toISOString() })
    } catch {
      setError('This classroom could not be scheduled. Please try again.')
    }
  }

  return (
    <form className="classroom-form" onSubmit={(event) => void submit(event)} noValidate>
      <div className="field">
        <label htmlFor="classroom-title">Class title</label>
        <input id="classroom-title" value={title} maxLength={200} required onChange={(event) => setTitle(event.target.value)} />
        <span className="teaching-form__limit">{title.length}/200</span>
      </div>
      <div className="field">
        <label htmlFor="classroom-description">Plan for the session</label>
        <textarea id="classroom-description" value={description} maxLength={4000} rows={3} onChange={(event) => setDescription(event.target.value)} />
        <span className="teaching-form__limit">{description.length}/4,000</span>
      </div>
      <div className="classroom-form__times">
        <div className="field"><label htmlFor="classroom-start">Starts</label><input id="classroom-start" type="datetime-local" value={startsAt} onChange={(event) => setStartsAt(event.target.value)} required /></div>
        <div className="field"><label htmlFor="classroom-end">Ends</label><input id="classroom-end" type="datetime-local" value={endsAt} onChange={(event) => setEndsAt(event.target.value)} required /></div>
      </div>
      {error && <p className="inline-error" role="alert">{error}</p>}
      <div className="teaching-actions">
        <button className="button button--primary" type="submit" disabled={isSaving}>{isSaving ? <LoaderCircle size={16} className="spin" aria-hidden="true" /> : <CalendarClock size={16} aria-hidden="true" />}{isSaving ? 'Scheduling…' : 'Schedule classroom'}</button>
        <button className="button button--outline" type="button" onClick={onCancel} disabled={isSaving}>Cancel</button>
      </div>
    </form>
  )
}

function ClassroomSchedule({ courseId, teacherMode }: { courseId: string; teacherMode: boolean }) {
  const queryClient = useQueryClient()
  const teachersQuery = useQuery({ queryKey: ['teaching', 'courses'], queryFn: getTeachingCourses, enabled: teacherMode })
  const studentCourseQuery = useQuery({ queryKey: ['education', 'course', courseId], queryFn: () => getCourse(courseId), enabled: !teacherMode })
  const course = teacherMode
    ? teachersQuery.data?.find((item) => item.id === courseId)
    : studentCourseQuery.data
  const sessionsQuery = useQuery({
    queryKey: ['classrooms', 'course', courseId],
    queryFn: () => listClassSessions(courseId),
    enabled: Boolean(course),
  })
  const [isCreating, setIsCreating] = useState(false)
  const createMutation = useMutation({
    mutationFn: (input: Pick<ClassSession, 'title' | 'description' | 'starts_at' | 'ends_at'>) => createClassSession(courseId, input),
    onSuccess: async () => {
      setIsCreating(false)
      await queryClient.invalidateQueries({ queryKey: ['classrooms', 'course', courseId] })
    },
  })
  const stateMutation = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'start' | 'cancel' }) => changeClassSessionState(id, action),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['classrooms', 'course', courseId] })
    },
  })

  const accessQuery = teacherMode ? teachersQuery : studentCourseQuery
  if (accessQuery.isPending) return <div className="page-state" role="status"><LoaderCircle className="spin" aria-hidden="true" /> Loading classrooms…</div>
  if (accessQuery.error) return <div className="page-state page-state--error" role="alert"><h2>Classrooms unavailable</h2><p>{classroomError(accessQuery.error)}</p></div>
  if (!course) return <div className="page-state page-state--error" role="alert"><h2>Classrooms unavailable</h2><p>You do not have access to this course.</p></div>

  const sessions = sessionsQuery.data ?? []
  return (
    <div className="page-stack classroom-page">
      <Link className="teaching-back" to={teacherMode ? `/teaching/courses/${courseId}` : `/courses/${courseId}`}><ArrowLeft size={17} aria-hidden="true" /> {course.name}</Link>
      <section className="page-heading-row teaching-heading">
        <div><span className="eyebrow">{course.code}</span><h1>Live classrooms</h1><p>{teacherMode ? 'Schedule class time and bring your course together.' : 'Join a live class or see what is coming up.'}</p></div>
        {teacherMode && !isCreating && <button className="button button--primary" type="button" onClick={() => setIsCreating(true)}><Plus size={17} aria-hidden="true" /> Schedule</button>}
      </section>
      {!teacherMode && <div className="classroom-note"><Video size={17} aria-hidden="true" /><span>Class chat and attendance are available here. Video calling requires a configured provider.</span></div>}
      {isCreating && <section className="teaching-editor" aria-labelledby="classroom-create-title"><h2 id="classroom-create-title">Schedule a classroom</h2><ClassroomScheduleForm isSaving={createMutation.isPending} onCancel={() => setIsCreating(false)} onSave={(input) => createMutation.mutateAsync(input).then(() => undefined)} /></section>}
      {createMutation.error && <p className="form-alert" role="alert">{classroomError(createMutation.error)}</p>}
      {stateMutation.error && <p className="form-alert" role="alert">{classroomError(stateMutation.error)}</p>}
      {sessionsQuery.isPending ? (
        <div className="page-state" role="status"><LoaderCircle className="spin" aria-hidden="true" /> Loading sessions…</div>
      ) : sessionsQuery.error ? (
        <div className="page-state page-state--error" role="alert"><h2>Sessions unavailable</h2><p>{classroomError(sessionsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void sessionsQuery.refetch()}>Try again</button></div>
      ) : sessions.length === 0 ? (
        <section className="teaching-empty" aria-labelledby="classrooms-empty-title"><CalendarClock size={27} aria-hidden="true" /><h2 id="classrooms-empty-title">No classrooms scheduled</h2><p>{teacherMode ? 'Set a time for your next live class.' : 'Your teacher has not scheduled a classroom yet.'}</p>{teacherMode && !isCreating && <button className="button button--primary" type="button" onClick={() => setIsCreating(true)}><Plus size={17} aria-hidden="true" /> Schedule first class</button>}</section>
      ) : (
        <div className="classroom-session-list" aria-label="Classroom sessions">
          {sessions.map((session) => (
            <article className="classroom-session" key={session.id}>
              <div className="classroom-session__status"><span className={`classroom-status classroom-status--${session.status.toLowerCase()}`}>{sessionStateLabel(session.status)}</span><span>{formatDate(session.starts_at)}</span></div>
              <h2>{session.title}</h2>
              {session.description && <p>{session.description}</p>}
              <div className="classroom-session__footer"><span><Clock3 size={15} aria-hidden="true" /> Until {formatDate(session.ends_at)}</span>
                <div className="teaching-actions">
                  {teacherMode && session.status === 'SCHEDULED' && <>
                    <Link className="button button--outline" to={`/teaching/courses/${courseId}/classrooms/${session.id}`}>Open room</Link>
                    <button className="button button--primary" type="button" disabled={stateMutation.isPending} onClick={() => stateMutation.mutate({ id: session.id, action: 'start' })}>Start class</button>
                    <button className="icon-button icon-button--danger" type="button" aria-label={`Cancel ${session.title}`} disabled={stateMutation.isPending} onClick={() => { if (window.confirm(`Cancel “${session.title}”?`)) stateMutation.mutate({ id: session.id, action: 'cancel' }) }}>×</button>
                  </>}
                  {session.status === 'LIVE' && <Link className="button button--primary" to={`${teacherMode ? '/teaching' : ''}/courses/${courseId}/classrooms/${session.id}`}>Join live class</Link>}
                  {teacherMode && session.status === 'ENDED' && <Link className="button button--outline" to={`/teaching/courses/${courseId}/classrooms/${session.id}`}>View room</Link>}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}

function ClassroomRoom({ courseId, sessionId, teacherMode }: { courseId: string; sessionId: string; teacherMode: boolean }) {
  const queryClient = useQueryClient()
  const attendancePageSize = 50
  const [messageType, setMessageType] = useState<ClassSessionMessageType>('CHAT')
  const [message, setMessage] = useState('')
  const sessionQuery = useQuery({
    queryKey: ['classrooms', 'course', courseId],
    queryFn: () => listClassSessions(courseId),
  })
  const classSession = sessionQuery.data?.find((item) => item.id === sessionId)
  const messagesQuery = useQuery({
    queryKey: ['classrooms', 'messages', sessionId],
    queryFn: () => listClassSessionMessages(sessionId),
    enabled: Boolean(classSession),
    refetchInterval: classSession?.status === 'LIVE' ? 5000 : false,
  })
  const attendanceQuery = useInfiniteQuery({
    queryKey: ['classrooms', 'attendance', sessionId],
    queryFn: ({ pageParam }) => getClassSessionAttendance(sessionId, pageParam, attendancePageSize),
    initialPageParam: 0,
    getNextPageParam: (lastPage, _pages, lastPageParam) =>
      lastPage.length === attendancePageSize ? lastPageParam + attendancePageSize : undefined,
    enabled: Boolean(classSession && teacherMode),
    refetchInterval: classSession?.status === 'LIVE' && teacherMode ? 10000 : false,
  })
  const attendance = attendanceQuery.data?.pages.flatMap((page) => page) ?? []
  const joinMutation = useMutation({
    mutationFn: () => joinClassSession(sessionId),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ['classrooms', 'attendance', sessionId] }),
  })
  const sendMutation = useMutation({
    mutationFn: () => sendClassSessionMessage(sessionId, message.trim(), messageType),
    onSuccess: async () => {
      setMessage('')
      await queryClient.invalidateQueries({ queryKey: ['classrooms', 'messages', sessionId] })
    },
  })
  const stateMutation = useMutation({
    mutationFn: (action: 'end') => changeClassSessionState(sessionId, action),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ['classrooms', 'course', courseId] }),
  })
  const attendanceMutation = useMutation({
    mutationFn: ({ userId, status }: { userId: string; status: ClassSessionAttendance['status'] }) => markClassSessionAttendance(sessionId, userId, status),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ['classrooms', 'attendance', sessionId] }),
  })

  if (sessionQuery.isPending) return <div className="page-state" role="status"><LoaderCircle className="spin" aria-hidden="true" /> Opening classroom…</div>
  if (sessionQuery.error) return <div className="page-state page-state--error" role="alert"><h2>Classroom unavailable</h2><p>{classroomError(sessionQuery.error)}</p></div>
  if (!classSession) return <div className="page-state page-state--error" role="alert"><h2>Classroom unavailable</h2><p>This session may have been removed or you may not belong to this course.</p></div>

  const backPath = `${teacherMode ? '/teaching' : ''}/courses/${courseId}/classrooms`
  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (message.trim()) await sendMutation.mutateAsync()
  }

  return (
    <div className="page-stack classroom-page">
      <Link className="teaching-back" to={backPath}><ArrowLeft size={17} aria-hidden="true" /> All classrooms</Link>
      <section className="classroom-room-heading">
        <div><span className={`classroom-status classroom-status--${classSession.status.toLowerCase()}`}>{sessionStateLabel(classSession.status)}</span><h1>{classSession.title}</h1><p>{classSession.description}</p><time dateTime={classSession.starts_at}>{formatDate(classSession.starts_at)} – {formatDate(classSession.ends_at)}</time></div>
        {teacherMode && classSession.status === 'LIVE' && <button className="button button--outline" type="button" disabled={stateMutation.isPending} onClick={() => { if (window.confirm('End this classroom for everyone?')) stateMutation.mutate('end') }}>End class</button>}
      </section>
      {joinMutation.isError && <p className="form-alert" role="alert">{classroomError(joinMutation.error)}</p>}
      {classSession.status === 'LIVE' && !joinMutation.isSuccess && <section className="classroom-join"><div><Users size={20} aria-hidden="true" /><div><strong>Class is live</strong><span>Join to register attendance and enter the room.</span></div></div><button className="button button--primary" type="button" disabled={joinMutation.isPending} onClick={() => joinMutation.mutate()}>{joinMutation.isPending ? <LoaderCircle size={16} className="spin" aria-hidden="true" /> : <Check size={16} aria-hidden="true" />}{joinMutation.isPending ? 'Joining…' : 'Join classroom'}</button></section>}
      {classSession.status !== 'LIVE' && <div className="classroom-note"><Clock3 size={17} aria-hidden="true" /><span>{classSession.status === 'SCHEDULED' ? 'This room opens when the teacher starts class.' : 'This classroom is closed to new messages.'}</span></div>}
      <div className="classroom-room-grid">
        <section className="classroom-chat" aria-labelledby="classroom-chat-title">
          <div className="classroom-chat__heading"><div><h2 id="classroom-chat-title">Class conversation</h2><p>Announcements and questions for this session.</p></div><MessageCircle size={20} aria-hidden="true" /></div>
          {messagesQuery.isPending ? <p className="learning-loading" role="status">Loading conversation…</p> : messagesQuery.error ? <div className="inline-error" role="alert"><p>{classroomError(messagesQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void messagesQuery.refetch()}>Retry</button></div> : (messagesQuery.data?.length ?? 0) === 0 ? <p className="learning-empty learning-empty--compact">No messages yet. Introduce yourself when class opens.</p> : (
            <ol className="classroom-messages" aria-label="Class messages">
              {messagesQuery.data?.map((item) => <li className={item.message_type === 'ANNOUNCEMENT' ? 'classroom-message classroom-message--announcement' : 'classroom-message'} key={item.id}><div><strong>{item.sender_name}</strong><time dateTime={item.created_at}>{formatDate(item.created_at)}</time></div>{item.message_type === 'ANNOUNCEMENT' && <span><Megaphone size={14} aria-hidden="true" /> Announcement</span>}<p>{item.content}</p></li>)}
            </ol>
          )}
          {(classSession.status === 'LIVE' && (teacherMode || joinMutation.isSuccess)) && <form className="classroom-composer" onSubmit={(event) => void sendMessage(event)}>
            {teacherMode && <div className="classroom-composer__mode" role="group" aria-label="Message type"><button type="button" className={messageType === 'CHAT' ? 'is-active' : ''} aria-pressed={messageType === 'CHAT'} onClick={() => setMessageType('CHAT')}><MessageCircle size={15} aria-hidden="true" /> Chat</button><button type="button" className={messageType === 'ANNOUNCEMENT' ? 'is-active' : ''} aria-pressed={messageType === 'ANNOUNCEMENT'} onClick={() => setMessageType('ANNOUNCEMENT')}><Megaphone size={15} aria-hidden="true" /> Announcement</button></div>}
            <label className="sr-only" htmlFor="classroom-message">{messageType === 'ANNOUNCEMENT' ? 'Class announcement' : 'Message'}</label>
            <textarea id="classroom-message" value={message} maxLength={5000} rows={2} placeholder={messageType === 'ANNOUNCEMENT' ? 'Share an update with the course…' : 'Ask a question…'} onChange={(event) => setMessage(event.target.value)} />
            {sendMutation.error && <p className="inline-error" role="alert">{classroomError(sendMutation.error)}</p>}
            <button className="button button--primary" type="submit" disabled={!message.trim() || sendMutation.isPending}>{sendMutation.isPending ? <LoaderCircle size={16} className="spin" aria-hidden="true" /> : <Send size={16} aria-hidden="true" />}{sendMutation.isPending ? 'Sending…' : messageType === 'ANNOUNCEMENT' ? 'Post announcement' : 'Send message'}</button>
          </form>}
        </section>
        {teacherMode && <section className="classroom-attendance" aria-labelledby="classroom-attendance-title"><div className="classroom-chat__heading"><div><h2 id="classroom-attendance-title">Attendance</h2><p>Enrolled students</p></div><Users size={20} aria-hidden="true" /></div>{attendanceQuery.isPending ? <p className="learning-loading" role="status">Loading attendance…</p> : attendanceQuery.error && !attendanceQuery.data ? <div className="inline-error" role="alert"><p>{classroomError(attendanceQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void attendanceQuery.refetch()}>Retry</button></div> : <><ul className="classroom-attendance__list">{attendance.map((record) => <AttendanceRow key={record.user_id} record={record} disabled={attendanceMutation.isPending} onChange={(status) => attendanceMutation.mutate({ userId: record.user_id, status })} />)}</ul>{attendanceQuery.error && <div className="inline-error" role="alert"><p>{classroomError(attendanceQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void attendanceQuery.fetchNextPage()}>Retry</button></div>}{attendanceQuery.hasNextPage && <button className="button button--outline classroom-attendance__more" type="button" disabled={attendanceQuery.isFetchingNextPage} onClick={() => void attendanceQuery.fetchNextPage()}>{attendanceQuery.isFetchingNextPage ? 'Loading…' : 'Load more students'}</button>}</>}</section>}
      </div>
    </div>
  )
}

function AttendanceRow({ record, disabled, onChange }: { record: ClassSessionAttendance; disabled: boolean; onChange: (status: ClassSessionAttendance['status']) => void }) {
  return <li className="classroom-attendance__row"><span>{record.username}</span><select aria-label={`Attendance for ${record.username}`} value={record.status} disabled={disabled} onChange={(event) => onChange(event.target.value as ClassSessionAttendance['status'])}><option value="ABSENT">Absent</option><option value="PRESENT">Present</option><option value="LATE">Late</option></select></li>
}

export function ClassroomsPage() {
  const { courseId = '', sessionId } = useParams()
  const { pathname } = useLocation()
  const teacherMode = pathname.startsWith('/teaching/')
  if (!courseId) return <div className="page-state page-state--error" role="alert"><h1>Classroom unavailable</h1><p>Choose a course to view its sessions.</p></div>
  if (sessionId) return <ClassroomRoom courseId={courseId} sessionId={sessionId} teacherMode={teacherMode} />
  return <ClassroomSchedule courseId={courseId} teacherMode={teacherMode} />
}