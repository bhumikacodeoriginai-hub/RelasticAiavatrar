/**
 * AvatarStateManager — Central coordinator for all avatar animation subsystems.
 *
 * Responsibilities:
 * - Orchestrates EmotionEngine, GazeSystem, GestureSystem, AdvancedLipSync,
 *   BreathingSystem, and VoiceReactiveExpressions
 * - Merges blendshape outputs with priority/weight system
 * - Manages head rotation from multiple sources (gesture, breathing, gaze-follow)
 * - Handles eye blink generation with coordination (no blink during saccade)
 * - Provides single update() call for render loop
 * - Converts conversation state changes into animation triggers
 *
 * Priority system (higher overrides lower for same blendshape):
 * 1. LipSync (mouth shapes are primary during speech)
 * 2. Emotion (facial expression baseline)
 * 3. Gaze (eye direction)
 * 4. Gesture (temporary overlays)
 * 5. Breathing (ambient body motion)
 * 6. VoiceReactive (subtle modifiers)
 * 7. Blink (periodic eye closure)
 */

import { EmotionEngine, type EmotionType } from './EmotionEngine'
import { GazeSystem, type GazeMode } from './GazeSystem'
import { GestureSystem, type GestureType } from './GestureSystem'
import { AdvancedLipSync } from './AdvancedLipSync'
import { BreathingSystem, type BreathingProfile } from './BreathingSystem'
import { VoiceReactiveExpressions } from './VoiceReactiveExpressions'
import type {
  BlendshapeMap,
  HeadRotation,
  AvatarActivityState,
  SpeechMark,
  VoiceAnalysis,
  AvatarAnimationOutput,
} from './types'

// ─── Blink Generator ──────────────────────────────────────────────────────────

class BlinkGenerator {
  private timer = 0
  private nextBlinkAt = 2 + Math.random() * 3
  private isBlinking = false
  private blinkProgress = 0
  private blinkSpeed = 8 // Full blink cycle speed
  private doubleBlinkPending = false

  update(deltaTime: number): { left: number; right: number } {
    this.timer += deltaTime

    if (!this.isBlinking && this.timer >= this.nextBlinkAt) {
      this.isBlinking = true
      this.blinkProgress = 0
      this.timer = 0
      this.nextBlinkAt = 2.5 + Math.random() * 4 // 2.5-6.5s between blinks
      // 15% chance of double blink
      this.doubleBlinkPending = Math.random() < 0.15
    }

    let blinkValue = 0
    if (this.isBlinking) {
      this.blinkProgress += deltaTime * this.blinkSpeed
      if (this.blinkProgress <= 1) {
        // Closing (fast)
        blinkValue = Math.pow(this.blinkProgress, 0.5) // Quick close
      } else if (this.blinkProgress <= 2) {
        // Opening (slightly slower)
        blinkValue = Math.pow(2 - this.blinkProgress, 0.7)
      } else {
        this.isBlinking = false
        blinkValue = 0
        // Handle double blink
        if (this.doubleBlinkPending) {
          this.doubleBlinkPending = false
          this.nextBlinkAt = 0.15 // Quick second blink
        }
      }
    }

    // Asymmetry: slight delay on one eye (more natural)
    return {
      left: blinkValue,
      right: blinkValue * 0.97, // Barely perceptible asymmetry
    }
  }

  /** Suppress blinks temporarily (during saccades). */
  suppress(duration: number): void {
    this.timer = Math.min(this.timer, this.nextBlinkAt - duration)
  }

  /** Force a blink (e.g., on surprise). */
  forceBlink(): void {
    this.isBlinking = true
    this.blinkProgress = 0
  }

  reset(): void {
    this.timer = 0
    this.isBlinking = false
    this.blinkProgress = 0
    this.nextBlinkAt = 2 + Math.random() * 3
  }
}

// ─── Blendshape Layer Weights ─────────────────────────────────────────────────

interface LayerConfig {
  weight: number
  // Which blendshape groups this layer primarily controls
  // Allows priority resolution for shared blendshapes
  priority: number
}

const LAYER_CONFIGS: Record<string, LayerConfig> = {
  lipSync: { weight: 1.0, priority: 100 },
  emotion: { weight: 1.0, priority: 80 },
  gaze: { weight: 1.0, priority: 90 },
  gesture: { weight: 1.0, priority: 70 },
  breathing: { weight: 1.0, priority: 30 },
  voiceReactive: { weight: 0.6, priority: 50 },
  blink: { weight: 1.0, priority: 95 },
}

// Blendshapes that are "owned" by specific layers (highest priority wins)
const MOUTH_SHAPES = new Set([
  'jawOpen', 'jawForward', 'jawLeft', 'jawRight',
  'mouthClose', 'mouthFunnel', 'mouthPucker', 'mouthLeft', 'mouthRight',
  'mouthSmileLeft', 'mouthSmileRight', 'mouthFrownLeft', 'mouthFrownRight',
  'mouthDimpleLeft', 'mouthDimpleRight', 'mouthStretchLeft', 'mouthStretchRight',
  'mouthRollLower', 'mouthRollUpper', 'mouthShrugLower', 'mouthShrugUpper',
  'mouthPressLeft', 'mouthPressRight', 'mouthLowerDownLeft', 'mouthLowerDownRight',
  'mouthUpperUpLeft', 'mouthUpperUpRight', 'tongueOut',
])

const EYE_SHAPES = new Set([
  'eyeBlinkLeft', 'eyeBlinkRight',
  'eyeLookDownLeft', 'eyeLookDownRight',
  'eyeLookInLeft', 'eyeLookInRight',
  'eyeLookOutLeft', 'eyeLookOutRight',
  'eyeLookUpLeft', 'eyeLookUpRight',
  'eyeWideLeft', 'eyeWideRight',
  'eyeSquintLeft', 'eyeSquintRight',
])

// ─── Avatar State Manager ─────────────────────────────────────────────────────

export class AvatarStateManager {
  // Subsystems
  public readonly emotion = new EmotionEngine()
  public readonly gaze = new GazeSystem()
  public readonly gesture = new GestureSystem()
  public readonly lipSync = new AdvancedLipSync()
  public readonly breathing = new BreathingSystem()
  public readonly voiceReactive = new VoiceReactiveExpressions()
  private readonly blink = new BlinkGenerator()

  // State
  private activityState: AvatarActivityState = 'idle'
  private isSpeaking = false
  private isListening = false
  private reducedMotion = false

  // Head rotation accumulator
  private headRotation: HeadRotation = { pitch: 0, yaw: 0, roll: 0 }
  private bodyOffsetY = 0

  /**
   * Set the overall activity state (from conversation system).
   */
  setActivityState(state: AvatarActivityState): void {
    const prevState = this.activityState
    this.activityState = state

    // Trigger appropriate animations on state change
    if (prevState !== state) {
      this.onStateTransition(prevState, state)
    }
  }

  /**
   * Set speaking state with optional speech marks.
   */
  setSpeaking(speaking: boolean, speechMarks?: SpeechMark[], startTime?: number): void {
    this.isSpeaking = speaking
    if (speaking) {
      if (speechMarks && speechMarks.length > 0 && startTime) {
        this.lipSync.startWithMarks(speechMarks, startTime)
      } else {
        this.lipSync.startFallback()
      }
      this.breathing.setProfile('speaking')
      this.gaze.setMode('social_scan')
    } else {
      this.lipSync.stop()
      this.breathing.resume()
      this.breathing.setProfile('normal')
    }
  }

  /**
   * Set listening state.
   */
  setListening(listening: boolean): void {
    this.isListening = listening
    if (listening) {
      this.gaze.setMode('track_cursor')
      this.gaze.setInterest(0.7)
      this.breathing.setProfile('normal')
    }
  }

  /**
   * Set emotion (from conversation context or backend analysis).
   */
  setEmotion(emotion: EmotionType, intensity?: number): void {
    this.emotion.setEmotion(emotion, intensity)
  }

  /**
   * Trigger a gesture.
   */
  triggerGesture(type: GestureType, intensity?: number): void {
    this.gesture.trigger(type, intensity)
  }

  /**
   * Update gaze target (mouse position).
   */
  updateGazeTarget(x: number, y: number): void {
    this.gaze.setTarget(x, y)
  }

  /**
   * Provide voice analysis data (from audio processing).
   */
  updateVoiceAnalysis(analysis: VoiceAnalysis): void {
    // Voice reactive gets the raw analysis
    this.voiceReactive.updateWithVoice(0.016, analysis) // approximate delta
  }

  /**
   * Enable/disable reduced motion for accessibility.
   */
  setReducedMotion(reduced: boolean): void {
    this.reducedMotion = reduced
  }

  /**
   * Main update loop — call every frame.
   * Returns merged blendshapes, head rotation, and body offset.
   */
  update(deltaTime: number): AvatarAnimationOutput {
    if (this.reducedMotion) {
      deltaTime *= 0.3 // Slow down all animations
    }

    // ─── Update All Subsystems ─────────────────────────────
    const emotionShapes = this.emotion.update(deltaTime)
    const gazeShapes = this.gaze.update(deltaTime)
    const gestureShapes = this.gesture.update(deltaTime)
    const lipSyncShapes = this.lipSync.update(deltaTime)
    const breathingShapes = this.breathing.update(deltaTime)
    const voiceShapes = this.voiceReactive.update(deltaTime)
    const blinkValues = this.blink.update(deltaTime)

    // ─── Merge Blendshapes with Priority System ────────────
    const merged: BlendshapeMap = {}

    // Start with lowest priority (breathing)
    this.applyLayer(merged, breathingShapes, 'breathing')

    // Voice reactive (subtle overlay)
    this.applyLayer(merged, voiceShapes, 'voiceReactive')

    // Gesture (temporary overlays)
    this.applyLayer(merged, gestureShapes, 'gesture')

    // Emotion (baseline expression — but mouth shapes only when NOT speaking)
    if (this.isSpeaking) {
      // During speech: apply emotion only to non-mouth blendshapes
      const emotionNonMouth: BlendshapeMap = {}
      for (const [key, value] of Object.entries(emotionShapes)) {
        if (!MOUTH_SHAPES.has(key)) {
          emotionNonMouth[key] = value
        }
      }
      this.applyLayer(merged, emotionNonMouth, 'emotion')
    } else {
      this.applyLayer(merged, emotionShapes, 'emotion')
    }

    // Gaze (eye direction — high priority for eye shapes)
    this.applyLayer(merged, gazeShapes, 'gaze')

    // Lip sync (highest priority for mouth shapes during speech)
    if (this.isSpeaking) {
      this.applyLayer(merged, lipSyncShapes, 'lipSync')
    }

    // Blink (highest priority for eye blink shapes)
    merged.eyeBlinkLeft = blinkValues.left
    merged.eyeBlinkRight = blinkValues.right

    // ─── Compute Head Rotation ─────────────────────────────
    const gestureHead = this.gesture.getHeadRotation()
    const gazeFollow = this.gaze.getCurrentGaze()

    // Head follows gaze slightly
    const gazeHeadX = gazeFollow.y * 0.03 // Look direction influences head pitch
    const gazeHeadY = gazeFollow.x * 0.04 // Head turns toward gaze target

    // Breathing sway
    const breatheSwayX = Math.sin(performance.now() * 0.001 * 1.0) * 0.005
    const breatheSwayY = Math.sin(performance.now() * 0.001 * 0.4) * 0.008

    // Idle micro-movement
    const idleX = Math.sin(performance.now() * 0.001 * 0.25) * 0.006
    const idleY = Math.sin(performance.now() * 0.001 * 0.15) * 0.01

    this.headRotation = {
      pitch: gestureHead.pitch + gazeHeadX + breatheSwayX + idleX,
      yaw: gestureHead.yaw + gazeHeadY + breatheSwayY + idleY,
      roll: gestureHead.roll + Math.sin(performance.now() * 0.001 * 0.3) * 0.003,
    }

    // ─── Body Offset (breathing) ───────────────────────────
    this.bodyOffsetY = this.breathing.getBodyOffset()

    // ─── Clamp All Values ──────────────────────────────────
    for (const key of Object.keys(merged)) {
      merged[key] = Math.max(0, Math.min(1, merged[key] || 0))
    }

    return {
      blendshapes: merged,
      headRotation: this.headRotation,
      bodyOffset: { x: 0, y: this.bodyOffsetY, z: 0 },
    }
  }

  /**
   * Apply a layer's blendshapes onto the merged result.
   * Uses additive blending weighted by layer config.
   */
  private applyLayer(merged: BlendshapeMap, layer: BlendshapeMap, layerName: string): void {
    const config = LAYER_CONFIGS[layerName]
    if (!config) return

    for (const [key, value] of Object.entries(layer)) {
      const weighted = (value || 0) * config.weight
      const current = merged[key] || 0

      // For most shapes: additive blend (clamped later)
      // For eye look shapes: take the dominant value
      if (EYE_SHAPES.has(key) && key.startsWith('eyeLook')) {
        // Eye direction: higher priority layer wins
        if (config.priority >= (LAYER_CONFIGS.gaze?.priority || 0) || current === 0) {
          merged[key] = weighted
        }
      } else {
        // Additive blend
        merged[key] = current + weighted
      }
    }
  }

  /**
   * Handle state transitions with appropriate animation triggers.
   */
  private onStateTransition(from: AvatarActivityState, to: AvatarActivityState): void {
    switch (to) {
      case 'greeting':
        this.emotion.setEmotion('happy', 0.8)
        this.gesture.trigger('nod', 0.6)
        this.gaze.setMode('social_scan')
        this.gaze.setInterest(0.8)
        this.breathing.setProfile('normal')
        break

      case 'speaking':
        this.gaze.setMode('social_scan')
        this.breathing.setProfile('speaking')
        break

      case 'listening':
        this.emotion.setEmotion('interested', 0.5)
        this.gaze.setMode('track_cursor')
        this.gaze.setInterest(0.7)
        this.breathing.setProfile('normal')
        // Periodic nods while listening
        setTimeout(() => {
          if (this.activityState === 'listening') {
            this.gesture.trigger('agreement', 0.4)
          }
        }, 2000 + Math.random() * 2000)
        break

      case 'thinking':
        this.emotion.setEmotion('confused', 0.4)
        this.gesture.trigger('thinking', 0.7)
        this.gaze.triggerLookAway(1.5)
        this.breathing.setProfile('calm')
        break

      case 'idle':
        this.emotion.setEmotion('neutral', 0.5)
        this.gaze.setMode('idle_wander')
        this.gaze.setInterest(0.3)
        this.breathing.setProfile('calm')
        break
    }
  }

  /**
   * Reset all subsystems.
   */
  reset(): void {
    this.emotion.reset()
    this.gaze.reset()
    this.gesture.reset()
    this.lipSync.reset()
    this.breathing.reset()
    this.voiceReactive.reset()
    this.blink.reset()
    this.activityState = 'idle'
    this.isSpeaking = false
    this.isListening = false
    this.headRotation = { pitch: 0, yaw: 0, roll: 0 }
    this.bodyOffsetY = 0
  }
}

export default AvatarStateManager
