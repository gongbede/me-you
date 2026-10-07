import type { components, paths } from './schema'

export type ApiPath = keyof paths & string
export type ApiSchemas = components['schemas']

const TOKEN_KEY = 'me-you.access-token'

export class ApiError extends Error {
  readonly status: number
  readonly retryAfter: string | null

  constructor(message: string, status: number, retryAfter: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.retryAfter = retryAfter
  }
}

export function getAccessToken(): string | null {
  return typeof window === 'undefined' ? null : window.sessionStorage.getItem(TOKEN_KEY)
}

export function storeAccessToken(token: string): void {
  window.sessionStorage.setItem(TOKEN_KEY, token)
}

export function clearAccessToken(): void {
  if (typeof window !== 'undefined') {
    window.sessionStorage.removeItem(TOKEN_KEY)
  }
}

function detailMessage(detail: unknown): string | null {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const firstMessage = detail.find(
      (item): item is { msg: string } =>
        typeof item === 'object' && item !== null && 'msg' in item && typeof item.msg === 'string',
    )
    return firstMessage?.msg ?? null
  }
  if (typeof detail === 'object' && detail !== null && 'message' in detail) {
    const message = detail.message
    return typeof message === 'string' ? message : null
  }
  return null
}

export function getFriendlyErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 429) {
    const seconds = Number(error.retryAfter)
    if (Number.isFinite(seconds) && seconds > 0) {
      return `You’re moving quickly. Please try again in ${Math.ceil(seconds)} seconds.`
    }
    return 'You’re moving quickly. Please try again in a little while.'
  }
  if (error instanceof Error) return error.message
  return 'Something went wrong. Please try again.'
}

export interface ApiRequestOptions extends Omit<RequestInit, 'body' | 'method'> {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  auth?: boolean
}

export interface ApiCursorPage<TResponse> {
  data: TResponse
  nextCursor: string | null
}

async function sendRequest(
  path: ApiPath | (string & {}),
  options: ApiRequestOptions,
): Promise<Response> {
  const { auth = true, body, headers: suppliedHeaders, ...requestOptions } = options
  const headers = new Headers(suppliedHeaders)
  const token = auth ? getAccessToken() : null

  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (body !== undefined && !(body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(path, {
    ...requestOptions,
    headers,
    body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
  })

  if (response.status === 401) {
    clearAccessToken()
    window.dispatchEvent(new Event('me-you:unauthorized'))
  }

  return response
}

async function throwApiError(response: Response): Promise<never> {
  const payload: unknown = await response.json().catch(() => null)
  const detail =
    typeof payload === 'object' && payload !== null && 'detail' in payload
      ? payload.detail
      : null
  const message = detailMessage(detail) ?? `Request failed (${response.status}). Please try again.`
  throw new ApiError(message, response.status, response.headers.get('Retry-After'))
}

export async function apiRequest<TResponse>(
  path: ApiPath | (string & {}),
  options: ApiRequestOptions = {},
): Promise<TResponse> {
  const response = await sendRequest(path, options)
  if (!response.ok) {
    return throwApiError(response)
  }

  if (response.status === 204) return undefined as TResponse
  return (await response.json()) as TResponse
}

export async function apiRequestWithCursor<TResponse>(
  path: ApiPath | (string & {}),
  options: ApiRequestOptions = {},
): Promise<ApiCursorPage<TResponse>> {
  const response = await sendRequest(path, options)
  if (!response.ok) return throwApiError(response)
  return {
    data: (await response.json()) as TResponse,
    nextCursor: response.headers.get('X-Next-Cursor'),
  }
}