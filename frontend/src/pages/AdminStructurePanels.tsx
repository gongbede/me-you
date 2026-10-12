import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Save, Trash2, UserPlus } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { getFriendlyErrorMessage } from '../api/client'
import {
  assignTeacherToCourse,
  createCourse,
  createDepartment,
  createFaculty,
  deleteCourse,
  deleteDepartment,
  deleteFaculty,
  getInstitutionCatalog,
  listCourseTeacherAssignments,
  listInstitutionTeachers,
  removeTeacherFromCourse,
  updateCourse,
  updateDepartment,
  updateFaculty,
  type Course,
  type CourseInput,
  type Department,
  type DepartmentInput,
  type Faculty,
  type FacultyInput,
  type InstitutionCatalog,
} from '../api/education'

type StructureAction =
  | { type: 'create-faculty'; name: string }
  | { type: 'update-faculty'; faculty: Faculty; name: string }
  | { type: 'delete-faculty'; facultyId: string }
  | { type: 'create-department'; facultyId: string; name: string }
  | { type: 'update-department'; department: Department; name: string }
  | { type: 'delete-department'; departmentId: string }
  | { type: 'create-course'; departmentId: string; code: string; name: string }
  | { type: 'update-course'; course: Course; code: string; name: string }
  | { type: 'delete-course'; courseId: string }

function structureError(error: unknown): string {
  const message = getFriendlyErrorMessage(error)
  if (message.includes('still has')) return `${message}. Remove the dependent records first.`
  return message
}

function saveFacultyInput(faculty: Faculty, name: string): FacultyInput {
  return { name, description: faculty.description }
}

function saveDepartmentInput(department: Department, name: string): DepartmentInput {
  return { name, description: department.description }
}

function saveCourseInput(course: Course, code: string, name: string): CourseInput {
  return { code, name, description: course.description }
}

function NameEditor({
  initialName,
  label,
  onSave,
}: {
  initialName: string
  label: string
  onSave: (name: string) => void
}) {
  const [name, setName] = useState(initialName)
  return (
    <form className="admin-inline-form" onSubmit={(event) => { event.preventDefault(); if (name.trim()) onSave(name.trim()) }}>
      <label className="field"><span>{label}</span><input required maxLength={200} value={name} onChange={(event) => setName(event.currentTarget.value)} /></label>
      <button className="button button--outline" type="submit" disabled={!name.trim()}><Save size={15} aria-hidden="true" /> Save name</button>
    </form>
  )
}

function CourseEditor({ course, onSave }: { course: Course; onSave: (code: string, name: string) => void }) {
  const [code, setCode] = useState(course.code)
  const [name, setName] = useState(course.name)
  return (
    <form className="admin-inline-form admin-inline-form--course" onSubmit={(event) => { event.preventDefault(); if (code.trim() && name.trim()) onSave(code.trim(), name.trim()) }}>
      <label className="field"><span>Course code</span><input required maxLength={50} value={code} onChange={(event) => setCode(event.currentTarget.value)} /></label>
      <label className="field"><span>Course name</span><input required maxLength={200} value={name} onChange={(event) => setName(event.currentTarget.value)} /></label>
      <button className="button button--outline" type="submit" disabled={!code.trim() || !name.trim()}><Save size={15} aria-hidden="true" /> Save course</button>
    </form>
  )
}

function CreationForm({
  label,
  placeholder,
  onCreate,
  codeInput = false,
}: {
  label: string
  placeholder: string
  onCreate: (name: string, code?: string) => void
  codeInput?: boolean
}) {
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  return (
    <form className={`admin-inline-form${codeInput ? ' admin-inline-form--course' : ''}`} onSubmit={(event) => { event.preventDefault(); if (name.trim() && (!codeInput || code.trim())) { onCreate(name.trim(), code.trim()); setName(''); setCode('') } }}>
      {codeInput && <label className="field"><span>Course code</span><input required maxLength={50} value={code} onChange={(event) => setCode(event.currentTarget.value)} placeholder="e.g. SCI-101" /></label>}
      <label className="field"><span>{label}</span><input required maxLength={200} value={name} onChange={(event) => setName(event.currentTarget.value)} placeholder={placeholder} /></label>
      <button className="button button--outline" type="submit" disabled={!name.trim() || (codeInput && !code.trim())}><Plus size={15} aria-hidden="true" /> Add</button>
    </form>
  )
}

export function StructurePanel({ institutionId }: { institutionId: string }) {
  const queryClient = useQueryClient()
  const queryKey = ['administration', 'structure', institutionId]
  const structureQuery = useQuery({ queryKey, queryFn: () => getInstitutionCatalog(institutionId) })
  const [actionError, setActionError] = useState('')
  const mutation = useMutation({
    mutationFn: async (action: StructureAction) => {
      switch (action.type) {
        case 'create-faculty': return createFaculty(institutionId, { name: action.name, description: null })
        case 'update-faculty': return updateFaculty(action.faculty.id, saveFacultyInput(action.faculty, action.name))
        case 'delete-faculty': return deleteFaculty(action.facultyId)
        case 'create-department': return createDepartment(action.facultyId, { name: action.name, description: null })
        case 'update-department': return updateDepartment(action.department.id, saveDepartmentInput(action.department, action.name))
        case 'delete-department': return deleteDepartment(action.departmentId)
        case 'create-course': return createCourse(action.departmentId, { code: action.code, name: action.name, description: null })
        case 'update-course': return updateCourse(action.course.id, saveCourseInput(action.course, action.code, action.name))
        case 'delete-course': return deleteCourse(action.courseId)
      }
    },
    onSuccess: async () => {
      setActionError('')
      await queryClient.invalidateQueries({ queryKey })
    },
    onError: (error) => setActionError(structureError(error)),
  })

  function confirmDelete(label: string, action: StructureAction) {
    if (window.confirm(`Delete ${label}? This cannot be undone.`)) mutation.mutate(action)
  }

  if (structureQuery.isPending) return <p className="learning-loading" role="status">Loading school structure…</p>
  if (structureQuery.isError) return <div className="inline-error" role="alert"><p>{structureError(structureQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void structureQuery.refetch()}>Retry</button></div>
  const structure: InstitutionCatalog = structureQuery.data
  const courseHeadingId = `structure-${institutionId}`

  return (
    <section className="learning-section admin-panel" aria-labelledby={courseHeadingId}>
      <div className="admin-panel-heading"><div><h2 id={courseHeadingId}>School structure</h2><p>Create and maintain faculties, departments, and courses.</p></div></div>
      <CreationForm label="Faculty name" placeholder="e.g. Faculty of Science" onCreate={(name) => mutation.mutate({ type: 'create-faculty', name })} />
      {structure.faculties.length === 0 ? <p className="learning-empty learning-empty--compact">No faculties yet. Add one to start building the school structure.</p> : <div className="admin-structure-list">
        {structure.faculties.map(({ faculty, departments }) => <article className="admin-structure-faculty" key={faculty.id}>
          <div className="admin-structure-title"><h3>{faculty.name}</h3><button className="button button--outline" type="button" aria-label={`Delete faculty ${faculty.name}`} disabled={mutation.isPending} onClick={() => confirmDelete(`faculty ${faculty.name}`, { type: 'delete-faculty', facultyId: faculty.id })}><Trash2 size={15} aria-hidden="true" /></button></div>
          <details className="admin-editor"><summary>Rename faculty</summary><NameEditor initialName={faculty.name} label="Faculty name" onSave={(name) => mutation.mutate({ type: 'update-faculty', faculty, name })} /></details>
          <CreationForm label="Department name" placeholder="e.g. Biology" onCreate={(name) => mutation.mutate({ type: 'create-department', facultyId: faculty.id, name })} />
          {departments.length === 0 ? <p className="learning-empty learning-empty--compact">No departments in this faculty.</p> : <div className="admin-structure-departments">
            {departments.map(({ department, courses }) => <section className="admin-structure-department" key={department.id}>
              <div className="admin-structure-title"><h4>{department.name}</h4><button className="button button--outline" type="button" aria-label={`Delete department ${department.name}`} disabled={mutation.isPending} onClick={() => confirmDelete(`department ${department.name}`, { type: 'delete-department', departmentId: department.id })}><Trash2 size={15} aria-hidden="true" /></button></div>
              <details className="admin-editor"><summary>Rename department</summary><NameEditor initialName={department.name} label="Department name" onSave={(name) => mutation.mutate({ type: 'update-department', department, name })} /></details>
              <CreationForm codeInput label="Course name" placeholder="e.g. Introduction to Biology" onCreate={(name, code) => mutation.mutate({ type: 'create-course', departmentId: department.id, code: code ?? '', name })} />
              {courses.length === 0 ? <p className="learning-empty learning-empty--compact">No courses in this department.</p> : <ul className="admin-structure-courses">
                {courses.map((course) => <li key={course.id}>
                  <div className="admin-structure-title"><div><strong>{course.name}</strong><span>{course.code}</span></div><button className="button button--outline" type="button" aria-label={`Delete course ${course.name}`} disabled={mutation.isPending} onClick={() => confirmDelete(`course ${course.name}`, { type: 'delete-course', courseId: course.id })}><Trash2 size={15} aria-hidden="true" /></button></div>
                  <details className="admin-editor"><summary>Edit course</summary><CourseEditor course={course} onSave={(code, name) => mutation.mutate({ type: 'update-course', course, code, name })} /></details>
                </li>)}
              </ul>}
            </section>)}
          </div>}
        </article>)}
      </div>}
      {mutation.isPending && <p className="learning-loading" role="status">Saving school structure…</p>}
      {actionError && <p className="form-alert" role="alert">{actionError}</p>}
    </section>
  )
}

type TeacherAdminData = {
  teachers: Awaited<ReturnType<typeof listInstitutionTeachers>>
  courses: Array<{ course: Course; assignments: Awaited<ReturnType<typeof listCourseTeacherAssignments>> }>
}

export function TeachersPanel({ institutionId }: { institutionId: string }) {
  const queryClient = useQueryClient()
  const queryKey = ['administration', 'teachers', institutionId]
  const teachersQuery = useQuery({
    queryKey,
    queryFn: async (): Promise<TeacherAdminData> => {
      const [teachers, catalog] = await Promise.all([
        listInstitutionTeachers(institutionId),
        getInstitutionCatalog(institutionId),
      ])
      const courses = catalog.faculties.flatMap(({ departments }) =>
        departments.flatMap(({ courses: departmentCourses }) => departmentCourses),
      )
      const courseAssignments = await Promise.all(courses.map(async (course) => ({
        course,
        assignments: await listCourseTeacherAssignments(course.id),
      })))
      return { teachers, courses: courseAssignments }
    },
  })
  const [selectedTeacherByCourse, setSelectedTeacherByCourse] = useState<Record<string, string>>({})
  const [actionError, setActionError] = useState('')
  const assignMutation = useMutation({
    mutationFn: ({ courseId, teacherId }: { courseId: string; teacherId: string }) => assignTeacherToCourse(courseId, teacherId),
    onSuccess: async () => {
      setActionError('')
      await queryClient.invalidateQueries({ queryKey })
    },
    onError: (error) => setActionError(getFriendlyErrorMessage(error)),
  })
  const removeMutation = useMutation({
    mutationFn: ({ courseId, teacherId }: { courseId: string; teacherId: string }) => removeTeacherFromCourse(courseId, teacherId),
    onSuccess: async () => {
      setActionError('')
      await queryClient.invalidateQueries({ queryKey })
    },
    onError: (error) => setActionError(getFriendlyErrorMessage(error)),
  })

  if (teachersQuery.isPending) return <p className="learning-loading" role="status">Loading teachers and courses…</p>
  if (teachersQuery.isError) return <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(teachersQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void teachersQuery.refetch()}>Retry</button></div>
  const { teachers, courses } = teachersQuery.data

  return (
    <section className="learning-section admin-panel" aria-labelledby="admin-teachers-title">
      <div className="admin-panel-heading"><div><h2 id="admin-teachers-title">Teachers</h2><p>Assign approved teacher records to courses.</p></div><UserPlus size={20} aria-hidden="true" /></div>
      {teachers.length === 0 ? <p className="learning-empty">No teacher records are available yet. A person must first request TEACHER membership and an administrator must approve that request. The teacher record will then appear here.</p> : courses.length === 0 ? <p className="learning-empty">Create a course in Structure before assigning teachers.</p> : <ul className="admin-teacher-courses">
        {courses.map(({ course, assignments }) => {
          const assignedIds = new Set(assignments.map((assignment) => assignment.teacher_id))
          const availableTeachers = teachers.filter((teacher) => !assignedIds.has(teacher.id))
          return <li key={course.id}>
            <div className="admin-teacher-course-heading"><div><strong>{course.name}</strong><span>{course.code}</span></div></div>
            {assignments.length ? <ul className="admin-assigned-teachers">{assignments.map((assignment) => {
              const teacher = teachers.find((item) => item.id === assignment.teacher_id)
              return <li key={assignment.id}><span>Teacher record {teacher?.user_id ?? assignment.teacher_id}</span><button className="button button--outline" type="button" disabled={removeMutation.isPending} onClick={() => { if (window.confirm('Remove this teacher from the course?')) removeMutation.mutate({ courseId: course.id, teacherId: assignment.teacher_id }) }}><Trash2 size={15} aria-hidden="true" /> Remove</button></li>
            })}</ul> : <p className="learning-empty learning-empty--compact">No teacher assigned.</p>}
            {availableTeachers.length > 0 && <form className="admin-inline-form" onSubmit={(event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const teacherId = selectedTeacherByCourse[course.id] ?? ''; if (teacherId) assignMutation.mutate({ courseId: course.id, teacherId }) }}>
              <label className="field"><span>Teacher record</span><select aria-label={`Teacher for ${course.name}`} value={selectedTeacherByCourse[course.id] ?? ''} onChange={(event) => { const teacherId = event.currentTarget.value; setSelectedTeacherByCourse((current) => ({ ...current, [course.id]: teacherId })) }}><option value="">Choose a teacher</option>{availableTeachers.map((teacher) => <option key={teacher.id} value={teacher.id}>{teacher.user_id}</option>)}</select></label>
              <button className="button button--outline" type="submit" disabled={!selectedTeacherByCourse[course.id] || assignMutation.isPending}><Plus size={15} aria-hidden="true" /> Assign</button>
            </form>}
          </li>
        })}
      </ul>}
      {(assignMutation.isPending || removeMutation.isPending) && <p className="learning-loading" role="status">Updating teacher assignment…</p>}
      {actionError && <p className="form-alert" role="alert">{actionError}</p>}
    </section>
  )
}