import { useState, useEffect } from 'react'
import { useVoiceStore } from './store/useVoiceStore.js'

function App() {
  const { status, transcript, isConnected, startSession, stopSession, interruptPlayback } = useVoiceStore()
  const [isRecording, setIsRecording] = useState(false)

  useEffect(() => {
    // Initialize WebSocket connection
    const ws = new WebSocket('ws://localhost:8000/ws/audio')
    
    ws.onopen = () => {
      console.log('WebSocket connected')
      useVoiceStore.getState().setConnected(true)
    }
    
    ws.onmessage = (event) => {
      if (event.data instanceof Blob) {
        // Audio data - would need to play it
        console.log('Received audio data')
      } else {
        const data = JSON.parse(event.data)
        console.log('Received message:', data)
        
        if (data.type === 'status') {
          useVoiceStore.getState().setStatus(data.state)
        } else if (data.type === 'transcript') {
          useVoiceStore.getState().addTranscript(data.text, data.is_final)
        } else if (data.type === 'error') {
          console.error('Error:', data.message)
        }
      }
    }
    
    ws.onclose = () => {
      console.log('WebSocket disconnected')
      useVoiceStore.getState().setConnected(false)
    }
    
    return () => ws.close()
  }, [])

  const handleStart = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      setIsRecording(true)
      // Would need to set up audio capture and send to WebSocket
      console.log('Microphone access granted')
    } catch (error) {
      console.error('Microphone access denied:', error)
    }
  }

  const handleStop = () => {
    setIsRecording(false)
    // Would need to stop audio capture
  }

  return (
    <div className="min-h-screen bg-gray-100 p-4">
      <div className="max-w-4xl mx-auto bg-white rounded-lg shadow-lg p-6">
        <h1 className="text-2xl font-bold mb-4">Voice Agent</h1>
        
        <div className="mb-4">
          <p>Status: {status}</p>
          <p>Connected: {isConnected ? 'Yes' : 'No'}</p>
        </div>
        
        <div className="flex gap-2 mb-4">
          <button
            onClick={handleStart}
            disabled={isRecording}
            className="px-4 py-2 bg-green-500 text-white rounded disabled:opacity-50"
          >
            Start
          </button>
          <button
            onClick={handleStop}
            disabled={!isRecording}
            className="px-4 py-2 bg-red-500 text-white rounded disabled:opacity-50"
          >
            Stop
          </button>
          <button
            onClick={interruptPlayback}
            className="px-4 py-2 bg-yellow-500 text-white rounded"
          >
            Interrupt
          </button>
        </div>
        
        <div className="border rounded p-4 h-64 overflow-y-auto">
          {transcript.map((item, index) => (
            <div key={index} className={`mb-2 ${item.isFinal ? 'font-bold' : 'opacity-50'}`}>
              {item.text}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default App
