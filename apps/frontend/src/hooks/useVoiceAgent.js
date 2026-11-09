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
  const captureRef = useRef(null)
  const playbackTimerRef = useRef(null)
  const playbackCursorRef = useRef(0)

  const playAudio = useCallback((context, data) => {
    const pcm = new Int16Array(data)
    if (!pcm.length) return
    const buffer = context.createBuffer(1, pcm.length, 16000)
    const samples = buffer.getChannelData(0)
    for (let i = 0; i < pcm.length; i += 1) samples[i] = pcm[i] / 32768
    const source = context.createBufferSource()
    source.buffer = buffer
    source.connect(context.destination)
    const startAt = Math.max(context.currentTime + 0.02, playbackCursorRef.current)
    source.start(startAt)
    playbackCursorRef.current = startAt + buffer.duration
    setStatus('speaking')
    clearTimeout(playbackTimerRef.current)
    playbackTimerRef.current = setTimeout(() => setStatus('listening'), 500)
  }, [])

  const stopCapture = useCallback(() => {
    const capture = captureRef.current
    if (!capture) return
    captureRef.current = null
    capture.processor.disconnect()
    capture.source.disconnect()
    capture.stream.getTracks().forEach((track) => track.stop())
    void capture.context.close()
  }, [])

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
      if (event.data instanceof ArrayBuffer) {
        const context = captureRef.current?.context
        if (context && context.state === 'running') playAudio(context, event.data)
        return
      }
      if (event.data instanceof Blob) return

      try {
        const data = JSON.parse(event.data)
        if (data.type === 'status') {
          setStatus(data.state || data.status || 'ready')
        } else if (data.type === 'transcript') {
          setMessages((prev) => applyTranscript(prev, data))
        } else if (data.type === 'session_started') {
          setStatus('ready')
        } else if (data.type === 'session_ended' || data.type === 'session_stopped') {
          stopCapture()
          setStatus('offline')
        } else if (data.type === 'error') {
          stopCapture()
          setStatus('error')
        }
      } catch {
        return
      }
    }

    return () => {
      stopCapture()
      clearTimeout(playbackTimerRef.current)
      wsRef.current = null
      if (ws.readyState === WebSocket.OPEN) {
        ws.close()
      } else if (ws.readyState === WebSocket.CONNECTING) {
        // don't close mid-handshake — that's the console warning + server disconnect
        ws.addEventListener('open', () => ws.close(), { once: true })
      }
    }
  }, [playAudio, stopCapture])

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

  const start = useCallback(async () => {
    if (wsRef.current?.readyState !== WebSocket.OPEN || captureRef.current) return
    setStatus('starting')

    let stream
    let context
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      })
      context = new AudioContext()
      await context.resume()
      await context.audioWorklet.addModule('/pcm-capture-worklet.js')
      const source = context.createMediaStreamSource(stream)
      const processor = new AudioWorkletNode(context, 'pcm-capture')
      const mute = context.createGain()
      mute.gain.value = 0
      processor.port.onmessage = (event) => {
        const socket = wsRef.current
        if (socket?.readyState === WebSocket.OPEN) socket.send(event.data)
      }
      source.connect(processor)
      processor.connect(mute)
      mute.connect(context.destination)
      captureRef.current = { stream, context, source, processor, mute }
      playbackCursorRef.current = 0
      wsRef.current.send(JSON.stringify({ type: 'session_start' }))
    } catch (error) {
      stream?.getTracks().forEach((track) => track.stop())
      if (context && context.state !== 'closed') await context.close()
      setStatus('error')
      setMessages((previous) => [...previous, {
        role: 'agent',
        text: error.name === 'NotAllowedError'
          ? 'Microphone access was denied. Allow microphone access and try again.'
          : `Could not start microphone: ${error.message}`,
      }].slice(-100))
    }
  }, [])

  const stop = useCallback(() => {
    stopCapture()
    send({ type: 'session_stop' })
  }, [send, stopCapture])

  const clear = useCallback(() => setMessages([]), [])

  return { connected, status, messages, level, send, start, stop, clear }
}
