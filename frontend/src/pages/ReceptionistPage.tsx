import { useState, useCallback, useRef, useEffect } from 'react'
import AvatarAdapter from '../components/AvatarAdapter'
import CameraFeed from '../components/CameraFeed'
import ConversationPanel from '../components/ConversationPanel'
import TextInputPanel from '../components/TextInputPanel'
import PrivacyNotice from '../components/PrivacyNotice'
import { useWebSocket } from '../hooks/useWebSocket'
import { useSpeechRecognition } from '../hooks/useSpeechRecognition'
import { useCamera } from '../hooks/useCamera'
import { authApi, apiFetch } from '../lib/api'

interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
}

interface SpeechMark {
  time: number
  type: string
  value: string
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
  const [speechMarks, setSpeechMarks] = useState<SpeechMark[]>([])
  const [audioStartTime, setAudioStartTime] = useState<number>(0)
  const [wsUrl, setWsUrl] = useState<string>('')
  const [isMuted, setIsMuted] = useState(false)
  const [captionsEnabled, setCaptionsEnabled] = useState(true)
  const [showChat, setShowChat] = useState(false)
  const [showCamera, setShowCamera] = useState(false)
  const audioRef = useRef<HTMLAudioElement>(null)
  const clientId = useRef(`client_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`).current

  // Get WebSocket ticket on mount (authenticated)
  useEffect(() => {
    let cancelled = false
    async function getTicket() {
      try {
        const { ticket } = await authApi.getWsTicket()
        if (!cancelled) {
          setWsUrl(`${WS_URL}/ws/conversation/${clientId}?ticket=${ticket}`)
        }
      } catch (err) {
        console.error('Failed to get WS ticket:', err)
      }
    }
    getTicket()
    return () => { cancelled = true }
  }, [clientId])

  // WebSocket for real-time communication (connects after ticket is obtained)
  const { isConnected, sendMessage } = useWebSocket(
    wsUrl,
    {
      onMessage: handleWebSocketMessage,
      autoConnect: !!wsUrl,
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

    if (state === 'asking_consent') {
      setShowConsentButtons(true)
    } else {
      setShowConsentButtons(false)
    }

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
      if (isSpeaking) {
        audioRef.current.pause()
        audioRef.current.currentTime = 0
      }

      const marks = data.speech_marks as SpeechMark[] | null
      if (marks && marks.length > 0) {
        setSpeechMarks(marks)
      } else {
        setSpeechMarks([])
      }

      setIsSpeaking(true)
      setAvatarState('speaking')
      const audioBlob = new Blob(
        [Uint8Array.from(atob(audio), c => c.charCodeAt(0))],
        { type: 'audio/mp3' }
      )
      const audioUrl = URL.createObjectURL(audioBlob)
      audioRef.current.src = audioUrl

      if (isMuted) {
        setAudioStartTime(Date.now())
        setTimeout(() => {
          setIsSpeaking(false)
          setAvatarState('listening')
        }, 3000)
      } else {
        audioRef.current.play().then(() => {
          setAudioStartTime(Date.now())
        }).catch(err => {
          console.error('Audio playback error:', err)
          setIsSpeaking(false)
          setAvatarState('listening')
        })
      }
    } else {
      setAvatarState('listening')
    }
  }

  function handleSpeechResult(transcript: string, isFinal: boolean) {
    if (isFinal && transcript.trim()) {
      const newMessage: Message = {
        id: `msg_${Date.now()}`,
        role: 'user',
        content: transcript.trim(),
        timestamp: new Date().toISOString(),
      }
      setMessages(prev => [...prev, newMessage])

      if (isSpeaking && audioRef.current) {
        audioRef.current.pause()
        audioRef.current.currentTime = 0
        setIsSpeaking(false)
      }

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

  const handleConsent = useCallback((granted: boolean) => {
    sendMessage({
      type: 'consent',
      value: granted,
    })
    setShowConsentButtons(false)
  }, [sendMessage])

  const handleMuteToggle = useCallback((muted: boolean) => {
    setIsMuted(muted)
    if (muted && audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
      setIsSpeaking(false)
      setAvatarState('listening')
    }
  }, [])

  const handleTextInput = useCallback((text: string) => {
    if (!sessionId || !isConnected) return

    const newMessage: Message = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    }
    setMessages(prev => [...prev, newMessage])
    setAvatarState('thinking')

    sendMessage({
      type: 'speech',
      text: text,
      is_final: true,
    })
  }, [sessionId, isConnected, sendMessage])

  const handleInvitationCode = useCallback(async (code: string) => {
    try {
      const response = await apiFetch<{ valid: boolean; message: string; visitor_name?: string }>(
        '/api/invitations/validate',
        { method: 'POST', body: JSON.stringify({ code }) }
      )
      const systemMsg: Message = {
        id: `msg_${Date.now()}`,
        role: 'system',
        content: response.message,
        timestamp: new Date().toISOString(),
      }
      setMessages(prev => [...prev, systemMsg])

      if (response.valid && response.visitor_name) {
        setVisitorName(response.visitor_name)
      }
    } catch (err) {
      const errorMsg: Message = {
        id: `msg_${Date.now()}`,
        role: 'system',
        content: 'Unable to validate code. Please try again or ask for assistance.',
        timestamp: new Date().toISOString(),
      }
      setMessages(prev => [...prev, errorMsg])
    }
  }, [])

  const startNewSession = useCallback((isReturning: boolean = false) => {
    sendMessage({
      type: 'start_session',
      match_status: isReturning ? 'match_found' : 'no_match',
      visitor_name: isReturning ? 'Rahul' : undefined,
      visit_count: isReturning ? 5 : 0,
    })

    if (isSupported) {
      startListening()
    }
  }, [sendMessage, isSupported, startListening])

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

  const toggleCamera = useCallback(() => {
    if (cameraActive) {
      stopCamera()
      setShowCamera(false)
    } else {
      startCamera()
      setShowCamera(true)
    }
  }, [cameraActive, startCamera, stopCamera])

  const handleAudioEnded = () => {
    setIsSpeaking(false)
    setAvatarState('listening')
    setSpeechMarks([])
    if (isSupported && !isListening && sessionId) {
      startListening()
    }
  }

  return (
    <div className="fixed inset-0 w-screen h-screen overflow-hidden bg-black">
      <audio ref={audioRef} onEnded={handleAudioEnded} className="hidden" />

      {/* ═══════════════════════════════════════════════════════════
          FULL-SCREEN 3D AVATAR (Background Layer)
          Mouse drag to rotate • Scroll to zoom
          ═══════════════════════════════════════════════════════════ */}
      <div className="absolute inset-0 w-full h-full">
        <AvatarAdapter
          isSpeaking={isSpeaking}
          isListening={isListening}
          state={avatarState}
          speechMarks={speechMarks}
          audioStartTime={audioStartTime}
          name={visitorName || undefined}
          fullScreen={true}
        />
      </div>

      {/* ═══════════════════════════════════════════════════════════
          OVERLAY UI (on top of avatar)
          ═══════════════════════════════════════════════════════════ */}

      {/* Top bar — Status + Name */}
      <div className="absolute top-0 left-0 right-0 z-30 p-4 flex items-center justify-between pointer-events-none">
        {/* Left: Connection status */}
        <div className="flex items-center gap-3 pointer-events-auto">
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full backdrop-blur-md ${
            isConnected ? 'bg-green-900/50 border border-green-500/30' : 'bg-red-900/50 border border-red-500/30'
          }`}>
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} />
            <span className="text-xs text-white font-medium">
              {isConnected ? 'Online' : 'Offline'}
            </span>
          </div>
          {visitorName && (
            <div className="px-3 py-1.5 rounded-full bg-blue-900/50 backdrop-blur-md border border-blue-500/30">
              <span className="text-xs text-blue-200 font-medium">👤 {visitorName}</span>
            </div>
          )}
        </div>

        {/* Right: Toggle buttons */}
        <div className="flex items-center gap-2 pointer-events-auto">
          <button
            onClick={() => setShowChat(!showChat)}
            className={`p-2.5 rounded-full backdrop-blur-md transition-all ${
              showChat
                ? 'bg-blue-600/80 border border-blue-400/50'
                : 'bg-white/10 border border-white/20 hover:bg-white/20'
            }`}
            title="Toggle chat panel"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          </button>
          <button
            onClick={toggleCamera}
            className={`p-2.5 rounded-full backdrop-blur-md transition-all ${
              cameraActive
                ? 'bg-green-600/80 border border-green-400/50'
                : 'bg-white/10 border border-white/20 hover:bg-white/20'
            }`}
            title="Toggle camera"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </button>
        </div>
      </div>

      {/* Consent Buttons (centered overlay) */}
      {showConsentButtons && (
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-40 flex gap-4">
          <button
            onClick={() => handleConsent(true)}
            className="px-8 py-4 rounded-2xl bg-green-600/90 hover:bg-green-500 backdrop-blur-md text-white font-semibold text-lg transition-all shadow-2xl border border-green-400/30"
          >
            ✓ Yes, remember me
          </button>
          <button
            onClick={() => handleConsent(false)}
            className="px-8 py-4 rounded-2xl bg-gray-700/90 hover:bg-gray-600 backdrop-blur-md text-white font-semibold text-lg transition-all shadow-2xl border border-gray-500/30"
          >
            ✗ No thanks
          </button>
        </div>
      )}

      {/* Bottom Controls Bar */}
      <div className="absolute bottom-0 left-0 right-0 z-30 p-4 pointer-events-none">
        <div className="max-w-2xl mx-auto flex flex-col items-center gap-3">
          {/* Session controls */}
          <div className="flex flex-wrap items-center justify-center gap-3 pointer-events-auto">
            {!sessionId ? (
              <>
                <button
                  onClick={() => startNewSession(false)}
                  className="px-5 py-2.5 rounded-full bg-blue-600/80 hover:bg-blue-500 backdrop-blur-md text-white font-medium text-sm transition-all border border-blue-400/30 shadow-lg"
                  disabled={!isConnected}
                >
                  🆕 New Visitor
                </button>
                <button
                  onClick={() => startNewSession(true)}
                  className="px-5 py-2.5 rounded-full bg-purple-600/80 hover:bg-purple-500 backdrop-blur-md text-white font-medium text-sm transition-all border border-purple-400/30 shadow-lg"
                  disabled={!isConnected}
                >
                  🔄 Returning Visitor
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={isListening ? stopListening : startListening}
                  className={`px-5 py-2.5 rounded-full backdrop-blur-md text-white font-medium text-sm transition-all shadow-lg ${
                    isListening
                      ? 'bg-red-600/80 hover:bg-red-500 border border-red-400/30'
                      : 'bg-green-600/80 hover:bg-green-500 border border-green-400/30'
                  }`}
                  disabled={!isSupported}
                >
                  {isListening ? '🔴 Stop Mic' : '🎤 Start Mic'}
                </button>
                <button
                  onClick={() => handleMuteToggle(!isMuted)}
                  className={`px-4 py-2.5 rounded-full backdrop-blur-md text-white font-medium text-sm transition-all shadow-lg ${
                    isMuted
                      ? 'bg-yellow-600/80 border border-yellow-400/30'
                      : 'bg-white/10 border border-white/20 hover:bg-white/20'
                  }`}
                >
                  {isMuted ? '🔇 Unmute' : '🔊 Mute'}
                </button>
                <button
                  onClick={endSession}
                  className="px-5 py-2.5 rounded-full bg-gray-700/80 hover:bg-gray-600 backdrop-blur-md text-white font-medium text-sm transition-all border border-gray-500/30 shadow-lg"
                >
                  ⏹ End Session
                </button>
              </>
            )}
          </div>

          {/* Text input (when session active) */}
          {sessionId && (
            <div className="w-full max-w-lg pointer-events-auto">
              <TextInputPanel
                onSubmit={handleTextInput}
                onInvitationCode={handleInvitationCode}
                isDisabled={!isConnected}
                sessionActive={!!sessionId}
              />
            </div>
          )}
        </div>
      </div>

      {/* Chat Panel (slide-in from right) */}
      <div
        className={`absolute top-0 right-0 h-full w-full max-w-md z-30 transition-transform duration-300 ease-in-out ${
          showChat ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="h-full flex flex-col bg-gray-900/85 backdrop-blur-xl border-l border-white/10">
          {/* Chat header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
            <h3 className="text-white font-medium text-sm">Conversation</h3>
            <button
              onClick={() => setShowChat(false)}
              className="p-1.5 rounded-lg hover:bg-white/10 text-white/60 hover:text-white transition-colors"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          {/* Chat messages */}
          <div className="flex-1 min-h-0 overflow-hidden">
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

      {/* Camera Feed (small overlay, bottom-left) */}
      {showCamera && cameraActive && (
        <div className="absolute bottom-24 left-4 z-30 w-48 h-36 rounded-xl overflow-hidden border-2 border-white/20 shadow-2xl">
          <CameraFeed
            videoRef={videoRef as React.RefObject<HTMLVideoElement>}
            canvasRef={canvasRef as React.RefObject<HTMLCanvasElement>}
            isActive={cameraActive}
            personDetected={personDetected}
            faceDetected={faceDetected}
            onToggle={toggleCamera}
          />
        </div>
      )}

      {/* Privacy notice */}
      <PrivacyNotice
        isCameraActive={cameraActive}
        isMicActive={isListening}
        isSpeaking={isSpeaking}
        isMuted={isMuted}
        onMuteToggle={handleMuteToggle}
        captionsEnabled={captionsEnabled}
        onCaptionsToggle={setCaptionsEnabled}
      />
    </div>
  )
}

export default ReceptionistPage
