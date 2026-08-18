/**
 * 3D Avatar Component — Realistic GLB Model with ARKit 52 Blendshapes
 *
 * Features:
 * - Loads angelica.glb model with full morph target support
 * - 52 ARKit blendshape-driven facial animation
 * - Viseme-based lip sync (Polly speech marks → blendshapes)
 * - Natural eye blink at random intervals
 * - Eye tracking (follows mouse cursor)
 * - Mouse drag & drop orbit controls (rotate model freely)
 * - Full-screen canvas rendering
 * - Realistic skin tone with enhanced PBR lighting
 * - Idle breathing & micro-expressions
 * - Fallback to procedural head if GLB fails to load
 */

import { useRef, useEffect, useState, useCallback, useMemo } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import {
  useGLTF,
  OrbitControls,
  Environment,
  ContactShadows,
  useAnimations,
  Html,
} from '@react-three/drei'
import * as THREE from 'three'

// ============================================================
// ARKit 52 Blendshape Names
// ============================================================

const ARKIT_BLENDSHAPES = [
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

type BlendshapeName = typeof ARKIT_BLENDSHAPES[number]

// ============================================================
// Polly Viseme → ARKit Blendshape Mapping (Full)
// ============================================================

const VISEME_TO_BLENDSHAPES: Record<string, Partial<Record<BlendshapeName, number>>> = {
  'sil': { jawOpen: 0.0, mouthClose: 0.8 },
  'p': { jawOpen: 0.05, mouthPucker: 0.6, mouthPressLeft: 0.4, mouthPressRight: 0.4 },
  'f': { jawOpen: 0.04, mouthFunnel: 0.4, mouthLowerDownLeft: 0.3, mouthLowerDownRight: 0.3 },
  't': { jawOpen: 0.15, mouthStretchLeft: 0.2, mouthStretchRight: 0.2 },
  'k': { jawOpen: 0.22, mouthShrugUpper: 0.3 },
  'S': { jawOpen: 0.12, mouthFunnel: 0.5, mouthShrugUpper: 0.3 },
  's': { jawOpen: 0.06, mouthSmileLeft: 0.15, mouthSmileRight: 0.15, mouthStretchLeft: 0.2, mouthStretchRight: 0.2 },
  'T': { jawOpen: 0.1, tongueOut: 0.4 },
  'r': { jawOpen: 0.15, mouthFunnel: 0.35, mouthPucker: 0.2 },
  'i': { jawOpen: 0.1, mouthSmileLeft: 0.5, mouthSmileRight: 0.5, mouthStretchLeft: 0.3, mouthStretchRight: 0.3 },
  'u': { jawOpen: 0.18, mouthPucker: 0.7, mouthFunnel: 0.3 },
  'e': { jawOpen: 0.22, mouthSmileLeft: 0.3, mouthSmileRight: 0.3, mouthUpperUpLeft: 0.1, mouthUpperUpRight: 0.1 },
  '@': { jawOpen: 0.35, mouthFunnel: 0.2, mouthShrugLower: 0.2 },
  'a': { jawOpen: 0.55, mouthLowerDownLeft: 0.4, mouthLowerDownRight: 0.4, mouthUpperUpLeft: 0.2, mouthUpperUpRight: 0.2 },
  'o': { jawOpen: 0.4, mouthPucker: 0.5, mouthFunnel: 0.4 },
  'E': { jawOpen: 0.28, mouthSmileLeft: 0.4, mouthSmileRight: 0.4 },
  'O': { jawOpen: 0.32, mouthPucker: 0.4, mouthFunnel: 0.3 },
}

// ============================================================
// Interfaces
// ============================================================

interface SpeechMark {
  time: number
  type: string
  value: string
  start?: number
  end?: number
}

interface Avatar3DProps {
  isSpeaking: boolean
  isListening: boolean
  state: 'idle' | 'greeting' | 'speaking' | 'listening' | 'thinking'
  speechMarks?: SpeechMark[]
  audioStartTime?: number
  name?: string
}

// ============================================================
// GLB Model Avatar (angelica.glb with ARKit blendshapes)
// ============================================================

const MODEL_PATH = '/models/angelica.glb'

function AngelicaModel({
  isSpeaking,
  isListening,
  state,
  speechMarks,
  audioStartTime,
}: Avatar3DProps) {
  const group = useRef<THREE.Group>(null)
  const { scene, animations } = useGLTF(MODEL_PATH)
  const { actions, mixer } = useAnimations(animations, group)

  // Refs for morph target meshes
  const morphMeshes = useRef<THREE.Mesh[]>([])
  const timeRef = useRef(0)
  const blinkTimerRef = useRef(0)
  const isBlinkingRef = useRef(false)
  const blinkProgressRef = useRef(0)
  const nextBlinkRef = useRef(2 + Math.random() * 3)
  const targetBlendshapes = useRef<Partial<Record<BlendshapeName, number>>>({})
  const currentBlendshapes = useRef<Partial<Record<BlendshapeName, number>>>({})
  const mouseRef = useRef({ x: 0, y: 0 })

  // Get Three.js renderer state
  const { gl } = useThree()

  // Track mouse position for eye following
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      const rect = gl.domElement.getBoundingClientRect()
      mouseRef.current.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
      mouseRef.current.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
    }
    window.addEventListener('mousemove', handleMouseMove)
    return () => window.removeEventListener('mousemove', handleMouseMove)
  }, [gl])

  // Find all meshes with morph targets in the loaded model
  useEffect(() => {
    const meshes: THREE.Mesh[] = []
    scene.traverse((child) => {
      if (child instanceof THREE.Mesh && child.morphTargetInfluences && child.morphTargetDictionary) {
        meshes.push(child)

        // Enhance skin materials for realism
        if (child.material instanceof THREE.MeshStandardMaterial) {
          const mat = child.material as THREE.MeshStandardMaterial
          // Warm up skin tone slightly
          mat.roughness = Math.max(mat.roughness, 0.55)
          mat.metalness = Math.min(mat.metalness, 0.05)
          // Enable proper shading
          mat.needsUpdate = true
        }
      }
    })
    morphMeshes.current = meshes
    console.log(`[Avatar3D] Found ${meshes.length} mesh(es) with morph targets`)

    // Log available blendshape names for debugging
    if (meshes.length > 0 && meshes[0].morphTargetDictionary) {
      console.log('[Avatar3D] Available blendshapes:', Object.keys(meshes[0].morphTargetDictionary))
    }
  }, [scene])

  // Play idle animation if available
  useEffect(() => {
    if (actions && Object.keys(actions).length > 0) {
      const idleAction = actions['idle'] || actions['Idle'] || Object.values(actions)[0]
      if (idleAction) {
        idleAction.reset().fadeIn(0.5).play()
      }
    }
  }, [actions])

  // Viseme lip sync — update target blendshapes based on speech marks
  useEffect(() => {
    if (!isSpeaking || !speechMarks || !audioStartTime || speechMarks.length === 0) {
      // Reset mouth to closed
      targetBlendshapes.current = { jawOpen: 0, mouthClose: 0.5 }
      return
    }

    let animFrame: number
    const animate = () => {
      const elapsed = Date.now() - audioStartTime
      // Find current viseme
      let currentViseme = 'sil'
      for (const mark of speechMarks) {
        if (mark.type === 'viseme' && mark.time <= elapsed) {
          currentViseme = mark.value
        } else if (mark.type === 'viseme' && mark.time > elapsed) {
          break
        }
      }
      targetBlendshapes.current = VISEME_TO_BLENDSHAPES[currentViseme] || VISEME_TO_BLENDSHAPES['sil']
      animFrame = requestAnimationFrame(animate)
    }
    animFrame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(animFrame)
  }, [isSpeaking, speechMarks, audioStartTime])

  // Fallback random mouth movement when speaking without speech marks
  useEffect(() => {
    if (isSpeaking && (!speechMarks || speechMarks.length === 0)) {
      const interval = setInterval(() => {
        const openness = 0.1 + Math.random() * 0.5
        targetBlendshapes.current = {
          jawOpen: openness,
          mouthSmileLeft: Math.random() * 0.15,
          mouthSmileRight: Math.random() * 0.15,
          mouthFunnel: Math.random() * 0.3,
          mouthLowerDownLeft: openness * 0.5,
          mouthLowerDownRight: openness * 0.5,
        }
      }, 100)
      return () => clearInterval(interval)
    } else if (!isSpeaking) {
      targetBlendshapes.current = { jawOpen: 0, mouthClose: 0.3 }
    }
  }, [isSpeaking, speechMarks])

  // Main animation frame loop
  useFrame((_, delta) => {
    timeRef.current += delta

    if (morphMeshes.current.length === 0) return

    // ─── EYE BLINK ───────────────────────────────────────────
    blinkTimerRef.current += delta
    if (!isBlinkingRef.current && blinkTimerRef.current >= nextBlinkRef.current) {
      isBlinkingRef.current = true
      blinkProgressRef.current = 0
      blinkTimerRef.current = 0
      nextBlinkRef.current = 2 + Math.random() * 4 // Next blink in 2-6 seconds
    }

    let blinkValue = 0
    if (isBlinkingRef.current) {
      blinkProgressRef.current += delta * 8 // Blink speed
      if (blinkProgressRef.current <= 1) {
        // Closing
        blinkValue = blinkProgressRef.current
      } else if (blinkProgressRef.current <= 2) {
        // Opening
        blinkValue = 2 - blinkProgressRef.current
      } else {
        isBlinkingRef.current = false
        blinkValue = 0
      }
    }

    // ─── EYE TRACKING (follow mouse) ─────────────────────────
    const eyeLookX = mouseRef.current.x * 0.5
    const eyeLookY = mouseRef.current.y * 0.3

    // ─── IDLE MICRO-EXPRESSIONS ──────────────────────────────
    const idleBrowInner = Math.sin(timeRef.current * 0.3) * 0.03
    const idleSmile = Math.sin(timeRef.current * 0.2) * 0.05 + 0.05

    // ─── BREATHING (subtle jaw/chest) ────────────────────────
    const breathe = Math.sin(timeRef.current * 1.0) * 0.02

    // ─── COMBINE ALL BLENDSHAPE TARGETS ──────────────────────
    const finalTargets: Partial<Record<string, number>> = {
      // Blink
      eyeBlinkLeft: blinkValue,
      eyeBlinkRight: blinkValue,

      // Eye tracking
      eyeLookInLeft: eyeLookX > 0 ? eyeLookX : 0,
      eyeLookOutLeft: eyeLookX < 0 ? -eyeLookX : 0,
      eyeLookInRight: eyeLookX < 0 ? -eyeLookX : 0,
      eyeLookOutRight: eyeLookX > 0 ? eyeLookX : 0,
      eyeLookUpLeft: eyeLookY > 0 ? eyeLookY : 0,
      eyeLookUpRight: eyeLookY > 0 ? eyeLookY : 0,
      eyeLookDownLeft: eyeLookY < 0 ? -eyeLookY : 0,
      eyeLookDownRight: eyeLookY < 0 ? -eyeLookY : 0,

      // Idle micro-expressions
      browInnerUp: idleBrowInner,
      mouthSmileLeft: state !== 'speaking' ? idleSmile : 0,
      mouthSmileRight: state !== 'speaking' ? idleSmile : 0,

      // Breathing
      jawOpen: breathe,

      // Lip sync (override from viseme targets)
      ...targetBlendshapes.current,
    }

    // State-specific expressions
    if (state === 'listening') {
      finalTargets.browInnerUp = 0.1
      finalTargets.eyeWideLeft = 0.1
      finalTargets.eyeWideRight = 0.1
    } else if (state === 'thinking') {
      finalTargets.browDownLeft = 0.15
      finalTargets.browDownRight = 0.15
      finalTargets.eyeSquintLeft = 0.1
      finalTargets.eyeSquintRight = 0.1
      finalTargets.mouthPucker = 0.1
    } else if (state === 'greeting') {
      finalTargets.mouthSmileLeft = 0.6
      finalTargets.mouthSmileRight = 0.6
      finalTargets.cheekSquintLeft = 0.3
      finalTargets.cheekSquintRight = 0.3
    }

    // ─── APPLY BLENDSHAPES TO ALL MORPH TARGET MESHES ────────
    for (const mesh of morphMeshes.current) {
      if (!mesh.morphTargetDictionary || !mesh.morphTargetInfluences) continue

      for (const [shapeName, targetValue] of Object.entries(finalTargets)) {
        const index = mesh.morphTargetDictionary[shapeName]
        if (index !== undefined) {
          const current = mesh.morphTargetInfluences[index] || 0
          // Smooth interpolation for natural movement
          const smoothing = shapeName.includes('Blink') ? 0.6 : 0.2
          mesh.morphTargetInfluences[index] = THREE.MathUtils.lerp(
            current,
            targetValue ?? 0,
            smoothing
          )
        }
      }
    }

    // ─── SUBTLE HEAD MOVEMENT ────────────────────────────────
    if (group.current) {
      // Breathing sway
      group.current.position.y = Math.sin(timeRef.current * 1.0) * 0.005

      // State-based head animation
      if (state === 'idle') {
        group.current.rotation.y = Math.sin(timeRef.current * 0.4) * 0.02
        group.current.rotation.x = Math.sin(timeRef.current * 0.25) * 0.01
      } else if (state === 'thinking') {
        group.current.rotation.z = Math.sin(timeRef.current * 0.6) * 0.03
        group.current.rotation.x = -0.03
      } else if (state === 'speaking') {
        group.current.rotation.y = Math.sin(timeRef.current * 0.5) * 0.015
        group.current.rotation.x = Math.sin(timeRef.current * 0.3) * 0.008
      } else if (state === 'listening') {
        group.current.rotation.x = 0.02 // Slight forward lean (attentive)
        group.current.rotation.y = Math.sin(timeRef.current * 0.3) * 0.01
      }
    }
  })

  return (
    <group ref={group} dispose={null}>
      <primitive object={scene} scale={1} position={[0, -1.5, 0]} />
    </group>
  )
}

// Preload the model
useGLTF.preload(MODEL_PATH)

// ============================================================
// Procedural Head Fallback (when GLB is unavailable)
// ============================================================

function ProceduralHeadFallback({
  isSpeaking,
  isListening,
  state,
  speechMarks,
  audioStartTime,
}: Avatar3DProps) {
  const headRef = useRef<THREE.Group>(null)
  const mouthRef = useRef<THREE.Mesh>(null)
  const leftLidRef = useRef<THREE.Mesh>(null)
  const rightLidRef = useRef<THREE.Mesh>(null)
  const leftIrisRef = useRef<THREE.Mesh>(null)
  const rightIrisRef = useRef<THREE.Mesh>(null)

  const timeRef = useRef(0)
  const blinkTimerRef = useRef(0)
  const isBlinkingRef = useRef(false)
  const nextBlinkRef = useRef(2 + Math.random() * 3)
  const targetMouthRef = useRef(0)
  const currentMouthRef = useRef(0)
  const mouseRef = useRef({ x: 0, y: 0 })

  const { gl } = useThree()

  // Mouse tracking
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      const rect = gl.domElement.getBoundingClientRect()
      mouseRef.current.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
      mouseRef.current.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
    }
    window.addEventListener('mousemove', handleMouseMove)
    return () => window.removeEventListener('mousemove', handleMouseMove)
  }, [gl])

  // Viseme lip sync
  useEffect(() => {
    if (!isSpeaking || !speechMarks || !audioStartTime || speechMarks.length === 0) {
      targetMouthRef.current = 0
      return
    }
    let animFrame: number
    const VISEME_SIMPLE: Record<string, number> = {
      'sil': 0, 'p': 0.2, 'f': 0.15, 't': 0.3, 'k': 0.4,
      'S': 0.3, 's': 0.2, 'T': 0.35, 'r': 0.25, 'i': 0.15,
      'u': 0.5, 'e': 0.3, '@': 0.45, 'a': 0.6, 'o': 0.5, 'E': 0.35, 'O': 0.45,
    }
    const animate = () => {
      const elapsed = Date.now() - audioStartTime
      let currentViseme = 'sil'
      for (const mark of speechMarks) {
        if (mark.type === 'viseme' && mark.time <= elapsed) currentViseme = mark.value
        else if (mark.type === 'viseme' && mark.time > elapsed) break
      }
      targetMouthRef.current = VISEME_SIMPLE[currentViseme] || 0
      animFrame = requestAnimationFrame(animate)
    }
    animFrame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(animFrame)
  }, [isSpeaking, speechMarks, audioStartTime])

  // Random mouth when speaking without marks
  useEffect(() => {
    if (isSpeaking && (!speechMarks || speechMarks.length === 0)) {
      const interval = setInterval(() => {
        targetMouthRef.current = 0.15 + Math.random() * 0.45
      }, 110)
      return () => clearInterval(interval)
    } else if (!isSpeaking) {
      targetMouthRef.current = 0
    }
  }, [isSpeaking, speechMarks])

  useFrame((_, delta) => {
    timeRef.current += delta
    if (!headRef.current) return

    // Smooth mouth
    currentMouthRef.current += (targetMouthRef.current - currentMouthRef.current) * 0.25
    if (mouthRef.current) {
      mouthRef.current.scale.y = 0.3 + currentMouthRef.current * 1.8
      mouthRef.current.scale.x = 1.0 - currentMouthRef.current * 0.15
    }

    // Blink
    blinkTimerRef.current += delta
    if (!isBlinkingRef.current && blinkTimerRef.current >= nextBlinkRef.current) {
      isBlinkingRef.current = true
      blinkTimerRef.current = 0
      nextBlinkRef.current = 2 + Math.random() * 4
    }
    let lidScale = 0
    if (isBlinkingRef.current) {
      const progress = blinkTimerRef.current * 8
      if (progress <= 1) lidScale = progress
      else if (progress <= 2) lidScale = 2 - progress
      else { isBlinkingRef.current = false; lidScale = 0 }
    }
    if (leftLidRef.current) leftLidRef.current.scale.y = lidScale
    if (rightLidRef.current) rightLidRef.current.scale.y = lidScale

    // Eye tracking
    if (leftIrisRef.current && rightIrisRef.current) {
      const eyeX = mouseRef.current.x * 0.025
      const eyeY = mouseRef.current.y * 0.015
      leftIrisRef.current.position.x = -0.15 + eyeX
      leftIrisRef.current.position.y = 0.05 + eyeY
      rightIrisRef.current.position.x = 0.15 + eyeX
      rightIrisRef.current.position.y = 0.05 + eyeY
    }

    // Head sway
    headRef.current.position.y = Math.sin(timeRef.current * 1.0) * 0.004
    if (state === 'idle') {
      headRef.current.rotation.y = Math.sin(timeRef.current * 0.4) * 0.025
      headRef.current.rotation.x = Math.sin(timeRef.current * 0.25) * 0.012
    } else if (state === 'thinking') {
      headRef.current.rotation.z = Math.sin(timeRef.current * 0.6) * 0.04
      headRef.current.rotation.x = -0.04
    } else if (state === 'speaking') {
      headRef.current.rotation.y = Math.sin(timeRef.current * 0.6) * 0.018
    }
  })

  // Warm realistic skin tone
  const skinColor = '#e8b896'
  const hairColor = '#1a0e08'
  const eyeColor = '#3d2b1f'
  const lipColor = '#b85050'

  return (
    <group ref={headRef}>
      {/* Head */}
      <mesh castShadow>
        <sphereGeometry args={[0.5, 64, 64]} />
        <meshStandardMaterial color={skinColor} roughness={0.65} metalness={0.02} />
      </mesh>

      {/* Hair back */}
      <mesh position={[0, 0.15, -0.1]} castShadow>
        <sphereGeometry args={[0.53, 32, 32, 0, Math.PI * 2, 0, Math.PI * 0.6]} />
        <meshStandardMaterial color={hairColor} roughness={0.9} />
      </mesh>

      {/* Hair bangs */}
      <mesh position={[0, 0.36, 0.18]}>
        <boxGeometry args={[0.72, 0.14, 0.22]} />
        <meshStandardMaterial color={hairColor} roughness={0.9} />
      </mesh>

      {/* Left Eye White */}
      <mesh position={[-0.15, 0.05, 0.43]}>
        <sphereGeometry args={[0.068, 24, 24]} />
        <meshStandardMaterial color="#fafafa" roughness={0.2} />
      </mesh>
      {/* Left Iris */}
      <mesh ref={leftIrisRef} position={[-0.15, 0.05, 0.475]}>
        <sphereGeometry args={[0.038, 20, 20]} />
        <meshStandardMaterial color={eyeColor} roughness={0.3} />
      </mesh>
      {/* Left Pupil */}
      <mesh position={[-0.15, 0.05, 0.495]}>
        <sphereGeometry args={[0.018, 16, 16]} />
        <meshStandardMaterial color="#0a0a0a" />
      </mesh>

      {/* Right Eye White */}
      <mesh position={[0.15, 0.05, 0.43]}>
        <sphereGeometry args={[0.068, 24, 24]} />
        <meshStandardMaterial color="#fafafa" roughness={0.2} />
      </mesh>
      {/* Right Iris */}
      <mesh ref={rightIrisRef} position={[0.15, 0.05, 0.475]}>
        <sphereGeometry args={[0.038, 20, 20]} />
        <meshStandardMaterial color={eyeColor} roughness={0.3} />
      </mesh>
      {/* Right Pupil */}
      <mesh position={[0.15, 0.05, 0.495]}>
        <sphereGeometry args={[0.018, 16, 16]} />
        <meshStandardMaterial color="#0a0a0a" />
      </mesh>

      {/* Eyelids */}
      <mesh ref={leftLidRef} position={[-0.15, 0.09, 0.44]} scale={[1, 0, 1]}>
        <boxGeometry args={[0.16, 0.08, 0.06]} />
        <meshStandardMaterial color={skinColor} />
      </mesh>
      <mesh ref={rightLidRef} position={[0.15, 0.09, 0.44]} scale={[1, 0, 1]}>
        <boxGeometry args={[0.16, 0.08, 0.06]} />
        <meshStandardMaterial color={skinColor} />
      </mesh>

      {/* Eyebrows */}
      <mesh position={[-0.15, 0.14, 0.42]} rotation={[0, 0, 0.1]}>
        <boxGeometry args={[0.12, 0.02, 0.03]} />
        <meshStandardMaterial color={hairColor} />
      </mesh>
      <mesh position={[0.15, 0.14, 0.42]} rotation={[0, 0, -0.1]}>
        <boxGeometry args={[0.12, 0.02, 0.03]} />
        <meshStandardMaterial color={hairColor} />
      </mesh>

      {/* Nose */}
      <mesh position={[0, -0.04, 0.49]}>
        <coneGeometry args={[0.035, 0.09, 12]} />
        <meshStandardMaterial color={skinColor} roughness={0.55} />
      </mesh>

      {/* Mouth */}
      <mesh ref={mouthRef} position={[0, -0.17, 0.44]} scale={[1, 0.3, 1]}>
        <sphereGeometry args={[0.07, 20, 20]} />
        <meshStandardMaterial color={lipColor} roughness={0.4} />
      </mesh>

      {/* Ears */}
      <mesh position={[-0.49, 0, 0]}>
        <sphereGeometry args={[0.055, 12, 12]} />
        <meshStandardMaterial color={skinColor} />
      </mesh>
      <mesh position={[0.49, 0, 0]}>
        <sphereGeometry args={[0.055, 12, 12]} />
        <meshStandardMaterial color={skinColor} />
      </mesh>

      {/* Neck */}
      <mesh position={[0, -0.55, 0]}>
        <cylinderGeometry args={[0.12, 0.14, 0.22, 20]} />
        <meshStandardMaterial color={skinColor} roughness={0.65} />
      </mesh>

      {/* Shoulders */}
      <mesh position={[0, -0.76, 0]}>
        <boxGeometry args={[0.85, 0.22, 0.32]} />
        <meshStandardMaterial color="#3b82f6" roughness={0.7} />
      </mesh>
    </group>
  )
}

// ============================================================
// Loading Error Boundary
// ============================================================

function ModelLoadingFallback() {
  return (
    <Html center>
      <div className="text-center text-white">
        <div className="w-10 h-10 border-3 border-blue-400 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-sm opacity-80">Loading avatar model...</p>
      </div>
    </Html>
  )
}

// ============================================================
// Main Avatar3D Component (Full-Screen Canvas)
// ============================================================

function Avatar3D({
  isSpeaking,
  isListening,
  state,
  speechMarks,
  audioStartTime,
  name,
}: Avatar3DProps) {
  const [modelError, setModelError] = useState(false)
  const [modelLoaded, setModelLoaded] = useState(false)

  // Check if GLB model exists
  useEffect(() => {
    fetch(MODEL_PATH, { method: 'HEAD' })
      .then((res) => {
        if (res.ok) {
          setModelLoaded(true)
          setModelError(false)
        } else {
          setModelError(true)
          setModelLoaded(false)
        }
      })
      .catch(() => {
        setModelError(true)
        setModelLoaded(false)
      })
  }, [])

  return (
    <div className="w-full h-full absolute inset-0">
      <Canvas
        camera={{ position: [0, 0, 2.2], fov: 40 }}
        style={{ background: 'linear-gradient(180deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)' }}
        gl={{
          antialias: true,
          alpha: false,
          powerPreference: 'high-performance',
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: 1.2,
        }}
        shadows
        dpr={[1, 2]}
      >
        {/* Studio Lighting for Realistic Skin */}
        <ambientLight intensity={0.4} color="#ffe8d6" />
        <directionalLight
          position={[3, 4, 5]}
          intensity={1.2}
          color="#fff5eb"
          castShadow
          shadow-mapSize={[2048, 2048]}
          shadow-bias={-0.0001}
        />
        <directionalLight position={[-2, 3, 4]} intensity={0.5} color="#b4d4ff" />
        <pointLight position={[0, 1.5, 3]} intensity={0.6} color="#ffeedd" distance={8} />
        {/* Rim light for depth */}
        <pointLight position={[-2, 0, -2]} intensity={0.3} color="#4488ff" distance={6} />
        <pointLight position={[2, 0, -2]} intensity={0.3} color="#ff8844" distance={6} />

        {/* Avatar Model */}
        {modelLoaded && !modelError ? (
          <AngelicaModel
            isSpeaking={isSpeaking}
            isListening={isListening}
            state={state}
            speechMarks={speechMarks}
            audioStartTime={audioStartTime}
            name={name}
          />
        ) : (
          <ProceduralHeadFallback
            isSpeaking={isSpeaking}
            isListening={isListening}
            state={state}
            speechMarks={speechMarks}
            audioStartTime={audioStartTime}
            name={name}
          />
        )}

        {/* Ground shadow */}
        <ContactShadows
          position={[0, -1.6, 0]}
          opacity={0.5}
          scale={4}
          blur={2.5}
          far={4}
        />

        {/* HDR Environment for realistic reflections */}
        <Environment preset="studio" />

        {/* Mouse Drag Orbit Controls */}
        <OrbitControls
          enableZoom={true}
          enablePan={false}
          enableDamping={true}
          dampingFactor={0.05}
          rotateSpeed={0.5}
          zoomSpeed={0.5}
          minDistance={1.2}
          maxDistance={4}
          minPolarAngle={Math.PI / 4}
          maxPolarAngle={Math.PI / 1.6}
          minAzimuthAngle={-Math.PI / 3}
          maxAzimuthAngle={Math.PI / 3}
          // Touch support for mobile
          touches={{
            ONE: THREE.TOUCH.ROTATE,
            TWO: THREE.TOUCH.DOLLY_PAN,
          }}
        />
      </Canvas>

      {/* Model status badge */}
      {modelError && (
        <div className="absolute top-4 left-4 z-20 px-3 py-1.5 bg-yellow-600/80 backdrop-blur-sm rounded-lg text-xs text-white">
          ⚠️ GLB model not found — using procedural avatar
        </div>
      )}

      {/* State indicator overlay */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-20">
        {isSpeaking && (
          <div className="flex items-center gap-2 px-4 py-2 bg-blue-600/80 backdrop-blur-md rounded-full shadow-lg border border-blue-400/30">
            <div className="flex items-center gap-0.5">
              {[...Array(5)].map((_, i) => (
                <div
                  key={i}
                  className="w-0.5 bg-white rounded-full animate-pulse"
                  style={{
                    height: `${8 + Math.random() * 12}px`,
                    animationDelay: `${i * 0.1}s`,
                    animationDuration: '0.4s',
                  }}
                />
              ))}
            </div>
            <span className="text-sm text-white font-medium">Speaking</span>
          </div>
        )}
        {isListening && !isSpeaking && (
          <div className="flex items-center gap-2 px-4 py-2 bg-green-600/80 backdrop-blur-md rounded-full shadow-lg border border-green-400/30">
            <div className="w-2.5 h-2.5 bg-green-300 rounded-full animate-pulse" />
            <span className="text-sm text-white font-medium">Listening</span>
          </div>
        )}
        {state === 'thinking' && (
          <div className="flex items-center gap-2 px-4 py-2 bg-amber-600/80 backdrop-blur-md rounded-full shadow-lg border border-amber-400/30">
            <div className="w-2.5 h-2.5 bg-amber-300 rounded-full animate-pulse" />
            <span className="text-sm text-white font-medium">Thinking...</span>
          </div>
        )}
      </div>

      {/* Drag hint */}
      <div className="absolute bottom-6 right-6 z-20 text-xs text-white/40 select-none pointer-events-none">
        🖱️ Drag to rotate • Scroll to zoom
      </div>
    </div>
  )
}

export default Avatar3D
