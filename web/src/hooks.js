import { useCallback, useEffect, useRef, useState } from 'react'

export function usePolling(loader, interval = 4000, deps = []) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const mounted = useRef(true)

  const refresh = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const next = await loader()
      if (mounted.current) {
        setData(next)
        setError('')
      }
      return next
    } catch (err) {
      if (mounted.current) setError(err.message)
      throw err
    } finally {
      if (mounted.current) setLoading(false)
    }
  }, deps)

  useEffect(() => {
    mounted.current = true
    refresh().catch(() => {})
    const timer = setInterval(() => refresh(true).catch(() => {}), interval)
    return () => {
      mounted.current = false
      clearInterval(timer)
    }
  }, [refresh, interval])

  return { data, loading, error, refresh, setData }
}

export function useNotice() {
  const [notice, setNotice] = useState(null)
  function show(message, tone = 'success') {
    setNotice({ message, tone })
    setTimeout(() => setNotice(null), 4200)
  }
  return { notice, show, clear: () => setNotice(null) }
}
