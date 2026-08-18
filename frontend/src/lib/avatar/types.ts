/**
 * Shared types for the Avatar Animation System.
 * All subsystems use these common interfaces.
 */

// Map of blendshape names to their target values [0, 1]
export type BlendshapeMap = Record<string, number>

// The 52 ARKit blendshape names
export const ARKIT_BLENDSHAPES = [
  // Eye
  'eyeBlinkLeft', 'eyeBlinkRight',
  'eyeLookDownLeft', 'eyeLookDownRight',
  'eyeLookInLeft', 'eyeLookInRight',
  'eyeLookOutLeft', 'eyeLookOutRight',
  'eyeLookUpLeft', 'eyeLookUpRight',
  'eyeSquintLeft', 'eyeSquintRight',
  'eyeWideLeft', 'eyeWideRight',
  // Jaw
  'jawForward', 'jawLeft', 'jawRight', 'jawOpen',
  // Mouth
  'mouthClose',
  'mouthFunnel', 'mouthPucker',
  'mouthLeft', 'mouthRight',
  'mouthSmileLeft', 'mouthSmileRight',
  'mouthFrownLeft', 'mouthFrownRight',
  'mouthDimpleLeft', 'mouthDimpleRight',
  'mouthStretchLeft', 'mouthStretchRight',
  'mouthRollLower', 'mouthRollUpper',
  'mouthShrugLower', 'mouthShrugUpper',
  'mouthPressLeft', 'mouthPressRight',
  'mouthLowerDownLeft', 'mouthLowerDownRight',
  'mouthUpperUpLeft', 'mouthUpperUpRight',
  // Brow
  'browDownLeft', 'browDownRight',
  'browInnerUp',
  'browOuterUpLeft', 'browOuterUpRight',
  // Nose
  'noseSneerLeft', 'noseSneerRight',
  // Cheek
  'cheekPuff', 'cheekSquintLeft', 'cheekSquintRight',
  // Tongue
  'tongueOut',
] as const

export type BlendshapeName = typeof ARKIT_BLENDSHAPES[number]

// Avatar state as driven by the conversation system
export type AvatarActivityState = 'idle' | 'greeting' | 'speaking' | 'listening' | 'thinking'

// Speech mark from AWS Polly
export interface SpeechMark {
  time: number
  type: string
  value: string
  start?: number
  end?: number
}

// Head rotation (Euler angles in radians)
export interface HeadRotation {
  pitch: number // x - nod
  yaw: number   // y - turn left/right
  roll: number  // z - tilt
}

// Animation subsystem interface — all engines must implement this
export interface AnimationSubsystem {
  update(deltaTime: number): BlendshapeMap
  reset(): void
}

// Voice analysis data passed to reactive systems
export interface VoiceAnalysis {
  amplitude: number    // 0-1 current voice loudness
  pitch: number        // 0-1 normalized pitch (0=low, 1=high)
  isSpeaking: boolean  // Whether audio is currently playing
  energy: number       // 0-1 speech energy/intensity
}

// Merged output from all systems
export interface AvatarAnimationOutput {
  blendshapes: BlendshapeMap
  headRotation: HeadRotation
  bodyOffset: { x: number; y: number; z: number }
}
