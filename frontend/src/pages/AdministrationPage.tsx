import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Building2, Check, CircleAlert, MailPlus, RotateCw, Save, Settings2, Trash2, UserRoundCheck, X } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError, getFriendlyErrorMessage, type ApiSchemas } from '../api/client'
import {
  approveInstitutionJoinRequest,
  cancelSentInstitutionInvitation,
  getInstitution,
  inviteInstitutionByEmail,
  listInstitutionJoinRequests,
  listInstitutionMembers,
  listAdministeredInstitutions,
  listSentInstitutionInvitations,
  rejectInstitutionJoinRequest,
  removeInstitutionMember,
  updateInstitution,
  updateInstitutionMemberRole,
  type Institution,
  type InstitutionRole,
} from '../api/education'

type AdminTab = 'members' | 'requests' | 'settings'

function adminError(error: unknown): string {
  const message = getFriendlyErrorMessage(error)
  if (message.includes('Final administrator cannot be demoted') || message.includes('Final administrator cannot be removed')) {
    return 'This is the school’s last active administrator. Add another administrator before changing or removing this role.'
  }
  if (error instanceof ApiError && error.status === 403) {
    return 'Only this school’s administrators can make that change.'
  }
  return message
}

function AdminHome({ institutions }: { institutions: Institution[] }) {
  if (institutions.length === 0) {
    return (
      <div className="page-stack admin-page">
        <section className="page-heading-row learning-heading"><div><span className="eyebrow">SCHOOL MANAGEMENT</span><h1>Administration</h1><p>Manage school memberships and learning structure.</p></div></section>
        <section className="learning-empty admin-empty" aria-labelledby="admin-empty-title">
          <Building2 size={27} aria-hidden="true" />
          <h2 id="admin-empty-title">No schools to administer</h2>
          <p>You’ll see schools here when you create one or an administrator gives you the ADMIN role.</p>
          <Link className="button button--primary" to="/schools">Find or create a school</Link>
        </section>
      </div>
    )
  }

  return (
    <div className="page-stack admin-page">
      <section className="page-heading-row learning-heading"><div><span className="eyebrow">SCHOOL MANAGEMENT</span><h1>Administration</h1><p>Schools you administer.</p></div></section>
      <ul className="admin-school-list" aria-label="Schools I administer">
        {institutions.map((institution) => (
          <li key={institution.id}>
            <div><span className="learning-kicker">{institution.institution_type.replace('_', ' ')}</span><h2>{institution.name}</h2><p>{institution.public_description || 'School settings and membership'}</p></div>
            <Link className="button button--outline" to={`/administration/schools/${institution.id}`}>Manage <ArrowLeft className="admin-arrow" size={16} aria-hidden="true" /></Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

function SchoolSettings({ institution }: { institution: Institution }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState(institution.name)
  const [description, setDescription] = useState(institution.public_description ?? '')
  const [isListed, setIsListed] = useState(institution.is_listed)
  const [saved, setSaved] = useState(false)
  const saveMutation = useMutation({
    mutationFn: (input: ApiSchemas['InstitutionCreate']) => updateInstitution(institution.id, input),
    onSuccess: async () => {
      setSaved(true)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['administration', 'institution', institution.id] }),
        queryClient.invalidateQueries({ queryKey: ['administration', 'institutions'] }),
      ])
    },
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaved(false)
    saveMutation.mutate({
      name: name.trim(),
      institution_type: institution.institution_type,
      description: institution.description,
      public_description: description.trim() || null,
      is_listed: isListed,
      website: institution.website,
      location: institution.location,
    })
  }

  return (
    <section className="learning-section admin-panel" aria-labelledby="admin-settings-title">
      <h2 id="admin-settings-title">School settings</h2>
      <form className="admin-form" onSubmit={submit}>
        <label className="field" htmlFor="admin-school-name"><span>Name</span><input id="admin-school-name" required maxLength={200} value={name} onChange={(event) => setName(event.currentTarget.value)} /></label>
        <label className="field" htmlFor="admin-school-description"><span>Public description</span><textarea id="admin-school-description" rows={3} maxLength={500} value={description} onChange={(event) => setDescription(event.currentTarget.value)} /></label>
        <label className="learning-listed-toggle"><input type="checkbox" checked={isListed} onChange={(event) => setIsListed(event.currentTarget.checked)} /><span>Show in Find a school</span></label>
        <button className="button button--primary" type="submit" disabled={!name.trim() || saveMutation.isPending}><Save size={16} aria-hidden="true" />{saveMutation.isPending ? 'Saving…' : 'Save settings'}</button>
      </form>
      {saveMutation.isError && <p className="form-alert" role="alert">{adminError(saveMutation.error)}</p>}
      {saved && <p className="form-success" role="status">School settings saved.</p>}
    </section>
  )
}

function MembersPanel({ institutionId }: { institutionId: string }) {
  const queryClient = useQueryClient()
  const queryKey = ['administration', 'members', institutionId]
  const membersQuery = useQuery({ queryKey, queryFn: () => listInstitutionMembers(institutionId) })
  const [email, setEmail] = useState('')
  const [inviteRole, setInviteRole] = useState<InstitutionRole>('STUDENT')
  const [inviteNotice, setInviteNotice] = useState('')
  const inviteMutation = useMutation({
    mutationFn: () => inviteInstitutionByEmail(institutionId, email.trim(), inviteRole),
    onSuccess: async () => {
      setEmail('')
      setInviteNotice('If an active account uses this address, its user can accept the invitation after signing in. If the person has not registered yet, invite again after registration. Email notifications are not set up yet.')
      await queryClient.invalidateQueries({ queryKey: ['administration', 'invitations', institutionId] })
    },
  })
  const roleMutation = useMutation({
    mutationFn: ({ membershipId, role }: { membershipId: string; role: InstitutionRole }) => updateInstitutionMemberRole(institutionId, membershipId, role),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  })
  const removeMutation = useMutation({
    mutationFn: ({ membershipId }: { institutionId: string; membershipId: string }) => removeInstitutionMember(institutionId, membershipId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  })

  function submitInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setInviteNotice('')
    inviteMutation.mutate()
  }

  function removeMember(membershipId: string) {
    if (!window.confirm('Remove this person from the school?')) return
    removeMutation.mutate({ institutionId, membershipId })
  }

  return (
    <div className="admin-panel-stack">
      <section className="learning-section admin-panel" aria-labelledby="admin-members-title">
        <div className="admin-panel-heading"><div><h2 id="admin-members-title">Members</h2><p>Manage school roles and membership.</p></div><UserRoundCheck size={20} aria-hidden="true" /></div>
        {membersQuery.isPending ? <p className="learning-loading" role="status">Loading members…</p> : membersQuery.isError ? <div className="inline-error" role="alert"><p>{adminError(membersQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void membersQuery.refetch()}>Retry</button></div> : membersQuery.data.length === 0 ? <p className="learning-empty learning-empty--compact">No members found.</p> : (
          <ul className="admin-record-list">
            {membersQuery.data.map((member) => <li key={member.id}>
              <div><strong>Member</strong><span>{member.user_id}</span></div>
              <label className="admin-role-control"><span className="sr-only">Role for {member.user_id}</span><select value={member.role} disabled={roleMutation.isPending} onChange={(event) => roleMutation.mutate({ membershipId: member.id, role: event.currentTarget.value as InstitutionRole })}><option value="ADMIN">Admin</option><option value="TEACHER">Teacher</option><option value="STUDENT">Student</option></select></label>
              <button className="button button--outline" type="button" aria-label={`Remove ${member.user_id}`} onClick={() => removeMember(member.id)} disabled={removeMutation.isPending}><Trash2 size={16} aria-hidden="true" /><span className="desktop-action-label">Remove</span></button>
            </li>)}
          </ul>
        )}
        {roleMutation.isError && <p className="form-alert" role="alert">{adminError(roleMutation.error)}</p>}
        {removeMutation.isError && <p className="form-alert" role="alert">{adminError(removeMutation.error)}</p>}
      </section>
      <section className="learning-section admin-panel" aria-labelledby="admin-invite-title">
        <h2 id="admin-invite-title">Invite a person</h2>
        <form className="admin-invite-form" onSubmit={submitInvite}>
          <label className="field" htmlFor="admin-invite-email"><span>Email</span><input id="admin-invite-email" type="email" autoComplete="email" required maxLength={320} value={email} onChange={(event) => setEmail(event.currentTarget.value)} /></label>
          <label className="field" htmlFor="admin-invite-role"><span>Role</span><select id="admin-invite-role" value={inviteRole} onChange={(event) => setInviteRole(event.currentTarget.value as InstitutionRole)}><option value="ADMIN">Admin</option><option value="TEACHER">Teacher</option><option value="STUDENT">Student</option></select></label>
          <button className="button button--primary" type="submit" disabled={!email.trim() || inviteMutation.isPending}><MailPlus size={16} aria-hidden="true" />{inviteMutation.isPending ? 'Sending…' : 'Invite'}</button>
        </form>
        <p className="admin-note">If an active account exists for the address, the person can accept after signing in. Otherwise, they must register first and you can invite them again. Email notification is not set up yet.</p>
        {inviteMutation.isError && <p className="form-alert" role="alert">{adminError(inviteMutation.error)}</p>}
        {inviteNotice && <p className="form-success" role="status">{inviteNotice}</p>}
      </section>
    </div>
  )
}

function RequestsPanel({ institutionId }: { institutionId: string }) {
  const queryClient = useQueryClient()
  const requestsKey = ['administration', 'requests', institutionId]
  const invitationsKey = ['administration', 'invitations', institutionId]
  const requestsQuery = useQuery({ queryKey: requestsKey, queryFn: () => listInstitutionJoinRequests(institutionId) })
  const invitationsQuery = useQuery({ queryKey: invitationsKey, queryFn: () => listSentInstitutionInvitations(institutionId) })
  const decisionMutation = useMutation({
    mutationFn: ({ requestId, decision }: { requestId: string; decision: 'approve' | 'reject' }) => decision === 'approve' ? approveInstitutionJoinRequest(institutionId, requestId) : rejectInstitutionJoinRequest(institutionId, requestId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: requestsKey }),
        queryClient.invalidateQueries({ queryKey: ['administration', 'members', institutionId] }),
      ])
    },
  })
  const cancelMutation = useMutation({
    mutationFn: ({ requestId }: { institutionId: string; requestId: string }) => cancelSentInstitutionInvitation(institutionId, requestId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: invitationsKey }),
  })
  const isLoading = requestsQuery.isPending || invitationsQuery.isPending
  const isError = requestsQuery.isError || invitationsQuery.isError
  if (isLoading) return <p className="learning-loading" role="status">Loading requests and invitations…</p>
  if (isError) return <div className="inline-error" role="alert"><p>{adminError(requestsQuery.error ?? invitationsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => { void requestsQuery.refetch(); void invitationsQuery.refetch() }}>Retry</button></div>
  const requests = requestsQuery.data ?? []
  const invitations = invitationsQuery.data ?? []

  return (
    <div className="admin-panel-stack">
      <section className="learning-section admin-panel" aria-labelledby="admin-requests-title">
        <div className="admin-panel-heading"><div><h2 id="admin-requests-title">Join requests</h2><p>Review people asking to join this school.</p></div></div>
        {requests.length === 0 ? <p className="learning-empty learning-empty--compact">No pending join requests.</p> : <ul className="admin-record-list">{requests.map((request) => <li key={request.id}>
          <div><strong>{request.role} request</strong><span>{request.user_id}</span></div>
          <div className="learning-row-actions">
            <button className="button button--primary" type="button" disabled={decisionMutation.isPending} onClick={() => decisionMutation.mutate({ requestId: request.id, decision: 'approve' })}><Check size={16} aria-hidden="true" /> Approve</button>
            <button className="button button--outline" type="button" disabled={decisionMutation.isPending} onClick={() => decisionMutation.mutate({ requestId: request.id, decision: 'reject' })}><X size={16} aria-hidden="true" /> Reject</button>
          </div>
        </li>)}</ul>}
        {decisionMutation.isError && <p className="form-alert" role="alert">{adminError(decisionMutation.error)}</p>}
      </section>
      <section className="learning-section admin-panel" aria-labelledby="admin-invitations-title">
        <h2 id="admin-invitations-title">Invitations sent</h2>
        {invitations.length === 0 ? <p className="learning-empty learning-empty--compact">No pending invitations sent by you.</p> : <ul className="admin-record-list">{invitations.map((invitation) => <li key={invitation.id}>
          <div><strong>{invitation.email}</strong><span>{invitation.role} · pending</span></div>
          <button className="button button--outline" type="button" disabled={cancelMutation.isPending} onClick={() => cancelMutation.mutate({ institutionId, requestId: invitation.id })}><X size={16} aria-hidden="true" /> Cancel invitation</button>
        </li>)}</ul>}
        {cancelMutation.isError && <p className="form-alert" role="alert">{adminError(cancelMutation.error)}</p>}
      </section>
    </div>
  )
}

function AdminSchool({ institution }: { institution: Institution }) {
  const [tab, setTab] = useState<AdminTab>('members')
  const tabs: Array<{ id: AdminTab; label: string }> = [
    { id: 'members', label: 'Members' },
    { id: 'requests', label: 'Requests' },
    { id: 'settings', label: 'Settings' },
  ]

  return (
    <div className="page-stack admin-page">
      <Link className="learning-back-link" to="/administration"><ArrowLeft size={16} aria-hidden="true" /> All administered schools</Link>
      <section className="page-heading-row learning-heading"><div><span className="eyebrow">SCHOOL ADMINISTRATION</span><h1>{institution.name}</h1><p>Members, requests, and school settings.</p></div><Settings2 size={22} aria-hidden="true" /></section>
      <div className="admin-tabs" role="tablist" aria-label="School administration sections">
        {tabs.map(({ id, label }) => <button key={id} type="button" role="tab" aria-selected={tab === id} className={tab === id ? 'is-active' : ''} onClick={() => setTab(id)}>{label}</button>)}
      </div>
      {tab === 'members' && <MembersPanel institutionId={institution.id} />}
      {tab === 'requests' && <RequestsPanel institutionId={institution.id} />}
      {tab === 'settings' && <SchoolSettings key={institution.id} institution={institution} />}
    </div>
  )
}

export function AdministrationPage() {
  const { institutionId } = useParams()
  const navigate = useNavigate()
  const institutionsQuery = useQuery({ queryKey: ['administration', 'institutions'], queryFn: listAdministeredInstitutions })
  const institutionQuery = useQuery({
    queryKey: ['administration', 'institution', institutionId],
    queryFn: () => getInstitution(institutionId ?? ''),
    enabled: Boolean(institutionId) && Boolean(institutionsQuery.data?.some((institution) => institution.id === institutionId)),
  })

  if (institutionsQuery.isPending) return <div className="page-state" role="status">Loading administration…</div>
  if (institutionsQuery.isError) return <div className="page-state page-state--error" role="alert"><CircleAlert aria-hidden="true" /><h1>Administration unavailable</h1><p>{adminError(institutionsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void institutionsQuery.refetch()}><RotateCw size={16} aria-hidden="true" /> Retry</button></div>
  if (!institutionId) return <AdminHome institutions={institutionsQuery.data} />
  if (!institutionsQuery.data.some((institution) => institution.id === institutionId)) {
    return <div className="page-state page-state--error" role="alert"><h1>School unavailable</h1><p>You do not have administrator access to this school.</p><button className="button button--outline" type="button" onClick={() => navigate('/administration')}>Back to administration</button></div>
  }
  if (institutionQuery.isPending) return <div className="page-state" role="status">Loading school administration…</div>
  if (institutionQuery.isError) return <div className="page-state page-state--error" role="alert"><h1>School unavailable</h1><p>{adminError(institutionQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void institutionQuery.refetch()}>Retry</button></div>
  return <AdminSchool institution={institutionQuery.data} />
}