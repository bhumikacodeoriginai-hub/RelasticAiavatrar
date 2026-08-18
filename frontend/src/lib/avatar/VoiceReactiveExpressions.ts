/**
 * VoiceReactiveExpressions — Real-time voice amplitude/pitch drives subtle facial reactions.
 *
 * When the avatar is speaking:
 * - Jaw opens proportional to amplitude
 * - Brows raise slightly on emphasis (high energy)
 * - Cheeks activate on louder phonemes
 * - Head micro-nods on stress syllables
 *
 * When listening:
 * - Subtle brow raises showing attention
 * - Small mouth reactions (empathetic responses)
 * - Eye widening on surprising/loud input
 */

import type { BlendshapeMap, VoiceAnalysis, AnimationSubsystem } from './types'

export class VoiceReactiveExpressions implements AnimationSubsystem {
  private smoothAmplitude = 0
  private smoothPitch = 0
  private smoothEnergy = 0
  private emphasisCooldown = 0
  private lastEmphasisTime = 0
  private headNodAccumulator = 0

  // Configurable sensitivity
  private amplitudeSensitivity = 1.0
  private pitchSensitivity = 0.8
  private emphasisThreshold = 0.65

  /**
   * Configure sensitivity parameters.
   */
  configure(options: {
    amplitudeSensitivity?: number
    pitchSensitivity?: number
    emphasisThreshold?: number
  }): void {
    if (options.amplitudeSensitivity !== undefined) this.amplitudeSensitivity = options.amplitudeSensitivity
    if (options.pitchSensitivity !== undefined) this.pitchSensitivity = options.pitchSensitivity
    if (options.emphasisThreshold !== undefined) this.emphasisThreshold = options.emphasisThreshold
  }

  /**
   * Update with current voice analysis data.
   * Returns blendshape modifiers driven by voice characteristics.
   */
  updateWithVoice(deltaTime: number, voice: VoiceAnalysis): BlendshapeMap {
    const result: BlendshapeMap = {}

    // Smooth the input values for natural movement
    const smoothing = 8 * deltaTime
    this.smoothAmplitude += (voice.amplitude * this.amplitudeSensitivity - this.smoothAmplitude) * smoothing
    this.smoothPitch += (voice.pitch * this.pitchSensitivity - this.smoothPitch) * (smoothing * 0.5)
    this.smoothEnergy += (voice.energy - this.smoothEnergy) * smoothing

    if (voice.isSpeaking) {
      // ─── Speaking Reactions ─────────────────────────────────
      // Jaw movement correlated with amplitude (additive to lip sync)
      result.jawOpen = this.smoothAmplitude * 0.15

      // Brow raise on emphasis/stress
      if (this.smoothEnergy > this.emphasisThreshold && this.emphasisCooldown <= 0) {
        result.browInnerUp = (this.smoothEnergy - this.emphasisThreshold) * 0.4
        result.browOuterUpLeft = (this.smoothEnergy - this.emphasisThreshold) * 0.25
        result.browOuterUpRight = (this.smoothEnergy - this.emphasisThreshold) * 0.25
        this.emphasisCooldown = 0.3 // Don't raise brows too often
      }
      this.emphasisCooldown = Math.max(0, this.emphasisCooldown - deltaTime)

      // Cheek activation on louder parts
      if (this.smoothAmplitude > 0.5) {
        const cheekIntensity = (this.smoothAmplitude - 0.5) * 0.3
        result.cheekSquintLeft = cheekIntensity
        result.cheekSquintRight = cheekIntensity
      }

      // Subtle smile during speaking (conversational warmth)
      result.mouthSmileLeft = 0.05 + this.smoothPitch * 0.08
      result.mouthSmileRight = 0.05 + this.smoothPitch * 0.08

      // Head nod accumulation for stress patterns
      this.headNodAccumulator += this.smoothEnergy * deltaTime * 2

    } else {
      // ─── Listening Reactions ────────────────────────────────
      // Attentive brow raise
      result.browInnerUp = 0.08 + this.smoothAmplitude * 0.15
      result.browOuterUpLeft = this.smoothAmplitude * 0.1
      result.browOuterUpRight = this.smoothAmplitude * 0.1

      // Empathetic mouth reactions
      if (this.smoothAmplitude > 0.3) {
        result.mouthSmileLeft = 0.06
        result.mouthSmileRight = 0.06
      }

      // Eye widening on loud/surprising input
      if (this.smoothAmplitude > 0.7) {
        const wideAmount = (this.smoothAmplitude - 0.7) * 0.5
        result.eyeWideLeft = wideAmount
        result.eyeWideRight = wideAmount
      }

      // Subtle nod pattern while listening
      this.headNodAccumulator += this.smoothAmplitude * deltaTime * 0.5
    }

    return result
  }

  /**
   * Get head nod impulse (consumed when read, resets accumulator).
   * Returns a value 0-1 indicating how strong the next nod should be.
   */
  consumeHeadNod(): number {
    if (this.headNodAccumulator > 1.0) {
      this.headNodAccumulator = 0
      return Math.min(1, this.headNodAccumulator)
    }
    return 0
  }

  /**
   * Standard update interface (without voice data, returns minimal output).
   */
  update(deltaTime: number): BlendshapeMap {
    // Decay smoothed values
    this.smoothAmplitude *= 1 - 3 * deltaTime
    this.smoothPitch *= 1 - 2 * deltaTime
    this.smoothEnergy *= 1 - 3 * deltaTime
    return {}
  }

  reset(): void {
    this.smoothAmplitude = 0
    this.smoothPitch = 0
    this.smoothEnergy = 0
    this.emphasisCooldown = 0
    this.headNodAccumulator = 0
  }
}

export default VoiceReactiveExpressions
