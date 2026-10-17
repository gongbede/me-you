import { ApiError, apiRequest, clearCsrfToken, setCsrfToken, type ApiSchemas } from './client'

function acceptCookieSession(response: ApiSchemas['LoginResponse']): ApiSchemas['LoginResponse'] {
  if (!response.csrf_token) throw new Error('The server did not establish a secure session.')
  setCsrfToken(response.csrf_token)
  return response
}

export async function login(input: ApiSchemas['LoginRequest']): Promise<ApiSchemas['LoginResponse']> {
  return acceptCookieSession(await apiRequest<ApiSchemas['LoginResponse']>('/api/v1/login', {
    method: 'POST',
    body: input,
    auth: false,
    sessionMode: true,
  }))
}

export async function googleLogin(idToken: string): Promise<ApiSchemas['LoginResponse']> {
  return acceptCookieSession(await apiRequest<ApiSchemas['LoginResponse']>('/api/v1/auth/google', {
    method: 'POST',
    body: { id_token: idToken },
    auth: false,
    sessionMode: true,
  }))
}

export function requestPhoneLoginCode(phoneNumber: string): Promise<{ message: string }> {
  return apiRequest('/api/v1/auth/phone/request', {
    method: 'POST',
    body: { phone_number: phoneNumber },
    auth: false,
  })
}

export async function verifyPhoneLoginCode(
  phoneNumber: string,
  code: string,
): Promise<ApiSchemas['LoginResponse']> {
  return acceptCookieSession(await apiRequest<ApiSchemas['LoginResponse']>('/api/v1/auth/phone/verify', {
    method: 'POST',
    body: { phone_number: phoneNumber, code },
    auth: false,
    sessionMode: true,
  }))
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
    await apiRequest<ApiSchemas['AccountLifecycleResponse']>('/api/v1/account/logout', {
      method: 'POST',
    })
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) throw error
  } finally {
    clearCsrfToken()
  }
}

export async function getCurrentSession(): Promise<ApiSchemas['AuthSessionResponse']> {
  const session = await apiRequest<ApiSchemas['AuthSessionResponse']>('/api/v1/account/session')
  setCsrfToken(session.csrf_token)
  return session
}

export function requestEmailVerification(): Promise<ApiSchemas['AccountLifecycleResponse']> {
  return apiRequest('/api/v1/account/email-verification', { method: 'POST' })
}

export function getMyAccount(): Promise<ApiSchemas['UserResponse']> {
  return apiRequest('/api/v1/account/me')
}

export function changeMyPassword(
  input: ApiSchemas['PasswordChangeRequest'],
): Promise<ApiSchemas['PasswordChangeResponse']> {
  return apiRequest('/api/v1/account/password', { method: 'PUT', body: input })
}

export function requestEmailChange(
  input: ApiSchemas['EmailChangeRequest'],
): Promise<ApiSchemas['AccountLifecycleResponse']> {
  return apiRequest('/api/v1/account/email-change', { method: 'POST', body: input })
}

export function confirmEmailChange(
  input: ApiSchemas['EmailTokenConfirm'],
): Promise<ApiSchemas['AccountLifecycleResponse']> {
  return apiRequest('/api/v1/account/email-change/confirm', { method: 'POST', body: input, auth: false })
}

export function revokeAllSessions(
  input: ApiSchemas['PasswordConfirmationRequest'],
): Promise<ApiSchemas['AccountLifecycleResponse']> {
  return apiRequest('/api/v1/account/sessions/revoke', { method: 'POST', body: input })
}

export function deleteMyAccount(
  input: ApiSchemas['PasswordConfirmationRequest'],
): Promise<ApiSchemas['AccountLifecycleResponse']> {
  return apiRequest('/api/v1/account/me', { method: 'DELETE', body: input })
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