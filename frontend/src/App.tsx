import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppErrorBoundary } from './components/AppErrorBoundary'
import { AppShell } from './components/AppShell'
import { ProtectedRoute } from './components/ProtectedRoute'
import { AuthProvider } from './hooks/useAuth'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage'
import { HomePage } from './pages/HomePage'
import { LoginPage } from './pages/LoginPage'
import { LogoutPage } from './pages/LogoutPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { ProfilePage } from './pages/ProfilePage'
import { PublicProfilePage } from './pages/PublicProfilePage'
import { RegisterPage } from './pages/RegisterPage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'
import { CoursePage } from './pages/CoursePage'
import { LessonPage } from './pages/LessonPage'
import { MyCoursesPage } from './pages/MyCoursesPage'
import { SchoolDetailPage } from './pages/SchoolDetailPage'
import { SchoolsPage } from './pages/SchoolsPage'
import { VerifyEmailPage } from './pages/VerifyEmailPage'
import { TeachingPage } from './pages/TeachingPage'
import { ClassroomsPage } from './pages/ClassroomsPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <AppErrorBoundary>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route path="/forgot-password" element={<ForgotPasswordPage />} />
              <Route path="/reset-password" element={<ResetPasswordPage />} />
              <Route path="/verify-email" element={<VerifyEmailPage />} />
              <Route element={<ProtectedRoute />}>
                <Route path="/logout" element={<LogoutPage />} />
                <Route element={<AppShell />}>
                  <Route index element={<HomePage />} />
                  <Route path="profile" element={<ProfilePage />} />
                  <Route path="schools" element={<SchoolsPage />} />
                  <Route path="schools/:institutionId" element={<SchoolDetailPage />} />
                  <Route path="my-courses" element={<MyCoursesPage />} />
                  <Route path="courses/:courseId" element={<CoursePage />} />
                  <Route path="courses/:courseId/classrooms" element={<ClassroomsPage />} />
                  <Route path="courses/:courseId/classrooms/:sessionId" element={<ClassroomsPage />} />
                  <Route path="lessons/:lessonId" element={<LessonPage />} />
                  <Route path="teaching" element={<TeachingPage />} />
                  <Route path="teaching/courses/:courseId" element={<TeachingPage />} />
                  <Route path="teaching/courses/:courseId/classrooms" element={<ClassroomsPage />} />
                  <Route path="teaching/courses/:courseId/classrooms/:sessionId" element={<ClassroomsPage />} />
                  <Route path="teaching/courses/:courseId/reviews" element={<TeachingPage />} />
                  <Route path="teaching/courses/:courseId/submissions/:submissionId" element={<TeachingPage />} />
                  <Route path="teaching/lessons/:lessonId" element={<TeachingPage />} />
                  <Route path="users/:userId" element={<PublicProfilePage />} />
                </Route>
              </Route>
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </AppErrorBoundary>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
