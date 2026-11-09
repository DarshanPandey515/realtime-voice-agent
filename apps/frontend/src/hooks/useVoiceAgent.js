import { useCallback, useEffect, useRef, useState } from 'react'

function applyTranscript(messages, data) {
  const next = [...messages]
  const role = data.speaker === 'agent' ? 'agent' : 'user'

  if (data.is_final) {
    next.push({ role, text: data.text })
  } else {
    const last = next[next.length - 1]
    if (last && last.partial) {
      next[next.length - 1] = { ...last, text: data.text }
    } else {
      next.push({ role, text: data.text, partial: true })
    }
  }

  return next.slice(-100)
}

export function useVoiceAgent() {
  const [connected, setConnected] = useState(false)
  const [status, setStatus] = useState('offline')
  const [messages, setMessages] = useState([])
  const [level, setLevel] = useState(0)
  const wsRef = useRef(null)

  useEffect(() => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/audio`)
    wsRef.current = ws
    ws.binaryType = 'arraybuffer'

    // only apply state from the socket that is currently active
    const isCurrent = () => wsRef.current === ws

    ws.onopen = () => { if (isCurrent()) setConnected(true) }
    ws.onclose = () => {
      if (isCurrent()) {
        setConnected(false)
        setStatus('offline')
      }
    }
    ws.onerror = () => { if (isCurrent()) setStatus('error') }

    ws.onmessage = (event) => {
      if (!isCurrent()) return
      if (event.data instanceof ArrayBuffer || event.data instanceof Blob) return

      try {
        const data = JSON.parse(event.data)
        if (data.type === 'status') {
          setStatus(data.state || data.status || 'ready')
        } else if (data.type === 'transcript') {
          setMessages((prev) => applyTranscript(prev, data))
        } else if (data.type === 'session_started') {
          setStatus('ready')
        } else if (data.type === 'session_ended') {
          setStatus('offline')
        } else if (data.type === 'error') {
          setStatus('error')
        }
      } catch {
        return
      }
    }

    return () => {
      wsRef.current = null
      if (ws.readyState === WebSocket.OPEN) {
        ws.close()
      } else if (ws.readyState === WebSocket.CONNECTING) {
        // don't close mid-handshake — that's the console warning + server disconnect
        ws.addEventListener('open', () => ws.close(), { once: true })
      }
    }
  }, [])

  useEffect(() => {
    const active = status === 'speaking' || status === 'listening'
    const id = setInterval(() => {
      setLevel(active ? 0.35 + Math.random() * 0.6 : 0.03)
    }, 110)
    return () => clearInterval(id)
  }, [status])

  const send = useCallback((message) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message))
    }
  }, [])

  const clear = useCallback(() => setMessages([]), [])

  return { connected, status, messages, level, send, clear }
}
