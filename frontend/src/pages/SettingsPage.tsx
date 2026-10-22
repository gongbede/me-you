import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle, RotateCw } from 'lucide-react'
import {
  changeMyPassword,
  deleteMyAccount,
  getMyAccount,
  requestEmailChange,
  requestEmailVerification,
  revokeAllSessions,
} from '../api/auth'
import {
  getNotificationPreferences,
  updateNotificationPreferences,
  type NotificationPreferences,
} from '../api/notifications'
import { getFriendlyErrorMessage } from '../api/client'
import { listBlockedUsers, unblockUser } from '../api/moderation'
import { getMyProfile, updateMyProfile } from '../api/profile'
import { useAuth } from '../hooks/useAuth'
import { useTheme } from '../hooks/useTheme'
import { PageHeader } from '../components/PageHeader'

const notificationLabels: Record<keyof NotificationPreferences, string> = {
  COMMENT: 'Comments and replies',
  FOLLOW: 'New followers',
  LIKE: 'Post likes',
  MESSAGE: 'Messages',
  CLASS_ANNOUNCEMENT: 'Classroom announcements',
  EXERCISE_SUBMISSION: 'Exercise submissions',
  EXERCISE_REVIEWED: 'Exercise reviews',
  NEW_VIDEO: 'New videos from people you follow',
  VIDEO_COMMENT: 'Comments on your videos',
  VIDEO_LIKE: 'Likes on your videos',
  NEW_TRACK: 'New music tracks',
}

export function SettingsPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { logout } = useAuth()
  const { choice, setChoice } = useTheme()
  const [emailNotice, setEmailNotice] = useState<string | null>(null)
  const [deletionError, setDeletionError] = useState<string | null>(null)
  const accountQuery = useQuery({ queryKey: ['account', 'me'], queryFn: getMyAccount })
  const profileQuery = useQuery({ queryKey: ['profile', 'me'], queryFn: getMyProfile })
  const queryKey = ['notifications', 'preferences'] as const
  const preferencesQuery = useQuery({
    queryKey,
    queryFn: getNotificationPreferences,
  })
  const saveMutation = useMutation({
    mutationFn: updateNotificationPreferences,
    onSuccess: async (result) => {
      queryClient.setQueryData(queryKey, result)
    },
  })
  const blocksQuery = useInfiniteQuery({
    queryKey: ['moderation', 'blocks'],
    queryFn: ({ pageParam }) => listBlockedUsers(pageParam),
    initialPageParam: 0,
    getNextPageParam: (page, pages) => page.length === 50 ? pages.length * 50 : undefined,
  })
  const unblockMutation = useMutation({
    mutationFn: unblockUser,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['moderation', 'blocks'] })
    },
  })
  const verifyEmailMutation = useMutation({
    mutationFn: requestEmailVerification,
  })
  const emailChangeMutation = useMutation({
    mutationFn: requestEmailChange,
    onSuccess: (result) => setEmailNotice(result.message),
  })
  const privacyMutation = useMutation({
    mutationFn: updateMyProfile,
    onSuccess: (profile) => queryClient.setQueryData(['profile', 'me'], profile),
  })
  const signOutOnSuccess = async () => {
    await logout()
    navigate('/login')
  }
  const passwordMutation = useMutation({
    mutationFn: changeMyPassword,
    onSuccess: signOutOnSuccess,
  })
  const sessionsMutation = useMutation({
    mutationFn: revokeAllSessions,
    onSuccess: signOutOnSuccess,
  })
  const deleteMutation = useMutation({
    mutationFn: deleteMyAccount,
    onSuccess: signOutOnSuccess,
  })

  function togglePreference(type: keyof NotificationPreferences) {
    const preferences = preferencesQuery.data?.preferences
    if (!preferences) return
    saveMutation.mutate({ preferences: { [type]: !preferences[type] } })
  }
  const blockedUsers = blocksQuery.data?.pages.flatMap((page) => page) ?? []

  function submitForm(
    event: FormEvent<HTMLFormElement>,
    submit: (values: Record<string, string>) => void,
  ) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const values: Record<string, string> = {}
    data.forEach((value, key) => { values[key] = String(value) })
    submit(values)
    event.currentTarget.reset()
  }

  return (
    <section className="page-shell">
      <PageHeader section="ACCOUNT" title="Settings" description="Manage your account, privacy, and preferences." />

      <div className="stacked-card-list">
        <section className="card">
          <h2>Appearance</h2>
          <label className="field" htmlFor="theme-choice">
            <span>Theme</span>
            <select id="theme-choice" value={choice} onChange={(event) => {
              const nextChoice = event.currentTarget.value
              if (nextChoice === 'system' || nextChoice === 'light' || nextChoice === 'dark') setChoice(nextChoice)
            }}>
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </label>
          <p className="muted-copy">System follows your device appearance setting.</p>
        </section>

        <section className="card">
          <h2>Notifications</h2>
          {preferencesQuery.isPending ? (
            <p className="learning-loading" role="status"><LoaderCircle className="spin" aria-hidden="true" /> Loading notification preferences…</p>
          ) : preferencesQuery.isError ? (
            <div className="inline-error" role="alert">
              <p>{getFriendlyErrorMessage(preferencesQuery.error)}</p>
              <button className="button button--outline" type="button" onClick={() => void preferencesQuery.refetch()}><RotateCw size={16} aria-hidden="true" /> Retry</button>
            </div>
          ) : (
            <div className="settings-list" aria-label="Notification preferences" aria-busy={saveMutation.isPending}>
              {(Object.keys(notificationLabels) as (keyof NotificationPreferences)[]).map((type) => (
                <label className="settings-row" key={type}>
                  <span>{notificationLabels[type]}</span>
                  <input
                    type="checkbox"
                    checked={preferencesQuery.data.preferences[type]}
                    disabled={saveMutation.isPending}
                    onChange={() => togglePreference(type)}
                    aria-label={`Toggle ${notificationLabels[type].toLowerCase()} notifications`}
                  />
                </label>
              ))}
              {saveMutation.isPending && <p className="learning-loading" role="status">Saving preferences…</p>}
              {saveMutation.isSuccess && <p className="form-success" role="status">Notification preferences saved.</p>}
              {saveMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(saveMutation.error)}</p>}
            </div>
          )}
        </section>

        <section className="card">
          <h2>Blocked users</h2>
          {blocksQuery.isPending ? <p className="learning-loading" role="status">Loading blocked users…</p> : blocksQuery.isError ? (
            <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(blocksQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void blocksQuery.refetch()}>Retry</button></div>
          ) : blockedUsers.length === 0 ? <p className="muted-copy">You haven’t blocked anyone.</p> : (
            <ul className="settings-blocked-list">
              {blockedUsers.map((blocked) => <li key={blocked.id}><span>@{blocked.username}</span><button className="button button--outline" type="button" disabled={unblockMutation.isPending} onClick={() => unblockMutation.mutate(blocked.id)}>Unblock</button></li>)}
            </ul>
          )}
          {blocksQuery.hasNextPage && <button className="button button--outline" type="button" disabled={blocksQuery.isFetchingNextPage} onClick={() => void blocksQuery.fetchNextPage()}>{blocksQuery.isFetchingNextPage ? 'Loading…' : 'Load more blocked users'}</button>}
          {unblockMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(unblockMutation.error)}</p>}
        </section>

        <section className="card">
          <h2>Account</h2>
          {accountQuery.isPending ? <p className="learning-loading" role="status">Loading account details…</p> : accountQuery.isError ? (
            <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(accountQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void accountQuery.refetch()}>Retry</button></div>
          ) : (
            <>
              <p>Signed in as <strong>{accountQuery.data.email}</strong></p>
              {!accountQuery.data.email_verified_at && <div className="form-note" role="status">
                Your email is not verified. <button className="button button--outline" type="button" disabled={verifyEmailMutation.isPending} onClick={() => verifyEmailMutation.mutate()}>{verifyEmailMutation.isPending ? 'Sending…' : 'Resend verification email'}</button>
              </div>}
              {verifyEmailMutation.isSuccess && <p className="form-success" role="status">{verifyEmailMutation.data.message}</p>}
              {verifyEmailMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(verifyEmailMutation.error)}</p>}
              <form className="profile-form" onSubmit={(event) => submitForm(event, (values) => {
                setEmailNotice(null)
                emailChangeMutation.mutate({ email: values.email ?? '', current_password: values.current_password ?? '' })
              })}>
                <h3>Change email</h3>
                <label className="field"><span>New email address</span><input type="email" name="email" required maxLength={255} /></label>
                <label className="field"><span>Current password</span><input type="password" name="current_password" required minLength={8} maxLength={128} autoComplete="current-password" /></label>
                <button className="button button--primary" type="submit" disabled={emailChangeMutation.isPending}>{emailChangeMutation.isPending ? 'Sending…' : 'Send confirmation'}</button>
                {emailNotice && <p className="form-success" role="status">{emailNotice}</p>}
                {emailChangeMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(emailChangeMutation.error)}</p>}
              </form>
              <form className="profile-form" onSubmit={(event) => submitForm(event, (values) => passwordMutation.mutate({
                current_password: values.current_password ?? '',
                new_password: values.new_password ?? '',
              }))}>
                <h3>Change password</h3>
                <label className="field"><span>Current password</span><input type="password" name="current_password" required minLength={8} maxLength={128} autoComplete="current-password" /></label>
                <label className="field"><span>New password</span><input type="password" name="new_password" required minLength={8} maxLength={128} autoComplete="new-password" /></label>
                <button className="button button--primary" type="submit" disabled={passwordMutation.isPending}>{passwordMutation.isPending ? 'Updating…' : 'Update password'}</button>
                {passwordMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(passwordMutation.error)}</p>}
              </form>
            </>
          )}
        </section>

        <section className="card">
          <h2>Sessions</h2>
          <p className="muted-copy">Log out everywhere by revoking all active sessions.</p>
          <form className="profile-form" onSubmit={(event) => submitForm(event, (values) => sessionsMutation.mutate({ current_password: values.current_password ?? '' }))}>
            <label className="field"><span>Current password</span><input type="password" name="current_password" required minLength={8} maxLength={128} autoComplete="current-password" /></label>
            <button className="button button--outline" type="submit" disabled={sessionsMutation.isPending}>{sessionsMutation.isPending ? 'Revoking…' : 'Log out of all devices'}</button>
            {sessionsMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(sessionsMutation.error)}</p>}
          </form>
        </section>

        <section className="card">
          <h2>Privacy</h2>
          {profileQuery.isPending ? <p className="learning-loading" role="status">Loading privacy settings…</p> : profileQuery.isError ? (
            <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(profileQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void profileQuery.refetch()}>Retry</button></div>
          ) : (
            <>
              <label className="field" htmlFor="profile-visibility"><span>Profile visibility</span>
                <select id="profile-visibility" value={profileQuery.data.visibility} disabled={privacyMutation.isPending} onChange={(event) => privacyMutation.mutate({ visibility: event.target.value as typeof profileQuery.data.visibility })}>
                  <option value="PUBLIC">Everyone</option>
                  <option value="FOLLOWERS">Followers only</option>
                  <option value="AUTHENTICATED">Signed-in members</option>
                  <option value="NETWORK">My institution network</option>
                  <option value="PRIVATE">Only me</option>
                </select>
              </label>
              {privacyMutation.isSuccess && <p className="form-success" role="status">Privacy settings saved.</p>}
              {privacyMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(privacyMutation.error)}</p>}
            </>
          )}
          {profileQuery.isError && <p className="muted-copy">Set up a profile to manage its visibility. <Link to="/profile">Open profile</Link>.</p>}
        </section>

        <section className="card">
          <h2>Danger zone</h2>
          <p className="muted-copy">Deleting your account anonymizes retained activity and signs you out.</p>
          <form className="profile-form" onSubmit={(event) => submitForm(event, (values) => {
            setDeletionError(null)
            if (values.confirmation !== 'DELETE') {
              setDeletionError('Type DELETE to confirm account deletion.')
              return
            }
            deleteMutation.mutate({ current_password: values.current_password ?? '' })
          })}>
            <label className="field"><span>Type DELETE to confirm</span><input name="confirmation" required autoComplete="off" /></label>
            <label className="field"><span>Current password</span><input type="password" name="current_password" required minLength={8} maxLength={128} autoComplete="current-password" /></label>
            <button className="button button--outline" type="submit" disabled={deleteMutation.isPending}>{deleteMutation.isPending ? 'Deleting…' : 'Delete account'}</button>
            {deletionError && <p className="form-alert" role="alert">{deletionError}</p>}
            {deleteMutation.isError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(deleteMutation.error)}</p>}
          </form>
        </section>
      </div>
    </section>
  )
}
