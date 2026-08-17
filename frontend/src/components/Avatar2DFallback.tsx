/**
 * 2D SVG Avatar Fallback.
 * Used when WebGL is not available (low-power devices, older browsers).
 * Provides visual state feedback without Three.js overhead.
 *
 * Animations: CSS-based (no Canvas/WebGL required)
 * - Idle: subtle breathing pulse
 * - Speaking: mouth animation + audio wave
 * - Listening: green indicator pulse
 * - Thinking: gentle head sway
 */

import { useState, useEffect } from 'react'

interface Avatar2DProps {
  isSpeaking: boolean
  isListening: boolean
  state: 'idle' | 'greeting' | 'speaking' | 'listening' | 'thinking'
  name?: string
}

export default function Avatar2DFallback({ isSpeaking, isListening, state }: Avatar2DProps) {
  const [mouthOpen, setMouthOpen] = useState(false)

  // Animate mouth when speaking
  useEffect(() => {
    if (!isSpeaking) {
      setMouthOpen(false)
      return
    }
    const interval = setInterval(() => {
      setMouthOpen(prev => !prev)
    }, 150)
    return () => clearInterval(interval)
  }, [isSpeaking])

  return (
    <div
      className="relative w-full h-full min-h-[280px] flex flex-col items-center justify-center"
      role="img"
      aria-label={`AI receptionist avatar, currently ${state}`}
    >
      {/* Background glow */}
      <div
        className={`absolute inset-0 rounded-full max-w-[250px] max-h-[250px] m-auto transition-all duration-1000 ${
          isSpeaking
            ? 'bg-gradient-to-r from-primary-500/20 to-accent-500/20 scale-110'
            : isListening
            ? 'bg-gradient-to-r from-green-500/15 to-primary-500/15 scale-105'
            : 'bg-gradient-to-r from-gray-800/50 to-gray-900/50 scale-100'
        }`}
      />

      {/* SVG Avatar */}
      <svg
        viewBox="0 0 200 220"
        className={`w-48 h-48 relative z-10 transition-transform duration-700 ${
          state === 'thinking' ? 'animate-pulse' : ''
        }`}
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        {/* Face */}
        <ellipse cx="100" cy="95" rx="65" ry="75" fill="#f5deb3" stroke="#d4a574" strokeWidth="1" />

        {/* Hair */}
        <path
          d="M35 85 C35 40 65 15 100 15 C135 15 165 40 165 85 C165 65 145 35 100 35 C55 35 35 65 35 85"
          fill="#2d1810"
        />

        {/* Eyes */}
        <ellipse cx="75" cy="90" rx="9" ry={state === 'thinking' ? 3 : 6} fill="white" />
        <ellipse cx="75" cy="90" rx="4.5" ry="4.5" fill="#4a3728" />
        <ellipse cx="125" cy="90" rx="9" ry={state === 'thinking' ? 3 : 6} fill="white" />
        <ellipse cx="125" cy="90" rx="4.5" ry="4.5" fill="#4a3728" />

        {/* Eyebrows */}
        <path d="M60 75 Q75 69 90 75" fill="none" stroke="#2d1810" strokeWidth="2.5" strokeLinecap="round" />
        <path d="M110 75 Q125 69 140 75" fill="none" stroke="#2d1810" strokeWidth="2.5" strokeLinecap="round" />

        {/* Nose */}
        <path d="M100 95 L96 110 Q100 113 104 110 Z" fill="#e8c9a0" />

        {/* Mouth */}
        {mouthOpen ? (
          <ellipse cx="100" cy="132" rx="12" ry="7" fill="#c94040" />
        ) : isListening ? (
          <path d="M87 130 Q100 140 113 130" fill="none" stroke="#c94040" strokeWidth="2.5" strokeLinecap="round" />
        ) : (
          <path d="M90 130 Q100 137 110 130" fill="none" stroke="#c94040" strokeWidth="2" strokeLinecap="round" />
        )}

        {/* Neck */}
        <rect x="88" y="165" width="24" height="20" rx="4" fill="#f5deb3" />

        {/* Shoulders */}
        <path d="M60 195 Q100 180 140 195 L145 220 H55 Z" fill="#3b82f6" rx="8" />
      </svg>

      {/* State indicator */}
      <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-20" aria-live="polite">
        {isSpeaking && (
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-primary-600/90 rounded-full">
            <div className="audio-wave text-white" aria-hidden="true">
              <div className="audio-wave-bar" />
              <div className="audio-wave-bar" />
              <div className="audio-wave-bar" />
            </div>
            <span className="text-xs text-white font-medium">Speaking</span>
          </div>
        )}
        {isListening && !isSpeaking && (
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600/90 rounded-full">
            <div className="w-2 h-2 bg-green-300 rounded-full animate-pulse" aria-hidden="true" />
            <span className="text-xs text-white font-medium">Listening</span>
          </div>
        )}
        {state === 'thinking' && (
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-yellow-600/90 rounded-full">
            <div className="w-2 h-2 bg-yellow-300 rounded-full animate-pulse" aria-hidden="true" />
            <span className="text-xs text-white font-medium">Thinking...</span>
          </div>
        )}
      </div>
    </div>
  )
}
