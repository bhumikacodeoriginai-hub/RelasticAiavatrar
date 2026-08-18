/**
 * Avatar3D — Angelica GLB Model with Complete 52 ARKit Blendshape Animation System
 *
 * This is the primary 3D avatar component that renders the Angelica model
 * with full human-realistic animation driven by the AvatarStateManager.
 *
 * Animation features:
 * - 52 ARKit blendshape-driven facial animation
 * - EmotionEngine: 14 distinct human emotions with micro-expressions
 * - AdvancedLipSync: Viseme-based with coarticulation & jaw damping
 * - GazeSystem: Saccades, social scanning, micro-saccades, attention shifts
 * - GestureSystem: Head nods, tilts, shrugs, thinking pose
 * - BreathingSystem: Thoracic/diaphragmatic with emotional adaptation
 * - VoiceReactiveExpressions: Voice amplitude drives subtle facial reactions
 * - Natural eye blink with double-blink & asymmetry
 *
 * Rendering:
 * - Full-screen canvas with studio lighting for realistic skin
 * - PBR materials with subsurface approximation
 * - Mouse drag orbit controls (rotate/zoom)
 * - Environment map for reflections
 * - Contact shadows
 * - Reduced-motion support (accessibility)
 */

import { useRef, useEffect, useState, useMemo, useCallback } from 'react'
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

import { AvatarStateManager } from '../lib/avatar'
import type { AvatarActivityState, SpeechMark, EmotionType, GestureType } from '../lib/avatar'

// ============================================================
// Props Interface
// ============================================================

export interface Avatar3DProps {
  isSpeaking: boolean
  isListening: boolean
  state: AvatarActivityState
  speechMarks?: SpeechMark[]
  audioStartTime?: number
  name?: string
  emotion?: EmotionType
  emotionIntensity?: number
  gesture?: GestureType
  reducedMotion?: boolean
  onReady?: () => void
}

// ============================================================
// GLB Model Path
// ============================================================

const MODEL_PATH = '/models/angelica.glb'

// ============================================================
// Angelica Model Component (the 3D character)
// ============================================================

function AngelicaModel({
  isSpeaking,
  isListening,
  state,
  speechMarks,
  audioStartTime,
  emotion,
  emotionIntensity,
  gesture,
  reducedMotion,
  onReady,
}: Avatar3DProps) {
  const group = useRef<THREE.Group>(null)
  const { scene, animations } = useGLTF(MODEL_PATH)
  const { actions } = useAnimations(animations, group)

  // Avatar State Manager — coordinates all animation subsystems
  const stateManager = useMemo(() => new AvatarStateManager(), [])

  // Refs for morph target meshes
  const morphMeshes = useRef<THREE.Mesh[]>([])
  const mouseRef = useRef({ x: 0, y: 0 })
  const isReadyRef = useRef(false)

  // Get Three.js renderer
  const { gl } = useThree()

  // ─── Mouse Tracking ────────────────────────────────────────
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      const rect = gl.domElement.getBoundingClientRect()
      mouseRef.current.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
      mouseRef.current.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
      // Update gaze system
      stateManager.updateGazeTarget(mouseRef.current.x, mouseRef.current.y)
    }
    window.addEventListener('mousemove', handleMouseMove)
    return () => window.removeEventListener('mousemove', handleMouseMove)
  }, [gl, stateManager])

  // ─── Find Morph Target Meshes ──────────────────────────────
  useEffect(() => {
    const meshes: THREE.Mesh[] = []
    scene.traverse((child) => {
      if (child instanceof THREE.Mesh && child.morphTargetInfluences && child.morphTargetDictionary) {
        meshes.push(child)

        // Enhance skin materials for realism
        if (child.material instanceof THREE.MeshStandardMaterial) {
          const mat = child.material as THREE.MeshStandardMaterial
          mat.roughness = Math.max(mat.roughness, 0.5)
          mat.metalness = Math.min(mat.metalness, 0.05)
          mat.envMapIntensity = 0.6
          mat.needsUpdate = true
        }
      }
    })
    morphMeshes.current = meshes

    if (meshes.length > 0) {
      console.log(`[Avatar3D] Loaded Angelica with ${meshes.length} morph mesh(es)`)
      if (meshes[0].morphTargetDictionary) {
        console.log(`[Avatar3D] Available blendshapes: ${Object.keys(meshes[0].morphTargetDictionary).length}`)
      }
      isReadyRef.current = true
      onReady?.()
    }
  }, [scene, onReady])

  // ─── Play Idle Animation (if model has skeletal animations) ─
  useEffect(() => {
    if (actions && Object.keys(actions).length > 0) {
      const idleAction = actions['idle'] || actions['Idle'] || actions['breathing'] || Object.values(actions)[0]
      if (idleAction) {
        idleAction.reset().fadeIn(0.5).play()
      }
    }
  }, [actions])

  // ─── Sync Activity State ───────────────────────────────────
  useEffect(() => {
    stateManager.setActivityState(state)
  }, [state, stateManager])

  // ─── Sync Speaking State ───────────────────────────────────
  useEffect(() => {
    stateManager.setSpeaking(isSpeaking, speechMarks, audioStartTime)
  }, [isSpeaking, speechMarks, audioStartTime, stateManager])

  // ─── Sync Listening State ──────────────────────────────────
  useEffect(() => {
    stateManager.setListening(isListening)
  }, [isListening, stateManager])

  // ─── Sync Emotion from Props ───────────────────────────────
  useEffect(() => {
    if (emotion) {
      stateManager.setEmotion(emotion, emotionIntensity ?? 0.7)
    }
  }, [emotion, emotionIntensity, stateManager])

  // ─── Trigger Gestures from Props ───────────────────────────
  useEffect(() => {
    if (gesture) {
      stateManager.triggerGesture(gesture)
    }
  }, [gesture, stateManager])

  // ─── Reduced Motion ────────────────────────────────────────
  useEffect(() => {
    stateManager.setReducedMotion(reducedMotion ?? false)
  }, [reducedMotion, stateManager])

  // ─── Main Animation Frame Loop ────────────────────────────
  useFrame((_, delta) => {
    if (morphMeshes.current.length === 0) return

    // Clamp delta to prevent large jumps (e.g., tab switch)
    const dt = Math.min(delta, 0.05)

    // Update the entire animation system
    const output = stateManager.update(dt)

    // ─── Apply Blendshapes to All Morph Target Meshes ────
    for (const mesh of morphMeshes.current) {
      if (!mesh.morphTargetDictionary || !mesh.morphTargetInfluences) continue

      for (const [shapeName, targetValue] of Object.entries(output.blendshapes)) {
        const index = mesh.morphTargetDictionary[shapeName]
        if (index !== undefined) {
          const current = mesh.morphTargetInfluences[index] || 0
          // Final smoothing pass for silky-smooth output
          const smoothFactor = shapeName.includes('Blink') ? 0.5 : 0.25
          mesh.morphTargetInfluences[index] = THREE.MathUtils.lerp(
            current,
            targetValue ?? 0,
            smoothFactor
          )
        }
      }
    }

    // ─── Apply Head Rotation ─────────────────────────────
    if (group.current) {
      // Breathing body offset
      group.current.position.y = output.bodyOffset.y

      // Head rotation (smooth)
      const rot = output.headRotation
      group.current.rotation.x = THREE.MathUtils.lerp(group.current.rotation.x, rot.pitch, 0.1)
      group.current.rotation.y = THREE.MathUtils.lerp(group.current.rotation.y, rot.yaw, 0.1)
      group.current.rotation.z = THREE.MathUtils.lerp(group.current.rotation.z, rot.roll, 0.1)
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
// Procedural Head Fallback (when GLB model is unavailable)
// ============================================================

function ProceduralHeadFallback({
  isSpeaking,
  isListening,
  state,
}: Avatar3DProps) {
  const headRef = useRef<THREE.Group>(null)
  const mouthRef = useRef<THREE.Mesh>(null)
  const leftIrisRef = useRef<THREE.Mesh>(null)
  const rightIrisRef = useRef<THREE.Mesh>(null)
  const leftLidRef = useRef<THREE.Mesh>(null)
  const rightLidRef = useRef<THREE.Mesh>(null)

  const timeRef = useRef(0)
  const blinkTimerRef = useRef(0)
  const isBlinkingRef = useRef(false)
  const nextBlinkRef = useRef(2 + Math.random() * 3)
  const targetMouthRef = useRef(0)
  const currentMouthRef = useRef(0)
  const mouseRef = useRef({ x: 0, y: 0 })

  const { gl } = useThree()

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      const rect = gl.domElement.getBoundingClientRect()
      mouseRef.current.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
      mouseRef.current.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
    }
    window.addEventListener('mousemove', handleMouseMove)
    return () => window.removeEventListener('mousemove', handleMouseMove)
  }, [gl])

  // Speaking fallback
  useEffect(() => {
    if (isSpeaking) {
      const interval = setInterval(() => {
        targetMouthRef.current = 0.15 + Math.random() * 0.45
      }, 110)
      return () => clearInterval(interval)
    } else {
      targetMouthRef.current = 0
    }
  }, [isSpeaking])

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
      {/* Hair */}
      <mesh position={[0, 0.15, -0.1]} castShadow>
        <sphereGeometry args={[0.53, 32, 32, 0, Math.PI * 2, 0, Math.PI * 0.6]} />
        <meshStandardMaterial color={hairColor} roughness={0.9} />
      </mesh>
      <mesh position={[0, 0.36, 0.18]}>
        <boxGeometry args={[0.72, 0.14, 0.22]} />
        <meshStandardMaterial color={hairColor} roughness={0.9} />
      </mesh>
      {/* Eyes */}
      <mesh position={[-0.15, 0.05, 0.43]}>
        <sphereGeometry args={[0.068, 24, 24]} />
        <meshStandardMaterial color="#fafafa" roughness={0.2} />
      </mesh>
      <mesh ref={leftIrisRef} position={[-0.15, 0.05, 0.475]}>
        <sphereGeometry args={[0.038, 20, 20]} />
        <meshStandardMaterial color={eyeColor} roughness={0.3} />
      </mesh>
      <mesh position={[0.15, 0.05, 0.43]}>
        <sphereGeometry args={[0.068, 24, 24]} />
        <meshStandardMaterial color="#fafafa" roughness={0.2} />
      </mesh>
      <mesh ref={rightIrisRef} position={[0.15, 0.05, 0.475]}>
        <sphereGeometry args={[0.038, 20, 20]} />
        <meshStandardMaterial color={eyeColor} roughness={0.3} />
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
      {/* Neck + Shoulders */}
      <mesh position={[0, -0.55, 0]}>
        <cylinderGeometry args={[0.12, 0.14, 0.22, 20]} />
        <meshStandardMaterial color={skinColor} roughness={0.65} />
      </mesh>
      <mesh position={[0, -0.76, 0]}>
        <boxGeometry args={[0.85, 0.22, 0.32]} />
        <meshStandardMaterial color="#3b82f6" roughness={0.7} />
      </mesh>
    </group>
  )
}

// ============================================================
// Loading Fallback
// ============================================================

function ModelLoadingFallback() {
  return (
    <Html center>
      <div className="text-center text-white">
        <div className="w-10 h-10 border-3 border-blue-400 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-sm opacity-80">Loading Angelica avatar...</p>
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
  emotion,
  emotionIntensity,
  gesture,
  reducedMotion,
  onReady,
}: Avatar3DProps) {
  const [modelError, setModelError] = useState(false)
  const [modelLoaded, setModelLoaded] = useState(false)

  // Check prefers-reduced-motion
  const prefersReducedMotion = useMemo(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }, [])

  const effectiveReducedMotion = reducedMotion ?? prefersReducedMotion

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
    <div
      className="w-full h-full absolute inset-0"
      role="img"
      aria-label={`3D avatar ${name || 'Angelica'}${isSpeaking ? ', currently speaking' : isListening ? ', currently listening' : ''}`}
    >
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
        {/* Rim lights for depth */}
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
            emotion={emotion}
            emotionIntensity={emotionIntensity}
            gesture={gesture}
            reducedMotion={effectiveReducedMotion}
            onReady={onReady}
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
          touches={{
            ONE: THREE.TOUCH.ROTATE,
            TWO: THREE.TOUCH.DOLLY_PAN,
          }}
        />
      </Canvas>

      {/* Model status badge */}
      {modelError && (
        <div className="absolute top-4 left-4 z-20 px-3 py-1.5 bg-yellow-600/80 backdrop-blur-sm rounded-lg text-xs text-white">
          ⚠️ GLB model not found — using procedural fallback
        </div>
      )}

      {/* State indicator overlay */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-20">
        {isSpeaking && (
          <div className="flex items-center gap-2 px-4 py-2 bg-blue-600/80 backdrop-blur-md rounded-full shadow-lg border border-blue-400/30">
            <div className="flex items-center gap-0.5" aria-hidden="true">
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
            <div className="w-2.5 h-2.5 bg-green-300 rounded-full animate-pulse" aria-hidden="true" />
            <span className="text-sm text-white font-medium">Listening</span>
          </div>
        )}
        {state === 'thinking' && (
          <div className="flex items-center gap-2 px-4 py-2 bg-amber-600/80 backdrop-blur-md rounded-full shadow-lg border border-amber-400/30">
            <div className="w-2.5 h-2.5 bg-amber-300 rounded-full animate-pulse" aria-hidden="true" />
            <span className="text-sm text-white font-medium">Thinking...</span>
          </div>
        )}
      </div>

      {/* Drag hint */}
      <div className="absolute bottom-6 right-6 z-20 text-xs text-white/40 select-none pointer-events-none" aria-hidden="true">
        🖱️ Drag to rotate • Scroll to zoom
      </div>
    </div>
  )
}

export default Avatar3D
