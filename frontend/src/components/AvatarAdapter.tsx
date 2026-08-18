/**
 * AvatarAdapter — Intelligent Avatar Renderer Selection
 *
 * Strategy:
 * 1. Check WebGL2 availability (required for Three.js / Angelica GLB)
 * 2. Check prefers-reduced-motion for accessibility
 * 3. Render:
 *    - WebGL2 available → Avatar3D (Angelica GLB with full 52 ARKit blendshapes)
 *    - No WebGL2 → Avatar2DFallback (accessible SVG animation)
 *
 * The Angelica model is the PRIMARY and ONLY 3D avatar.
 * If the GLB file is missing, Avatar3D internally falls back to a procedural head.
 */

import { useState, useEffect, Suspense, lazy, useMemo } from 'react'
import type { EmotionType, GestureType, AvatarActivityState, SpeechMark } from '../lib/avatar'

// Lazy load renderers
const Avatar3D = lazy(() => import('./Avatar3D'))
const Avatar2DFallback = lazy(() => import('./Avatar2DFallback'))

export interface AvatarProps {
  isSpeaking: boolean
  isListening: boolean
  state: AvatarActivityState
  speechMarks?: SpeechMark[]
  audioStartTime?: number
  name?: string
  /** Emotion to express (from emotion analysis) */
  emotion?: EmotionType
  /** Emotion intensity 0-1 */
  emotionIntensity?: number
  /** Trigger a gesture */
  gesture?: GestureType
  /** Override reduced motion (otherwise detects from OS preference) */
  reducedMotion?: boolean
  /** Full-screen immersive mode */
  fullScreen?: boolean
  /** Called when avatar is ready to render */
  onReady?: () => void
}

// Detect WebGL2 support
function isWebGLAvailable(): boolean {
  try {
    const canvas = document.createElement('canvas')
    return !!(
      window.WebGL2RenderingContext &&
      canvas.getContext('webgl2')
    )
  } catch {
    return false
  }
}

export default function AvatarAdapter(props: AvatarProps) {
  const [renderer, setRenderer] = useState<'3d' | '2d' | 'loading'>('loading')

  // Detect reduced motion preference
  const prefersReducedMotion = useMemo(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }, [])

  useEffect(() => {
    if (isWebGLAvailable()) {
      setRenderer('3d')
    } else {
      setRenderer('2d')
    }
  }, [])

  const containerClass = props.fullScreen
    ? 'w-full h-full absolute inset-0'
    : 'w-full h-full min-h-[300px]'

  if (renderer === 'loading') {
    return (
      <div
        className={`flex items-center justify-center bg-gradient-to-b from-[#1a1a2e] to-[#0f3460] ${containerClass}`}
        role="img"
        aria-label="Avatar loading"
      >
        <div className="text-center">
          <div className="w-10 h-10 border-3 border-blue-400 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-white/60 text-sm">Initializing avatar...</p>
        </div>
      </div>
    )
  }

  return (
    <Suspense
      fallback={
        <div
          className={`flex items-center justify-center bg-gradient-to-b from-[#1a1a2e] to-[#0f3460] ${containerClass}`}
          role="img"
          aria-label="Avatar loading"
        >
          <div className="text-center">
            <div className="w-10 h-10 border-3 border-blue-400 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="text-white/60 text-sm">Loading Angelica avatar...</p>
          </div>
        </div>
      }
    >
      {renderer === '3d' ? (
        <Avatar3D
          isSpeaking={props.isSpeaking}
          isListening={props.isListening}
          state={props.state}
          speechMarks={props.speechMarks}
          audioStartTime={props.audioStartTime}
          name={props.name}
          emotion={props.emotion}
          emotionIntensity={props.emotionIntensity}
          gesture={props.gesture}
          reducedMotion={props.reducedMotion ?? prefersReducedMotion}
          onReady={props.onReady}
        />
      ) : (
        <Avatar2DFallback
          isSpeaking={props.isSpeaking}
          isListening={props.isListening}
          state={props.state}
          speechMarks={props.speechMarks}
          audioStartTime={props.audioStartTime}
          name={props.name}
        />
      )}
    </Suspense>
  )
}
