import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ChevronUp, LoaderCircle, MessageCircle, Plus, Send, Trash2 } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getFriendlyErrorMessage } from '../api/client'
import { getUserFollowers, getUserFollowing } from '../api/social'
import { ReportDialog } from '../components/ReportDialog'
import { useAuth } from '../hooks/useAuth'
import {
  createGroupConversation,
  deleteMessage,
  editMessage,
  getConversation,
  listConversationMessages,
  listConversations,
  markConversationRead,
  sendConversationMessage,
  type Conversation,
  type Message,
} from '../api/messaging'

const conversationKey = ['messages', 'conversations'] as const
const conversationQuery = {
  queryKey: conversationKey,
  queryFn: listConversations,
}
let optimisticMessageSequence = 0

function nextOptimisticMessageId() {
  optimisticMessageSequence += 1
  return `local-message-${optimisticMessageSequence}`
}

function useVisibleTab() {
  const [visible, setVisible] = useState(() => !document.hidden)
  useEffect(() => {
    const update = () => setVisible(!document.hidden)
    document.addEventListener('visibilitychange', update)
    return () => document.removeEventListener('visibilitychange', update)
  }, [])
  return visible
}

function timeLabel(value: string | null) {
  if (!value) return ''
  return new Date(value).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

function conversationTitle(conversation: Conversation, currentUserId: string) {
  if (conversation.type === 'GROUP') return conversation.name || 'Group conversation'
  return conversation.members.find((member) => member.user.id !== currentUserId)?.user.username ?? 'Direct conversation'
}

function NewGroupForm({ onCreated }: { onCreated: (conversation: Conversation) => void }) {
  const { user } = useAuth()
  const [isOpen, setIsOpen] = useState(false)
  const [name, setName] = useState('')
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const contactsQuery = useQuery({
    queryKey: ['messages', 'contacts', user?.id],
    queryFn: async () => {
      if (!user) return []
      const [following, followers] = await Promise.all([getUserFollowing(user.id), getUserFollowers(user.id)])
      const people = new Map([...following, ...followers].map((person) => [person.id, person]))
      people.delete(user.id)
      return [...people.values()].sort((left, right) => left.username.localeCompare(right.username))
    },
    enabled: isOpen && Boolean(user),
  })
  const createMutation = useMutation({
    mutationFn: () => createGroupConversation(name.trim(), selectedIds),
    onSuccess: (conversation) => {
      setName('')
      setSelectedIds([])
      setIsOpen(false)
      onCreated(conversation)
    },
  })

  function toggleMember(id: string) {
    setSelectedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : current.length < 99 ? [...current, id] : current)
  }

  return (
    <div className="messages-new-group">
      <button className="button button--outline" type="button" aria-expanded={isOpen} onClick={() => setIsOpen((current) => !current)}><Plus size={16} aria-hidden="true" /> New group</button>
      {isOpen && <form className="messages-group-form" onSubmit={(event) => { event.preventDefault(); createMutation.mutate() }}>
        <label className="field"><span>Group name</span><input value={name} required maxLength={120} onChange={(event) => setName(event.currentTarget.value)} /></label>
        <fieldset className="messages-contact-picker">
          <legend>Members from your network <span>({selectedIds.length}/99)</span></legend>
          {contactsQuery.isPending ? <p role="status">Loading people…</p> : contactsQuery.isError ? <div role="alert"><p>{getFriendlyErrorMessage(contactsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void contactsQuery.refetch()}>Retry</button></div> : contactsQuery.data.length === 0 ? <p>No people in your follower or following lists yet.</p> : contactsQuery.data.map((person) => <label className="messages-contact-option" key={person.id}><input type="checkbox" checked={selectedIds.includes(person.id)} disabled={!selectedIds.includes(person.id) && selectedIds.length >= 99} onChange={() => toggleMember(person.id)} /><span>{person.username}</span></label>)}
        </fieldset>
        <button className="button button--primary" type="submit" disabled={!name.trim() || selectedIds.length === 0 || createMutation.isPending}>{createMutation.isPending ? 'Creating…' : 'Create group'}</button>
        {createMutation.isError && <p role="alert" className="form-alert">{getFriendlyErrorMessage(createMutation.error)}</p>}
      </form>}
    </div>
  )
}

function MessagesList({
  conversations,
  isPending,
  error,
  selectedId,
  onRetry,
  onGroupCreated,
}: {
  conversations: Conversation[]
  isPending: boolean
  error: unknown
  selectedId?: string
  onRetry: () => void
  onGroupCreated: (conversation: Conversation) => void
}) {
  const { user } = useAuth()
  return (
    <section className="messages-list-panel" aria-label="Conversation list">
      <div className="messages-list-heading"><h1>Messages</h1><NewGroupForm onCreated={onGroupCreated} /></div>
      {isPending ? <p className="learning-loading" role="status">Loading conversations…</p> : error ? <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(error)}</p><button className="button button--outline" type="button" onClick={onRetry}>Retry</button></div> : conversations.length === 0 ? (
        <div className="messages-empty"><MessageCircle size={24} aria-hidden="true" /><p>No conversations yet.</p><span>Open someone’s profile to start a direct chat, or create a group.</span></div>
      ) : <ul className="messages-conversation-list">{conversations.map((conversation) => {
        const title = conversationTitle(conversation, user?.id ?? '')
        return <li key={conversation.id}><Link className={`messages-conversation${selectedId === conversation.id ? ' is-selected' : ''}`} to={`/messages/${conversation.id}`}>
          <span className="messages-conversation__avatar" aria-hidden="true">{title.slice(0, 1).toUpperCase()}</span>
          <span className="messages-conversation__copy"><strong>{title}</strong><span>{conversation.last_message_preview || (conversation.type === 'GROUP' ? 'Group created' : 'Start the conversation')}</span></span>
          <span className="messages-conversation__meta">{conversation.last_message_at && <time dateTime={conversation.last_message_at}>{timeLabel(conversation.last_message_at)}</time>}{conversation.unread_count > 0 && <span className="messages-unread-count" aria-label={`${conversation.unread_count} unread`}>{conversation.unread_count > 99 ? '99+' : conversation.unread_count}</span>}</span>
        </Link></li>
      })}</ul>}
    </section>
  )
}

type LocalMessage = Message & { localStatus?: 'sending' | 'failed' | 'sent' }

function ConversationThread({ conversationId, conversation }: { conversationId: string; conversation?: Conversation }) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const visible = useVisibleTab()
  const [draft, setDraft] = useState('')
  const [localMessages, setLocalMessages] = useState<LocalMessage[]>([])
  const [editing, setEditing] = useState<{ id: string; content: string } | null>(null)
  const [actionError, setActionError] = useState('')
  const endRef = useRef<HTMLDivElement>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const loadingOlder = useRef(false)
  const messageKey = ['messages', 'thread', conversationId] as const
  const olderKey = ['messages', 'older', conversationId] as const
  const latestQuery = useQuery({
    queryKey: messageKey,
    queryFn: () => listConversationMessages(conversationId, undefined, 30),
    enabled: Boolean(conversationId),
    refetchInterval: visible ? 5_000 : false,
    refetchIntervalInBackground: false,
  })
  const olderQuery = useInfiniteQuery({
    queryKey: olderKey,
    queryFn: ({ pageParam }) => listConversationMessages(conversationId, pageParam ?? latestQuery.data?.nextCursor, 30),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    enabled: false,
  })
  const title = conversation ? conversationTitle(conversation, user?.id ?? '') : 'Conversation'
  const serverMessages = [
    ...(olderQuery.data?.pages.flatMap((page) => page.items) ?? []),
    ...(latestQuery.data?.items ?? []),
  ]
  const messageMap = new Map<string, LocalMessage>()
  for (const message of localMessages) messageMap.set(message.id, message)
  for (const message of serverMessages) messageMap.set(message.id, message)
  const messages = [...messageMap.values()].sort((left, right) => left.created_at.localeCompare(right.created_at) || left.id.localeCompare(right.id))
  const canLoadOlder = olderQuery.data ? olderQuery.hasNextPage : Boolean(latestQuery.data?.nextCursor)

  useEffect(() => {
    if (!conversationId) return
    void markConversationRead(conversationId)
      .then(() => queryClient.invalidateQueries({ queryKey: conversationKey }))
      .catch((error: unknown) => setActionError(getFriendlyErrorMessage(error)))
  }, [conversationId, queryClient])

  useEffect(() => {
    if (loadingOlder.current) {
      loadingOlder.current = false
      return
    }
    endRef.current?.scrollIntoView?.({ block: 'end' })
  }, [messages.length])

  const sendMutation = useMutation({ mutationFn: ({ content }: { content: string }) => sendConversationMessage(conversationId, content) })
  const editMutation = useMutation({ mutationFn: ({ id, content }: { id: string; content: string }) => editMessage(id, content) })
  const deleteMutation = useMutation({ mutationFn: deleteMessage })

  async function send(contentValue: string, localId?: string) {
    const content = contentValue.trim()
    if (!content || content.length > 10_000 || !user) return
    const messageId = localId ?? nextOptimisticMessageId()
    if (!localId) {
      const now = new Date().toISOString()
      setLocalMessages((current) => [...current, {
        id: messageId,
        conversation_id: conversationId,
        sender: { id: user.id, username: user.username },
        content,
        created_at: now,
        updated_at: now,
        deleted_at: null,
        localStatus: 'sending',
      }])
    } else {
      setLocalMessages((current) => current.map((message) => message.id === localId ? { ...message, localStatus: 'sending' } : message))
    }
    setDraft('')
    setActionError('')
    try {
      const saved = await sendMutation.mutateAsync({ content })
      setLocalMessages((current) => current.map((message) => message.id === messageId ? { ...saved, localStatus: 'sent' } : message))
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: messageKey }),
        queryClient.invalidateQueries({ queryKey: conversationKey }),
      ])
    } catch (error) {
      setLocalMessages((current) => current.map((message) => message.id === messageId ? { ...message, localStatus: 'failed' } : message))
      setActionError(getFriendlyErrorMessage(error))
    }
  }

  function handleSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void send(draft)
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      formRef.current?.requestSubmit()
    }
  }

  async function loadOlder() {
    const cursor = olderQuery.data?.pages.at(-1)?.nextCursor ?? latestQuery.data?.nextCursor
    if (!cursor) return
    loadingOlder.current = true
    await olderQuery.fetchNextPage()
  }

  async function saveEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editing?.content.trim()) return
    try {
      await editMutation.mutateAsync({ id: editing.id, content: editing.content.trim() })
      setEditing(null)
      await queryClient.invalidateQueries({ queryKey: messageKey })
    } catch (error) {
      setActionError(getFriendlyErrorMessage(error))
    }
  }

  async function removeMessage(messageId: string) {
    if (!window.confirm('Delete this message?')) return
    try {
      await deleteMutation.mutateAsync(messageId)
      await queryClient.invalidateQueries({ queryKey: messageKey })
    } catch (error) {
      setActionError(getFriendlyErrorMessage(error))
    }
  }

  if (latestQuery.isPending) return <section className="messages-thread-panel" role="status">Loading messages…</section>
  if (latestQuery.isError) return <section className="messages-thread-panel" role="alert"><h2>Conversation unavailable</h2><p>{getFriendlyErrorMessage(latestQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void latestQuery.refetch()}>Retry</button></section>

  return (
    <section className="messages-thread-panel" aria-label={title}>
      <header className="messages-thread-heading">
        <Link className="messages-back-link" to="/messages"><ArrowLeft size={17} aria-hidden="true" /> Back</Link>
        <div><h2>{title}</h2>{conversation?.type === 'GROUP' && <span>{conversation.members.length} members</span>}</div>
      </header>
      <div className="messages-thread-scroll" aria-live="polite">
        {canLoadOlder && <button className="button button--outline messages-load-older" type="button" disabled={olderQuery.isFetchingNextPage} onClick={() => void loadOlder()}><ChevronUp size={16} aria-hidden="true" />{olderQuery.isFetchingNextPage ? 'Loading older…' : 'Load older messages'}</button>}
        {olderQuery.isError && <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(olderQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void loadOlder()}>Retry</button></div>}
        {messages.length === 0 ? <p className="messages-thread-empty">No messages yet. Say hello.</p> : messages.map((message) => {
          const own = message.sender.id === user?.id
          const deleted = Boolean(message.deleted_at)
          return <article className={`message-bubble${own ? ' message-bubble--own' : ''}${message.localStatus === 'failed' ? ' message-bubble--failed' : ''}`} key={message.id}>
            {!own && <span className="message-bubble__sender">{message.sender.username}</span>}
            {editing?.id === message.id ? <form className="message-edit-form" onSubmit={(event) => void saveEdit(event)}><textarea aria-label="Edit message" maxLength={10_000} value={editing.content} onChange={(event) => setEditing({ ...editing, content: event.currentTarget.value })} /><button className="button button--primary" type="submit" disabled={!editing.content.trim() || editMutation.isPending}>Save</button><button className="button button--outline" type="button" onClick={() => setEditing(null)}>Cancel</button></form> : <p>{deleted ? 'Message deleted' : message.content}</p>}
            <div className="message-bubble__meta"><time dateTime={message.created_at}>{timeLabel(message.created_at)}</time>{message.localStatus === 'sending' && <span>Sending…</span>}{message.localStatus === 'failed' && <><span>Not sent</span><button type="button" onClick={() => void send(message.content ?? '', message.id)}>Retry</button></>}{message.localStatus === 'sent' && <span>Sent</span>}</div>
            {!own && !deleted && !message.localStatus && <ReportDialog targetType="MESSAGE" targetId={message.id} />}
            {own && !deleted && !message.localStatus && <div className="message-bubble__actions"><button type="button" onClick={() => setEditing({ id: message.id, content: message.content ?? '' })}>Edit</button><button type="button" onClick={() => void removeMessage(message.id)}><Trash2 size={14} aria-hidden="true" /> Delete</button></div>}
          </article>
        })}
        <div ref={endRef} />
      </div>
      {actionError && <p className="form-alert messages-action-error" role="alert">{actionError}</p>}
      <form className="messages-composer" ref={formRef} onSubmit={handleSend}>
        <label className="sr-only" htmlFor="message-composer">Write a message</label>
        <textarea id="message-composer" rows={2} maxLength={10_000} value={draft} onChange={(event) => setDraft(event.currentTarget.value)} onKeyDown={handleComposerKeyDown} placeholder="Write a message…" />
        <span className="messages-composer__limit">{draft.length}/10,000</span>
        <button className="button button--primary" type="submit" disabled={!draft.trim() || draft.length > 10_000 || sendMutation.isPending} aria-label="Send message">{sendMutation.isPending ? <LoaderCircle size={17} className="spin" aria-hidden="true" /> : <Send size={17} aria-hidden="true" />}</button>
      </form>
    </section>
  )
}

export function MessagesPage() {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const conversationsQuery = useQuery(conversationQuery)
  const detailQuery = useQuery({
    queryKey: ['messages', 'conversation', conversationId],
    queryFn: () => getConversation(conversationId ?? ''),
    enabled: Boolean(conversationId) && !conversationsQuery.data?.some((item) => item.id === conversationId),
  })
  const conversation = conversationsQuery.data?.find((item) => item.id === conversationId) ?? detailQuery.data

  return (
    <div className={`messages-page${conversationId ? ' messages-page--thread-open' : ''}`}>
      <MessagesList
        conversations={conversationsQuery.data ?? []}
        isPending={conversationsQuery.isPending}
        error={conversationsQuery.error}
        selectedId={conversationId}
        onRetry={() => void conversationsQuery.refetch()}
        onGroupCreated={(created) => {
          void queryClient.invalidateQueries({ queryKey: conversationKey })
          navigate(`/messages/${created.id}`)
        }}
      />
      {conversationId ? <ConversationThread conversationId={conversationId} conversation={conversation} /> : <section className="messages-thread-panel messages-thread-placeholder"><MessageCircle size={27} aria-hidden="true" /><p>Select a conversation to read your messages.</p></section>}
    </div>
  )
}