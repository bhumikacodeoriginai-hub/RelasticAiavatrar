# Avatar 3D Models

Place your GLB model files in this directory.

## Required Model: angelica.glb

The avatar system expects a GLB model named `angelica.glb` with the following requirements:

### ARKit 52 Blendshapes (Morph Targets)

The model MUST include these morph targets for full facial animation:

#### Eye Blendshapes
- eyeBlinkLeft, eyeBlinkRight
- eyeLookDownLeft, eyeLookDownRight
- eyeLookInLeft, eyeLookInRight
- eyeLookOutLeft, eyeLookOutRight
- eyeLookUpLeft, eyeLookUpRight
- eyeSquintLeft, eyeSquintRight
- eyeWideLeft, eyeWideRight

#### Jaw & Mouth Blendshapes
- jawForward, jawLeft, jawRight, jawOpen
- mouthClose
- mouthFunnel, mouthPucker
- mouthLeft, mouthRight
- mouthSmileLeft, mouthSmileRight
- mouthFrownLeft, mouthFrownRight
- mouthDimpleLeft, mouthDimpleRight
- mouthStretchLeft, mouthStretchRight
- mouthRollLower, mouthRollUpper
- mouthShrugLower, mouthShrugUpper
- mouthPressLeft, mouthPressRight
- mouthLowerDownLeft, mouthLowerDownRight
- mouthUpperUpLeft, mouthUpperUpRight

#### Brow & Nose Blendshapes
- browDownLeft, browDownRight
- browInnerUp
- browOuterUpLeft, browOuterUpRight
- noseSneerLeft, noseSneerRight

#### Cheek & Tongue
- cheekPuff, cheekSquintLeft, cheekSquintRight
- tongueOut

### Skin Material

The model should use PBR materials with:
- Base color / albedo map for realistic skin
- Normal map for skin detail
- Roughness map (skin is ~0.6-0.8 roughness)
- Subsurface scattering (optional, for translucency)

### Skeleton (Optional)

If the model includes an armature/skeleton, it should follow a standard humanoid rig
for potential body animations.

## How to Add Your Model

1. Export your model from Blender/Maya/etc. as `.glb` format
2. Ensure morph targets are named using ARKit conventions above
3. Place the file as `angelica.glb` in this directory
4. The avatar will automatically load it on next page refresh
