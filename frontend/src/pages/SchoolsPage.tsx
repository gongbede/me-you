import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Check, MailOpen, Search, School as SchoolIcon, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getFriendlyErrorMessage } from '../api/client'
import {
  acceptInvitation,
  declineInvitation,
  listInstitutions,
  listMyInvitations,
  listMyStudents,
  listMyTeachers,
  requestStudentMembership,
  searchResources,
  type InstitutionRequest,
} from '../api/education'

function accessError(error: unknown): string {
  return getFriendlyErrorMessage(error)
}

export function SchoolsPage() {
  const queryClient = useQueryClient()
  const [institutionId, setInstitutionId] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [joinResult, setJoinResult] = useState<InstitutionRequest | null>(null)
  const schoolsQuery = useQuery({
    queryKey: ['education', 'institutions'],
    queryFn: listInstitutions,
  })
  const invitationsQuery = useQuery({
    queryKey: ['education', 'invitations'],
    queryFn: listMyInvitations,
  })
  const rolesQuery = useQuery({
    queryKey: ['education', 'my-records'],
    queryFn: async () => Promise.all([listMyStudents(), listMyTeachers()]),
  })
  const searchQuery = useQuery({
    queryKey: ['education', 'school-search', searchTerm],
    queryFn: () => searchResources(searchTerm),
    enabled: searchTerm.length >= 2,
  })
  const joinMutation = useMutation({
    mutationFn: requestStudentMembership,
    onSuccess: (value) => setJoinResult(value),
  })
  const acceptMutation = useMutation({
    mutationFn: ({ institutionId: schoolId, requestId }: { institutionId: string; requestId: string }) =>
      acceptInvitation(schoolId, requestId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['education', 'institutions'] }),
        queryClient.invalidateQueries({ queryKey: ['education', 'invitations'] }),
        queryClient.invalidateQueries({ queryKey: ['education', 'my-records'] }),
      ])
    },
  })
  const declineMutation = useMutation({
    mutationFn: ({ institutionId: schoolId, requestId }: { institutionId: string; requestId: string }) =>
      declineInvitation(schoolId, requestId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['education', 'invitations'] }),
  })

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSearchTerm(searchInput.trim())
  }

  function submitJoin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const value = institutionId.trim()
    if (value) {
      setJoinResult(null)
      joinMutation.mutate(value)
    }
  }

  const [students = [], teachers = []] = rolesQuery.data ?? []
  const visibleMatches = searchQuery.data?.items.filter((item) => item.resource_type === 'institution') ?? []

  return (
    <div className="page-stack learning-page">
      <section className="page-heading-row learning-heading">
        <div>
          <span className="eyebrow">YOUR LEARNING COMMUNITY</span>
          <h1>Schools</h1>
          <p>Manage your school memberships and invitations.</p>
        </div>
      </section>

      <section className="learning-section" aria-labelledby="school-search-title">
        <div className="learning-section__heading">
          <div>
            <h2 id="school-search-title">Find a school</h2>
            <p>Search checks schools already visible to your account. To request a new school, use its ID from the school administrator.</p>
          </div>
          <Search size={20} aria-hidden="true" />
        </div>
        <form className="learning-inline-form" onSubmit={submitSearch}>
          <label className="sr-only" htmlFor="school-search">Search schools</label>
          <input id="school-search" value={searchInput} onChange={(event) => setSearchInput(event.currentTarget.value)} placeholder="School name" minLength={2} />
          <button className="button button--outline" type="submit" disabled={searchInput.trim().length < 2 || searchQuery.isFetching}>
            {searchQuery.isFetching ? 'Searching…' : 'Search'}
          </button>
        </form>
        {searchQuery.isError && <p className="form-alert" role="alert">{accessError(searchQuery.error)}</p>}
        {searchTerm && searchQuery.isSuccess && (
          visibleMatches.length ? (
            <ul className="learning-result-list">
              {visibleMatches.map((match) => <li key={match.id}><SchoolIcon size={18} aria-hidden="true" /><span>{match.name}</span><span className="status-label">Already a member</span></li>)}
            </ul>
          ) : <p className="learning-empty learning-empty--compact">No member-visible schools match that search.</p>
        )}
        <form className="learning-join-form" onSubmit={submitJoin}>
          <label className="field">
            <span>School ID</span>
            <input value={institutionId} onChange={(event) => setInstitutionId(event.currentTarget.value)} placeholder="Paste the institution ID" autoComplete="off" />
          </label>
          <button className="button button--primary" type="submit" disabled={!institutionId.trim() || joinMutation.isPending}>
            {joinMutation.isPending ? 'Requesting…' : 'Request to join'} <ArrowRight size={16} aria-hidden="true" />
          </button>
        </form>
        {joinResult && <p className="form-success" role="status">Request {joinResult.status.toLowerCase()} for the {joinResult.role.toLowerCase()} role. A school administrator must approve it before course enrollment.</p>}
        {joinMutation.isError && <p className="form-alert" role="alert">{accessError(joinMutation.error)} Check the school ID, or ask its administrator to invite you.</p>}
      </section>

      <section className="learning-section" aria-labelledby="invitations-title">
        <div className="learning-section__heading">
          <div><h2 id="invitations-title">Invitations</h2><p>Accept an invitation to activate your membership.</p></div>
          <MailOpen size={20} aria-hidden="true" />
        </div>
        {invitationsQuery.isPending ? <p className="learning-loading" role="status">Loading invitations…</p> : invitationsQuery.isError ? (
          <div className="inline-error" role="alert"><p>{accessError(invitationsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void invitationsQuery.refetch()}>Retry</button></div>
        ) : invitationsQuery.data.length === 0 ? <p className="learning-empty learning-empty--compact">No pending invitations.</p> : (
          <ul className="learning-invitation-list">
            {invitationsQuery.data.map((invitation) => <li key={invitation.id}>
              <div><strong>School invitation</strong><span>Institution {invitation.institution_id}</span><span>{invitation.role} · {invitation.status}</span></div>
              <div className="learning-row-actions">
                <button className="button button--primary" type="button" disabled={acceptMutation.isPending || declineMutation.isPending} onClick={() => acceptMutation.mutate({ institutionId: invitation.institution_id, requestId: invitation.id })}><Check size={16} aria-hidden="true" /> Accept</button>
                <button className="button button--outline" type="button" aria-label="Decline invitation" disabled={acceptMutation.isPending || declineMutation.isPending} onClick={() => declineMutation.mutate({ institutionId: invitation.institution_id, requestId: invitation.id })}><X size={16} aria-hidden="true" /><span className="desktop-action-label">Decline</span></button>
              </div>
            </li>)}
          </ul>
        )}
        {acceptMutation.isError && <p className="form-alert" role="alert">{accessError(acceptMutation.error)} The invitation may have expired.</p>}
        {declineMutation.isError && <p className="form-alert" role="alert">{accessError(declineMutation.error)}</p>}
      </section>

      <section className="learning-section" aria-labelledby="your-schools-title">
        <div className="learning-section__heading">
          <div><h2 id="your-schools-title">Your schools</h2><p>Memberships currently active for your account.</p></div>
          <SchoolIcon size={20} aria-hidden="true" />
        </div>
        {schoolsQuery.isPending || rolesQuery.isPending ? <p className="learning-loading" role="status">Loading your schools…</p> : schoolsQuery.isError || rolesQuery.isError ? (
          <div className="inline-error" role="alert"><p>{accessError(schoolsQuery.error ?? rolesQuery.error)}</p><button className="button button--outline" type="button" onClick={() => { void schoolsQuery.refetch(); void rolesQuery.refetch() }}>Retry</button></div>
        ) : schoolsQuery.data.length === 0 ? <p className="learning-empty learning-empty--compact">You do not have an active school membership yet. Accept an invitation or request to join with a school ID.</p> : (
          <ul className="learning-school-list">
            {schoolsQuery.data.map((school) => {
              const role = students.some((record) => record.institution_id === school.id) ? 'STUDENT' : teachers.some((record) => record.institution_id === school.id) ? 'TEACHER' : 'MEMBER'
              return <li key={school.id}>
                <div><span className="learning-kicker">{school.institution_type.replace('_', ' ')}</span><h3>{school.name}</h3><p>{school.location || 'Location not listed'}</p></div>
                <div className="learning-school-meta"><span className="status-label status-label--active">Active</span><span className="status-label">{role}</span><Link className="button button--outline" to={`/schools/${school.id}`}>View school <ArrowRight size={15} aria-hidden="true" /></Link></div>
              </li>
            })}
          </ul>
        )}
      </section>
    </div>
  )
}