/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { googleLogin as googleLoginRequest, login as loginRequest, logout as logoutRequest, register as registerRequest } from '../api/auth'
import { apiRequest, clearAccessToken, getAccessToken, type ApiSchemas } from '../api/client'

export type AuthUser = Pick<ApiSchemas['LoginResponse'], 'id' | 'username' | 'email'>

interface AuthContextValue {
  user: AuthUser | null
  isLoading: boolean
  login: (input: ApiSchemas['LoginRequest']) => Promise<void>
  loginWithGoogle: (idToken: string) => Promise<void>
  register: (input: ApiSchemas['UserCreate']) => Promise<ApiSchemas['UserResponse']>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState(Boolean(getAccessToken()))

  useEffect(() => {
    let isMounted = true
    const handleUnauthorized = () => {
      if (isMounted) setUser(null)
    }
    window.addEventListener('me-you:unauthorized', handleUnauthorized)

    if (getAccessToken()) {
      void apiRequest<ApiSchemas['UserResponse']>('/api/v1/account/me')
        .then((account) => {
          if (isMounted) {
            setUser({ id: account.id, username: account.username, email: account.email })
          }
        })
        .catch(() => {
          clearAccessToken()
          if (isMounted) setUser(null)
        })
        .finally(() => {
          if (isMounted) setIsLoading(false)
        })
    }

    return () => {
      isMounted = false
      window.removeEventListener('me-you:unauthorized', handleUnauthorized)
    }
  }, [])

  async function login(input: ApiSchemas['LoginRequest']) {
    const response = await loginRequest(input)
    setUser({ id: response.id, username: response.username, email: response.email })
  }

  async function loginWithGoogle(idToken: string) {
    const response = await googleLoginRequest(idToken)
    setUser({ id: response.id, username: response.username, email: response.email })
  }

  async function register(input: ApiSchemas['UserCreate']) {
    return registerRequest(input)
  }

  async function logout() {
    try {
      await logoutRequest()
    } finally {
      setUser(null)
    }
  }

  return (
    <AuthContext.Provider value={{ user, isLoading, login, loginWithGoogle, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}