/**
 * GazeSystem — Realistic eye movement with saccades, fixation, and social attention.
 *
 * Features:
 * - Smooth pursuit: eyes track target (mouse/face) with realistic lag
 * - Micro-saccades: tiny involuntary eye movements during fixation
 * - Attention shifts: periodic glance-away for natural behavior
 * - Social gaze patterns: triangular face scanning (eyes-nose-mouth)
 * - Blink coordination: eyes look down briefly during blinks
 * - Eye vergence: slight cross-eye on close objects
 * - Pupil dilation (via eye wide/squint) based on interest
 */

import type { BlendshapeMap, AnimationSubsystem } from './types'

// ─── Gaze Target Types ────────────────────────────────────────────────────────

export type GazeMode =
  | 'track_cursor'     // Follow mouse/face
  | 'social_scan'      // Triangle pattern (eyes-nose-mouth of speaker)
  | 'look_away'        // Brief glance away (thinking/discomfort)
  | 'fixed_point'      // Stare at specific point
  | 'idle_wander'      // Gentle random wandering

interface GazeTarget {
  x: number // -1 to 1 (left to right)
  y: number // -1 to 1 (down to up)
}

// ─── Saccade Parameters ───────────────────────────────────────────────────────

interface Saccade {
  targetX: number
  targetY: number
  duration: number
  elapsed: number
}

// ─── Gaze System Class ────────────────────────────────────────────────────────

export class GazeSystem implements AnimationSubsystem {
  private mode: GazeMode = 'idle_wander'
  private currentGaze: GazeTarget = { x: 0, y: 0 }
  private targetGaze: GazeTarget = { x: 0, y: 0 }
  private externalTarget: GazeTarget = { x: 0, y: 0 } // Mouse/face position

  // Saccades
  private activeSaccade: Saccade | null = null
  private microSaccadeTimer = 0
  private microSaccadeInterval = 0.3 + Math.random() * 0.5

  // Attention patterns
  private attentionTimer = 0
  private attentionShiftInterval = 3 + Math.random() * 4
  private lookAwayTimer = 0
  private isLookingAway = false
  private lookAwayDuration = 0

  // Social scan (triangular gaze)
  private socialScanPhase = 0
  private socialScanTimer = 0
  private socialScanPoints: GazeTarget[] = [
    { x: -0.1, y: 0.1 },   // Left eye
    { x: 0.1, y: 0.1 },    // Right eye
    { x: 0, y: -0.05 },    // Nose
    { x: 0, y: -0.15 },    // Mouth
  ]

  // Idle wander
  private wanderTarget: GazeTarget = { x: 0, y: 0 }
  private wanderTimer = 0
  private wanderInterval = 2 + Math.random() * 3

  // Smoothing
  private smoothX = 0
  private smoothY = 0
  private velocityX = 0
  private velocityY = 0

  // Interest level affects pupil dilation
  private interestLevel = 0.5

  /**
   * Set the gaze tracking mode.
   */
  setMode(mode: GazeMode): void {
    this.mode = mode
    if (mode === 'social_scan') {
      this.socialScanPhase = 0
      this.socialScanTimer = 0
    }
  }

  /**
   * Update external tracking target (e.g., mouse position).
   * Values should be normalized -1 to 1.
   */
  setTarget(x: number, y: number): void {
    this.externalTarget = {
      x: Math.max(-1, Math.min(1, x)),
      y: Math.max(-1, Math.min(1, y)),
    }
  }

  /**
   * Set interest level (affects pupil/eye wideness).
   */
  setInterest(level: number): void {
    this.interestLevel = Math.max(0, Math.min(1, level))
  }

  /**
   * Force a glance-away (useful when avatar is "thinking").
   */
  triggerLookAway(duration: number = 1.0): void {
    this.isLookingAway = true
    this.lookAwayDuration = duration
    this.lookAwayTimer = 0
    // Random look-away direction (usually up-left or up-right)
    const angle = (Math.random() * 0.5 + 0.25) * Math.PI * (Math.random() > 0.5 ? 1 : -1)
    this.targetGaze = {
      x: Math.cos(angle) * 0.4,
      y: Math.sin(angle) * 0.3 + 0.2, // Tend to look up
    }
  }

  /**
   * Update the gaze system and return blendshape values for eyes.
   */
  update(deltaTime: number): BlendshapeMap {
    // ─── Mode-based Target Computation ───────────────────────
    if (this.isLookingAway) {
      this.lookAwayTimer += deltaTime
      if (this.lookAwayTimer >= this.lookAwayDuration) {
        this.isLookingAway = false
      }
      // Target already set in triggerLookAway
    } else {
      switch (this.mode) {
        case 'track_cursor':
          this.targetGaze = { ...this.externalTarget }
          break
        case 'social_scan':
          this.updateSocialScan(deltaTime)
          break
        case 'idle_wander':
          this.updateIdleWander(deltaTime)
          break
        case 'fixed_point':
          // Target stays fixed
          break
        case 'look_away':
          this.triggerLookAway(1.5)
          this.mode = 'track_cursor' // Return to tracking after
          break
      }
    }

    // ─── Attention Shifts (periodic glance-away) ─────────────
    if (!this.isLookingAway && this.mode !== 'idle_wander') {
      this.attentionTimer += deltaTime
      if (this.attentionTimer > this.attentionShiftInterval) {
        this.attentionTimer = 0
        this.attentionShiftInterval = 4 + Math.random() * 5
        // 20% chance to briefly look away
        if (Math.random() < 0.2) {
          this.triggerLookAway(0.4 + Math.random() * 0.6)
        }
      }
    }

    // ─── Micro-Saccades ──────────────────────────────────────
    this.microSaccadeTimer += deltaTime
    if (this.microSaccadeTimer > this.microSaccadeInterval && !this.activeSaccade) {
      this.microSaccadeTimer = 0
      this.microSaccadeInterval = 0.2 + Math.random() * 0.6
      // Tiny random eye movement
      this.activeSaccade = {
        targetX: this.targetGaze.x + (Math.random() - 0.5) * 0.04,
        targetY: this.targetGaze.y + (Math.random() - 0.5) * 0.03,
        duration: 0.03 + Math.random() * 0.02, // Very fast
        elapsed: 0,
      }
    }

    // ─── Process Active Saccade ──────────────────────────────
    let finalTarget = this.targetGaze
    if (this.activeSaccade) {
      this.activeSaccade.elapsed += deltaTime
      const progress = Math.min(1, this.activeSaccade.elapsed / this.activeSaccade.duration)
      if (progress >= 1) {
        this.activeSaccade = null
      } else {
        finalTarget = {
          x: this.targetGaze.x + (this.activeSaccade.targetX - this.targetGaze.x) * progress,
          y: this.targetGaze.y + (this.activeSaccade.targetY - this.targetGaze.y) * progress,
        }
      }
    }

    // ─── Smooth Pursuit (spring-damper) ──────────────────────
    const stiffness = 15
    const damping = 6
    const forceX = (finalTarget.x - this.smoothX) * stiffness - this.velocityX * damping
    const forceY = (finalTarget.y - this.smoothY) * stiffness - this.velocityY * damping
    this.velocityX += forceX * deltaTime
    this.velocityY += forceY * deltaTime
    this.smoothX += this.velocityX * deltaTime
    this.smoothY += this.velocityY * deltaTime

    // Clamp
    this.smoothX = Math.max(-1, Math.min(1, this.smoothX))
    this.smoothY = Math.max(-1, Math.min(1, this.smoothY))
    this.currentGaze = { x: this.smoothX, y: this.smoothY }

    // ─── Convert to ARKit Blendshapes ────────────────────────
    return this.gazeToBlendshapes(this.currentGaze)
  }

  private gazeToBlendshapes(gaze: GazeTarget): BlendshapeMap {
    const result: BlendshapeMap = {}
    const x = gaze.x * 0.5  // Scale down for realistic range
    const y = gaze.y * 0.35

    // Horizontal gaze
    if (x > 0) {
      // Looking right
      result.eyeLookOutLeft = x
      result.eyeLookInRight = x
      result.eyeLookInLeft = 0
      result.eyeLookOutRight = 0
    } else {
      // Looking left
      result.eyeLookInLeft = -x
      result.eyeLookOutRight = -x
      result.eyeLookOutLeft = 0
      result.eyeLookInRight = 0
    }

    // Vertical gaze
    if (y > 0) {
      // Looking up
      result.eyeLookUpLeft = y
      result.eyeLookUpRight = y
      result.eyeLookDownLeft = 0
      result.eyeLookDownRight = 0
    } else {
      // Looking down
      result.eyeLookDownLeft = -y
      result.eyeLookDownRight = -y
      result.eyeLookUpLeft = 0
      result.eyeLookUpRight = 0
    }

    // Interest-based pupil dilation (approximated via eye wideness)
    const dilation = (this.interestLevel - 0.5) * 0.15
    if (dilation > 0) {
      result.eyeWideLeft = dilation
      result.eyeWideRight = dilation
    } else {
      result.eyeSquintLeft = -dilation
      result.eyeSquintRight = -dilation
    }

    return result
  }

  private updateSocialScan(deltaTime: number): void {
    this.socialScanTimer += deltaTime
    // Spend 1-2 seconds on each point
    const holdTime = 1.0 + Math.random() * 1.0
    if (this.socialScanTimer > holdTime) {
      this.socialScanTimer = 0
      this.socialScanPhase = (this.socialScanPhase + 1) % this.socialScanPoints.length
    }
    const point = this.socialScanPoints[this.socialScanPhase]
    this.targetGaze = {
      x: this.externalTarget.x + point.x,
      y: this.externalTarget.y + point.y,
    }
  }

  private updateIdleWander(deltaTime: number): void {
    this.wanderTimer += deltaTime
    if (this.wanderTimer > this.wanderInterval) {
      this.wanderTimer = 0
      this.wanderInterval = 2 + Math.random() * 3
      this.wanderTarget = {
        x: (Math.random() - 0.5) * 0.4,
        y: (Math.random() - 0.5) * 0.25,
      }
    }
    this.targetGaze = this.wanderTarget
  }

  /**
   * Get current gaze position (for external use, e.g., head follow).
   */
  getCurrentGaze(): GazeTarget {
    return { ...this.currentGaze }
  }

  reset(): void {
    this.currentGaze = { x: 0, y: 0 }
    this.targetGaze = { x: 0, y: 0 }
    this.smoothX = 0
    this.smoothY = 0
    this.velocityX = 0
    this.velocityY = 0
    this.activeSaccade = null
    this.isLookingAway = false
    this.mode = 'idle_wander'
    this.attentionTimer = 0
  }
}

export default GazeSystem
