import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, PencilLine, UserRound } from 'lucide-react'
import { createMyProfile, getMyProfile, updateMyProfile } from '../api/profile'
import { ApiError, getFriendlyErrorMessage, type ApiSchemas } from '../api/client'
import { Field } from '../components/Field'

type EditableProfile = ApiSchemas['CreateProfile']

function ProfileForm({ profile, onSaved }: {
  profile: ApiSchemas['ProfileResponse'] | null
  onSaved: () => void
}) {
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: (values: EditableProfile) =>
      profile ? updateMyProfile(values) : createMyProfile(values),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['profile', 'me'] })
      setSaved(true)
      setError(null)
      onSaved()
    },
    onError: (reason) => {
      setError(getFriendlyErrorMessage(reason))
      setSaved(false)
    },
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const visibility = String(data.get('visibility') ?? 'NETWORK') as EditableProfile['visibility']
    mutation.mutate({
      display_name: String(data.get('display_name') ?? '').trim(),
      bio: String(data.get('bio') ?? '').trim() || null,
      location: String(data.get('location') ?? '').trim() || null,
      website: String(data.get('website') ?? '').trim() || null,
      visibility,
    })
  }

  return (
    <form className="profile-form" onSubmit={(event) => void submit(event)}>
      {error && <div className="form-alert" role="alert">{error}</div>}
      {saved && <div className="form-success" role="status"><Check size={17} /> Profile saved.</div>}
      <div className="profile-form__grid">
        <Field label="Display name" name="display_name" minLength={1} maxLength={100} defaultValue={profile?.display_name ?? ''} required />
        <Field label="Location" name="location" maxLength={200} defaultValue={profile?.location ?? ''} placeholder="City or campus" />
      </div>
      <div className="field">
        <label htmlFor="bio">A little about you</label>
        <textarea id="bio" name="bio" maxLength={2000} rows={4} defaultValue={profile?.bio ?? ''} placeholder="What are you curious about?" />
      </div>
      <div className="profile-form__grid">
        <Field label="Website" name="website" type="url" maxLength={2048} defaultValue={profile?.website ?? ''} placeholder="https://" />
        <div className="field">
          <label htmlFor="visibility">Who can see your profile?</label>
          <select id="visibility" name="visibility" defaultValue={profile?.visibility ?? 'NETWORK'}>
            <option value="PUBLIC">Anyone</option>
            <option value="AUTHENTICATED">Signed-in members</option>
            <option value="NETWORK">My institution network</option>
            <option value="PRIVATE">Only me</option>
          </select>
        </div>
      </div>
      <button className="button button--primary" type="submit" disabled={mutation.isPending}>
        {mutation.isPending ? 'Saving…' : <><Check size={17} /> Save profile</>}
      </button>
    </form>
  )
}

export function ProfilePage() {
  const [editing, setEditing] = useState(false)
  const profileQuery = useQuery({
    queryKey: ['profile', 'me'],
    queryFn: async () => {
      try {
        return await getMyProfile()
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null
        throw error
      }
    },
  })

  if (profileQuery.isPending) return <div className="page-state" role="status">Loading your profile…</div>
  if (profileQuery.isError) {
    return (
      <div className="page-state page-state--error" role="alert">
        <h1>We couldn’t load your profile.</h1>
        <p>{getFriendlyErrorMessage(profileQuery.error)}</p>
        <button className="button button--outline" onClick={() => void profileQuery.refetch()}>Try again</button>
      </div>
    )
  }

  const profile = profileQuery.data
  return (
    <div className="page-stack profile-page">
      <section className="page-heading-row">
        <div>
          <span className="eyebrow">YOUR SPACE</span>
          <h1>Profile</h1>
          <p>Share a little of what makes you, you.</p>
        </div>
        {profile && !editing && (
          <button className="button button--outline" onClick={() => setEditing(true)}>
            <PencilLine size={17} /> Edit profile
          </button>
        )}
      </section>

      <section className="profile-card">
        <div className="profile-card__identity">
          <div className="profile-avatar" aria-hidden="true">
            {profile?.profile_picture_url ? <img src={profile.profile_picture_url} alt="" /> : <UserRound size={30} />}
          </div>
          <div>
            <span className="eyebrow">{profile ? 'YOUR INTRODUCTION' : 'NOT SET UP YET'}</span>
            <h2>{profile?.display_name ?? 'Make it yours.'}</h2>
            <p>{profile?.visibility ? `Visible to ${profile.visibility.toLowerCase()} viewers` : 'Add a display name and a few details to get started.'}</p>
          </div>
        </div>

        {!profile || editing ? (
          <ProfileForm
            key={profile?.updated_at ?? 'new-profile'}
            profile={profile}
            onSaved={() => setEditing(false)}
          />
        ) : (
          <div className="profile-details">
            <div><span>ABOUT</span><p>{profile.bio || 'Nothing here yet.'}</p></div>
            <div className="profile-form__grid">
              <div><span>LOCATION</span><p>{profile.location || 'Not added'}</p></div>
              <div><span>WEBSITE</span><p>{profile.website || 'Not added'}</p></div>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}