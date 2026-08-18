/**
 * EmotionEngine — Maps emotional states to precise ARKit 52 blendshape combinations.
 *
 * Supports 14 distinct human emotions with smooth transitions, intensity scaling,
 * and micro-expression overlays for realistic avatar behavior.
 *
 * Each emotion is defined as a set of blendshape targets with intensities [0-1].
 * The engine handles:
 * - Smooth interpolation between emotion states
 * - Intensity modulation (subtle vs. strong expression)
 * - Emotion blending (e.g., surprised + happy = delighted)
 * - Micro-expression flickers for realism
 * - Decay over time (emotions fade to neutral)
 */

import type { BlendshapeMap } from './types'

// ─── Emotion Definitions ──────────────────────────────────────────────────────

export type EmotionType =
  | 'neutral'
  | 'happy'
  | 'sad'
  | 'surprised'
  | 'angry'
  | 'disgusted'
  | 'fearful'
  | 'contempt'
  | 'interested'
  | 'confused'
  | 'empathetic'
  | 'proud'
  | 'embarrassed'
  | 'excited'

export interface EmotionState {
  primary: EmotionType
  intensity: number // 0-1
  secondary?: EmotionType
  secondaryIntensity?: number // 0-1
  microExpressionActive?: boolean
}

// ─── Blendshape Presets per Emotion ───────────────────────────────────────────

const EMOTION_BLENDSHAPES: Record<EmotionType, BlendshapeMap> = {
  neutral: {
    jawOpen: 0.0,
    mouthClose: 0.3,
    mouthSmileLeft: 0.02,
    mouthSmileRight: 0.02,
    browInnerUp: 0.0,
    eyeSquintLeft: 0.0,
    eyeSquintRight: 0.0,
  },

  happy: {
    mouthSmileLeft: 0.65,
    mouthSmileRight: 0.65,
    cheekSquintLeft: 0.4,
    cheekSquintRight: 0.4,
    eyeSquintLeft: 0.2,
    eyeSquintRight: 0.2,
    browInnerUp: 0.05,
    noseSneerLeft: 0.05,
    noseSneerRight: 0.05,
    mouthDimpleLeft: 0.2,
    mouthDimpleRight: 0.2,
    mouthUpperUpLeft: 0.08,
    mouthUpperUpRight: 0.08,
  },

  sad: {
    mouthFrownLeft: 0.5,
    mouthFrownRight: 0.5,
    browInnerUp: 0.45,
    browDownLeft: 0.1,
    browDownRight: 0.1,
    mouthLowerDownLeft: 0.15,
    mouthLowerDownRight: 0.15,
    eyeSquintLeft: 0.1,
    eyeSquintRight: 0.1,
    jawOpen: 0.02,
    mouthPressLeft: 0.2,
    mouthPressRight: 0.2,
  },

  surprised: {
    eyeWideLeft: 0.7,
    eyeWideRight: 0.7,
    browInnerUp: 0.6,
    browOuterUpLeft: 0.5,
    browOuterUpRight: 0.5,
    jawOpen: 0.4,
    mouthFunnel: 0.2,
    mouthUpperUpLeft: 0.1,
    mouthUpperUpRight: 0.1,
    mouthLowerDownLeft: 0.2,
    mouthLowerDownRight: 0.2,
  },

  angry: {
    browDownLeft: 0.6,
    browDownRight: 0.6,
    browInnerUp: 0.3,
    eyeSquintLeft: 0.35,
    eyeSquintRight: 0.35,
    noseSneerLeft: 0.4,
    noseSneerRight: 0.4,
    mouthFrownLeft: 0.3,
    mouthFrownRight: 0.3,
    jawForward: 0.15,
    mouthPressLeft: 0.3,
    mouthPressRight: 0.3,
    mouthRollLower: 0.1,
  },

  disgusted: {
    noseSneerLeft: 0.6,
    noseSneerRight: 0.6,
    mouthUpperUpLeft: 0.4,
    mouthUpperUpRight: 0.4,
    browDownLeft: 0.3,
    browDownRight: 0.3,
    mouthFrownLeft: 0.25,
    mouthFrownRight: 0.25,
    cheekSquintLeft: 0.2,
    cheekSquintRight: 0.2,
    eyeSquintLeft: 0.2,
    eyeSquintRight: 0.2,
    mouthShrugLower: 0.15,
  },

  fearful: {
    eyeWideLeft: 0.6,
    eyeWideRight: 0.6,
    browInnerUp: 0.7,
    browOuterUpLeft: 0.35,
    browOuterUpRight: 0.35,
    mouthStretchLeft: 0.3,
    mouthStretchRight: 0.3,
    jawOpen: 0.2,
    mouthFrownLeft: 0.15,
    mouthFrownRight: 0.15,
    mouthLowerDownLeft: 0.1,
    mouthLowerDownRight: 0.1,
  },

  contempt: {
    mouthSmileLeft: 0.35,
    mouthSmileRight: 0.0,
    mouthDimpleLeft: 0.3,
    browDownRight: 0.15,
    eyeSquintLeft: 0.15,
    noseSneerLeft: 0.1,
    mouthPressRight: 0.15,
    mouthRollLower: 0.08,
    cheekSquintLeft: 0.1,
  },

  interested: {
    browInnerUp: 0.25,
    browOuterUpLeft: 0.15,
    browOuterUpRight: 0.15,
    eyeWideLeft: 0.15,
    eyeWideRight: 0.15,
    mouthSmileLeft: 0.1,
    mouthSmileRight: 0.1,
    jawOpen: 0.03,
    mouthPucker: 0.05,
  },

  confused: {
    browDownLeft: 0.3,
    browInnerUp: 0.35,
    browOuterUpRight: 0.25,
    eyeSquintLeft: 0.2,
    mouthFrownLeft: 0.15,
    mouthFrownRight: 0.1,
    mouthPucker: 0.12,
    jawLeft: 0.05,
    mouthLeft: 0.08,
    mouthShrugLower: 0.1,
  },

  empathetic: {
    browInnerUp: 0.35,
    mouthSmileLeft: 0.2,
    mouthSmileRight: 0.2,
    eyeSquintLeft: 0.1,
    eyeSquintRight: 0.1,
    mouthFrownLeft: 0.08,
    mouthFrownRight: 0.08,
    cheekSquintLeft: 0.1,
    cheekSquintRight: 0.1,
    mouthPressLeft: 0.1,
    mouthPressRight: 0.1,
  },

  proud: {
    mouthSmileLeft: 0.4,
    mouthSmileRight: 0.4,
    browOuterUpLeft: 0.2,
    browOuterUpRight: 0.2,
    cheekSquintLeft: 0.2,
    cheekSquintRight: 0.2,
    eyeSquintLeft: 0.1,
    eyeSquintRight: 0.1,
    jawForward: 0.05,
    mouthShrugUpper: 0.1,
  },

  embarrassed: {
    mouthSmileLeft: 0.2,
    mouthSmileRight: 0.2,
    browInnerUp: 0.2,
    eyeSquintLeft: 0.15,
    eyeSquintRight: 0.15,
    mouthPressLeft: 0.2,
    mouthPressRight: 0.2,
    mouthRollLower: 0.15,
    cheekPuff: 0.1,
    mouthDimpleLeft: 0.1,
    mouthDimpleRight: 0.1,
  },

  excited: {
    mouthSmileLeft: 0.7,
    mouthSmileRight: 0.7,
    eyeWideLeft: 0.3,
    eyeWideRight: 0.3,
    browInnerUp: 0.3,
    browOuterUpLeft: 0.25,
    browOuterUpRight: 0.25,
    cheekSquintLeft: 0.35,
    cheekSquintRight: 0.35,
    jawOpen: 0.15,
    mouthUpperUpLeft: 0.1,
    mouthUpperUpRight: 0.1,
    noseSneerLeft: 0.05,
    noseSneerRight: 0.05,
  },
}

// ─── Micro-Expression Patterns (subtle involuntary flickers) ──────────────────

interface MicroExpression {
  blendshapes: BlendshapeMap
  duration: number // seconds
  probability: number // chance per second
}

const MICRO_EXPRESSIONS: MicroExpression[] = [
  // Lip corner twitch
  {
    blendshapes: { mouthSmileLeft: 0.15, mouthDimpleLeft: 0.1 },
    duration: 0.12,
    probability: 0.08,
  },
  // Brow flash (recognition/agreement)
  {
    blendshapes: { browInnerUp: 0.2, browOuterUpLeft: 0.15, browOuterUpRight: 0.15 },
    duration: 0.15,
    probability: 0.05,
  },
  // Nose wrinkle
  {
    blendshapes: { noseSneerLeft: 0.12, noseSneerRight: 0.12 },
    duration: 0.1,
    probability: 0.03,
  },
  // Lip press (thought processing)
  {
    blendshapes: { mouthPressLeft: 0.2, mouthPressRight: 0.2, mouthRollLower: 0.1 },
    duration: 0.2,
    probability: 0.06,
  },
  // Cheek dimple
  {
    blendshapes: { mouthDimpleRight: 0.15, cheekSquintRight: 0.08 },
    duration: 0.14,
    probability: 0.04,
  },
]

// ─── Engine Class ─────────────────────────────────────────────────────────────

export class EmotionEngine {
  private currentEmotion: EmotionState = { primary: 'neutral', intensity: 0.5 }
  private targetEmotion: EmotionState = { primary: 'neutral', intensity: 0.5 }
  private currentBlendshapes: BlendshapeMap = {}
  private microExprTimer = 0
  private activeMicroExpr: { blendshapes: BlendshapeMap; timeLeft: number } | null = null
  private transitionSpeed = 2.5 // blendshapes per second interpolation
  private decayRate = 0.15 // intensity decay per second toward neutral
  private emotionStartTime = 0
  private emotionDuration = 5.0 // seconds before decay starts

  /**
   * Set the target emotion. The engine smoothly transitions to it.
   */
  setEmotion(emotion: EmotionType, intensity: number = 0.7, secondary?: EmotionType, secondaryIntensity?: number): void {
    this.targetEmotion = {
      primary: emotion,
      intensity: Math.max(0, Math.min(1, intensity)),
      secondary,
      secondaryIntensity: secondaryIntensity ? Math.max(0, Math.min(1, secondaryIntensity)) : undefined,
    }
    this.emotionStartTime = performance.now() / 1000
  }

  /**
   * Get current emotion state for external queries.
   */
  getCurrentEmotion(): EmotionState {
    return { ...this.currentEmotion }
  }

  /**
   * Set transition speed (higher = faster emotion changes).
   */
  setTransitionSpeed(speed: number): void {
    this.transitionSpeed = Math.max(0.5, Math.min(10, speed))
  }

  /**
   * Update the engine and return current blendshape values.
   * Call this every frame with delta time.
   */
  update(deltaTime: number): BlendshapeMap {
    const now = performance.now() / 1000

    // ─── Emotion Decay ───────────────────────────────────────
    const elapsed = now - this.emotionStartTime
    if (elapsed > this.emotionDuration && this.targetEmotion.primary !== 'neutral') {
      this.targetEmotion.intensity = Math.max(
        0.1,
        this.targetEmotion.intensity - this.decayRate * deltaTime
      )
      if (this.targetEmotion.intensity <= 0.1) {
        this.targetEmotion = { primary: 'neutral', intensity: 0.5 }
      }
    }

    // ─── Smooth Interpolation of Emotion State ───────────────
    const lerpFactor = Math.min(1, this.transitionSpeed * deltaTime)
    this.currentEmotion.intensity += (this.targetEmotion.intensity - this.currentEmotion.intensity) * lerpFactor

    // If emotions differ, transition the primary
    if (this.currentEmotion.primary !== this.targetEmotion.primary) {
      // Crossfade: reduce current, then switch
      this.currentEmotion.intensity -= lerpFactor * 2
      if (this.currentEmotion.intensity <= 0.05) {
        this.currentEmotion.primary = this.targetEmotion.primary
        this.currentEmotion.intensity = 0.05
      }
    }

    // ─── Compute Blendshapes from Emotion ────────────────────
    const primaryShapes = EMOTION_BLENDSHAPES[this.currentEmotion.primary] || {}
    const result: BlendshapeMap = {}

    // Apply primary emotion with intensity
    for (const [key, value] of Object.entries(primaryShapes)) {
      result[key] = (value as number) * this.currentEmotion.intensity
    }

    // Blend secondary emotion if present
    if (this.targetEmotion.secondary && this.targetEmotion.secondaryIntensity) {
      const secondaryShapes = EMOTION_BLENDSHAPES[this.targetEmotion.secondary] || {}
      const secIntensity = this.targetEmotion.secondaryIntensity * 0.5 // Secondary is always weaker
      for (const [key, value] of Object.entries(secondaryShapes)) {
        const current = result[key] || 0
        result[key] = current + (value as number) * secIntensity
      }
    }

    // ─── Micro-Expressions ───────────────────────────────────
    this.microExprTimer += deltaTime
    if (!this.activeMicroExpr && this.microExprTimer > 0.5) {
      // Check if a micro-expression should fire
      for (const micro of MICRO_EXPRESSIONS) {
        if (Math.random() < micro.probability * deltaTime) {
          this.activeMicroExpr = {
            blendshapes: micro.blendshapes,
            timeLeft: micro.duration,
          }
          this.microExprTimer = 0
          break
        }
      }
    }

    if (this.activeMicroExpr) {
      this.activeMicroExpr.timeLeft -= deltaTime
      const microProgress = 1 - Math.abs(this.activeMicroExpr.timeLeft / 0.15 - 0.5) * 2
      const microFade = Math.max(0, Math.min(1, microProgress))

      for (const [key, value] of Object.entries(this.activeMicroExpr.blendshapes)) {
        const current = result[key] || 0
        result[key] = current + (value as number) * microFade
      }

      if (this.activeMicroExpr.timeLeft <= 0) {
        this.activeMicroExpr = null
      }
    }

    // ─── Smooth the final output ─────────────────────────────
    for (const key of Object.keys(result)) {
      const prev = this.currentBlendshapes[key] || 0
      result[key] = prev + ((result[key] || 0) - prev) * Math.min(1, 8 * deltaTime)
    }
    // Fade out blendshapes that are no longer in result
    for (const key of Object.keys(this.currentBlendshapes)) {
      if (!(key in result)) {
        const faded = (this.currentBlendshapes[key] || 0) * (1 - 5 * deltaTime)
        if (faded > 0.001) {
          result[key] = faded
        }
      }
    }

    this.currentBlendshapes = result

    // Clamp all values to [0, 1]
    for (const key of Object.keys(result)) {
      result[key] = Math.max(0, Math.min(1, result[key] || 0))
    }

    return result
  }

  /**
   * Reset the engine to neutral.
   */
  reset(): void {
    this.currentEmotion = { primary: 'neutral', intensity: 0.5 }
    this.targetEmotion = { primary: 'neutral', intensity: 0.5 }
    this.currentBlendshapes = {}
    this.activeMicroExpr = null
  }
}

export default EmotionEngine
