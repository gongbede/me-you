import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, BookOpen, Check, CircleAlert } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { getFriendlyErrorMessage } from '../api/client'
import {
  enrollInCourse,
  getCourse,
  getCourseProgress,
  getDepartment,
  getFaculty,
  getInstitution,
  getLessonProgress,
  listEnrollments,
  listLessons,
  listMyStudents,
  type LessonProgress,
} from '../api/education'

function learningAccessMessage(error: unknown): string {
  const message = getFriendlyErrorMessage(error)
  if (/membership|enrolled|not found|institution/i.test(message)) {
    return 'Your school membership may not be active. Accept an invitation or ask a school administrator to approve your student request.'
  }
  return message
}

export function CoursePage() {
  const { courseId = '' } = useParams()
  const queryClient = useQueryClient()
  const courseQuery = useQuery({ queryKey: ['education', 'course', courseId], queryFn: () => getCourse(courseId), enabled: Boolean(courseId) })
  const hierarchyQuery = useQuery({
    queryKey: ['education', 'course-hierarchy', courseId],
    queryFn: async () => {
      const course = courseQuery.data!
      const department = await getDepartment(course.department_id)
      const faculty = await getFaculty(department.faculty_id)
      const institution = await getInstitution(faculty.institution_id)
      return { department, faculty, institution }
    },
    enabled: Boolean(courseQuery.data),
  })
  const studentRecordsQuery = useQuery({ queryKey: ['education', 'my-records'], queryFn: listMyStudents })
  const enrollmentQuery = useQuery({ queryKey: ['education', 'enrollments'], queryFn: listEnrollments })
  const isEnrolled = enrollmentQuery.data?.some((enrollment) => enrollment.course_id === courseId) ?? false
  const schoolId = hierarchyQuery.data?.institution.id
  const hasStudentMembership = Boolean(schoolId && studentRecordsQuery.data?.some((student) => student.institution_id === schoolId))
  const lessonsQuery = useQuery({
    queryKey: ['education', 'course-lessons', courseId],
    queryFn: async () => {
      const [lessons, courseProgress] = await Promise.all([listLessons(courseId), getCourseProgress(courseId)])
      const lessonStates = await Promise.all(lessons.map(async (lesson) => ({ lesson, progress: await getLessonProgress(lesson.id) })))
      return { lessonStates, courseProgress }
    },
    enabled: isEnrolled,
  })
  const enrollMutation = useMutation({
    mutationFn: () => enrollInCourse(courseId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['education', 'enrollments'] }),
        queryClient.invalidateQueries({ queryKey: ['education', 'course-lessons', courseId] }),
        queryClient.invalidateQueries({ queryKey: ['education', 'my-courses'] }),
      ])
    },
  })

  if (courseQuery.isPending || studentRecordsQuery.isPending || enrollmentQuery.isPending || hierarchyQuery.isPending) {
    return <p className="learning-loading" role="status">Loading course details…</p>
  }
  if (courseQuery.isError || hierarchyQuery.isError || studentRecordsQuery.isError || enrollmentQuery.isError) {
    const error = courseQuery.error ?? hierarchyQuery.error ?? studentRecordsQuery.error ?? enrollmentQuery.error
    return <div className="page-state page-state--error" role="alert"><h1>Course unavailable</h1><p>{learningAccessMessage(error)}</p><Link className="button button--outline" to="/schools"><ArrowLeft size={16} aria-hidden="true" /> Schools</Link></div>
  }

  const course = courseQuery.data
  const school = hierarchyQuery.data.institution
  const courseProgress = lessonsQuery.data?.courseProgress
  const lessonStates: Array<{ lesson: { id: string; title: string; position: number }; progress: LessonProgress | null }> = lessonsQuery.data?.lessonStates ?? []

  return (
    <div className="page-stack learning-page">
      <Link className="learning-back-link" to={schoolId ? `/schools/${schoolId}` : '/schools'}><ArrowLeft size={16} aria-hidden="true" /> {school.name}</Link>
      <section className="learning-course-banner">
        <div><span className="eyebrow">{course.code} · {hierarchyQuery.data.faculty.name}</span><h1>{course.name}</h1><p>{course.description || 'Course learning materials and exercises.'}</p><span className="learning-kicker">{school.name} / {hierarchyQuery.data.department.name}</span></div>
        <BookOpen size={28} aria-hidden="true" />
      </section>

      {!hasStudentMembership ? (
        <div className="learning-rule-note" role="note"><CircleAlert size={19} aria-hidden="true" /><p>Enrollment requires an active <strong>STUDENT</strong> membership at this school. Accept an invitation or request to join; a school administrator must approve a join request.</p><Link to="/schools">Manage school access</Link></div>
      ) : !isEnrolled ? (
        <section className="learning-enroll-panel"><div><h2>Not enrolled yet</h2><p>Students with an active school membership can enroll themselves in this course.</p></div><button className="button button--primary" type="button" disabled={enrollMutation.isPending} onClick={() => enrollMutation.mutate()}>{enrollMutation.isPending ? 'Enrolling…' : 'Enroll in course'} <ArrowRight size={16} aria-hidden="true" /></button></section>
      ) : (
        <section className="learning-progress-section" aria-labelledby="course-progress-heading">
          <div className="learning-progress-copy"><div><span className="learning-kicker">COURSE PROGRESS</span><h2 id="course-progress-heading">{courseProgress ? `${courseProgress.completed_lessons} of ${courseProgress.published_lessons} lessons done` : 'Your progress'}</h2></div><strong>{Math.round(courseProgress?.progress_percent ?? 0)}%</strong></div>
          <progress aria-label="Course progress" max={100} value={courseProgress?.progress_percent ?? 0} />
        </section>
      )}

      {enrollMutation.isError && <p className="form-alert" role="alert">{learningAccessMessage(enrollMutation.error)} If the membership is active, ask a school administrator to check your student record.</p>}
      {isEnrolled && (lessonsQuery.isPending ? <p className="learning-loading" role="status">Loading lessons and progress…</p> : lessonsQuery.isError ? (
        <div className="inline-error" role="alert"><p>{learningAccessMessage(lessonsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void lessonsQuery.refetch()}>Retry</button></div>
      ) : lessonStates.length === 0 ? <p className="learning-empty">No published lessons are available in this course yet.</p> : (
        <section className="learning-section" aria-labelledby="lessons-heading">
          <div className="learning-section__heading"><div><h2 id="lessons-heading">Lessons</h2><p>Work through the course in order.</p></div><BookOpen size={20} aria-hidden="true" /></div>
          <ol className="learning-lesson-list">
            {lessonStates.map(({ lesson, progress }, index) => {
              const status = progress?.completed ? 'Done' : progress ? 'In progress' : 'Not started'
              return <li key={lesson.id}><span className={`learning-lesson-status${progress?.completed ? ' is-done' : progress ? ' is-progress' : ''}`} aria-label={status}>{progress?.completed ? <Check size={17} aria-hidden="true" /> : <span>{index + 1}</span>}</span><Link to={`/lessons/${lesson.id}`}><strong>{lesson.title}</strong><span>{status}</span></Link><ArrowRight size={17} aria-hidden="true" /></li>
            })}
          </ol>
        </section>
      ))}
    </div>
  )
}