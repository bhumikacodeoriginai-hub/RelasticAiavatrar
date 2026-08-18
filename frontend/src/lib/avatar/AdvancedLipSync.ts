/**
 * AdvancedLipSync — High-quality viseme-to-blendshape lip synchronization.
 *
 * Features:
 * - Smooth interpolation between visemes with configurable curves
 * - Coarticulation: upcoming phonemes influence current mouth shape
 * - Anticipatory lip rounding (e.g., rounding before 'u' while still on 't')
 * - Jaw damping to prevent jerky jaw movement
 * - Intensity modulation based on speech energy
 * - Silence detection for natural mouth resting
 */

import type { BlendshapeMap, SpeechMark, AnimationSubsystem } from './types'

// ─── Full Polly Viseme → ARKit Blendshape Mapping ─────────────────────────────

const VISEME_MAP: Record<string, BlendshapeMap> = {
  'sil': {
    jawOpen: 0.0,
    mouthClose: 0.6,
    mouthPressLeft: 0.05,
    mouthPressRight: 0.05,
  },
  'p': {
    jawOpen: 0.04,
    mouthPucker: 0.55,
    mouthPressLeft: 0.45,
    mouthPressRight: 0.45,
    mouthClose: 0.3,
  },
  'f': {
    jawOpen: 0.05,
    mouthFunnel: 0.35,
    mouthLowerDownLeft: 0.3,
    mouthLowerDownRight: 0.3,
    mouthRollLower: 0.15,
  },
  't': {
    jawOpen: 0.15,
    mouthStretchLeft: 0.2,
    mouthStretchRight: 0.2,
    mouthShrugUpper: 0.1,
    mouthUpperUpLeft: 0.05,
    mouthUpperUpRight: 0.05,
  },
  'k': {
    jawOpen: 0.22,
    mouthShrugUpper: 0.25,
    mouthStretchLeft: 0.1,
    mouthStretchRight: 0.1,
  },
  'S': {
    jawOpen: 0.12,
    mouthFunnel: 0.5,
    mouthShrugUpper: 0.25,
    mouthPucker: 0.15,
  },
  's': {
    jawOpen: 0.06,
    mouthSmileLeft: 0.15,
    mouthSmileRight: 0.15,
    mouthStretchLeft: 0.2,
    mouthStretchRight: 0.2,
    mouthClose: 0.1,
  },
  'T': {
    jawOpen: 0.1,
    tongueOut: 0.35,
    mouthLowerDownLeft: 0.1,
    mouthLowerDownRight: 0.1,
  },
  'r': {
    jawOpen: 0.16,
    mouthFunnel: 0.35,
    mouthPucker: 0.2,
    mouthRollLower: 0.08,
  },
  'i': {
    jawOpen: 0.1,
    mouthSmileLeft: 0.5,
    mouthSmileRight: 0.5,
    mouthStretchLeft: 0.3,
    mouthStretchRight: 0.3,
    mouthUpperUpLeft: 0.05,
    mouthUpperUpRight: 0.05,
  },
  'u': {
    jawOpen: 0.18,
    mouthPucker: 0.7,
    mouthFunnel: 0.35,
    mouthRollLower: 0.1,
    mouthShrugLower: 0.05,
  },
  'e': {
    jawOpen: 0.22,
    mouthSmileLeft: 0.3,
    mouthSmileRight: 0.3,
    mouthUpperUpLeft: 0.1,
    mouthUpperUpRight: 0.1,
    mouthStretchLeft: 0.15,
    mouthStretchRight: 0.15,
  },
  '@': {
    jawOpen: 0.35,
    mouthFunnel: 0.2,
    mouthShrugLower: 0.2,
    mouthLowerDownLeft: 0.15,
    mouthLowerDownRight: 0.15,
  },
  'a': {
    jawOpen: 0.55,
    mouthLowerDownLeft: 0.4,
    mouthLowerDownRight: 0.4,
    mouthUpperUpLeft: 0.2,
    mouthUpperUpRight: 0.2,
    mouthStretchLeft: 0.1,
    mouthStretchRight: 0.1,
  },
  'o': {
    jawOpen: 0.4,
    mouthPucker: 0.5,
    mouthFunnel: 0.4,
    mouthRollLower: 0.05,
    mouthShrugLower: 0.08,
  },
  'E': {
    jawOpen: 0.28,
    mouthSmileLeft: 0.4,
    mouthSmileRight: 0.4,
    mouthStretchLeft: 0.2,
    mouthStretchRight: 0.2,
  },
  'O': {
    jawOpen: 0.32,
    mouthPucker: 0.4,
    mouthFunnel: 0.3,
    mouthShrugLower: 0.1,
  },
}

// Coarticulation weights — how much next viseme influences current
const COARTICULATION_WEIGHTS: Record<string, number> = {
  'u': 0.4, // Strong lip rounding anticipation
  'o': 0.35,
  'O': 0.3,
  'p': 0.25, // Lip closure anticipation
  'f': 0.2,
  'i': 0.15,
  'e': 0.1,
}

// ─── LipSync Engine ───────────────────────────────────────────────────────────

export class AdvancedLipSync implements AnimationSubsystem {
  private speechMarks: SpeechMark[] = []
  private audioStartTime = 0
  private isActive = false
  private currentBlendshapes: BlendshapeMap = {}
  private jawVelocity = 0 // For jaw damping
  private lastJawOpen = 0
  private silenceTimer = 0
  private fallbackMode = false
  private fallbackTarget = 0
  private fallbackTimer = 0

  // Config
  private smoothingFactor = 12 // Higher = faster transitions (more responsive)
  private jawDamping = 0.7 // Prevents jerky jaw (0 = no damping, 1 = very smooth)
  private coarticulationStrength = 0.6 // How much next phoneme bleeds into current
  private intensityMultiplier = 1.0

  /**
   * Start lip sync with speech marks from Polly.
   */
  startWithMarks(marks: SpeechMark[], startTime: number): void {
    this.speechMarks = marks.filter(m => m.type === 'viseme')
    this.audioStartTime = startTime
    this.isActive = true
    this.fallbackMode = false
    this.silenceTimer = 0
  }

  /**
   * Start fallback lip sync (random mouth movement when no speech marks).
   */
  startFallback(): void {
    this.isActive = true
    this.fallbackMode = true
    this.fallbackTimer = 0
  }

  /**
   * Stop lip sync.
   */
  stop(): void {
    this.isActive = false
    this.speechMarks = []
    this.fallbackMode = false
  }

  /**
   * Set intensity multiplier (e.g., reduce for whispering).
   */
  setIntensity(multiplier: number): void {
    this.intensityMultiplier = Math.max(0.1, Math.min(2, multiplier))
  }

  /**
   * Update lip sync — returns blendshape values for the mouth.
   */
  update(deltaTime: number): BlendshapeMap {
    if (!this.isActive) {
      // Smoothly return to rest position
      return this.decayToRest(deltaTime)
    }

    if (this.fallbackMode) {
      return this.updateFallback(deltaTime)
    }

    return this.updateWithMarks(deltaTime)
  }

  private updateWithMarks(deltaTime: number): BlendshapeMap {
    const elapsed = Date.now() - this.audioStartTime
    if (this.speechMarks.length === 0) return this.decayToRest(deltaTime)

    // Find current and next viseme
    let currentViseme = 'sil'
    let nextViseme = 'sil'
    let currentTime = 0
    let nextTime = 0

    for (let i = 0; i < this.speechMarks.length; i++) {
      const mark = this.speechMarks[i]
      if (mark.time <= elapsed) {
        currentViseme = mark.value
        currentTime = mark.time
        // Find next
        if (i + 1 < this.speechMarks.length) {
          nextViseme = this.speechMarks[i + 1].value
          nextTime = this.speechMarks[i + 1].time
        }
      } else {
        break
      }
    }

    // Check if we've passed the end
    const lastMark = this.speechMarks[this.speechMarks.length - 1]
    if (elapsed > lastMark.time + 500) {
      return this.decayToRest(deltaTime)
    }

    // Get target blendshapes for current viseme
    let targetShapes = { ...(VISEME_MAP[currentViseme] || VISEME_MAP['sil']) }

    // ─── Coarticulation ──────────────────────────────────────
    if (nextViseme !== currentViseme && nextTime > currentTime) {
      const timeBetween = nextTime - currentTime
      const timeToNext = nextTime - elapsed
      const anticipation = Math.max(0, 1 - timeToNext / timeBetween)

      const coartWeight = (COARTICULATION_WEIGHTS[nextViseme] || 0.1) * this.coarticulationStrength
      const nextShapes = VISEME_MAP[nextViseme] || VISEME_MAP['sil']

      // Blend in anticipatory shapes (especially lip rounding)
      if (anticipation > 0.5) {
        const blendAmount = (anticipation - 0.5) * 2 * coartWeight
        for (const [key, value] of Object.entries(nextShapes)) {
          const current = targetShapes[key] || 0
          targetShapes[key] = current + ((value as number) - current) * blendAmount
        }
      }
    }

    // ─── Apply intensity ─────────────────────────────────────
    for (const key of Object.keys(targetShapes)) {
      targetShapes[key]! *= this.intensityMultiplier
    }

    // ─── Smooth interpolation with jaw damping ───────────────
    const result: BlendshapeMap = {}
    for (const [key, targetValue] of Object.entries(targetShapes)) {
      const current = this.currentBlendshapes[key] || 0
      let smoothing = this.smoothingFactor * deltaTime

      // Extra damping for jaw to prevent chatter
      if (key === 'jawOpen') {
        const jawDelta = (targetValue || 0) - this.lastJawOpen
        this.jawVelocity += jawDelta * deltaTime * 20
        this.jawVelocity *= 1 - this.jawDamping
        const dampedTarget = this.lastJawOpen + this.jawVelocity
        result[key] = Math.max(0, Math.min(1, current + (dampedTarget - current) * smoothing))
        this.lastJawOpen = result[key]!
      } else {
        result[key] = current + ((targetValue || 0) - current) * smoothing
      }
    }

    // Fade out shapes not in target
    for (const key of Object.keys(this.currentBlendshapes)) {
      if (!(key in targetShapes)) {
        const faded = (this.currentBlendshapes[key] || 0) * (1 - this.smoothingFactor * deltaTime)
        if (faded > 0.001) result[key] = faded
      }
    }

    this.currentBlendshapes = result
    return { ...result }
  }

  private updateFallback(deltaTime: number): BlendshapeMap {
    this.fallbackTimer += deltaTime

    // Generate pseudo-random mouth movement
    if (this.fallbackTimer > 0.08 + Math.random() * 0.05) {
      this.fallbackTarget = 0.1 + Math.random() * 0.5
      this.fallbackTimer = 0
    }

    const result: BlendshapeMap = {}
    const jawTarget = this.fallbackTarget
    const current = this.currentBlendshapes.jawOpen || 0
    const jawOpen = current + (jawTarget - current) * 6 * deltaTime

    result.jawOpen = jawOpen
    result.mouthSmileLeft = jawOpen * 0.1
    result.mouthSmileRight = jawOpen * 0.1
    result.mouthFunnel = jawOpen * 0.15 + Math.sin(this.fallbackTimer * 8) * 0.05
    result.mouthLowerDownLeft = jawOpen * 0.4
    result.mouthLowerDownRight = jawOpen * 0.4
    result.mouthUpperUpLeft = jawOpen * 0.15
    result.mouthUpperUpRight = jawOpen * 0.15

    this.currentBlendshapes = result
    return result
  }

  private decayToRest(deltaTime: number): BlendshapeMap {
    const result: BlendshapeMap = {}
    let hasValues = false

    for (const [key, value] of Object.entries(this.currentBlendshapes)) {
      const decayed = (value || 0) * (1 - 6 * deltaTime)
      if (decayed > 0.001) {
        result[key] = decayed
        hasValues = true
      }
    }

    // Add subtle resting mouth
    result.mouthClose = 0.3
    result.mouthPressLeft = 0.02
    result.mouthPressRight = 0.02

    this.currentBlendshapes = result
    return result
  }

  reset(): void {
    this.speechMarks = []
    this.isActive = false
    this.currentBlendshapes = {}
    this.jawVelocity = 0
    this.lastJawOpen = 0
    this.fallbackMode = false
  }
}

export default AdvancedLipSync
