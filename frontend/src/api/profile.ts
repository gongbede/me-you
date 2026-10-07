import { apiRequest, type ApiSchemas } from './client'

export function getMyProfile(): Promise<ApiSchemas['ProfileResponse']> {
  return apiRequest('/api/v1/profile/me')
}

export function updateMyProfile(
  input: ApiSchemas['UpdateProfile'],
): Promise<ApiSchemas['ProfileResponse']> {
  return apiRequest('/api/v1/profile/me', { method: 'PATCH', body: input })
}

export function createMyProfile(
  input: ApiSchemas['CreateProfile'],
): Promise<ApiSchemas['ProfileResponse']> {
  return apiRequest('/api/v1/profile', { method: 'POST', body: input })
}