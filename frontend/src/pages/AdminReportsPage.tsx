import { useState } from 'react'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getFriendlyErrorMessage } from '../api/client'
import { getPlatformAdminAccess, listAdminReports, setAdminContentHidden, suspendUser, unsuspendUser, updateAdminReport } from '../api/moderation'

const reportStatuses = ['OPEN', 'REVIEWED', 'DISMISSED', 'ACTIONED'] as const

export function AdminReportsPage() {
  const [status, setStatus] = useState<(typeof reportStatuses)[number]>('OPEN')
  const queryClient = useQueryClient()
  const accessQuery = useQuery({ queryKey: ['platform-admin', 'access'], queryFn: getPlatformAdminAccess })
  const reportsQuery = useInfiniteQuery({
    queryKey: ['admin', 'reports', status],
    queryFn: ({ pageParam }) => listAdminReports(status, pageParam),
    initialPageParam: 0,
    getNextPageParam: (page, pages) => page.length === 100 ? pages.length * 100 : undefined,
    enabled: accessQuery.data?.is_platform_admin === true,
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['admin', 'reports'] })
  const statusMutation = useMutation({
    mutationFn: ({ id, next }: { id: string; next: 'REVIEWED' | 'DISMISSED' | 'ACTIONED' }) => updateAdminReport(id, next),
    onSuccess: refresh,
  })
  const hideMutation = useMutation({
    mutationFn: ({ type, id }: { type: string; id: string }) => setAdminContentHidden(type, id, true),
    onSuccess: refresh,
  })
  const suspendMutation = useMutation({ mutationFn: suspendUser, onSuccess: refresh })
  const unsuspendMutation = useMutation({ mutationFn: unsuspendUser, onSuccess: refresh })
  const unhideMutation = useMutation({
    mutationFn: ({ type, id }: { type: string; id: string }) => setAdminContentHidden(type, id, false),
    onSuccess: refresh,
  })
  const reports = reportsQuery.data?.pages.flatMap((page) => page) ?? []

  if (accessQuery.isPending) return <p className="learning-loading" role="status">Checking administrator access…</p>
  if (accessQuery.isError) return <div className="page-state page-state--error" role="alert"><h1>Reports unavailable</h1><p>{getFriendlyErrorMessage(accessQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void accessQuery.refetch()}>Retry</button></div>
  if (!accessQuery.data.is_platform_admin) return <div className="page-state page-state--error" role="alert"><h1>Access denied</h1><p>Platform administrator access is required.</p></div>

  return (
    <section className="page-shell admin-reports-page">
      <header className="page-heading-row learning-heading"><div><span className="eyebrow">PLATFORM</span><h1>Reports</h1></div><label className="field"><span>Filter by status</span><select value={status} onChange={(event) => setStatus(event.currentTarget.value as (typeof reportStatuses)[number])}>{reportStatuses.map((value) => <option key={value} value={value}>{value}</option>)}</select></label></header>
      {reportsQuery.isPending ? <p className="learning-loading" role="status">Loading reports…</p> : reportsQuery.isError ? <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(reportsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void reportsQuery.refetch()}>Retry</button></div> : reports.length === 0 ? <p className="learning-empty">No {status.toLowerCase()} reports.</p> : (
        <ul className="admin-report-list">{reports.map((report) => <li className="card admin-report-card" key={report.id}>
          <header><strong>{report.target_type} · {report.reason}</strong><time dateTime={report.created_at}>{new Date(report.created_at).toLocaleString()}</time></header>
          <p>{report.details || 'No additional details provided.'}</p>
          <p className="muted-copy">Target ID: {report.target_id}</p>
          <div className="admin-report-actions">
            {['POST', 'REEL', 'COMMENT'].includes(report.target_type) && <button className="button button--outline" type="button" disabled={hideMutation.isPending} onClick={() => hideMutation.mutate({ type: report.target_type, id: report.target_id })}>Hide content</button>}
            {['POST', 'REEL', 'COMMENT'].includes(report.target_type) && <button className="button button--outline" type="button" disabled={unhideMutation.isPending} onClick={() => unhideMutation.mutate({ type: report.target_type, id: report.target_id })}>Unhide content</button>}
            {report.target_type === 'USER' && <><button className="button button--outline" type="button" disabled={suspendMutation.isPending} onClick={() => suspendMutation.mutate(report.target_id)}>Suspend user</button><button className="button button--outline" type="button" disabled={unsuspendMutation.isPending} onClick={() => unsuspendMutation.mutate(report.target_id)}>Unsuspend user</button></>}
            <button className="button button--outline" type="button" disabled={statusMutation.isPending} onClick={() => statusMutation.mutate({ id: report.id, next: 'DISMISSED' })}>Dismiss</button>
            <button className="button button--primary" type="button" disabled={statusMutation.isPending} onClick={() => statusMutation.mutate({ id: report.id, next: 'ACTIONED' })}>Mark actioned</button>
          </div>
        </li>)}</ul>
      )}
      {reportsQuery.hasNextPage && <button className="button button--outline" type="button" disabled={reportsQuery.isFetchingNextPage} onClick={() => void reportsQuery.fetchNextPage()}>{reportsQuery.isFetchingNextPage ? 'Loading…' : 'Load more reports'}</button>}
      {(statusMutation.isError || hideMutation.isError || unhideMutation.isError || suspendMutation.isError || unsuspendMutation.isError || reportsQuery.isFetchNextPageError) && <p className="form-alert" role="alert">{getFriendlyErrorMessage(statusMutation.error ?? hideMutation.error ?? unhideMutation.error ?? suspendMutation.error ?? unsuspendMutation.error ?? reportsQuery.error)}</p>}
    </section>
  )
}
