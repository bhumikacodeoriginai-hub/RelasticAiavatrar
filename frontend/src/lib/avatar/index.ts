/**
 * Avatar Animation System — Barrel Export
 *
 * Complete 52 ARKit blendshape animation system for the Angelica GLB model.
 * Provides human-realistic facial animation with emotion, gaze, gestures,
 * lip sync, breathing, and voice-reactive expressions.
 */

export { AvatarStateManager } from './AvatarStateManager'
export { EmotionEngine } from './EmotionEngine'
export { GazeSystem } from './GazeSystem'
export { GestureSystem } from './GestureSystem'
export { AdvancedLipSync } from './AdvancedLipSync'
export { BreathingSystem } from './BreathingSystem'
export { VoiceReactiveExpressions } from './VoiceReactiveExpressions'

export type { EmotionType, EmotionState } from './EmotionEngine'
export type { GazeMode } from './GazeSystem'
export type { GestureType } from './GestureSystem'
export type { BreathingProfile } from './BreathingSystem'

export type {
  BlendshapeMap,
  BlendshapeName,
  AvatarActivityState,
  SpeechMark,
  HeadRotation,
  VoiceAnalysis,
  AvatarAnimationOutput,
  AnimationSubsystem,
} from './types'

export { ARKIT_BLENDSHAPES } from './types'
