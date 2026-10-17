import { useState } from 'react'

const defaultPreferences = {
  follow: true,
  messages: true,
  comments: true,
  course_updates: false,
}

export function SettingsPage() {
  const [preferences, setPreferences] = useState(defaultPreferences)

  function togglePreference(key: keyof typeof defaultPreferences) {
    setPreferences((current) => ({ ...current, [key]: !current[key] }))
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
          <div className="settings-list" aria-label="Notification preferences">
            <label className="settings-row">
              <span>New followers</span>
              <input type="checkbox" checked={preferences.follow} onChange={() => togglePreference('follow')} aria-label="Toggle new follower notifications" />
            </label>
            <label className="settings-row">
              <span>Messages</span>
              <input type="checkbox" checked={preferences.messages} onChange={() => togglePreference('messages')} aria-label="Toggle message notifications" />
            </label>
            <label className="settings-row">
              <span>Comments and replies</span>
              <input type="checkbox" checked={preferences.comments} onChange={() => togglePreference('comments')} aria-label="Toggle comment notifications" />
            </label>
            <label className="settings-row">
              <span>Course updates</span>
              <input type="checkbox" checked={preferences.course_updates} onChange={() => togglePreference('course_updates')} aria-label="Toggle course update notifications" />
            </label>
          </div>
        </section>

        <section className="card">
          <h2>Account</h2>
          <p className="muted-copy">Manage sign-in details, sessions, and account safety settings.</p>
        </section>
      </div>
    </section>
  )
}
