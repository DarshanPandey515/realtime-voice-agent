import { create } from 'zustand'

export const useVoiceStore = create((set) => ({
  status: 'disconnected',
  isConnected: false,
  transcript: [],
  
  setStatus: (status) => set({ status }),
  setConnected: (isConnected) => set({ isConnected }),
  addTranscript: (text, isFinal) => set((state) => ({
    transcript: [...state.transcript, { text, isFinal, timestamp: Date.now() }]
  })),
  clearTranscript: () => set({ transcript: [] }),
  
  startSession: () => {
    // Will be implemented with WebSocket
    console.log('Start session')
  },
  
  stopSession: () => {
    // Will be implemented with WebSocket
    console.log('Stop session')
  },
  
  interruptPlayback: () => {
    // Will be implemented with WebSocket
    console.log('Interrupt playback')
  },
}))
