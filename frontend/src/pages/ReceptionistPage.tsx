/**
 * ReceptionistPage — Full-Screen Immersive AI Receptionist
 *
 * Integrates the complete Angelica 3D avatar with:
 * - 52 ARKit blendshape animation (emotions, lip sync, gaze, gestures, breathing)
 * - Real-time conversation with WebSocket
 * - Speech recognition + text input
 * - Camera feed for face detection
 * - Live captions (WCAG 2.2 AA)
 * - Emotion triggers from conversation context
 * - Accessibility: reduced-motion, screen reader support, keyboard navigation
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import AvatarAdapter from '../components/AvatarAdapter'
import CameraFeed from '../components/CameraFeed'
import ConversationPanel from '../components/ConversationPanel'
import TextInputPanel from '../components/TextInputPanel'
import PrivacyNotice from '../components/PrivacyNotice'
import CaptionOverlay from '../components/CaptionOverlay'
import { useWebSocket } from '../hooks/useWebSocket'
import { useSpeechRecognition } from '../hooks/useSpeechRecognition'
import { useCamera } from '../hooks/useCamera'
import { authApi, apiFetch } from '../lib/api'
import { announceToScreenReader } from '../components/AccessibilityShell'
import type { EmotionType, GestureType, AvatarActivityState } from '../lib/avatar'

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

// Emotion keyword detection for frontend emotion analysis
const EMOTION_KEYWORDS: Record<string, EmotionType> = {
  'welcome': 'happy',
  'hello': 'happy',
  'glad': 'happy',
  'great': 'excited',
  'wonderful': 'excited',
  'sorry': 'empathetic',
  'understand': 'empathetic',
  'unfortunately': 'sad',
  'wait': 'neutral',
  'let me check': 'thinking',
  'hmm': 'confused',
  'interesting': 'interested',
  'sure': 'happy',
  'absolutely': 'proud',
  'of course': 'happy',
  'goodbye': 'happy',
  'thank': 'happy',
  'help': 'interested',
  'problem': 'empathetic',
  'concern': 'empathetic',
}

/**
 * Simple client-side emotion detection from text.
 * Used as fallback when backend emotion analysis is unavailable.
 */
function detectEmotionFromText(text: string): { emotion: EmotionType; intensity: number } {
  const lower = text.toLowerCase()
  for (const [keyword, emotion] of Object.entries(EMOTION_KEYWORDS)) {
    if (lower.includes(keyword)) {
      return { emotion, intensity: 0.6 + Math.random() * 0.2 }
    }
  }
  return { emotion: 'neutral', intensity: 0.5 }
}

function ReceptionistPage() {
  // ─── Core State ────────────────────────────────────────────
  const [messages, setMessages] = useState<Message[]>([])
  const [avatarState, setAvatarState] = useState<AvatarActivityState>('idle')
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
  const [showChat, setShowChat] = useState(false)
  const [showCamera, setShowCamera] = useState(false)

  // ─── Enhanced Avatar State ─────────────────────────────────
  const [currentEmotion, setCurrentEmotion] = useState<EmotionType>('neutral')
  const [emotionIntensity, setEmotionIntensity] = useState(0.5)
  const [currentGesture, setCurrentGesture] = useState<GestureType | undefined>(undefined)
  const [currentCaption, setCurrentCaption] = useState<string | null>(null)
  const [captionsEnabled, setCaptionsEnabled] = useState(true)
  const [captionFontSize, setCaptionFontSize] = useState<'small' | 'medium' | 'large'>('medium')
  const [captionHighContrast, setCaptionHighContrast] = useState(false)
  const [reducedMotion, setReducedMotion] = useState(false)

  const audioRef = useRef<HTMLAudioElement>(null)
  const clientId = useRef(`client_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`).current

  // ─── Detect reduced motion preference ─────────────────────
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReducedMotion(mq.matches)
    const handler = (e: MediaQueryListEvent) => setReducedMotion(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  // ─── Get WebSocket ticket ──────────────────────────────────
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

  // ─── WebSocket ─────────────────────────────────────────────
  const { isConnected, sendMessage } = useWebSocket(
    wsUrl,
    {
      onMessage: handleWebSocketMessage,
      autoConnect: !!wsUrl,
    }
  )

  // ─── Speech Recognition ────────────────────────────────────
  const { isListening, interimTranscript, startListening, stopListening, isSupported } =
    useSpeechRecognition({
      language: 'en-IN',
      continuous: true,
      onResult: handleSpeechResult,
    })

  // ─── Camera ────────────────────────────────────────────────
  const { isActive: cameraActive, videoRef, canvasRef, startCamera, stopCamera } = useCamera({
    width: 640,
    height: 480,
    captureInterval: 2000,
    onFrame: handleCameraFrame,
  })

  // ─── WebSocket Message Handler ─────────────────────────────
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
      case 'emotion':
        // Backend emotion analysis result
        if (data.emotion) {
          setCurrentEmotion(data.emotion as EmotionType)
          setEmotionIntensity((data.intensity as number) || 0.7)
        }
        break
      case 'gesture':
        // Backend gesture trigger
        if (data.gesture) {
          setCurrentGesture(data.gesture as GestureType)
          // Clear after a moment to allow re-triggering same gesture
          setTimeout(() => setCurrentGesture(undefined), 100)
        }
        break
      case 'state':
        setSessionState(data.state as string)
        if (data.state === 'ended') {
          setSessionId(null)
          setVisitorName(null)
          setShowConsentButtons(false)
          setCurrentEmotion('neutral')
          announceToScreenReader('Session ended')
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
      setCurrentEmotion('happy')
      setEmotionIntensity(0.7)
      setCurrentGesture('nod')
      announceToScreenReader(`Recognized visitor: ${data.visitor_name}`)
    }
  }

  function handleRegistration(data: Record<string, unknown>) {
    const status = data.status as string
    if (status === 'success') {
      const systemMsg: Message = {
        id: `msg_${Date.now()}`,
        role: 'system',
        content: '✅ Visitor registered successfully',
        timestamp: new Date().toISOString(),
      }
      setMessages(prev => [...prev, systemMsg])
      setCurrentEmotion('happy')
      setCurrentGesture('agreement')
      announceToScreenReader('Visitor registered successfully')
    }
    setShowConsentButtons(false)
  }

  function handleAIResponse(data: Record<string, unknown>) {
    const text = data.text as string
    const audio = data.audio as string | null
    const responseState = data.state as string
    const name = data.visitor_name as string | null

    if (data.session_id) setSessionId(data.session_id as string)
    if (name) setVisitorName(name)
    setSessionState(responseState)

    if (responseState === 'asking_consent') {
      setShowConsentButtons(true)
      announceToScreenReader('The avatar is asking for your biometric consent. Please choose yes or no.')
    } else {
      setShowConsentButtons(false)
    }

    // ─── Emotion Detection from Response Text ────────────
    if (text) {
      const { emotion, intensity } = data.emotion
        ? { emotion: data.emotion as EmotionType, intensity: (data.emotion_intensity as number) || 0.7 }
        : detectEmotionFromText(text)
      setCurrentEmotion(emotion)
      setEmotionIntensity(intensity)

      // Gesture based on context
      if (responseState === 'greeting_new' || responseState === 'greeting_returning') {
        setCurrentGesture('nod')
      } else if (text.toLowerCase().includes("i'm not sure") || text.toLowerCase().includes("let me")) {
        setCurrentGesture('thinking')
      }

      const newMessage: Message = {
        id: `msg_${Date.now()}`,
        role: 'assistant',
        content: text,
        timestamp: new Date().toISOString(),
      }
      setMessages(prev => [...prev, newMessage])

      // Set caption
      setCurrentCaption(text)
    }

    // ─── Audio Playback ──────────────────────────────────
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
        // Simulate speech duration
        const wordCount = (text || '').split(' ').length
        setTimeout(() => {
          setIsSpeaking(false)
          setAvatarState('listening')
        }, Math.max(2000, wordCount * 300))
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

      // Barge-in: stop current audio
      if (isSpeaking && audioRef.current) {
        audioRef.current.pause()
        audioRef.current.currentTime = 0
        setIsSpeaking(false)
      }

      setAvatarState('thinking')
      setCurrentEmotion('interested')
      setCurrentGesture('agreement')
      sendMessage({
        type: 'speech',
        text: transcript.trim(),
        is_final: true,
      })
    }
  }

  function handleCameraFrame(base64: string) {
    if (isConnected) {
      sendMessage({ type: 'frame', data: base64 })
    }
  }

  // ─── Action Handlers ───────────────────────────────────────
  const handleConsent = useCallback((granted: boolean) => {
    sendMessage({ type: 'consent', value: granted })
    setShowConsentButtons(false)
    if (granted) {
      setCurrentEmotion('happy')
      setCurrentGesture('agreement')
      announceToScreenReader('Consent granted. Proceeding with registration.')
    } else {
      setCurrentEmotion('neutral')
      setCurrentGesture('nod')
      announceToScreenReader('Consent declined. Continuing without biometric registration.')
    }
  }, [sendMessage])

  const handleMuteToggle = useCallback((muted: boolean) => {
    setIsMuted(muted)
    if (muted && audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
      setIsSpeaking(false)
      setAvatarState('listening')
    }
    announceToScreenReader(muted ? 'Audio muted' : 'Audio unmuted')
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
    setCurrentEmotion('interested')
    sendMessage({ type: 'speech', text, is_final: true })
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
        setCurrentEmotion('excited')
        setCurrentGesture('nod')
        announceToScreenReader(`Invitation valid for ${response.visitor_name}`)
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
    setAvatarState('greeting')
    setCurrentEmotion('happy')
    setCurrentGesture('nod')
    if (isSupported) startListening()
    announceToScreenReader(isReturning ? 'Session started for returning visitor' : 'Session started for new visitor')
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
      setCurrentEmotion('neutral')
      setCurrentCaption(null)
      announceToScreenReader('Session ended')
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
    setCurrentCaption(null)
    if (isSupported && !isListening && sessionId) {
      startListening()
    }
  }

  // ─── Keyboard Shortcuts ────────────────────────────────────
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      // Only handle if not typing in an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return

      switch (e.key) {
        case 'c':
          if (e.ctrlKey || e.metaKey) return // Don't intercept copy
          setCaptionsEnabled(prev => !prev)
          break
        case 'm':
          handleMuteToggle(!isMuted)
          break
        case 'Escape':
          setShowChat(false)
          break
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [isMuted, handleMuteToggle])

  return (
    <div className="fixed inset-0 w-screen h-screen overflow-hidden bg-black">
      <audio ref={audioRef} onEnded={handleAudioEnded} className="hidden" />

      {/* ═══════════════════════════════════════════════════════
          FULL-SCREEN ANGELICA 3D AVATAR (Background)
          52 ARKit blendshapes • Emotion • Gaze • Gestures • Breathing
          ═══════════════════════════════════════════════════════ */}
      <div className="absolute inset-0 w-full h-full">
        <AvatarAdapter
          isSpeaking={isSpeaking}
          isListening={isListening}
          state={avatarState}
          speechMarks={speechMarks}
          audioStartTime={audioStartTime}
          name={visitorName || 'Angelica'}
          emotion={currentEmotion}
          emotionIntensity={emotionIntensity}
          gesture={currentGesture}
          reducedMotion={reducedMotion}
          fullScreen={true}
        />
      </div>

      {/* ═══════════════════════════════════════════════════════
          OVERLAY UI
          ═══════════════════════════════════════════════════════ */}

      {/* Top bar — Status + Controls */}
      <div className="absolute top-0 left-0 right-0 z-30 p-4 flex items-center justify-between pointer-events-none">
        {/* Left: Connection + Visitor */}
        <div className="flex items-center gap-3 pointer-events-auto">
          <div
            className={`flex items-center gap-2 px-3 py-1.5 rounded-full backdrop-blur-md ${
              isConnected ? 'bg-green-900/50 border border-green-500/30' : 'bg-red-900/50 border border-red-500/30'
            }`}
            role="status"
            aria-label={isConnected ? 'Connected' : 'Disconnected'}
          >
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} aria-hidden="true" />
            <span className="text-xs text-white font-medium">
              {isConnected ? 'Online' : 'Offline'}
            </span>
          </div>
          {visitorName && (
            <div className="px-3 py-1.5 rounded-full bg-blue-900/50 backdrop-blur-md border border-blue-500/30">
              <span className="text-xs text-blue-200 font-medium">👤 {visitorName}</span>
            </div>
          )}
          {currentEmotion !== 'neutral' && (
            <div className="px-3 py-1.5 rounded-full bg-purple-900/50 backdrop-blur-md border border-purple-500/30">
              <span className="text-xs text-purple-200 font-medium">
                {currentEmotion === 'happy' ? '😊' :
                 currentEmotion === 'interested' ? '🤔' :
                 currentEmotion === 'excited' ? '🎉' :
                 currentEmotion === 'empathetic' ? '💙' :
                 currentEmotion === 'confused' ? '😕' : '🙂'
                } {currentEmotion}
              </span>
            </div>
          )}
        </div>

        {/* Right: Toggle buttons */}
        <div className="flex items-center gap-2 pointer-events-auto">
          {/* Captions toggle */}
          <button
            onClick={() => setCaptionsEnabled(!captionsEnabled)}
            className={`p-2.5 rounded-full backdrop-blur-md transition-all ${
              captionsEnabled
                ? 'bg-yellow-600/80 border border-yellow-400/50'
                : 'bg-white/10 border border-white/20 hover:bg-white/20'
            }`}
            title="Toggle captions (C)"
            aria-label={captionsEnabled ? 'Captions on' : 'Captions off'}
            aria-pressed={captionsEnabled}
          >
            <span className="text-white text-xs font-bold" aria-hidden="true">CC</span>
          </button>
          {/* Chat toggle */}
          <button
            onClick={() => setShowChat(!showChat)}
            className={`p-2.5 rounded-full backdrop-blur-md transition-all ${
              showChat
                ? 'bg-blue-600/80 border border-blue-400/50'
                : 'bg-white/10 border border-white/20 hover:bg-white/20'
            }`}
            title="Toggle chat panel"
            aria-label={showChat ? 'Close chat' : 'Open chat'}
            aria-expanded={showChat}
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          </button>
          {/* Camera toggle */}
          <button
            onClick={toggleCamera}
            className={`p-2.5 rounded-full backdrop-blur-md transition-all ${
              cameraActive
                ? 'bg-green-600/80 border border-green-400/50'
                : 'bg-white/10 border border-white/20 hover:bg-white/20'
            }`}
            title="Toggle camera"
            aria-label={cameraActive ? 'Camera on' : 'Camera off'}
            aria-pressed={cameraActive}
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </button>
          {/* Reduced motion toggle */}
          <button
            onClick={() => setReducedMotion(!reducedMotion)}
            className={`p-2.5 rounded-full backdrop-blur-md transition-all ${
              reducedMotion
                ? 'bg-orange-600/80 border border-orange-400/50'
                : 'bg-white/10 border border-white/20 hover:bg-white/20'
            }`}
            title="Toggle reduced motion"
            aria-label={reducedMotion ? 'Reduced motion on' : 'Reduced motion off'}
            aria-pressed={reducedMotion}
          >
            <span className="text-white text-xs" aria-hidden="true">⚡</span>
          </button>
        </div>
      </div>

      {/* Captions Overlay */}
      <CaptionOverlay
        currentText={currentCaption}
        enabled={captionsEnabled}
        onToggle={setCaptionsEnabled}
        highContrast={captionHighContrast}
        fontSize={captionFontSize}
        className="bottom-32 left-0 right-0 px-4"
      />

      {/* Consent Buttons (centered) */}
      {showConsentButtons && (
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-40 flex gap-4" role="alertdialog" aria-label="Biometric consent request">
          <button
            onClick={() => handleConsent(true)}
            className="px-8 py-4 rounded-2xl bg-green-600/90 hover:bg-green-500 backdrop-blur-md text-white font-semibold text-lg transition-all shadow-2xl border border-green-400/30 focus:ring-2 focus:ring-green-300 focus:outline-none"
            autoFocus
          >
            ✓ Yes, remember me
          </button>
          <button
            onClick={() => handleConsent(false)}
            className="px-8 py-4 rounded-2xl bg-gray-700/90 hover:bg-gray-600 backdrop-blur-md text-white font-semibold text-lg transition-all shadow-2xl border border-gray-500/30 focus:ring-2 focus:ring-gray-300 focus:outline-none"
          >
            ✗ No thanks
          </button>
        </div>
      )}

      {/* Bottom Controls */}
      <div className="absolute bottom-0 left-0 right-0 z-30 p-4 pointer-events-none">
        <div className="max-w-2xl mx-auto flex flex-col items-center gap-3">
          {/* Session controls */}
          <div className="flex flex-wrap items-center justify-center gap-3 pointer-events-auto" role="toolbar" aria-label="Session controls">
            {!sessionId ? (
              <>
                <button
                  onClick={() => startNewSession(false)}
                  className="px-5 py-2.5 rounded-full bg-blue-600/80 hover:bg-blue-500 backdrop-blur-md text-white font-medium text-sm transition-all border border-blue-400/30 shadow-lg focus:ring-2 focus:ring-blue-300 focus:outline-none"
                  disabled={!isConnected}
                >
                  🆕 New Visitor
                </button>
                <button
                  onClick={() => startNewSession(true)}
                  className="px-5 py-2.5 rounded-full bg-purple-600/80 hover:bg-purple-500 backdrop-blur-md text-white font-medium text-sm transition-all border border-purple-400/30 shadow-lg focus:ring-2 focus:ring-purple-300 focus:outline-none"
                  disabled={!isConnected}
                >
                  🔄 Returning Visitor
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={isListening ? stopListening : startListening}
                  className={`px-5 py-2.5 rounded-full backdrop-blur-md text-white font-medium text-sm transition-all shadow-lg focus:ring-2 focus:outline-none ${
                    isListening
                      ? 'bg-red-600/80 hover:bg-red-500 border border-red-400/30 focus:ring-red-300'
                      : 'bg-green-600/80 hover:bg-green-500 border border-green-400/30 focus:ring-green-300'
                  }`}
                  disabled={!isSupported}
                  aria-pressed={isListening}
                >
                  {isListening ? '🔴 Stop Mic' : '🎤 Start Mic'}
                </button>
                <button
                  onClick={() => handleMuteToggle(!isMuted)}
                  className={`px-4 py-2.5 rounded-full backdrop-blur-md text-white font-medium text-sm transition-all shadow-lg focus:ring-2 focus:outline-none ${
                    isMuted
                      ? 'bg-yellow-600/80 border border-yellow-400/30 focus:ring-yellow-300'
                      : 'bg-white/10 border border-white/20 hover:bg-white/20 focus:ring-white/50'
                  }`}
                  aria-pressed={isMuted}
                >
                  {isMuted ? '🔇 Unmute' : '🔊 Mute'}
                </button>
                <button
                  onClick={endSession}
                  className="px-5 py-2.5 rounded-full bg-gray-700/80 hover:bg-gray-600 backdrop-blur-md text-white font-medium text-sm transition-all border border-gray-500/30 shadow-lg focus:ring-2 focus:ring-gray-300 focus:outline-none"
                >
                  ⏹ End Session
                </button>
              </>
            )}
          </div>

          {/* Text input */}
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

      {/* Chat Panel (slide-in) */}
      <div
        className={`absolute top-0 right-0 h-full w-full max-w-md z-30 transition-transform duration-300 ease-in-out ${
          showChat ? 'translate-x-0' : 'translate-x-full'
        }`}
        role="complementary"
        aria-label="Conversation panel"
        aria-hidden={!showChat}
      >
        <div className="h-full flex flex-col bg-gray-900/85 backdrop-blur-xl border-l border-white/10">
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
            <h3 className="text-white font-medium text-sm">Conversation</h3>
            <button
              onClick={() => setShowChat(false)}
              className="p-1.5 rounded-lg hover:bg-white/10 text-white/60 hover:text-white transition-colors focus:ring-2 focus:ring-white/50 focus:outline-none"
              aria-label="Close chat panel"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
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

      {/* Camera Feed */}
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

      {/* Privacy Notice */}
      <PrivacyNotice
        isCameraActive={cameraActive}
        isMicActive={isListening}
        isSpeaking={isSpeaking}
        isMuted={isMuted}
        onMuteToggle={handleMuteToggle}
        captionsEnabled={captionsEnabled}
        onCaptionsToggle={setCaptionsEnabled}
      />

      {/* Keyboard shortcuts help (hidden, screen reader accessible) */}
      <div className="sr-only" role="note" aria-label="Keyboard shortcuts">
        Press C to toggle captions. Press M to mute/unmute. Press Escape to close panels.
      </div>
    </div>
  )
}

export default ReceptionistPage
