import { apiRequest, type ApiSchemas } from './client'

export type SearchResponse = ApiSchemas['SearchResponse']

export function search(query: string, offset = 0): Promise<SearchResponse> {
  const params = new URLSearchParams({ query, offset: String(offset), limit: '100' })
  return apiRequest(`/api/v1/search?${params}`)
}
