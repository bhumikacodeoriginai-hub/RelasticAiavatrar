/**
 * Standalone Full-Screen Avatar Demo Page
 *
 * A dedicated page for viewing the 3D avatar in full immersive mode.
 * Features:
 * - Full viewport 3D avatar with angelica.glb (52 ARKit blendshapes)
 * - Mouse drag & drop to rotate the model
 * - Scroll to zoom in/out
 * - Touch support for mobile (pinch zoom, drag rotate)
 * - Realistic skin tone rendering with studio lighting
 * - Lip sync demo (simulated visemes)
 * - Eye blink animation (natural random intervals)
 * - Eye tracking (follows mouse cursor)
 * - State switching (idle, speaking, listening, thinking, greeting)
 * - No authentication required — great for demos/showcases
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import AvatarAdapter from '../components/AvatarAdapter'

interface SpeechMark {
  time: number
  type: string
  value: string
}

// Demo viseme sequence for lip sync testing
const DEMO_VISEMES: SpeechMark[] = [
  { time: 0, type: 'viseme', value: 'sil' },
  { time: 100, type: 'viseme', value: 'a' },
  { time: 200, type: 'viseme', value: 'e' },
  { time: 350, type: 'viseme', value: 'o' },
  { time: 500, type: 'viseme', value: 'i' },
  { time: 650, type: 'viseme', value: 'u' },
  { time: 800, type: 'viseme', value: 'a' },
  { time: 950, type: 'viseme', value: 'p' },
  { time: 1050, type: 'viseme', value: 'e' },
  { time: 1200, type: 'viseme', value: 'k' },
  { time: 1350, type: 'viseme', value: 'S' },
  { time: 1500, type: 'viseme', value: 'a' },
  { time: 1650, type: 'viseme', value: 'o' },
  { time: 1800, type: 'viseme', value: 'r' },
  { time: 1950, type: 'viseme', value: 'i' },
  { time: 2100, type: 'viseme', value: 'e' },
  { time: 2250, type: 'viseme', value: 'f' },
  { time: 2400, type: 'viseme', value: 'a' },
  { time: 2550, type: 'viseme', value: 'T' },
  { time: 2700, type: 'viseme', value: 'e' },
  { time: 2850, type: 'viseme', value: 'sil' },
  { time: 3000, type: 'viseme', value: 'sil' },
]

type AvatarState = 'idle' | 'greeting' | 'speaking' | 'listening' | 'thinking'

export default function AvatarFullScreenPage() {
  const [avatarState, setAvatarState] = useState<AvatarState>('idle')
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [isListening, setIsListening] = useState(false)
  const [speechMarks, setSpeechMarks] = useState<SpeechMark[]>([])
  const [audioStartTime, setAudioStartTime] = useState<number>(0)
  const [showControls, setShowControls] = useState(true)
  const speakingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Auto-hide controls after 5 seconds of inactivity
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>
    const resetTimer = () => {
      setShowControls(true)
      clearTimeout(timer)
      timer = setTimeout(() => setShowControls(false), 5000)
    }
    window.addEventListener('mousemove', resetTimer)
    window.addEventListener('touchstart', resetTimer)
    resetTimer()
    return () => {
      clearTimeout(timer)
      window.removeEventListener('mousemove', resetTimer)
      window.removeEventListener('touchstart', resetTimer)
    }
  }, [])

  // Demo: trigger speaking with viseme sequence
  const triggerSpeakingDemo = useCallback(() => {
    setAvatarState('speaking')
    setIsSpeaking(true)
    setIsListening(false)
    setSpeechMarks(DEMO_VISEMES)
    setAudioStartTime(Date.now())

    // End speaking after the demo sequence finishes
    if (speakingTimeoutRef.current) clearTimeout(speakingTimeoutRef.current)
    speakingTimeoutRef.current = setTimeout(() => {
      setIsSpeaking(false)
      setAvatarState('idle')
      setSpeechMarks([])
    }, 3200)
  }, [])

  // Cycle through states
  const cycleState = useCallback((newState: AvatarState) => {
    if (speakingTimeoutRef.current) clearTimeout(speakingTimeoutRef.current)

    setAvatarState(newState)
    setIsSpeaking(newState === 'speaking')
    setIsListening(newState === 'listening')

    if (newState === 'speaking') {
      setSpeechMarks(DEMO_VISEMES)
      setAudioStartTime(Date.now())
      speakingTimeoutRef.current = setTimeout(() => {
        setIsSpeaking(false)
        setAvatarState('idle')
        setSpeechMarks([])
      }, 3200)
    } else {
      setSpeechMarks([])
    }
  }, [])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      switch (e.key) {
        case '1': cycleState('idle'); break
        case '2': cycleState('greeting'); break
        case '3': cycleState('speaking'); break
        case '4': cycleState('listening'); break
        case '5': cycleState('thinking'); break
        case ' ': e.preventDefault(); triggerSpeakingDemo(); break
        case 'h': setShowControls(prev => !prev); break
        case 'Escape': setShowControls(true); break
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [cycleState, triggerSpeakingDemo])

  return (
    <div className="fixed inset-0 w-screen h-screen overflow-hidden bg-black select-none">
      {/* Full-Screen 3D Avatar */}
      <div className="absolute inset-0 w-full h-full">
        <AvatarAdapter
          isSpeaking={isSpeaking}
          isListening={isListening}
          state={avatarState}
          speechMarks={speechMarks}
          audioStartTime={audioStartTime}
          name="Angelica"
          fullScreen={true}
        />
      </div>

      {/* Controls Overlay (auto-hides) */}
      <div
        className={`absolute inset-0 z-30 pointer-events-none transition-opacity duration-500 ${
          showControls ? 'opacity-100' : 'opacity-0'
        }`}
      >
        {/* Top bar */}
        <div className="absolute top-0 left-0 right-0 p-4 flex items-center justify-between">
          <div className="flex items-center gap-3 pointer-events-auto">
            <a
              href="/"
              className="px-3 py-1.5 rounded-full bg-white/10 backdrop-blur-md border border-white/20 hover:bg-white/20 text-white text-xs font-medium transition-all"
            >
              ← Back
            </a>
            <h1 className="text-white/80 text-sm font-medium">
              3D Avatar — Full Screen Mode
            </h1>
          </div>

          <div className="flex items-center gap-2 pointer-events-auto">
            <div className={`px-3 py-1.5 rounded-full backdrop-blur-md border text-xs font-medium ${
              avatarState === 'idle' ? 'bg-gray-600/60 border-gray-400/30 text-gray-200' :
              avatarState === 'speaking' ? 'bg-blue-600/60 border-blue-400/30 text-blue-100' :
              avatarState === 'listening' ? 'bg-green-600/60 border-green-400/30 text-green-100' :
              avatarState === 'thinking' ? 'bg-amber-600/60 border-amber-400/30 text-amber-100' :
              'bg-purple-600/60 border-purple-400/30 text-purple-100'
            }`}>
              State: {avatarState}
            </div>
          </div>
        </div>

        {/* Bottom controls */}
        <div className="absolute bottom-0 left-0 right-0 p-6">
          <div className="max-w-xl mx-auto">
            {/* State buttons */}
            <div className="flex flex-wrap items-center justify-center gap-2 pointer-events-auto mb-4">
              {(['idle', 'greeting', 'speaking', 'listening', 'thinking'] as AvatarState[]).map((s) => (
                <button
                  key={s}
                  onClick={() => cycleState(s)}
                  className={`px-4 py-2 rounded-full backdrop-blur-md text-sm font-medium transition-all border shadow-lg ${
                    avatarState === s
                      ? 'bg-white/20 border-white/40 text-white scale-105'
                      : 'bg-white/5 border-white/15 text-white/70 hover:bg-white/10 hover:text-white'
                  }`}
                >
                  {s === 'idle' && '😐'}
                  {s === 'greeting' && '👋'}
                  {s === 'speaking' && '🗣️'}
                  {s === 'listening' && '👂'}
                  {s === 'thinking' && '🤔'}
                  {' '}{s.charAt(0).toUpperCase() + s.slice(1)}
                </button>
              ))}
            </div>

            {/* Lip sync demo button */}
            <div className="flex justify-center pointer-events-auto">
              <button
                onClick={triggerSpeakingDemo}
                className="px-6 py-2.5 rounded-full bg-gradient-to-r from-blue-600/80 to-purple-600/80 backdrop-blur-md text-white font-medium text-sm transition-all border border-blue-400/30 shadow-xl hover:scale-105 active:scale-95"
              >
                ▶ Play Lip Sync Demo
              </button>
            </div>

            {/* Keyboard shortcuts hint */}
            <div className="mt-4 text-center text-white/30 text-xs pointer-events-none">
              <p>🖱️ Drag to rotate • Scroll to zoom • Touch to interact</p>
              <p className="mt-1">Keys: 1-5 switch states • Space = speak • H = toggle UI</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
