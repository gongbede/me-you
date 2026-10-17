import { useEffect, useState } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { Building2, LoaderCircle, Search as SearchIcon, UserRound } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { getFriendlyErrorMessage } from '../api/client'
import { search } from '../api/search'

type SearchTab = 'people' | 'posts' | 'schools'
const tabs: { id: SearchTab; label: string }[] = [
  { id: 'people', label: 'People' },
  { id: 'posts', label: 'Posts' },
  { id: 'schools', label: 'Schools' },
]

export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const initialQuery = searchParams.get('q') ?? ''
  const [input, setInput] = useState(initialQuery)
  const [debounced, setDebounced] = useState(initialQuery.trim())
  const [activeTab, setActiveTab] = useState<SearchTab>('people')

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const value = input.trim()
      setDebounced(value)
      setSearchParams(value ? { q: value } : {}, { replace: true })
    }, 300)
    return () => window.clearTimeout(timer)
  }, [input, setSearchParams])

  const resultsQuery = useInfiniteQuery({
    queryKey: ['search', debounced],
    queryFn: ({ pageParam }) => search(debounced, pageParam),
    initialPageParam: 0,
    getNextPageParam: (page) => page.has_more ? page.offset + page.limit : undefined,
    enabled: debounced.length >= 2,
  })
  const items = resultsQuery.data?.pages.flatMap((page) => page.items) ?? []
  const visibleItems = items.filter((item) =>
    activeTab === 'people' ? item.resource_type === 'person'
      : activeTab === 'posts' ? item.resource_type === 'post'
        : item.resource_type === 'school',
  )

  return (
    <section className="page-shell search-page">
      <header className="page-heading-row learning-heading"><div><span className="eyebrow">DISCOVER</span><h1>Search</h1></div></header>
      <label className="search-page__input"><SearchIcon size={19} aria-hidden="true" /><span className="sr-only">Search people, posts, and schools</span><input autoFocus value={input} maxLength={100} onChange={(event) => setInput(event.currentTarget.value)} placeholder="Search people, posts, and schools" /></label>
      <div className="search-tabs" role="tablist" aria-label="Search categories">
        {tabs.map((tab) => <button key={tab.id} id={`search-tab-${tab.id}`} type="button" role="tab" aria-selected={activeTab === tab.id} aria-controls="search-results" onClick={() => setActiveTab(tab.id)}>{tab.label}</button>)}
      </div>
      {input.trim().length < 2 ? <p className="muted-copy">Enter at least 2 characters to search.</p> : resultsQuery.isPending ? (
        <p className="learning-loading" role="status"><LoaderCircle className="spin" aria-hidden="true" /> Searching…</p>
      ) : resultsQuery.isError ? (
        <div className="inline-error" role="alert"><p>{getFriendlyErrorMessage(resultsQuery.error)}</p><button className="button button--outline" type="button" onClick={() => void resultsQuery.refetch()}>Retry</button></div>
      ) : (
        <div id="search-results" role="tabpanel" aria-labelledby={`search-tab-${activeTab}`}>
          {visibleItems.length === 0 ? <p className="learning-empty">{items.length === 0 ? 'No results found.' : `No ${activeTab} found.`}</p> : (
            <ul className="search-results">
              {visibleItems.map((item) => {
                const destination = item.resource_type === 'person' ? `/users/${item.id}`
                  : item.resource_type === 'post' ? `/posts/${item.id}`
                    : `/schools/${item.institution_id ?? item.id}`
                const Icon = item.resource_type === 'person' ? UserRound : Building2
                return <li key={`${item.resource_type}-${item.id}`}><Link to={destination}><Icon size={20} aria-hidden="true" /><span><strong>{item.name}</strong>{item.code && <small>{item.resource_type === 'person' ? `@${item.code}` : item.code}</small>}</span></Link></li>
              })}
            </ul>
          )}
          {resultsQuery.hasNextPage && <button className="button button--outline" type="button" disabled={resultsQuery.isFetchingNextPage} onClick={() => void resultsQuery.fetchNextPage()}>{resultsQuery.isFetchingNextPage ? 'Loading…' : 'Load more'}</button>}
          {resultsQuery.isFetchNextPageError && <p className="form-alert" role="alert">{getFriendlyErrorMessage(resultsQuery.error)}</p>}
        </div>
      )}
    </section>
  )
}
