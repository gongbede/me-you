import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ImagePlus, PencilLine, Trash2, UserRound, X } from 'lucide-react'
import { ApiError, getFriendlyErrorMessage, type ApiSchemas } from '../api/client'
import { AVATAR_CONTENT_TYPES, clearAvatar, uploadAvatar, validateAvatarFile } from '../api/avatar'
import { createMyProfile, getMyProfile, updateMyProfile } from '../api/profile'
import { Field } from '../components/Field'

type EditableProfile = ApiSchemas['CreateProfile']

function ProfileForm({
  profile,
  onCancel,
  onSaved,
}: {
  profile: ApiSchemas['ProfileResponse'] | null
  onCancel: () => void
  onSaved: (profile: ApiSchemas['ProfileResponse']) => void
}) {
  const [error, setError] = useState<string | null>(null)
  const mutation = useMutation({
    mutationFn: (values: EditableProfile) => profile ? updateMyProfile(values) : createMyProfile(values),
    onSuccess: onSaved,
    onError: (reason) => setError(getFriendlyErrorMessage(reason)),
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    mutation.mutate({
      display_name: String(data.get('display_name') ?? '').trim(),
      bio: String(data.get('bio') ?? '').trim() || null,
      location: String(data.get('location') ?? '').trim() || null,
      website: String(data.get('website') ?? '').trim() || null,
      visibility: String(data.get('visibility') ?? 'NETWORK') as EditableProfile['visibility'],
    })
  }

  return (
    <form className="profile-form" onSubmit={(event) => void submit(event)}>
      {error && <div className="form-alert" role="alert">{error}</div>}
      <div className="profile-form__grid">
        <Field label="Display name" name="display_name" minLength={1} maxLength={100} defaultValue={profile?.display_name ?? ''} required />
        <Field label="Location" name="location" maxLength={200} defaultValue={profile?.location ?? ''} placeholder="City or campus" />
      </div>
      <div className="field">
        <label htmlFor="bio">A little about you</label>
        <textarea id="bio" name="bio" maxLength={2000} rows={4} defaultValue={profile?.bio ?? ''} placeholder="What are you curious about?" />
        <span className="field-help">Up to 2,000 characters</span>
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
      <div className="profile-form__actions">
        <button className="button button--primary" type="submit" disabled={mutation.isPending}>
          <Check size={17} aria-hidden="true" /> {mutation.isPending ? 'Saving…' : 'Save profile'}
        </button>
        {profile && <button className="button button--outline" type="button" onClick={onCancel} disabled={mutation.isPending}>
          <X size={17} aria-hidden="true" /> Cancel
        </button>}
      </div>
    </form>
  )
}

function AvatarControls({ profile }: { profile: ApiSchemas['ProfileResponse'] }) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [validationMessage, setValidationMessage] = useState<string | null>(null)
  const [progress, setProgress] = useState<number | null>(null)
  const previewUrlRef = useRef<string | null>(null)
  const queryClient = useQueryClient()

  useEffect(() => () => {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current)
  }, [])

  function clearPreview() {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current)
    previewUrlRef.current = null
    setPreview(null)
  }

  const uploadMutation = useMutation({
    mutationFn: (selectedFile: File) => uploadAvatar(selectedFile, setProgress),
    onSuccess: (updatedProfile) => {
      queryClient.setQueryData(['profile', 'me'], updatedProfile)
      setFile(null)
      setProgress(null)
      setValidationMessage(null)
      clearPreview()
    },
  })
  const removeMutation = useMutation({
    mutationFn: clearAvatar,
    onSuccess: (updatedProfile) => queryClient.setQueryData(['profile', 'me'], updatedProfile),
  })

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.currentTarget.files?.[0] ?? null
    event.currentTarget.value = ''
    setValidationMessage(null)
    clearPreview()
    setFile(null)
    if (!selected) return
    const validationError = validateAvatarFile(selected)
    if (validationError) {
      setValidationMessage(validationError)
      event.currentTarget.value = ''
      return
    }
    const objectUrl = URL.createObjectURL(selected)
    previewUrlRef.current = objectUrl
    setPreview(objectUrl)
    setFile(selected)
    uploadMutation.reset()
  }

  const uploadError = uploadMutation.isError ? getFriendlyErrorMessage(uploadMutation.error) : null
  const removeError = removeMutation.isError ? getFriendlyErrorMessage(removeMutation.error) : null

  return (
    <div className="avatar-controls">
      <div className="avatar-controls__preview">
        {preview
          ? <img src={preview} alt="Selected avatar preview" />
          : profile.profile_picture_url
            ? <img src={profile.profile_picture_url} alt={`${profile.display_name}'s avatar`} />
            : <UserRound size={28} aria-hidden="true" />}
      </div>
      <div className="avatar-controls__actions">
        <input id="avatar-file" className="avatar-file-input" type="file" accept={AVATAR_CONTENT_TYPES.join(',')} aria-label="Choose avatar image" onChange={chooseFile} />
        <label className="button button--outline avatar-file-label" htmlFor="avatar-file">
          <ImagePlus size={17} aria-hidden="true" /> Choose avatar
        </label>
        {file && <button className="button button--primary" type="button" disabled={uploadMutation.isPending} onClick={() => uploadMutation.mutate(file)}>
          <ImagePlus size={17} aria-hidden="true" /> {uploadMutation.isPending ? 'Uploading…' : 'Upload avatar'}
        </button>}
        {profile.profile_picture_url && <button className="button button--outline" type="button" disabled={removeMutation.isPending} onClick={() => removeMutation.mutate()}>
          <Trash2 size={16} aria-hidden="true" /> {removeMutation.isPending ? 'Removing…' : 'Remove avatar'}
        </button>}
      </div>
      <p className="field-help">JPEG, PNG, or WebP; maximum 5,000,000 bytes.</p>
      {validationMessage && <p className="form-alert" role="alert">{validationMessage}</p>}
      {uploadError && <p className="form-alert" role="alert">{uploadError}</p>}
      {removeError && <p className="form-alert" role="alert">{removeError}</p>}
      {uploadMutation.isSuccess && <p className="form-success" role="status">Avatar updated.</p>}
      {removeMutation.isSuccess && <p className="form-success" role="status">Avatar removed.</p>}
      {progress !== null && uploadMutation.isPending && <div className="avatar-progress" role="status" aria-live="polite">
        <progress value={progress} max={100} aria-label="Avatar upload progress" /><span>{progress}%</span>
      </div>}
    </div>
  )
}

export function ProfilePage() {
  const [editing, setEditing] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const queryClient = useQueryClient()
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

  function profileSaved(profile: ApiSchemas['ProfileResponse']) {
    queryClient.setQueryData(['profile', 'me'], profile)
    setEditing(false)
    setNotice('Profile saved.')
  }

  if (profileQuery.isPending) return <div className="page-state" role="status">Loading your profile…</div>
  if (profileQuery.isError) return (
    <div className="page-state page-state--error" role="alert">
      <h1>We couldn’t load your profile.</h1>
      <p>{getFriendlyErrorMessage(profileQuery.error)}</p>
      <button className="button button--outline" type="button" onClick={() => void profileQuery.refetch()}>Retry</button>
    </div>
  )

  const profile = profileQuery.data
  return (
    <div className="page-stack profile-page">
      <section className="page-heading-row">
        <div><span className="eyebrow">YOUR SPACE</span><h1>Profile</h1><p>Share a little of what makes you, you.</p></div>
        {profile && !editing && <button className="button button--outline" type="button" onClick={() => { setNotice(null); setEditing(true) }}>
          <PencilLine size={17} aria-hidden="true" /> Edit profile
        </button>}
      </section>
      {notice && <p className="form-success" role="status">{notice}</p>}
      <section className="profile-card" aria-label="Profile details">
        <div className="profile-card__identity">
          {profile ? <AvatarControls profile={profile} /> : <div className="profile-avatar"><UserRound size={30} aria-hidden="true" /></div>}
          <div className="profile-card__intro">
            <span className="eyebrow">{profile ? 'YOUR INTRODUCTION' : 'NOT SET UP YET'}</span>
            <h2>{profile?.display_name ?? 'Make it yours.'}</h2>
            <p>{profile?.visibility ? `Visible to ${profile.visibility.toLowerCase()} viewers` : 'Add a display name and a few details to get started.'}</p>
          </div>
        </div>
        {!profile || editing ? <ProfileForm key={profile?.updated_at ?? 'new-profile'} profile={profile} onCancel={() => setEditing(false)} onSaved={profileSaved} /> : (
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