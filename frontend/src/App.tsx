import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense } from 'react'
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
import { ClassroomsIndexPage, ClassroomsPage } from './pages/ClassroomsPage'
import { NotificationsPage } from './pages/NotificationsPage'
import { MessagesPage } from './pages/MessagesPage'
import { PostDetailPage } from './pages/PostDetailPage'
import { MusicPlayerProvider } from './components/MusicPlayer'

const AdministrationPage = lazy(() => import('./pages/AdministrationPage').then((module) => ({ default: module.AdministrationPage })))
const AdminReportsPage = lazy(() => import('./pages/AdminReportsPage').then((module) => ({ default: module.AdminReportsPage })))
const ReelsPage = lazy(() => import('./pages/ReelsPage').then((module) => ({ default: module.ReelsPage })))
const SettingsPage = lazy(() => import('./pages/SettingsPage').then((module) => ({ default: module.SettingsPage })))
const SearchPage = lazy(() => import('./pages/SearchPage').then((module) => ({ default: module.SearchPage })))
const VideosPage = lazy(() => import('./pages/MediaLibraryPage').then((module) => ({ default: module.VideosPage })))
const MusicPage = lazy(() => import('./pages/MediaLibraryPage').then((module) => ({ default: module.MusicPage })))
const VideoWatchPage = lazy(() => import('./pages/VideoWatchPage').then((module) => ({ default: module.VideoWatchPage })))
const TrackDetailPage = lazy(() => import('./pages/MusicManagement').then((module) => ({ default: module.TrackDetailPage })))
const PlaylistDetailPage = lazy(() => import('./pages/MusicManagement').then((module) => ({ default: module.PlaylistDetailPage })))

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
          <MusicPlayerProvider>
          <AppErrorBoundary>
            <Suspense fallback={<p role="status" className="learning-loading">Loading page…</p>}>
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
                  <Route path="administration" element={<AdministrationPage />} />
                  <Route path="administration/schools/:institutionId" element={<AdministrationPage />} />
                  <Route path="notifications" element={<NotificationsPage />} />
                  <Route path="search" element={<SearchPage />} />
                  <Route path="posts/:postId" element={<PostDetailPage />} />
                  <Route path="admin/reports" element={<AdminReportsPage />} />
                  <Route path="settings" element={<SettingsPage />} />
                  <Route path="messages" element={<MessagesPage />} />
                  <Route path="messages/:conversationId" element={<MessagesPage />} />
                  <Route path="reels" element={<ReelsPage />} />
                  <Route path="videos" element={<VideosPage />} />
                  <Route path="videos/:videoId" element={<VideoWatchPage />} />
                  <Route path="music" element={<MusicPage />} />
                  <Route path="music/tracks/:trackId" element={<TrackDetailPage />} />
                  <Route path="music/playlists/:playlistId" element={<PlaylistDetailPage />} />
                  <Route path="my-courses" element={<MyCoursesPage />} />
                  <Route path="classrooms" element={<ClassroomsIndexPage />} />
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
            </Suspense>
          </AppErrorBoundary>
          </MusicPlayerProvider>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}
