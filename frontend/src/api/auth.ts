import { apiRequest, clearAccessToken, storeAccessToken, type ApiSchemas } from './client'

export async function login(input: ApiSchemas['LoginRequest']): Promise<ApiSchemas['LoginResponse']> {
  const response = await apiRequest<ApiSchemas['LoginResponse']>('/api/v1/login', {
    method: 'POST',
    body: input,
    auth: false,
  })
  storeAccessToken(response.access_token)
  return response
}

export async function googleLogin(idToken: string): Promise<ApiSchemas['LoginResponse']> {
  const response = await apiRequest<ApiSchemas['LoginResponse']>('/api/v1/auth/google', {
    method: 'POST',
    body: { id_token: idToken },
    auth: false,
  })
  storeAccessToken(response.access_token)
  return response
}

export function register(input: ApiSchemas['UserCreate']): Promise<ApiSchemas['UserResponse']> {
  return apiRequest<ApiSchemas['UserResponse']>('/api/v1/register', {
    method: 'POST',
    body: input,
    auth: false,
  })
}

export async function logout(): Promise<void> {
  try {
    if (getTokenPresent()) {
      await apiRequest<ApiSchemas['AccountLifecycleResponse']>('/api/v1/account/logout', {
        method: 'POST',
      })
    }
  } finally {
    clearAccessToken()
  }
}

function getTokenPresent(): boolean {
  return Boolean(window.sessionStorage.getItem('me-you.access-token'))
}

export function requestEmailVerification(): Promise<ApiSchemas['AccountLifecycleResponse']> {
  return apiRequest('/api/v1/account/email-verification', { method: 'POST' })
}

export function confirmEmailVerification(
  input: ApiSchemas['EmailTokenConfirm'],
): Promise<ApiSchemas['AccountLifecycleResponse']> {
  return apiRequest('/api/v1/account/email-verification/confirm', {
    method: 'POST',
    body: input,
    auth: false,
  })
}

export function requestPasswordRecovery(
  input: ApiSchemas['PasswordRecoveryRequest'],
): Promise<ApiSchemas['AccountLifecycleResponse']> {
  return apiRequest('/api/v1/account/password-recovery', {
    method: 'POST',
    body: input,
    auth: false,
  })
}

export function confirmPasswordRecovery(
  input: ApiSchemas['PasswordRecoveryConfirm'],
): Promise<ApiSchemas['PasswordChangeResponse']> {
  return apiRequest('/api/v1/account/password-recovery/confirm', {
    method: 'POST',
    body: input,
    auth: false,
  })
}