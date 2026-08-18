/**
 * Avatar Adapter — Full-screen GLB Avatar Renderer
 *
 * Strategy:
 * 1. Check if WebGL2 is available (required for Three.js)
 * 2. Select renderer:
 *    - WebGL available → Avatar3D (loads angelica.glb with 52 ARKit blendshapes,
 *      falls back to procedural head internally if GLB not found)
 *    - No WebGL → Avatar2D (SVG fallback for low-power devices)
 *
 * The Avatar3D component handles full-screen rendering, mouse drag controls,
 * lip sync, eye blink, eye tracking, and realistic skin tone internally.
 */

import { useState, useEffect, Suspense, lazy } from 'react'

// Lazy load renderers (heavy — don't load if not needed)
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
  /** When true, avatar renders in full-screen immersive mode */
  fullScreen?: boolean
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

  useEffect(() => {
    if (isWebGLAvailable()) {
      setRenderer('3d')
    } else {
      setRenderer('2d')
    }
  }, [])

  if (renderer === 'loading') {
    return (
      <div
        className={`flex items-center justify-center bg-gradient-to-b from-[#1a1a2e] to-[#0f3460] ${
          props.fullScreen ? 'w-full h-full absolute inset-0' : 'w-full h-full min-h-[300px]'
        }`}
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
          className={`flex items-center justify-center bg-gradient-to-b from-[#1a1a2e] to-[#0f3460] ${
            props.fullScreen ? 'w-full h-full absolute inset-0' : 'w-full h-full min-h-[300px]'
          }`}
          role="img"
          aria-label="Avatar loading"
        >
          <div className="text-center">
            <div className="w-10 h-10 border-3 border-blue-400 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="text-white/60 text-sm">Loading 3D avatar...</p>
          </div>
        </div>
      }
    >
      {renderer === '3d' ? (
        <Avatar3D {...props} />
      ) : (
        <Avatar2D {...props} />
      )}
    </Suspense>
  )
}

/**
 * ARKit 52 Blendshape reference mapping from Polly visemes.
 * Used by Avatar3D internally when GLB model with morph targets is loaded.
 * Exported for reference/testing.
 */
export const VISEME_TO_BLENDSHAPE: Record<string, Record<string, number>> = {
  'sil': { jawOpen: 0.0, mouthClose: 1.0 },
  'p':   { jawOpen: 0.05, mouthPucker: 0.6, mouthPressLeft: 0.4, mouthPressRight: 0.4 },
  'f':   { jawOpen: 0.04, mouthFunnel: 0.4, mouthLowerDownLeft: 0.3, mouthLowerDownRight: 0.3 },
  't':   { jawOpen: 0.15, mouthStretchLeft: 0.2, mouthStretchRight: 0.2 },
  'k':   { jawOpen: 0.22, mouthShrugUpper: 0.3 },
  'S':   { jawOpen: 0.12, mouthFunnel: 0.5, mouthShrugUpper: 0.3 },
  's':   { jawOpen: 0.06, mouthSmileLeft: 0.15, mouthSmileRight: 0.15 },
  'T':   { jawOpen: 0.1, tongueOut: 0.4 },
  'r':   { jawOpen: 0.15, mouthFunnel: 0.35, mouthPucker: 0.2 },
  'i':   { jawOpen: 0.1, mouthSmileLeft: 0.5, mouthSmileRight: 0.5 },
  'u':   { jawOpen: 0.18, mouthPucker: 0.7, mouthFunnel: 0.3 },
  'e':   { jawOpen: 0.22, mouthSmileLeft: 0.3, mouthSmileRight: 0.3 },
  '@':   { jawOpen: 0.35, mouthFunnel: 0.2, mouthShrugLower: 0.2 },
  'a':   { jawOpen: 0.55, mouthLowerDownLeft: 0.4, mouthLowerDownRight: 0.4 },
  'o':   { jawOpen: 0.4, mouthPucker: 0.5, mouthFunnel: 0.4 },
  'E':   { jawOpen: 0.28, mouthSmileLeft: 0.4, mouthSmileRight: 0.4 },
  'O':   { jawOpen: 0.32, mouthPucker: 0.4, mouthFunnel: 0.3 },
}
