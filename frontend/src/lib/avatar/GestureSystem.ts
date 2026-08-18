/**
 * GestureSystem — Procedural head gestures triggered by conversation context.
 *
 * Supports:
 * - Head nods (affirmative, acknowledgment)
 * - Head shakes (negation, disagreement)
 * - Head tilts (curiosity, empathy)
 * - Head turns (attention shifts)
 * - Shoulder shrugs (uncertainty, via brow + mouth blendshapes)
 * - Thinking pose (chin up, eyes up)
 *
 * Gestures are queued and played sequentially. Each gesture has:
 * - Duration
 * - Intensity
 * - Blendshape component (facial part of gesture)
 * - Head rotation component
 */

import type { BlendshapeMap, HeadRotation, AnimationSubsystem } from './types'

// ─── Gesture Definitions ──────────────────────────────────────────────────────

export type GestureType =
  | 'nod'
  | 'shake'
  | 'tilt_left'
  | 'tilt_right'
  | 'shrug'
  | 'thinking'
  | 'attention_shift'
  | 'agreement'
  | 'surprise_brow'
  | 'empathy_tilt'

interface GestureDefinition {
  headRotation: (progress: number, intensity: number) => HeadRotation
  blendshapes: (progress: number, intensity: number) => BlendshapeMap
  duration: number
  canInterrupt: boolean
}

interface QueuedGesture {
  type: GestureType
  intensity: number
  startTime: number
}

// Easing functions
const easeInOutSine = (t: number): number => -(Math.cos(Math.PI * t) - 1) / 2
const easeOutBack = (t: number): number => {
  const c1 = 1.70158
  const c3 = c1 + 1
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2)
}

// ─── Gesture Library ──────────────────────────────────────────────────────────

const GESTURES: Record<GestureType, GestureDefinition> = {
  nod: {
    duration: 0.6,
    canInterrupt: true,
    headRotation: (progress, intensity) => {
      // Two quick nods
      const cycle = Math.sin(progress * Math.PI * 2) * easeInOutSine(1 - Math.abs(progress * 2 - 1))
      return { pitch: cycle * 0.08 * intensity, yaw: 0, roll: 0 }
    },
    blendshapes: (progress, intensity) => ({
      browInnerUp: Math.sin(progress * Math.PI) * 0.05 * intensity,
      mouthSmileLeft: Math.sin(progress * Math.PI) * 0.08 * intensity,
      mouthSmileRight: Math.sin(progress * Math.PI) * 0.08 * intensity,
    }),
  },

  shake: {
    duration: 0.8,
    canInterrupt: true,
    headRotation: (progress, intensity) => {
      const cycle = Math.sin(progress * Math.PI * 3) * easeInOutSine(1 - Math.abs(progress * 2 - 1))
      return { pitch: 0, yaw: cycle * 0.06 * intensity, roll: 0 }
    },
    blendshapes: (progress, intensity) => ({
      mouthFrownLeft: Math.sin(progress * Math.PI) * 0.1 * intensity,
      mouthFrownRight: Math.sin(progress * Math.PI) * 0.1 * intensity,
      browDownLeft: Math.sin(progress * Math.PI) * 0.08 * intensity,
      browDownRight: Math.sin(progress * Math.PI) * 0.08 * intensity,
    }),
  },

  tilt_left: {
    duration: 1.2,
    canInterrupt: true,
    headRotation: (progress, intensity) => {
      const tilt = easeInOutSine(progress < 0.4 ? progress / 0.4 : 1 - (progress - 0.4) / 0.6)
      return { pitch: 0.02 * intensity, yaw: -0.02 * intensity, roll: tilt * 0.06 * intensity }
    },
    blendshapes: (progress, intensity) => ({
      browInnerUp: easeInOutSine(progress < 0.5 ? progress * 2 : 2 - progress * 2) * 0.12 * intensity,
      eyeSquintRight: easeInOutSine(progress) * 0.06 * intensity,
    }),
  },

  tilt_right: {
    duration: 1.2,
    canInterrupt: true,
    headRotation: (progress, intensity) => {
      const tilt = easeInOutSine(progress < 0.4 ? progress / 0.4 : 1 - (progress - 0.4) / 0.6)
      return { pitch: 0.02 * intensity, yaw: 0.02 * intensity, roll: -tilt * 0.06 * intensity }
    },
    blendshapes: (progress, intensity) => ({
      browInnerUp: easeInOutSine(progress < 0.5 ? progress * 2 : 2 - progress * 2) * 0.12 * intensity,
      eyeSquintLeft: easeInOutSine(progress) * 0.06 * intensity,
    }),
  },

  shrug: {
    duration: 1.0,
    canInterrupt: true,
    headRotation: (progress, intensity) => {
      const lift = easeInOutSine(progress < 0.4 ? progress / 0.4 : 1 - (progress - 0.4) / 0.6)
      return { pitch: -lift * 0.03 * intensity, yaw: 0, roll: 0 }
    },
    blendshapes: (progress, intensity) => {
      const curve = easeInOutSine(progress < 0.4 ? progress / 0.4 : 1 - (progress - 0.4) / 0.6)
      return {
        browInnerUp: curve * 0.35 * intensity,
        browOuterUpLeft: curve * 0.25 * intensity,
        browOuterUpRight: curve * 0.25 * intensity,
        mouthFrownLeft: curve * 0.2 * intensity,
        mouthFrownRight: curve * 0.2 * intensity,
        mouthShrugLower: curve * 0.3 * intensity,
        mouthPressLeft: curve * 0.15 * intensity,
        mouthPressRight: curve * 0.15 * intensity,
      }
    },
  },

  thinking: {
    duration: 2.0,
    canInterrupt: false,
    headRotation: (progress, intensity) => {
      const upPhase = easeInOutSine(Math.min(progress * 3, 1))
      return {
        pitch: -upPhase * 0.04 * intensity,
        yaw: Math.sin(progress * Math.PI * 0.8) * 0.03 * intensity,
        roll: 0,
      }
    },
    blendshapes: (progress, intensity) => {
      const holdPhase = progress > 0.2 && progress < 0.7 ? 1 : easeInOutSine(progress < 0.2 ? progress * 5 : (1 - progress) * 3.3)
      return {
        browDownLeft: holdPhase * 0.15 * intensity,
        browDownRight: holdPhase * 0.15 * intensity,
        browInnerUp: holdPhase * 0.1 * intensity,
        eyeSquintLeft: holdPhase * 0.12 * intensity,
        eyeSquintRight: holdPhase * 0.12 * intensity,
        mouthPucker: holdPhase * 0.12 * intensity,
        mouthPressLeft: holdPhase * 0.1 * intensity,
        mouthPressRight: holdPhase * 0.1 * intensity,
        eyeLookUpLeft: holdPhase * 0.2 * intensity,
        eyeLookUpRight: holdPhase * 0.2 * intensity,
      }
    },
  },

  attention_shift: {
    duration: 0.5,
    canInterrupt: true,
    headRotation: (progress, intensity) => {
      const snap = easeOutBack(Math.min(progress * 2, 1))
      const returnPhase = progress > 0.5 ? easeInOutSine((progress - 0.5) * 2) : 0
      const yaw = (snap - returnPhase) * 0.08 * intensity * (Math.random() > 0.5 ? 1 : -1)
      return { pitch: 0, yaw, roll: 0 }
    },
    blendshapes: (progress, intensity) => ({
      eyeWideLeft: Math.sin(progress * Math.PI) * 0.1 * intensity,
      eyeWideRight: Math.sin(progress * Math.PI) * 0.1 * intensity,
    }),
  },

  agreement: {
    duration: 0.9,
    canInterrupt: true,
    headRotation: (progress, intensity) => {
      // Slow single nod with hold
      const nod = easeInOutSine(progress < 0.3 ? progress / 0.3 : progress < 0.6 ? 1 : 1 - (progress - 0.6) / 0.4)
      return { pitch: nod * 0.06 * intensity, yaw: 0, roll: 0 }
    },
    blendshapes: (progress, intensity) => ({
      mouthSmileLeft: easeInOutSine(progress) * 0.15 * intensity,
      mouthSmileRight: easeInOutSine(progress) * 0.15 * intensity,
      browInnerUp: Math.sin(progress * Math.PI) * 0.08 * intensity,
      cheekSquintLeft: Math.sin(progress * Math.PI) * 0.06 * intensity,
      cheekSquintRight: Math.sin(progress * Math.PI) * 0.06 * intensity,
    }),
  },

  surprise_brow: {
    duration: 0.5,
    canInterrupt: true,
    headRotation: (progress, intensity) => {
      const back = progress < 0.2 ? easeOutBack(progress * 5) * 0.03 : (1 - (progress - 0.2) / 0.8) * 0.03
      return { pitch: -back * intensity, yaw: 0, roll: 0 }
    },
    blendshapes: (progress, intensity) => {
      const flash = progress < 0.15 ? progress / 0.15 : 1 - (progress - 0.15) / 0.85
      return {
        browInnerUp: flash * 0.4 * intensity,
        browOuterUpLeft: flash * 0.3 * intensity,
        browOuterUpRight: flash * 0.3 * intensity,
        eyeWideLeft: flash * 0.2 * intensity,
        eyeWideRight: flash * 0.2 * intensity,
      }
    },
  },

  empathy_tilt: {
    duration: 1.5,
    canInterrupt: true,
    headRotation: (progress, intensity) => {
      const tiltPhase = easeInOutSine(progress < 0.3 ? progress / 0.3 : 1 - (progress - 0.3) / 0.7)
      return {
        pitch: tiltPhase * 0.03 * intensity,
        yaw: 0,
        roll: tiltPhase * 0.04 * intensity,
      }
    },
    blendshapes: (progress, intensity) => {
      const curve = easeInOutSine(progress < 0.4 ? progress / 0.4 : 1 - (progress - 0.4) / 0.6)
      return {
        browInnerUp: curve * 0.25 * intensity,
        mouthSmileLeft: curve * 0.12 * intensity,
        mouthSmileRight: curve * 0.12 * intensity,
        eyeSquintLeft: curve * 0.08 * intensity,
        eyeSquintRight: curve * 0.08 * intensity,
        mouthFrownLeft: curve * 0.05 * intensity,
        mouthFrownRight: curve * 0.05 * intensity,
      }
    },
  },
}

// ─── Gesture System Class ─────────────────────────────────────────────────────

export class GestureSystem implements AnimationSubsystem {
  private queue: QueuedGesture[] = []
  private activeGesture: QueuedGesture | null = null
  private elapsedTime = 0
  private lastHeadRotation: HeadRotation = { pitch: 0, yaw: 0, roll: 0 }
  private lastBlendshapes: BlendshapeMap = {}
  private idleTimer = 0
  private idleGestureInterval = 4 + Math.random() * 3 // 4-7 seconds

  /**
   * Trigger a gesture. Queues it if another is active.
   */
  trigger(type: GestureType, intensity: number = 0.7): void {
    const gesture: QueuedGesture = {
      type,
      intensity: Math.max(0, Math.min(1, intensity)),
      startTime: 0,
    }

    // If nothing is playing, start immediately
    if (!this.activeGesture) {
      this.activeGesture = gesture
      this.elapsedTime = 0
    } else {
      const activeDef = GESTURES[this.activeGesture.type]
      if (activeDef.canInterrupt) {
        // Replace current gesture
        this.activeGesture = gesture
        this.elapsedTime = 0
      } else {
        // Queue for later (max 3 in queue)
        if (this.queue.length < 3) {
          this.queue.push(gesture)
        }
      }
    }
  }

  /**
   * Trigger random idle gesture for natural behavior.
   */
  private triggerIdleGesture(): void {
    const idleGestures: GestureType[] = ['tilt_left', 'tilt_right', 'nod', 'attention_shift']
    const randomGesture = idleGestures[Math.floor(Math.random() * idleGestures.length)]
    this.trigger(randomGesture, 0.3 + Math.random() * 0.3)
    this.idleGestureInterval = 4 + Math.random() * 4
    this.idleTimer = 0
  }

  /**
   * Update the gesture system.
   * Returns blendshapes for the current gesture.
   */
  update(deltaTime: number): BlendshapeMap {
    // Idle gesture timer
    this.idleTimer += deltaTime
    if (!this.activeGesture && this.idleTimer > this.idleGestureInterval) {
      this.triggerIdleGesture()
    }

    if (!this.activeGesture) {
      // Smooth decay of last values
      for (const key of Object.keys(this.lastBlendshapes)) {
        this.lastBlendshapes[key]! *= 1 - 5 * deltaTime
        if (this.lastBlendshapes[key]! < 0.001) delete this.lastBlendshapes[key]
      }
      this.lastHeadRotation.pitch *= 1 - 5 * deltaTime
      this.lastHeadRotation.yaw *= 1 - 5 * deltaTime
      this.lastHeadRotation.roll *= 1 - 5 * deltaTime
      return { ...this.lastBlendshapes }
    }

    const def = GESTURES[this.activeGesture.type]
    this.elapsedTime += deltaTime
    const progress = Math.min(1, this.elapsedTime / def.duration)

    // Compute gesture output
    this.lastHeadRotation = def.headRotation(progress, this.activeGesture.intensity)
    this.lastBlendshapes = def.blendshapes(progress, this.activeGesture.intensity)

    // Check if gesture is complete
    if (progress >= 1) {
      this.activeGesture = null
      this.elapsedTime = 0

      // Play next in queue
      if (this.queue.length > 0) {
        this.activeGesture = this.queue.shift()!
      }
    }

    return { ...this.lastBlendshapes }
  }

  /**
   * Get current head rotation from gesture.
   */
  getHeadRotation(): HeadRotation {
    return { ...this.lastHeadRotation }
  }

  /**
   * Check if a gesture is currently playing.
   */
  isPlaying(): boolean {
    return this.activeGesture !== null
  }

  /**
   * Clear all queued gestures.
   */
  clearQueue(): void {
    this.queue = []
  }

  reset(): void {
    this.activeGesture = null
    this.queue = []
    this.elapsedTime = 0
    this.lastHeadRotation = { pitch: 0, yaw: 0, roll: 0 }
    this.lastBlendshapes = {}
    this.idleTimer = 0
  }
}

export default GestureSystem
