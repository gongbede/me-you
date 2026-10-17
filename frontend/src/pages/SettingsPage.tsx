import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LoaderCircle, RotateCw } from 'lucide-react'
import {
  getNotificationPreferences,
  updateNotificationPreferences,
  type NotificationPreferences,
} from '../api/notifications'
import { getFriendlyErrorMessage } from '../api/client'

const notificationLabels: Record<keyof NotificationPreferences, string> = {
  COMMENT: 'Comments and replies',
  FOLLOW: 'New followers',
  LIKE: 'Post likes',
  MESSAGE: 'Messages',
  CLASS_ANNOUNCEMENT: 'Classroom announcements',
  EXERCISE_SUBMISSION: 'Exercise submissions',
  EXERCISE_REVIEWED: 'Exercise reviews',
}

export function SettingsPage() {
  const queryClient = useQueryClient()
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

  function togglePreference(type: keyof NotificationPreferences) {
    const preferences = preferencesQuery.data?.preferences
    if (!preferences) return
    saveMutation.mutate({ preferences: { [type]: !preferences[type] } })
  }

  return (
    <section className="page-shell">
      <header className="page-heading-row learning-heading">
        <div>
          <span className="eyebrow">ACCOUNT</span>
          <h1>Settings</h1>
        </div>
      </header>

      <div className="stacked-card-list">
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
          <h2>Account</h2>
          <p className="muted-copy">Manage sign-in details, sessions, and account safety settings.</p>
        </section>
      </div>
    </section>
  )
}
