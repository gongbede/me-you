import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { getPost } from '../api/social'
import { getFriendlyErrorMessage } from '../api/client'
import { PostCard } from '../components/PostCard'

export function PostDetailPage() {
  const { postId = '' } = useParams()
  const navigate = useNavigate()
  const postQuery = useQuery({
    queryKey: ['posts', postId],
    queryFn: () => getPost(postId),
    enabled: Boolean(postId),
  })

  if (postQuery.isPending) return <p className="learning-loading" role="status">Loading post…</p>
  if (postQuery.isError) return <div className="page-state page-state--error" role="alert"><h1>Post unavailable</h1><p>{getFriendlyErrorMessage(postQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void postQuery.refetch()}>Retry</button></div>
  return <section className="page-shell"><PostCard post={postQuery.data} onDeleted={() => navigate('/')} /></section>
}
