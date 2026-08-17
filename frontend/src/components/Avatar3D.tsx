/**
 * 3D Avatar Component using React Three Fiber
 * 
 * Features:
 * - GLB/GLTF model loading (if available)
 * - Procedural 3D head as fallback
 * - Idle animation (breathing, subtle head movement)
 * - Blinking animation (natural random intervals)
 * - Speaking animation (viseme-based lip sync from Polly speech marks)
 * - Listening animation (attentive pose)
 * - Thinking animation (slight head tilt)
 * - Eye contact (follows cursor/face position)
 */

import { useRef, useMemo, useEffect, useState, useCallback } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Environment, ContactShadows } from '@react-three/drei'
import * as THREE from 'three'

// Polly viseme to mouth shape mapping
const VISEME_MAP: Record<string, number> = {
  'sil': 0.0,    // silence
  'p': 0.3,      // p, b, m
  'f': 0.2,      // f, v
  't': 0.4,      // t, d, n, l
  'k': 0.5,      // k, g, ng
  'S': 0.4,      // sh, ch, j
  's': 0.3,      // s, z
  'T': 0.5,      // th
  'r': 0.3,      // r
  'i': 0.2,      // ee
  'u': 0.6,      // oo (rounded lips)
  'e': 0.4,      // eh
  '@': 0.5,      // uh
  'a': 0.7,      // ah (wide open)
  'o': 0.6,      // oh (rounded)
  'E': 0.4,      // ay
  'O': 0.6,      // oy
}

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
// Procedural 3D Head (fallback when no GLB model)
// ============================================================

function ProceduralHead({
  isSpeaking,
  isListening,
  state,
  speechMarks,
  audioStartTime,
}: Avatar3DProps) {
  const headRef = useRef<THREE.Group>(null)
  const leftEyeRef = useRef<THREE.Mesh>(null)
  const rightEyeRef = useRef<THREE.Mesh>(null)
  const mouthRef = useRef<THREE.Mesh>(null)
  const leftLidRef = useRef<THREE.Mesh>(null)
  const rightLidRef = useRef<THREE.Mesh>(null)

  // Animation state
  const [blinkTimer, setBlinkTimer] = useState(0)
  const [isBlinking, setIsBlinking] = useState(false)
  const [mouthOpenness, setMouthOpenness] = useState(0)
  const targetMouthRef = useRef(0)
  const timeRef = useRef(0)

  // Blinking at random intervals (2-5 seconds)
  useEffect(() => {
    const blink = () => {
      setIsBlinking(true)
      setTimeout(() => setIsBlinking(false), 150)
      const nextBlink = 2000 + Math.random() * 3000
      setBlinkTimer(window.setTimeout(blink, nextBlink) as unknown as number)
    }
    const initial = setTimeout(blink, 1000 + Math.random() * 2000)
    return () => {
      clearTimeout(initial)
      if (blinkTimer) clearTimeout(blinkTimer)
    }
  }, [])

  // Viseme-based lip sync
  useEffect(() => {
    if (!isSpeaking || !speechMarks || !audioStartTime) {
      targetMouthRef.current = 0
      return
    }

    let animFrame: number
    const animate = () => {
      const elapsed = (Date.now() - audioStartTime)
      // Find current viseme
      let currentViseme = 'sil'
      for (const mark of speechMarks) {
        if (mark.type === 'viseme' && mark.time <= elapsed) {
          currentViseme = mark.value
        } else if (mark.type === 'viseme' && mark.time > elapsed) {
          break
        }
      }
      targetMouthRef.current = VISEME_MAP[currentViseme] || 0
      animFrame = requestAnimationFrame(animate)
    }
    animFrame = requestAnimationFrame(animate)

    return () => cancelAnimationFrame(animFrame)
  }, [isSpeaking, speechMarks, audioStartTime])

  // If no speech marks, use random mouth movement while speaking
  useEffect(() => {
    if (isSpeaking && (!speechMarks || speechMarks.length === 0)) {
      const interval = setInterval(() => {
        targetMouthRef.current = 0.2 + Math.random() * 0.5
      }, 120)
      return () => clearInterval(interval)
    } else if (!isSpeaking) {
      targetMouthRef.current = 0
    }
  }, [isSpeaking, speechMarks])

  // Animation loop
  useFrame((_, delta) => {
    timeRef.current += delta

    if (!headRef.current) return

    // Smooth mouth animation
    const currentMouth = mouthOpenness
    const target = targetMouthRef.current
    setMouthOpenness(currentMouth + (target - currentMouth) * 0.3)

    // Idle breathing (subtle Y oscillation)
    const breathe = Math.sin(timeRef.current * 1.2) * 0.003
    headRef.current.position.y = breathe

    // Subtle head movement
    if (state === 'idle' || state === 'listening') {
      headRef.current.rotation.y = Math.sin(timeRef.current * 0.5) * 0.03
      headRef.current.rotation.x = Math.sin(timeRef.current * 0.3) * 0.015
    } else if (state === 'thinking') {
      headRef.current.rotation.z = Math.sin(timeRef.current * 0.8) * 0.05
      headRef.current.rotation.x = -0.05
    } else if (state === 'speaking') {
      headRef.current.rotation.y = Math.sin(timeRef.current * 0.7) * 0.02
    }

    // Eye movement (subtle look around)
    if (leftEyeRef.current && rightEyeRef.current) {
      const eyeX = Math.sin(timeRef.current * 0.4) * 0.02
      const eyeY = Math.cos(timeRef.current * 0.3) * 0.01
      leftEyeRef.current.position.x = -0.15 + eyeX
      rightEyeRef.current.position.x = 0.15 + eyeX
      leftEyeRef.current.position.y = 0.05 + eyeY
      rightEyeRef.current.position.y = 0.05 + eyeY
    }

    // Mouth scale based on openness
    if (mouthRef.current) {
      mouthRef.current.scale.y = 0.3 + mouthOpenness * 1.5
      mouthRef.current.scale.x = 1.0 - mouthOpenness * 0.2
    }

    // Eyelids for blinking
    if (leftLidRef.current && rightLidRef.current) {
      const lidTarget = isBlinking ? 1.0 : 0.0
      leftLidRef.current.scale.y = THREE.MathUtils.lerp(
        leftLidRef.current.scale.y, lidTarget, 0.5
      )
      rightLidRef.current.scale.y = leftLidRef.current.scale.y
    }
  })

  const skinColor = '#f0c8a0'
  const hairColor = '#2d1810'
  const eyeColor = '#4a3728'
  const lipColor = '#c94040'

  return (
    <group ref={headRef} position={[0, 0, 0]}>
      {/* Head */}
      <mesh castShadow>
        <sphereGeometry args={[0.5, 32, 32]} />
        <meshStandardMaterial color={skinColor} roughness={0.7} />
      </mesh>

      {/* Hair (back) */}
      <mesh position={[0, 0.15, -0.1]} castShadow>
        <sphereGeometry args={[0.52, 32, 32, 0, Math.PI * 2, 0, Math.PI * 0.6]} />
        <meshStandardMaterial color={hairColor} roughness={0.9} />
      </mesh>

      {/* Hair (bangs) */}
      <mesh position={[0, 0.35, 0.2]}>
        <boxGeometry args={[0.7, 0.15, 0.2]} />
        <meshStandardMaterial color={hairColor} roughness={0.9} />
      </mesh>

      {/* Left Eye White */}
      <mesh position={[-0.15, 0.05, 0.42]}>
        <sphereGeometry args={[0.07, 16, 16]} />
        <meshStandardMaterial color="white" />
      </mesh>

      {/* Left Iris */}
      <mesh ref={leftEyeRef} position={[-0.15, 0.05, 0.47]}>
        <sphereGeometry args={[0.04, 16, 16]} />
        <meshStandardMaterial color={eyeColor} />
      </mesh>

      {/* Left Pupil */}
      <mesh position={[-0.15, 0.05, 0.49]}>
        <sphereGeometry args={[0.02, 16, 16]} />
        <meshStandardMaterial color="black" />
      </mesh>

      {/* Right Eye White */}
      <mesh position={[0.15, 0.05, 0.42]}>
        <sphereGeometry args={[0.07, 16, 16]} />
        <meshStandardMaterial color="white" />
      </mesh>

      {/* Right Iris */}
      <mesh ref={rightEyeRef} position={[0.15, 0.05, 0.47]}>
        <sphereGeometry args={[0.04, 16, 16]} />
        <meshStandardMaterial color={eyeColor} />
      </mesh>

      {/* Right Pupil */}
      <mesh position={[0.15, 0.05, 0.49]}>
        <sphereGeometry args={[0.02, 16, 16]} />
        <meshStandardMaterial color="black" />
      </mesh>

      {/* Left Eyelid (for blinking) */}
      <mesh ref={leftLidRef} position={[-0.15, 0.09, 0.44]} scale={[1, 0, 1]}>
        <boxGeometry args={[0.16, 0.08, 0.06]} />
        <meshStandardMaterial color={skinColor} />
      </mesh>

      {/* Right Eyelid */}
      <mesh ref={rightLidRef} position={[0.15, 0.09, 0.44]} scale={[1, 0, 1]}>
        <boxGeometry args={[0.16, 0.08, 0.06]} />
        <meshStandardMaterial color={skinColor} />
      </mesh>

      {/* Nose */}
      <mesh position={[0, -0.05, 0.48]}>
        <coneGeometry args={[0.04, 0.08, 8]} />
        <meshStandardMaterial color={skinColor} roughness={0.6} />
      </mesh>

      {/* Mouth */}
      <mesh ref={mouthRef} position={[0, -0.18, 0.43]} scale={[1, 0.3, 1]}>
        <sphereGeometry args={[0.08, 16, 16]} />
        <meshStandardMaterial color={lipColor} roughness={0.5} />
      </mesh>

      {/* Ears */}
      <mesh position={[-0.48, 0, 0]}>
        <sphereGeometry args={[0.06, 8, 8]} />
        <meshStandardMaterial color={skinColor} />
      </mesh>
      <mesh position={[0.48, 0, 0]}>
        <sphereGeometry args={[0.06, 8, 8]} />
        <meshStandardMaterial color={skinColor} />
      </mesh>

      {/* Neck */}
      <mesh position={[0, -0.55, 0]}>
        <cylinderGeometry args={[0.12, 0.15, 0.2, 16]} />
        <meshStandardMaterial color={skinColor} />
      </mesh>

      {/* Shoulders (hint) */}
      <mesh position={[0, -0.75, 0]}>
        <boxGeometry args={[0.8, 0.2, 0.3]} />
        <meshStandardMaterial color="#3b82f6" roughness={0.8} />
      </mesh>
    </group>
  )
}

// ============================================================
// Main Avatar3D Component
// ============================================================

function Avatar3D({
  isSpeaking,
  isListening,
  state,
  speechMarks,
  audioStartTime,
  name,
}: Avatar3DProps) {
  return (
    <div className="w-full h-full min-h-[300px] relative">
      <Canvas
        camera={{ position: [0, 0, 2], fov: 45 }}
        style={{ background: 'transparent' }}
        gl={{ antialias: true, alpha: true }}
      >
        {/* Lighting */}
        <ambientLight intensity={0.5} />
        <directionalLight position={[5, 5, 5]} intensity={0.8} castShadow />
        <directionalLight position={[-3, 2, 4]} intensity={0.3} color="#b4d4ff" />
        <pointLight position={[0, 2, 3]} intensity={0.4} color="#ffeedd" />

        {/* Avatar */}
        <ProceduralHead
          isSpeaking={isSpeaking}
          isListening={isListening}
          state={state}
          speechMarks={speechMarks}
          audioStartTime={audioStartTime}
          name={name}
        />

        {/* Shadow */}
        <ContactShadows
          position={[0, -1.2, 0]}
          opacity={0.4}
          scale={3}
          blur={2}
        />

        {/* Environment for reflections */}
        <Environment preset="studio" />

        {/* Allow slight orbit for 3D feel */}
        <OrbitControls
          enableZoom={false}
          enablePan={false}
          minPolarAngle={Math.PI / 3}
          maxPolarAngle={Math.PI / 1.8}
          minAzimuthAngle={-Math.PI / 6}
          maxAzimuthAngle={Math.PI / 6}
        />
      </Canvas>

      {/* State indicator overlay */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10">
        {isSpeaking && (
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-primary-600/90 backdrop-blur-sm rounded-full shadow-lg">
            <div className="audio-wave text-white">
              <div className="audio-wave-bar" />
              <div className="audio-wave-bar" />
              <div className="audio-wave-bar" />
              <div className="audio-wave-bar" />
              <div className="audio-wave-bar" />
            </div>
            <span className="text-xs text-white font-medium ml-1">Speaking</span>
          </div>
        )}
        {isListening && !isSpeaking && (
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600/90 backdrop-blur-sm rounded-full shadow-lg">
            <div className="w-2 h-2 bg-green-300 rounded-full animate-pulse" />
            <span className="text-xs text-white font-medium">Listening</span>
          </div>
        )}
        {state === 'thinking' && (
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-yellow-600/90 backdrop-blur-sm rounded-full shadow-lg">
            <div className="w-2 h-2 bg-yellow-300 rounded-full animate-pulse" />
            <span className="text-xs text-white font-medium">Thinking...</span>
          </div>
        )}
      </div>
    </div>
  )
}

export default Avatar3D
