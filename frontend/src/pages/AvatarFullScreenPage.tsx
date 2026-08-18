/**
 * AvatarFullScreenPage — Standalone Full-Screen Angelica Avatar Demo
 *
 * Showcases the complete 52 ARKit blendshape animation system:
 * - Emotion switching (14 human emotions)
 * - Gesture triggers (nod, shake, tilt, shrug, thinking)
 * - Lip sync demo (Polly viseme sequence)
 * - Eye tracking (follows mouse)
 * - Breathing (visible chest movement)
 * - Micro-expressions
 * - Reduced-motion toggle
 * - Keyboard shortcuts for all controls
 * - No auth required — great for demos/showcases
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import AvatarAdapter from '../components/AvatarAdapter'
import type { EmotionType, GestureType, AvatarActivityState, SpeechMark } from '../lib/avatar'

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

const EMOTIONS: EmotionType[] = [
  'neutral', 'happy', 'sad', 'surprised', 'angry',
  'interested', 'confused', 'empathetic', 'proud', 'excited',
  'embarrassed', 'contempt', 'fearful', 'disgusted',
]

const GESTURES: GestureType[] = [
  'nod', 'shake', 'tilt_left', 'tilt_right', 'shrug',
  'thinking', 'agreement', 'surprise_brow', 'empathy_tilt',
]

const EMOTION_EMOJIS: Record<EmotionType, string> = {
  neutral: '😐',
  happy: '😊',
  sad: '😢',
  surprised: '😲',
  angry: '😠',
  interested: '🧐',
  confused: '😕',
  empathetic: '💙',
  proud: '😌',
  excited: '🎉',
  embarrassed: '😳',
  contempt: '😏',
  fearful: '😰',
  disgusted: '🤢',
}

export default function AvatarFullScreenPage() {
  const [avatarState, setAvatarState] = useState<AvatarActivityState>('idle')
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [isListening, setIsListening] = useState(false)
  const [speechMarks, setSpeechMarks] = useState<SpeechMark[]>([])
  const [audioStartTime, setAudioStartTime] = useState<number>(0)
  const [showControls, setShowControls] = useState(true)
  const [currentEmotion, setCurrentEmotion] = useState<EmotionType>('neutral')
  const [emotionIntensity, setEmotionIntensity] = useState(0.7)
  const [currentGesture, setCurrentGesture] = useState<GestureType | undefined>(undefined)
  const [reducedMotion, setReducedMotion] = useState(false)
  const [showEmotionPanel, setShowEmotionPanel] = useState(false)
  const [showGesturePanel, setShowGesturePanel] = useState(false)
  const speakingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Auto-hide controls
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>
    const resetTimer = () => {
      setShowControls(true)
      clearTimeout(timer)
      timer = setTimeout(() => setShowControls(false), 6000)
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

  const triggerSpeakingDemo = useCallback(() => {
    setAvatarState('speaking')
    setIsSpeaking(true)
    setIsListening(false)
    setSpeechMarks(DEMO_VISEMES)
    setAudioStartTime(Date.now())
    setCurrentEmotion('happy')

    if (speakingTimeoutRef.current) clearTimeout(speakingTimeoutRef.current)
    speakingTimeoutRef.current = setTimeout(() => {
      setIsSpeaking(false)
      setAvatarState('idle')
      setSpeechMarks([])
      setCurrentEmotion('neutral')
    }, 3200)
  }, [])

  const cycleState = useCallback((newState: AvatarActivityState) => {
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

  const triggerGesture = useCallback((gesture: GestureType) => {
    setCurrentGesture(gesture)
    setTimeout(() => setCurrentGesture(undefined), 100)
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
        case 'e': setShowEmotionPanel(prev => !prev); break
        case 'g': setShowGesturePanel(prev => !prev); break
        case 'r': setReducedMotion(prev => !prev); break
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
          emotion={currentEmotion}
          emotionIntensity={emotionIntensity}
          gesture={currentGesture}
          reducedMotion={reducedMotion}
          fullScreen={true}
        />
      </div>

      {/* Controls Overlay */}
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
              Angelica Avatar — 52 ARKit Blendshapes
            </h1>
          </div>

          <div className="flex items-center gap-2 pointer-events-auto">
            {/* Current state badge */}
            <div className={`px-3 py-1.5 rounded-full backdrop-blur-md border text-xs font-medium ${
              avatarState === 'idle' ? 'bg-gray-600/60 border-gray-400/30 text-gray-200' :
              avatarState === 'speaking' ? 'bg-blue-600/60 border-blue-400/30 text-blue-100' :
              avatarState === 'listening' ? 'bg-green-600/60 border-green-400/30 text-green-100' :
              avatarState === 'thinking' ? 'bg-amber-600/60 border-amber-400/30 text-amber-100' :
              'bg-purple-600/60 border-purple-400/30 text-purple-100'
            }`}>
              State: {avatarState}
            </div>
            {/* Current emotion badge */}
            <div className="px-3 py-1.5 rounded-full bg-pink-600/60 backdrop-blur-md border border-pink-400/30 text-xs font-medium text-pink-100">
              {EMOTION_EMOJIS[currentEmotion]} {currentEmotion}
            </div>
            {/* Reduced motion */}
            <button
              onClick={() => setReducedMotion(!reducedMotion)}
              className={`px-3 py-1.5 rounded-full backdrop-blur-md border text-xs font-medium transition-all ${
                reducedMotion
                  ? 'bg-orange-600/60 border-orange-400/30 text-orange-100'
                  : 'bg-white/10 border-white/20 text-white/60 hover:bg-white/20'
              }`}
            >
              {reducedMotion ? '⚡ Slow' : '⚡ Normal'}
            </button>
          </div>
        </div>

        {/* Emotion Panel (left side) */}
        {showEmotionPanel && (
          <div className="absolute top-20 left-4 w-56 max-h-[60vh] overflow-y-auto p-3 bg-gray-900/90 backdrop-blur-xl rounded-xl border border-white/10 pointer-events-auto">
            <h3 className="text-white text-xs font-bold mb-2 uppercase tracking-wider">Emotions</h3>
            <div className="grid grid-cols-2 gap-1.5">
              {EMOTIONS.map((em) => (
                <button
                  key={em}
                  onClick={() => { setCurrentEmotion(em); setEmotionIntensity(0.7) }}
                  className={`px-2 py-1.5 rounded-lg text-xs transition-all ${
                    currentEmotion === em
                      ? 'bg-pink-600/80 text-white font-medium'
                      : 'bg-white/5 text-white/60 hover:bg-white/15 hover:text-white'
                  }`}
                >
                  {EMOTION_EMOJIS[em]} {em}
                </button>
              ))}
            </div>
            <div className="mt-3">
              <label className="text-white/50 text-xs block mb-1">Intensity: {emotionIntensity.toFixed(1)}</label>
              <input
                type="range"
                min="0.1"
                max="1"
                step="0.1"
                value={emotionIntensity}
                onChange={(e) => setEmotionIntensity(parseFloat(e.target.value))}
                className="w-full h-1.5 rounded-full appearance-none bg-white/20"
              />
            </div>
          </div>
        )}

        {/* Gesture Panel (right side) */}
        {showGesturePanel && (
          <div className="absolute top-20 right-4 w-48 p-3 bg-gray-900/90 backdrop-blur-xl rounded-xl border border-white/10 pointer-events-auto">
            <h3 className="text-white text-xs font-bold mb-2 uppercase tracking-wider">Gestures</h3>
            <div className="flex flex-col gap-1.5">
              {GESTURES.map((g) => (
                <button
                  key={g}
                  onClick={() => triggerGesture(g)}
                  className="px-3 py-1.5 rounded-lg bg-white/5 text-white/70 text-xs text-left hover:bg-white/15 hover:text-white transition-all"
                >
                  {g.replace(/_/g, ' ')}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Bottom controls */}
        <div className="absolute bottom-0 left-0 right-0 p-6">
          <div className="max-w-3xl mx-auto">
            {/* Panel toggles */}
            <div className="flex justify-center gap-2 mb-3 pointer-events-auto">
              <button
                onClick={() => setShowEmotionPanel(!showEmotionPanel)}
                className={`px-4 py-2 rounded-full backdrop-blur-md text-sm font-medium transition-all border ${
                  showEmotionPanel
                    ? 'bg-pink-600/60 border-pink-400/30 text-white'
                    : 'bg-white/5 border-white/15 text-white/60 hover:bg-white/10'
                }`}
              >
                🎭 Emotions (E)
              </button>
              <button
                onClick={() => setShowGesturePanel(!showGesturePanel)}
                className={`px-4 py-2 rounded-full backdrop-blur-md text-sm font-medium transition-all border ${
                  showGesturePanel
                    ? 'bg-teal-600/60 border-teal-400/30 text-white'
                    : 'bg-white/5 border-white/15 text-white/60 hover:bg-white/10'
                }`}
              >
                🤲 Gestures (G)
              </button>
            </div>

            {/* State buttons */}
            <div className="flex flex-wrap items-center justify-center gap-2 pointer-events-auto mb-3">
              {(['idle', 'greeting', 'speaking', 'listening', 'thinking'] as AvatarActivityState[]).map((s) => (
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

            {/* Lip sync demo */}
            <div className="flex justify-center pointer-events-auto">
              <button
                onClick={triggerSpeakingDemo}
                className="px-6 py-2.5 rounded-full bg-gradient-to-r from-blue-600/80 to-purple-600/80 backdrop-blur-md text-white font-medium text-sm transition-all border border-blue-400/30 shadow-xl hover:scale-105 active:scale-95"
              >
                ▶ Play Lip Sync Demo
              </button>
            </div>

            {/* Keyboard shortcuts */}
            <div className="mt-4 text-center text-white/30 text-xs pointer-events-none">
              <p>🖱️ Drag to rotate • Scroll to zoom • Touch to interact</p>
              <p className="mt-1">Keys: 1-5 states • Space = speak • E = emotions • G = gestures • R = reduced motion • H = toggle UI</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
