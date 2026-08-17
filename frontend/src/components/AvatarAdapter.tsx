/**
 * Avatar Adapter — Selects the appropriate avatar renderer.
 *
 * Strategy:
 * 1. Check if WebGL2 is available (required for Three.js)
 * 2. Check if a GLB model URL is configured
 * 3. Select renderer:
 *    - GLB model available + WebGL → GLBAvatar (blendshape lip sync)
 *    - WebGL available, no GLB → ProceduralAvatar3D (current fallback)
 *    - No WebGL → Avatar2D (SVG fallback for low-power devices)
 *
 * Props are identical regardless of renderer.
 */

import { useState, useEffect, Suspense, lazy } from 'react'

// Lazy load 3D components (heavy — don't load if not needed)
const Avatar3D = lazy(() => import('./Avatar3D'))
const Avatar2D = lazy(() => import('./Avatar2DFallback'))

interface SpeechMark {
  time: number
  type: string
  value: string
}

export interface AvatarProps {
  isSpeaking: boolean
  isListening: boolean
  state: 'idle' | 'greeting' | 'speaking' | 'listening' | 'thinking'
  speechMarks?: SpeechMark[]
  audioStartTime?: number
  name?: string
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

// Check if a GLB model URL is configured
const GLB_MODEL_URL = import.meta.env.VITE_AVATAR_MODEL_URL || ''

export default function AvatarAdapter(props: AvatarProps) {
  const [renderer, setRenderer] = useState<'3d' | '2d' | 'loading'>('loading')

  useEffect(() => {
    if (isWebGLAvailable()) {
      setRenderer('3d')
    } else {
      setRenderer('2d')
    }
  }, [])

  if (renderer === 'loading') {
    return (
      <div className="w-full h-full min-h-[300px] flex items-center justify-center" role="img" aria-label="Avatar loading">
        <div className="text-gray-400 text-sm">Loading avatar...</div>
      </div>
    )
  }

  return (
    <Suspense fallback={
      <div className="w-full h-full min-h-[300px] flex items-center justify-center" role="img" aria-label="Avatar loading">
        <div className="w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
      </div>
    }>
      {renderer === '3d' ? (
        <Avatar3D {...props} />
      ) : (
        <Avatar2D {...props} />
      )}
    </Suspense>
  )
}

/**
 * Blendshape mapping from Polly visemes to standard ARKit blendshapes.
 * Used when a GLB model with morph targets is loaded.
 *
 * Polly viseme → ARKit blendshape name → weight (0-1)
 */
export const VISEME_TO_BLENDSHAPE: Record<string, Record<string, number>> = {
  'sil': { 'jawOpen': 0.0, 'mouthClose': 1.0 },
  'p':   { 'jawOpen': 0.05, 'mouthPucker': 0.6, 'mouthClose': 0.3 },
  'f':   { 'jawOpen': 0.05, 'mouthFunnel': 0.5, 'mouthLowerDownLeft': 0.3 },
  't':   { 'jawOpen': 0.15, 'tongueOut': 0.1 },
  'k':   { 'jawOpen': 0.2, 'mouthOpen': 0.3 },
  'S':   { 'jawOpen': 0.1, 'mouthShrugUpper': 0.4 },
  's':   { 'jawOpen': 0.05, 'mouthSmile': 0.2 },
  'T':   { 'jawOpen': 0.1, 'tongueOut': 0.3 },
  'r':   { 'jawOpen': 0.15, 'mouthFunnel': 0.3 },
  'i':   { 'jawOpen': 0.1, 'mouthSmile': 0.5 },
  'u':   { 'jawOpen': 0.15, 'mouthPucker': 0.7 },
  'e':   { 'jawOpen': 0.2, 'mouthSmile': 0.3 },
  '@':   { 'jawOpen': 0.3, 'mouthOpen': 0.4 },
  'a':   { 'jawOpen': 0.5, 'mouthOpen': 0.6 },
  'o':   { 'jawOpen': 0.35, 'mouthPucker': 0.5 },
  'E':   { 'jawOpen': 0.25, 'mouthSmile': 0.4 },
  'O':   { 'jawOpen': 0.3, 'mouthPucker': 0.4, 'mouthOpen': 0.3 },
}
