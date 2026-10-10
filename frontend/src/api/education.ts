import { ApiError, apiRequest, type ApiSchemas } from './client'

export type Institution = ApiSchemas['InstitutionResponse']
export type InstitutionRequest = ApiSchemas['InstitutionMembershipRequestResponse']
export type Faculty = ApiSchemas['FacultyResponse']
export type Department = ApiSchemas['DepartmentResponse']
export type Course = ApiSchemas['CourseResponse']
export type Enrollment = ApiSchemas['EnrollmentResponse']
export type Lesson = ApiSchemas['LessonResponse']
export type LessonInput = Pick<Lesson, 'title' | 'content' | 'position' | 'is_published'>
export type LessonProgress = ApiSchemas['LessonProgressResponse']
export type CourseProgress = ApiSchemas['CourseProgressResponse']
export type Exercise = ApiSchemas['ExerciseResponse']
export type ExerciseSubmission = ApiSchemas['ExerciseSubmissionResponse']
export type Student = ApiSchemas['StudentResponse']
export type Teacher = ApiSchemas['TeacherResponse']
export type SearchResult = ApiSchemas['SearchResponse']['items'][number]

export interface InstitutionCatalog {
  institution: Institution
  faculties: Array<{
    faculty: Faculty
    departments: Array<{ department: Department; courses: Course[] }>
  }>
}

export function listInstitutions(): Promise<Institution[]> {
  return apiRequest('/api/v1/institutions?limit=100')
}

export function listMyInvitations(): Promise<InstitutionRequest[]> {
  return apiRequest('/api/v1/institutions/invitations/me?limit=100')
}

export function listMyStudents(): Promise<Student[]> {
  return apiRequest('/api/v1/education/students/me?limit=100')
}

export function listMyTeachers(): Promise<Teacher[]> {
  return apiRequest('/api/v1/education/teachers/me?limit=100')
}

export function searchResources(query: string): Promise<ApiSchemas['SearchResponse']> {
  const params = new URLSearchParams({ query, limit: '100' })
  return apiRequest(`/api/v1/search?${params}`)
}

export function getInstitution(institutionId: string): Promise<Institution> {
  return apiRequest(`/api/v1/institutions/${institutionId}`)
}

export function requestStudentMembership(institutionId: string): Promise<InstitutionRequest> {
  return apiRequest(`/api/v1/institutions/${institutionId}/join-requests`, {
    method: 'POST',
    body: { role: 'STUDENT' },
  })
}

export function acceptInvitation(institutionId: string, requestId: string): Promise<ApiSchemas['InstitutionMembershipResponse']> {
  return apiRequest(`/api/v1/institutions/${institutionId}/invitations/${requestId}/accept`, {
    method: 'POST',
  })
}

export function declineInvitation(institutionId: string, requestId: string): Promise<InstitutionRequest> {
  return apiRequest(`/api/v1/institutions/${institutionId}/invitations/${requestId}/decline`, {
    method: 'POST',
  })
}

export function listFaculties(institutionId: string): Promise<Faculty[]> {
  return apiRequest(`/api/v1/institutions/${institutionId}/faculties?limit=100`)
}

export function listDepartments(facultyId: string): Promise<Department[]> {
  return apiRequest(`/api/v1/institutions/faculties/${facultyId}/departments?limit=100`)
}

export function listDepartmentCourses(departmentId: string): Promise<Course[]> {
  return apiRequest(`/api/v1/institutions/departments/${departmentId}/courses?limit=100`)
}

export function getCourse(courseId: string): Promise<Course> {
  return apiRequest(`/api/v1/institutions/courses/${courseId}`)
}

export function getDepartment(departmentId: string): Promise<Department> {
  return apiRequest(`/api/v1/institutions/departments/${departmentId}`)
}

export function getFaculty(facultyId: string): Promise<Faculty> {
  return apiRequest(`/api/v1/institutions/faculties/${facultyId}`)
}

export async function getInstitutionCatalog(institutionId: string): Promise<InstitutionCatalog> {
  const institution = await getInstitution(institutionId)
  const faculties = await listFaculties(institutionId)
  return {
    institution,
    faculties: await Promise.all(faculties.map(async (faculty) => ({
      faculty,
      departments: await Promise.all((await listDepartments(faculty.id)).map(async (department) => ({
        department,
        courses: await listDepartmentCourses(department.id),
      }))),
    }))),
  }
}

export function listEnrollments(): Promise<Enrollment[]> {
  return apiRequest('/api/v1/education/enrollments?limit=100')
}

export function enrollInCourse(courseId: string): Promise<Enrollment> {
  return apiRequest('/api/v1/education/enrollments', {
    method: 'POST',
    body: { course_id: courseId },
  })
}

export function listLessons(courseId: string): Promise<Lesson[]> {
  return apiRequest(`/api/v1/education/courses/${courseId}/lessons?limit=100`)
}

export function getLesson(lessonId: string): Promise<Lesson> {
  return apiRequest(`/api/v1/education/lessons/${lessonId}`)
}

export async function getLessonProgress(lessonId: string): Promise<LessonProgress | null> {
  try {
    return await apiRequest(`/api/v1/education/lessons/${lessonId}/progress`)
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}

export function setLessonProgress(lessonId: string, completed: boolean): Promise<LessonProgress> {
  return apiRequest(`/api/v1/education/lessons/${lessonId}/progress`, {
    method: 'POST',
    body: { completed },
  })
}

export function getCourseProgress(courseId: string): Promise<CourseProgress> {
  return apiRequest(`/api/v1/education/courses/${courseId}/progress`)
}

export function listExercises(lessonId: string): Promise<Exercise[]> {
  return apiRequest(`/api/v1/education/lessons/${lessonId}/exercises?limit=100`)
}

export function listExerciseSubmissions(exerciseId: string): Promise<ExerciseSubmission[]> {
  return apiRequest(`/api/v1/education/exercises/${exerciseId}/submissions?limit=100`)
}

export function submitExercise(
  exerciseId: string,
  attemptNumber: number,
  answerText: string,
): Promise<ExerciseSubmission> {
  return apiRequest(`/api/v1/education/exercises/${exerciseId}/submissions`, {
    method: 'POST',
    body: { attempt_number: attemptNumber, answer_text: answerText },
  })
}

export async function getTeachingCourses(): Promise<Course[]> {
  const teachers = await listMyTeachers()
  const teacherIdsByInstitution = new Map<string, Set<string>>()
  for (const teacher of teachers) {
    const teacherIds = teacherIdsByInstitution.get(teacher.institution_id) ?? new Set<string>()
    teacherIds.add(teacher.id)
    teacherIdsByInstitution.set(teacher.institution_id, teacherIds)
  }

  const coursesByInstitution = await Promise.all([...teacherIdsByInstitution].map(async ([institutionId, teacherIds]) => {
    const catalog = await getInstitutionCatalog(institutionId)
    const courses = catalog.faculties.flatMap(({ departments }) =>
      departments.flatMap(({ courses: departmentCourses }) => departmentCourses),
    )
    const assignments = await Promise.all(courses.map(async (course) => ({
      course,
      teachers: await apiRequest<Array<{ teacher_id: string }>>(
        `/api/v1/education/courses/${course.id}/teachers?limit=100`,
      ),
    })))
    return assignments
      .filter(({ teachers: assigned }) => assigned.some(({ teacher_id }) => teacherIds.has(teacher_id)))
      .map(({ course }) => course)
  }))

  return coursesByInstitution.flat()
}

export function getCourseLessons(courseId: string): Promise<Lesson[]> {
  return listLessons(courseId)
}

export function createLesson(courseId: string, lesson: LessonInput): Promise<Lesson> {
  return apiRequest(`/api/v1/education/courses/${courseId}/lessons`, {
    method: 'POST',
    body: lesson,
  })
}

export function updateLesson(lessonId: string, updates: Partial<LessonInput>): Promise<Lesson> {
  return apiRequest(`/api/v1/education/lessons/${lessonId}`, {
    method: 'PATCH',
    body: updates,
  })
}

export function deleteLesson(lessonId: string): Promise<void> {
  return apiRequest(`/api/v1/education/lessons/${lessonId}`, { method: 'DELETE' })
}