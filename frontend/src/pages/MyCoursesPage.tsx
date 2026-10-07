import { useQuery } from '@tanstack/react-query'
import { ArrowRight, BookOpen, GraduationCap } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getFriendlyErrorMessage } from '../api/client'
import { getInstitutionCatalog, listEnrollments, listInstitutions } from '../api/education'

export function MyCoursesPage() {
  const coursesQuery = useQuery({
    queryKey: ['education', 'my-courses'],
    queryFn: async () => {
      const [enrollments, institutions] = await Promise.all([listEnrollments(), listInstitutions()])
      const catalogs = await Promise.all(institutions.map((institution) => getInstitutionCatalog(institution.id)))
      const enrolledIds = new Set(enrollments.map((enrollment) => enrollment.course_id))
      return catalogs.flatMap((catalog) => catalog.faculties.flatMap(({ faculty, departments }) => departments.flatMap(({ department, courses }) => courses
        .filter((course) => enrolledIds.has(course.id))
        .map((course) => ({ course, department, faculty, institution: catalog.institution })),
      )))
    },
  })

  return (
    <div className="page-stack learning-page">
      <section className="page-heading-row learning-heading">
        <div><span className="eyebrow">YOUR STUDY PLAN</span><h1>My Courses</h1><p>Courses where your enrollment is active.</p></div>
      </section>
      {coursesQuery.isPending ? <p className="learning-loading" role="status">Loading your courses…</p> : coursesQuery.isError ? (
        <div className="page-state page-state--error" role="alert"><h2>Courses unavailable</h2><p>{getFriendlyErrorMessage(coursesQuery.error)} Check that your school membership is active.</p><button className="button button--outline" type="button" onClick={() => void coursesQuery.refetch()}>Retry</button></div>
      ) : coursesQuery.data.length === 0 ? (
        <div className="learning-empty learning-empty--large"><GraduationCap size={28} aria-hidden="true" /><h2>No courses yet</h2><p>Browse a school and enroll in a course, or accept an invitation to activate your student membership.</p><Link className="button button--primary" to="/schools">Browse schools <ArrowRight size={16} aria-hidden="true" /></Link></div>
      ) : (
        <ul className="learning-enrolled-list">
          {coursesQuery.data.map(({ course, department, faculty, institution }) => <li key={course.id}>
            <div className="learning-course-code">{course.code}</div>
            <div className="learning-course-copy"><span className="learning-kicker">{institution.name} · {faculty.name}</span><h2>{course.name}</h2><p>{department.name}{course.description ? ` · ${course.description}` : ''}</p></div>
            <Link className="icon-link" to={`/courses/${course.id}`} aria-label={`Continue ${course.name}`}><BookOpen size={20} aria-hidden="true" /></Link>
          </li>)}
        </ul>
      )}
    </div>
  )
}