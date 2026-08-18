/**
 * BreathingSystem — Realistic thoracic and diaphragmatic breathing animation.
 *
 * Features:
 * - Natural breath cycle with inhale/exhale asymmetry (inhale shorter than exhale)
 * - Breath rate varies with emotional state (calm=slow, excited=fast, anxious=shallow)
 * - Subtle jaw movement on exhale
 * - Chest/body rise via position offset
 * - Breath holds during speaking (natural speech breathing)
 * - Random breath depth variation (not robotic)
 * - Sigh generation (deep exhale with vocalization marker)
 */

import type { BlendshapeMap, AnimationSubsystem } from './types'

// ─── Breathing Profiles ───────────────────────────────────────────────────────

export type BreathingProfile = 'calm' | 'normal' | 'excited' | 'anxious' | 'speaking' | 'deep'

interface BreathProfile {
  cycleTime: number       // Full breath cycle in seconds
  inhaleRatio: number     // Proportion of cycle that is inhale (0-1)
  depth: number           // Breath depth multiplier (0-1)
  variability: number     // Random variation in timing (0-1)
  jawComponent: number    // How much jaw opens on exhale (0-1)
  chestAmplitude: number  // Vertical body movement (units)
  noseFlare: number       // Nose flare amount on inhale
}

const BREATH_PROFILES: Record<BreathingProfile, BreathProfile> = {
  calm: {
    cycleTime: 5.5,
    inhaleRatio: 0.38,
    depth: 0.6,
    variability: 0.15,
    jawComponent: 0.01,
    chestAmplitude: 0.006,
    noseFlare: 0.03,
  },
  normal: {
    cycleTime: 4.0,
    inhaleRatio: 0.4,
    depth: 0.7,
    variability: 0.2,
    jawComponent: 0.015,
    chestAmplitude: 0.008,
    noseFlare: 0.05,
  },
  excited: {
    cycleTime: 2.8,
    inhaleRatio: 0.42,
    depth: 0.85,
    variability: 0.25,
    jawComponent: 0.02,
    chestAmplitude: 0.012,
    noseFlare: 0.08,
  },
  anxious: {
    cycleTime: 2.2,
    inhaleRatio: 0.45,
    depth: 0.5, // Shallow
    variability: 0.3,
    jawComponent: 0.01,
    chestAmplitude: 0.005,
    noseFlare: 0.04,
  },
  speaking: {
    cycleTime: 6.0, // Longer cycles during speech (breath between phrases)
    inhaleRatio: 0.25, // Quick inhale, long exhale (speech)
    depth: 0.4,
    variability: 0.1,
    jawComponent: 0.0, // Jaw controlled by lip sync during speech
    chestAmplitude: 0.004,
    noseFlare: 0.02,
  },
  deep: {
    cycleTime: 7.0,
    inhaleRatio: 0.35,
    depth: 1.0,
    variability: 0.1,
    jawComponent: 0.025,
    chestAmplitude: 0.015,
    noseFlare: 0.1,
  },
}

// ─── Breathing System Class ───────────────────────────────────────────────────

export class BreathingSystem implements AnimationSubsystem {
  private phase = 0 // 0-1 through the breath cycle
  private currentProfile: BreathProfile = BREATH_PROFILES.normal
  private targetProfile: BreathProfile = BREATH_PROFILES.normal
  private currentCycleTime = 4.0
  private currentDepth = 0.7
  private breathHold = false
  private holdTimer = 0
  private lastBodyOffset = 0
  private sighPending = false
  private sighPhase = 0

  // Smoothed outputs
  private smoothChestOffset = 0
  private smoothJaw = 0

  /**
   * Set the breathing profile (based on emotional/activity state).
   */
  setProfile(profile: BreathingProfile): void {
    this.targetProfile = BREATH_PROFILES[profile]
  }

  /**
   * Hold breath (e.g., during speech phrase).
   */
  hold(): void {
    this.breathHold = true
    this.holdTimer = 0
  }

  /**
   * Resume breathing after hold.
   */
  resume(): void {
    this.breathHold = false
  }

  /**
   * Trigger a sigh (deep exhale, often emotional).
   */
  triggerSigh(): void {
    this.sighPending = true
  }

  /**
   * Get the vertical body offset for chest movement.
   */
  getBodyOffset(): number {
    return this.smoothChestOffset
  }

  /**
   * Update breathing and return blendshape contributions.
   */
  update(deltaTime: number): BlendshapeMap {
    const result: BlendshapeMap = {}

    // ─── Profile Interpolation ───────────────────────────────
    const lerpFactor = 2 * deltaTime
    this.currentCycleTime += (this.targetProfile.cycleTime - this.currentCycleTime) * lerpFactor
    this.currentDepth += (this.targetProfile.depth - this.currentDepth) * lerpFactor
    this.currentProfile = {
      ...this.currentProfile,
      jawComponent: this.currentProfile.jawComponent + (this.targetProfile.jawComponent - this.currentProfile.jawComponent) * lerpFactor,
      chestAmplitude: this.currentProfile.chestAmplitude + (this.targetProfile.chestAmplitude - this.currentProfile.chestAmplitude) * lerpFactor,
      noseFlare: this.currentProfile.noseFlare + (this.targetProfile.noseFlare - this.currentProfile.noseFlare) * lerpFactor,
      inhaleRatio: this.currentProfile.inhaleRatio + (this.targetProfile.inhaleRatio - this.currentProfile.inhaleRatio) * lerpFactor,
    }

    // ─── Breath Hold ─────────────────────────────────────────
    if (this.breathHold) {
      this.holdTimer += deltaTime
      // Auto-resume after max hold (2 seconds)
      if (this.holdTimer > 2.0) {
        this.breathHold = false
      }
      // Maintain current chest position during hold
      result.noseSneerLeft = 0
      result.noseSneerRight = 0
      return result
    }

    // ─── Phase Advancement ───────────────────────────────────
    // Add variability
    const variation = 1 + (Math.sin(performance.now() * 0.001) * this.targetProfile.variability)
    const effectiveCycleTime = this.currentCycleTime * variation
    this.phase += deltaTime / effectiveCycleTime

    // Handle sigh
    if (this.sighPending && this.phase > 0.9) {
      this.sighPending = false
      this.sighPhase = 1.0
      this.currentDepth = 1.0 // Force deep breath
    }
    if (this.sighPhase > 0) {
      this.sighPhase -= deltaTime * 0.5
    }

    if (this.phase >= 1.0) {
      this.phase -= 1.0
      // Randomize next cycle slightly
      this.currentDepth = this.targetProfile.depth * (0.85 + Math.random() * 0.3)
    }

    // ─── Compute Breath Curve ────────────────────────────────
    const inhaleEnd = this.currentProfile.inhaleRatio
    let breathValue: number

    if (this.phase < inhaleEnd) {
      // Inhale phase — smooth rise
      const t = this.phase / inhaleEnd
      breathValue = this.easeInOutCubic(t)
    } else {
      // Exhale phase — slower descent
      const t = (this.phase - inhaleEnd) / (1 - inhaleEnd)
      breathValue = 1 - this.easeInOutCubic(t)
    }

    breathValue *= this.currentDepth

    // ─── Apply to Blendshapes ────────────────────────────────
    // Nose flare on inhale
    const isInhaling = this.phase < inhaleEnd
    if (isInhaling) {
      const flareAmount = breathValue * this.currentProfile.noseFlare
      result.noseSneerLeft = flareAmount
      result.noseSneerRight = flareAmount
    } else {
      result.noseSneerLeft = 0
      result.noseSneerRight = 0
    }

    // Jaw opens slightly on exhale
    if (!isInhaling) {
      const exhaleProgress = (this.phase - inhaleEnd) / (1 - inhaleEnd)
      const jawOpen = Math.sin(exhaleProgress * Math.PI) * this.currentProfile.jawComponent * this.currentDepth
      result.jawOpen = jawOpen

      // Sigh adds extra jaw and vocalization appearance
      if (this.sighPhase > 0) {
        result.jawOpen = (result.jawOpen || 0) + this.sighPhase * 0.08
        result.mouthFunnel = this.sighPhase * 0.05
      }
    }

    // Subtle brow movement with breathing (very subtle)
    result.browInnerUp = breathValue * 0.01

    // ─── Chest/Body Offset ───────────────────────────────────
    const targetChestOffset = breathValue * this.currentProfile.chestAmplitude
    this.smoothChestOffset += (targetChestOffset - this.smoothChestOffset) * 8 * deltaTime

    return result
  }

  /**
   * Cubic ease in-out for natural breath curves.
   */
  private easeInOutCubic(t: number): number {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2
  }

  reset(): void {
    this.phase = 0
    this.currentProfile = BREATH_PROFILES.normal
    this.targetProfile = BREATH_PROFILES.normal
    this.currentCycleTime = 4.0
    this.currentDepth = 0.7
    this.breathHold = false
    this.smoothChestOffset = 0
    this.sighPending = false
    this.sighPhase = 0
  }
}

export default BreathingSystem
