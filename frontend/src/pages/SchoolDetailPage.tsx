import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, BookOpen, Building2 } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { getFriendlyErrorMessage } from '../api/client'
import { getInstitutionCatalog } from '../api/education'

export function SchoolDetailPage() {
  const { institutionId = '' } = useParams()
  const catalogQuery = useQuery({
    queryKey: ['education', 'catalog', institutionId],
    queryFn: () => getInstitutionCatalog(institutionId),
    enabled: Boolean(institutionId),
  })

  if (catalogQuery.isPending) return <p className="learning-loading" role="status">Loading school and courses…</p>
  if (catalogQuery.isError) {
    return <div className="page-state page-state--error" role="alert"><h1>School unavailable</h1><p>{getFriendlyErrorMessage(catalogQuery.error)} You may need an active membership to view this school.</p><Link className="button button--outline" to="/schools"><ArrowLeft size={16} aria-hidden="true" /> Back to schools</Link></div>
  }

  const { institution, faculties } = catalogQuery.data
  const courseCount = faculties.reduce((total, faculty) => total + faculty.departments.reduce((subtotal, department) => subtotal + department.courses.length, 0), 0)

  return (
    <div className="page-stack learning-page">
      <Link className="learning-back-link" to="/schools"><ArrowLeft size={16} aria-hidden="true" /> All schools</Link>
      <section className="learning-school-banner">
        <div className="learning-school-banner__icon"><Building2 size={25} aria-hidden="true" /></div>
        <div><span className="eyebrow">{institution.institution_type.replace('_', ' ')}</span><h1>{institution.name}</h1><p>{institution.description || institution.location || 'School information'}</p></div>
        <div className="learning-school-banner__count"><strong>{courseCount}</strong><span>courses</span></div>
      </section>
      {faculties.length === 0 ? <p className="learning-empty">This school has no faculties yet.</p> : faculties.map(({ faculty, departments }) => (
        <section className="learning-section" key={faculty.id} aria-labelledby={`faculty-${faculty.id}`}>
          <div className="learning-section__heading"><div><span className="learning-kicker">FACULTY</span><h2 id={`faculty-${faculty.id}`}>{faculty.name}</h2>{faculty.description && <p>{faculty.description}</p>}</div><Building2 size={20} aria-hidden="true" /></div>
          {departments.length === 0 ? <p className="learning-empty learning-empty--compact">No departments listed in this faculty.</p> : departments.map(({ department, courses }) => (
            <div className="learning-department" key={department.id}>
              <h3>{department.name}</h3>
              {courses.length === 0 ? <p className="learning-empty learning-empty--compact">No courses in this department.</p> : (
                <ul className="learning-course-list">
                  {courses.map((course) => <li key={course.id}><div className="learning-course-code">{course.code}</div><div className="learning-course-copy"><h4>{course.name}</h4><p>{course.description || 'Course details are available inside.'}</p></div><Link className="icon-link" to={`/courses/${course.id}`} aria-label={`Open ${course.name}`}><BookOpen size={19} aria-hidden="true" /></Link></li>)}
                </ul>
              )}
            </div>
          ))}
        </section>
      ))}
    </div>
  )
}