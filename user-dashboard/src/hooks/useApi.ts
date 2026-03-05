import { useState, useCallback } from 'react'
import { useAuth } from '../contexts/AuthContext'

const API_BASE = import.meta.env.VITE_API_URL || ''

interface ApiState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

export function useApi<T>() {
  const { token } = useAuth()
  const [state, setState] = useState<ApiState<T>>({
    data: null,
    loading: false,
    error: null
  })

  const request = useCallback(async (
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> => {
    setState(s => ({ ...s, loading: true, error: null }))

    try {
      const res = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...(token && { Authorization: `Bearer ${token}` }),
          ...options.headers
        }
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Request failed' }))
        throw new Error(err.detail || 'Request failed')
      }

      const data = await res.json()
      setState({ data, loading: false, error: null })
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error'
      setState(s => ({ ...s, loading: false, error: message }))
      throw err
    }
  }, [token])

  const get = useCallback((endpoint: string) => request(endpoint), [request])

  const post = useCallback((endpoint: string, body: unknown) =>
    request(endpoint, { method: 'POST', body: JSON.stringify(body) }), [request])

  const put = useCallback((endpoint: string, body: unknown) =>
    request(endpoint, { method: 'PUT', body: JSON.stringify(body) }), [request])

  const del = useCallback((endpoint: string) =>
    request(endpoint, { method: 'DELETE' }), [request])

  return { ...state, get, post, put, del, request }
}
