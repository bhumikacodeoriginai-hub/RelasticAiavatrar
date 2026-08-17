import { useState, useCallback, useRef } from 'react'
import Avatar from '../components/Avatar'
import CameraFeed from '../components/CameraFeed'
import ConversationPanel from '../components/ConversationPanel'
import { useWebSocket } from '../hooks/useWebSocket'
import { useSpeechRecognition } from '../hooks/useSpeechRecognition'
import { useCamera } from '../hooks/useCamera'

interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
}

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'

function ReceptionistPage() {
  // State
  const [messages, setMessages] = useState<Message[]>([])
  const [avatarState, setAvatarState] = useState<'idle' | 'greeting' | 'speaking' | 'listening' | 'thinking'>('idle')
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [visitorName, setVisitorName] = useState<string | null>(null)
  const [sessionState, setSessionState] = useState('idle')
  const [personDetected, setPersonDetected] = useState(false)
  const [faceDetected, setFaceDetected] = useState(false)
  const [recognitionStatus, setRecognitionStatus] = useState<string | null>(null)
  const [showConsentButtons, setShowConsentButtons] = useState(false)
  const audioRef = useRef<HTMLAudioElement>(null)
  const clientId = useRef(`client_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`).current

  // WebSocket for real-time communication
  const { isConnected, sendMessage } = useWebSocket(
    `${WS_URL}/ws/conversation/${clientId}`,
    {
      onMessage: handleWebSocketMessage,
      autoConnect: true,
    }
  )

  // Speech recognition
  const { isListening, interimTranscript, startListening, stopListening, isSupported } =
    useSpeechRecognition({
      language: 'en-IN',
      continuous: true,
      onResult: handleSpeechResult,
    })

  // Camera
  const { isActive: cameraActive, videoRef, canvasRef, startCamera, stopCamera } = useCamera({
    width: 640,
    height: 480,
    captureInterval: 2000,
    onFrame: handleCameraFrame,
  })

  function handleWebSocketMessage(data: Record<string, unknown>) {
    switch (data.type) {
      case 'response':
        handleAIResponse(data)
        break
      case 'detection':
        setPersonDetected(data.person_detected as boolean)
        setFaceDetected(data.face_detected as boolean)
        break
      case 'recognition':
        handleRecognition(data)
        break
      case 'registration':
        handleRegistration(data)
        break
      case 'state':
        setSessionState(data.state as string)
        if (data.state === 'ended') {
          setSessionId(null)
          setVisitorName(null)
          setShowConsentButtons(false)
        }
        break
      case 'error':
        console.error('WebSocket error:', data.message)
        break
    }
  }

  function handleRecognition(data: Record<string, unknown>) {
    const status = data.status as string
    setRecognitionStatus(status)
    setPersonDetected(data.person_detected as boolean || false)
    setFaceDetected(data.face_detected as boolean || false)

    if (status === 'match_found' && data.visitor_name) {
      setVisitorName(data.visitor_name as string)
    }
  }

  function handleRegistration(data: Record<string, unknown>) {
    const status = data.status as string
    if (status === 'success') {
      // Show success notification
      const systemMsg: Message = {
        id: `msg_${Date.now()}`,
        role: 'system',
        content: `✅ Visitor registered successfully`,
        timestamp: new Date().toISOString(),
      }
      setMessages(prev => [...prev, systemMsg])
    }
    setShowConsentButtons(false)
  }

  function handleAIResponse(data: Record<string, unknown>) {
    const text = data.text as string
    const audio = data.audio as string | null
    const state = data.state as string
    const name = data.visitor_name as string | null

    if (data.session_id) {
      setSessionId(data.session_id as string)
    }
    if (name) {
      setVisitorName(name)
    }
    setSessionState(state)

    // Show consent buttons when in asking_consent state
    if (state === 'asking_consent') {
      setShowConsentButtons(true)
    } else {
      setShowConsentButtons(false)
    }

    // Add AI message
    if (text) {
      const newMessage: Message = {
        id: `msg_${Date.now()}`,
        role: 'assistant',
        content: text,
        timestamp: new Date().toISOString(),
      }
      setMessages(prev => [...prev, newMessage])
    }

    // Play audio (barge-in: stop current audio if new response arrives)
    if (audio && audioRef.current) {
      // Stop any currently playing audio
      if (isSpeaking) {
        audioRef.current.pause()
        audioRef.current.currentTime = 0
      }

      setIsSpeaking(true)
      setAvatarState('speaking')
      const audioBlob = new Blob(
        [Uint8Array.from(atob(audio), c => c.charCodeAt(0))],
        { type: 'audio/mp3' }
      )
      const audioUrl = URL.createObjectURL(audioBlob)
      audioRef.current.src = audioUrl
      audioRef.current.play().catch(err => {
        console.error('Audio playback error:', err)
        setIsSpeaking(false)
        setAvatarState('listening')
      })
    } else {
      setAvatarState('listening')
    }
  }

  function handleSpeechResult(transcript: string, isFinal: boolean) {
    if (isFinal && transcript.trim()) {
      // Add user message
      const newMessage: Message = {
        id: `msg_${Date.now()}`,
        role: 'user',
        content: transcript.trim(),
        timestamp: new Date().toISOString(),
      }
      setMessages(prev => [...prev, newMessage])

      // If visitor is speaking while avatar is speaking (barge-in)
      if (isSpeaking && audioRef.current) {
        audioRef.current.pause()
        audioRef.current.currentTime = 0
        setIsSpeaking(false)
      }

      // Send to WebSocket
      setAvatarState('thinking')
      sendMessage({
        type: 'speech',
        text: transcript.trim(),
        is_final: true,
      })
    }
  }

  function handleCameraFrame(base64: string) {
    if (isConnected) {
      sendMessage({
        type: 'frame',
        data: base64,
      })
    }
  }

  // Handle consent button clicks
  const handleConsent = useCallback((granted: boolean) => {
    sendMessage({
      type: 'consent',
      value: granted,
    })
    setShowConsentButtons(false)
  }, [sendMessage])

  // Start a new conversation (simulated trigger)
  const startNewSession = useCallback((isReturning: boolean = false) => {
    sendMessage({
      type: 'start_session',
      match_status: isReturning ? 'match_found' : 'no_match',
      visitor_name: isReturning ? 'Rahul' : undefined,
      visit_count: isReturning ? 5 : 0,
    })

    // Start listening
    if (isSupported) {
      startListening()
    }
  }, [sendMessage, isSupported, startListening])

  // End current session
  const endSession = useCallback(() => {
    if (sessionId) {
      sendMessage({ type: 'end_session', session_id: sessionId })
      stopListening()
      setMessages([])
      setAvatarState('idle')
      setIsSpeaking(false)
      setSessionId(null)
      setVisitorName(null)
      setSessionState('idle')
      setShowConsentButtons(false)
      setRecognitionStatus(null)
    }
  }, [sessionId, sendMessage, stopListening])

  // Toggle camera
  const toggleCamera = useCallback(() => {
    if (cameraActive) {
      stopCamera()
    } else {
      startCamera()
    }
  }, [cameraActive, startCamera, stopCamera])

  // Handle audio ended
  const handleAudioEnded = () => {
    setIsSpeaking(false)
    setAvatarState('listening')
    if (isSupported && !isListening && sessionId) {
      startListening()
    }
  }

  return (
    <div className="min-h-screen pt-20 pb-6 px-4 lg:px-8">
      <audio ref={audioRef} onEnded={handleAudioEnded} className="hidden" />

      <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-6 h-[calc(100vh-6rem)]">
        {/* Left column: Avatar + Camera */}
        <div className="lg:col-span-5 flex flex-col gap-4">
          {/* Avatar */}
          <div className="glass-panel p-6 flex-1 flex flex-col items-center justify-center">
            <Avatar
              isSpeaking={isSpeaking}
              isListening={isListening}
              state={avatarState}
              name={visitorName || undefined}
            />

            {/* Consent Buttons */}
            {showConsentButtons && (
              <div className="mt-4 flex gap-3">
                <button
                  onClick={() => handleConsent(true)}
                  className="px-6 py-3 rounded-xl bg-green-600 hover:bg-green-700 text-white font-medium transition-all"
                >
                  ✓ Yes, remember me
                </button>
                <button
                  onClick={() => handleConsent(false)}
                  className="px-6 py-3 rounded-xl bg-gray-600 hover:bg-gray-700 text-white font-medium transition-all"
                >
                  ✗ No thanks
                </button>
              </div>
            )}

            {/* Controls */}
            <div className="mt-6 flex flex-wrap gap-3 justify-center">
              {!sessionId ? (
                <>
                  <button
                    onClick={() => startNewSession(false)}
                    className="btn-primary text-sm"
                    disabled={!isConnected}
                  >
                    🆕 Simulate New Visitor
                  </button>
                  <button
                    onClick={() => startNewSession(true)}
                    className="btn-secondary text-sm"
                    disabled={!isConnected}
                  >
                    🔄 Simulate Returning
                  </button>
                </>
              ) : (
                <>
                  <button
                    onClick={isListening ? stopListening : startListening}
                    className={`px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                      isListening
                        ? 'bg-red-600 hover:bg-red-700 text-white'
                        : 'bg-green-600 hover:bg-green-700 text-white'
                    }`}
                    disabled={!isSupported}
                  >
                    {isListening ? '🔴 Stop Mic' : '🎤 Start Mic'}
                  </button>
                  <button onClick={endSession} className="btn-secondary text-sm">
                    End Session
                  </button>
                </>
              )}
            </div>

            {/* Status indicators */}
            <div className="mt-4 flex flex-col items-center gap-1">
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="text-xs text-gray-400">
                  {isConnected ? 'Connected' : 'Disconnected'}
                </span>
              </div>
              {recognitionStatus && (
                <span className="text-xs text-gray-400">
                  Recognition: {recognitionStatus}
                </span>
              )}
            </div>
          </div>

          {/* Camera */}
          <CameraFeed
            videoRef={videoRef as React.RefObject<HTMLVideoElement>}
            canvasRef={canvasRef as React.RefObject<HTMLCanvasElement>}
            isActive={cameraActive}
            personDetected={personDetected}
            faceDetected={faceDetected}
            onToggle={toggleCamera}
          />
        </div>

        {/* Right column: Conversation */}
        <div className="lg:col-span-7 min-h-0">
          <ConversationPanel
            messages={messages}
            isListening={isListening}
            interimTranscript={interimTranscript}
            visitorName={visitorName}
            sessionState={sessionState}
          />
        </div>
      </div>
    </div>
  )
}

export default ReceptionistPage
