
import * as THREE from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import {
  hudVertexShader,
  hudFragmentShader,
} from "./orbShadersHUD";
import type { AIOrbConfig, AIOrbState } from "./types";

export const DEFAULT_HUD_CONFIG: AIOrbConfig = {
  particleCount: 14000,
  particleCountMobile: 7000,
  radius: 1.25,
  basePointSize: 2.5,
  colors: {
    royalBlue:       "#1e40ff",
    violet:          "#9d32ff",
    magenta:         "#ff28d4",
    hotspot:         "#ffffff",
    thinkingBlue:    "#00d8ff",
    speakingMagenta: "#ff1f9c",
  },
  bloom: {
    strength:  1.15,
    radius:    0.55,
    threshold: 0.28,
  },
  rotationSpeed: {
    idle:      0.20,
    listening: 0.30,
    thinking:  0.90,
    speaking:  0.45,
  },
  noiseSpeed: {
    idle:      0.38,
    listening: 0.55,
    thinking:  1.4,
    speaking:  0.80,
  },
  noiseStrength: {
    idle:      0.05,
    listening: 0.09,
    thinking:  0.15,
    speaking:  0.11,
  },
  arcSpread: {
    idle:      0.25,
    listening: 0.80,
    thinking:  0.45,
    speaking:  0.95,
  },
};

function buildRingGeometry(radius: number, segments: number): THREE.BufferGeometry {
  const geo = new THREE.BufferGeometry();
  const positions = new Float32Array(segments * 3);
  const progress   = new Float32Array(segments);

  for (let i = 0; i < segments; i++) {
    const t     = i / segments;
    const angle = t * Math.PI * 2;
    positions[i * 3]     = Math.cos(angle) * radius;
    positions[i * 3 + 1] = 0;
    positions[i * 3 + 2] = Math.sin(angle) * radius;
    progress[i] = t;
  }

  geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geo.setAttribute("aProgress", new THREE.BufferAttribute(progress, 1));
  return geo;
}

function buildSatelliteNodes(
  radius: number,
  count: number,
  color: THREE.Color,
  nodeRadius: number = 0.025
): THREE.Mesh[] {
  const nodes: THREE.Mesh[] = [];
  const geo = new THREE.SphereGeometry(nodeRadius, 8, 8);
  for (let i = 0; i < count; i++) {
    const t     = i / count;
    const angle = t * Math.PI * 2;
    const mat = new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: 0.9,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(Math.cos(angle) * radius, 0, Math.sin(angle) * radius);
    nodes.push(mesh);
  }
  return nodes;
}

export interface HUDSceneHandles {
  update: (delta: number, state: AIOrbState, audioLevel: number) => void;
  dispose: () => void;
  composer: EffectComposer;
}

export function createOrbitalHUDScene(
  container: HTMLDivElement,
  width: number,
  height: number,
  cfg: AIOrbConfig,
  isMobile: boolean,
  prefersReducedMotion: boolean
): HUDSceneHandles {
  const particleTotal = isMobile ? cfg.particleCountMobile : cfg.particleCount;

  const scene  = new THREE.Scene();
  scene.background = new THREE.Color(0x000000);

  const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
  camera.position.z = 8.0;

  const renderer = new THREE.WebGLRenderer({
    powerPreference: "high-performance",
    antialias:       false,
    alpha:           false,
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(width, height);
  renderer.toneMapping         = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  container.appendChild(renderer.domElement);

  const composer   = new EffectComposer(renderer);
  const renderPass = new RenderPass(scene, camera);
  composer.addPass(renderPass);

  const bloomPass = new UnrealBloomPass(
    new THREE.Vector2(width, height),
    cfg.bloom.strength,
    cfg.bloom.radius,
    cfg.bloom.threshold
  );
  composer.addPass(bloomPass);

  const geoSphere = new THREE.BufferGeometry();
  const positions  = new Float32Array(particleTotal * 3);
  const randoms    = new Float32Array(particleTotal);
  const layers     = new Float32Array(particleTotal);

  const phi = Math.PI * (1 + Math.sqrt(5)); // razão áurea

  for (let i = 0; i < particleTotal; i++) {
    const y    = 1 - (i / (particleTotal - 1)) * 2;
    const rAtY = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = phi * i;
    const x = Math.cos(theta) * rAtY;
    const z = Math.sin(theta) * rAtY;

    const isInner = i % 6 === 0;
    const r = isInner ? cfg.radius * (0.65 + Math.random() * 0.25) : cfg.radius;

    positions[i * 3]     = x * r;
    positions[i * 3 + 1] = y * r;
    positions[i * 3 + 2] = z * r;

    randoms[i] = Math.random();
    layers[i]  = isInner ? 1.0 : 0.0;
  }

  geoSphere.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geoSphere.setAttribute("aRandom",  new THREE.BufferAttribute(randoms, 1));
  geoSphere.setAttribute("aLayer",   new THREE.BufferAttribute(layers, 1));

  const uniforms = {
    uTime:         { value: 0 },
    uNoiseSpeed:   { value: cfg.noiseSpeed.idle },
    uNoiseStrength:{ value: cfg.noiseStrength.idle },
    uAudioLevel:   { value: 0.0 },
    uPointSize:    { value: cfg.basePointSize },
    uArcSpread:    { value: cfg.arcSpread.idle },
    uLightAngle:   { value: 0.0 },
    uAccentMix:    { value: 0.0 },
    uColorCore:    { value: new THREE.Color(cfg.colors.magenta) },
    uColorMid:     { value: new THREE.Color(cfg.colors.violet) },
    uColorOuter:   { value: new THREE.Color(cfg.colors.royalBlue) },
    uColorFlare:   { value: new THREE.Color(cfg.colors.hotspot) },
    uColorAccent:  { value: new THREE.Color(cfg.colors.royalBlue) },
  };

  const matSphere = new THREE.ShaderMaterial({
    vertexShader:   hudVertexShader,
    fragmentShader: hudFragmentShader,
    uniforms,
    transparent:    true,
    depthWrite:     false,
    blending:       THREE.AdditiveBlending,
  });

  const spherePoints = new THREE.Points(geoSphere, matSphere);
  scene.add(spherePoints);

  const ringColors = {
    outer: new THREE.Color(cfg.colors.royalBlue),   // anel externo: azul/ciano
    mid:   new THREE.Color(cfg.colors.violet),       // anel médio: violeta
    inner: new THREE.Color(cfg.colors.magenta),      // anel interno: magenta
  };

  interface RingDef {
    radius:     number;
    tilt:       { x: number; y: number; z: number };
    color:      THREE.Color;
    rotAxis:    THREE.Vector3;
    rotSpeed:   number;
    dashLen:    number;
    gapLen:     number;
    segments:   number;
    nodes:      number;
    lineWidth:  number;
    opacity:    number;
  }

  const ringDefs: RingDef[] = [
    {
      radius:   1.78,
      tilt:     { x: 0.44, y: 0.0, z: 0.18 },
      color:    ringColors.outer,
      rotAxis:  new THREE.Vector3(0.3, 1.0, 0.2).normalize(),
      rotSpeed: 0.14,
      dashLen:  0.12,
      gapLen:   0.06,
      segments: 512,
      nodes:    4,
      lineWidth:1,
      opacity:  0.75,
    },
    {
      radius:   1.52,
      tilt:     { x: -0.28, y: 0.15, z: 0.55 },
      color:    ringColors.mid,
      rotAxis:  new THREE.Vector3(-0.2, 0.8, 0.5).normalize(),
      rotSpeed: 0.22,
      dashLen:  0.08,
      gapLen:   0.04,
      segments: 384,
      nodes:    3,
      lineWidth:1,
      opacity:  0.65,
    },
    {
      radius:   1.34,
      tilt:     { x: 0.70, y: -0.10, z: 0.30 },
      color:    ringColors.inner,
      rotAxis:  new THREE.Vector3(0.1, -0.6, 0.8).normalize(),
      rotSpeed: 0.35,
      dashLen:  0.05,
      gapLen:   0.025,
      segments: 256,
      nodes:    2,
      lineWidth:1,
      opacity:  0.55,
    },
  ];

  interface RingInstance {
    group:     THREE.Group;
    material:  THREE.LineLoop["material"];
    uniforms:  Record<string, { value: any }>;
    rotAxis:   THREE.Vector3;
    rotSpeed:  number;
    nodeObjs:  THREE.Mesh[];
    nodeAngles: number[];
    ringRadius: number;
  }

  const rings: RingInstance[] = ringDefs.map((def) => {
    const ringUniforms = {
      uRingColor: { value: def.color.clone() },
      uAlpha:     { value: def.opacity },
      uDashLen:   { value: def.dashLen },
      uGapLen:    { value: def.gapLen },
      uOffset:    { value: 0.0 },
      uAudioLevel:{ value: 0.0 },
    };

    const ringMat = new THREE.ShaderMaterial({
      uniforms:       ringUniforms,
      vertexShader:   `
        attribute float aProgress;
        varying float vProgress;
        void main() {
          vProgress = aProgress;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform vec3  uRingColor;
        uniform float uAlpha;
        uniform float uDashLen;
        uniform float uGapLen;
        uniform float uOffset;
        uniform float uAudioLevel;
        varying float vProgress;

        void main() {
          float period = uDashLen + uGapLen;
          float pos    = mod(vProgress + uOffset, period);
          if (pos > uDashLen) discard;

          float edgeFade = smoothstep(0.0, 0.1, pos / uDashLen) *
                           smoothstep(1.0, 0.9, pos / uDashLen);
          float glow = 0.65 + edgeFade * 0.45 + uAudioLevel * 0.35;
          gl_FragColor = vec4(uRingColor * glow, uAlpha * (0.65 + edgeFade * 0.35));
        }
      `,
      transparent:  true,
      depthWrite:   false,
      blending:     THREE.AdditiveBlending,
    });

    const ringGeo = buildRingGeometry(def.radius, def.segments);
    const lineLoop = new THREE.LineLoop(ringGeo, ringMat);

    const group = new THREE.Group();
    group.rotation.x = def.tilt.x;
    group.rotation.y = def.tilt.y;
    group.rotation.z = def.tilt.z;
    group.add(lineLoop);

    const nodeObjs = buildSatelliteNodes(def.radius, def.nodes, def.color, 0.028);
    const nodeAngles: number[] = [];
    nodeObjs.forEach((node, idx) => {
      const initAngle = (idx / def.nodes) * Math.PI * 2;
      nodeAngles.push(initAngle);
      group.add(node);
    });

    scene.add(group);

    return {
      group,
      material:   ringMat,
      uniforms:   ringUniforms,
      rotAxis:    def.rotAxis,
      rotSpeed:   def.rotSpeed,
      nodeObjs,
      nodeAngles,
      ringRadius: def.radius,
    };
  });

  const animState = {
    currentRotSpeed:    cfg.rotationSpeed.idle,
    currentNoiseSpeed:  cfg.noiseSpeed.idle,
    currentNoiseStrength: cfg.noiseStrength.idle,
    currentAudioLevel:  0.0,
    currentAccentMix:   0.0,
    currentAccentColor: new THREE.Color(cfg.colors.royalBlue),
    targetAccentColor:  new THREE.Color(cfg.colors.royalBlue),
    lightAngleAcc:      0.0,
  };

  const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

  const resizeObserver = new ResizeObserver((entries) => {
    for (const entry of entries) {
      const w = Math.max(10, Math.floor(entry.contentRect.width));
      const h = Math.max(10, Math.floor(entry.contentRect.height));
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      composer.setSize(w, h);
      bloomPass.setSize(w, h);
    }
  });
  resizeObserver.observe(container);

  function update(delta: number, state: AIOrbState, audioLevel: number): void {
    const lerpSpeed = Math.min(delta * 5.0, 1.0);

    const targetRotSpeed     = prefersReducedMotion ? 0.04 : cfg.rotationSpeed[state] ?? 0.20;
    const targetNoiseSpeed   = prefersReducedMotion ? 0.08 : cfg.noiseSpeed[state]    ?? 0.38;
    const targetNoiseStr     = prefersReducedMotion ? 0.02 : cfg.noiseStrength[state]  ?? 0.05;
    const targetAccentMix    = (state === "thinking" || state === "speaking") ? 0.70 : 0.0;

    if (state === "thinking")        animState.targetAccentColor.set(cfg.colors.thinkingBlue);
    else if (state === "speaking")   animState.targetAccentColor.set(cfg.colors.speakingMagenta);
    else if (state === "listening")  animState.targetAccentColor.set(cfg.colors.royalBlue);
    else                             animState.targetAccentColor.set(cfg.colors.violet);

    animState.currentRotSpeed      = lerp(animState.currentRotSpeed, targetRotSpeed, lerpSpeed);
    animState.currentNoiseSpeed    = lerp(animState.currentNoiseSpeed, targetNoiseSpeed, lerpSpeed);
    animState.currentNoiseStrength = lerp(animState.currentNoiseStrength, targetNoiseStr, lerpSpeed);
    animState.currentAudioLevel    = lerp(animState.currentAudioLevel, audioLevel, Math.min(delta * 12, 1));
    animState.currentAccentMix     = lerp(animState.currentAccentMix, targetAccentMix, lerpSpeed);
    animState.currentAccentColor.lerp(animState.targetAccentColor, lerpSpeed);

    uniforms.uTime.value         += delta;
    uniforms.uNoiseSpeed.value    = animState.currentNoiseSpeed;
    uniforms.uNoiseStrength.value = animState.currentNoiseStrength;
    uniforms.uAudioLevel.value    = animState.currentAudioLevel;
    uniforms.uAccentMix.value     = animState.currentAccentMix;
    uniforms.uColorAccent.value.copy(animState.currentAccentColor);

    animState.lightAngleAcc += delta * (animState.currentRotSpeed * 1.3 + animState.currentAudioLevel * 0.4);
    uniforms.uLightAngle.value = animState.lightAngleAcc;

    if (!prefersReducedMotion) {
      spherePoints.rotation.y += delta * animState.currentRotSpeed * 0.55;
      spherePoints.rotation.x  = Math.sin(uniforms.uTime.value * 0.32) * 0.10;
      spherePoints.rotation.z  = Math.cos(uniforms.uTime.value * 0.22) * 0.08;
    }

    rings.forEach((ring, rIdx) => {
      const baseSpeed = ringDefs[rIdx].rotSpeed;
      const speed = baseSpeed * (1.0 + animState.currentAudioLevel * 0.6);

      if (!prefersReducedMotion) {
        ring.group.rotateOnAxis(ring.rotAxis, delta * speed * 0.65);
      }

      ring.uniforms.uOffset.value = (ring.uniforms.uOffset.value + delta * speed * 0.12) % 1.0;
      ring.uniforms.uAudioLevel.value = animState.currentAudioLevel;

      const baseOpacity = ringDefs[rIdx].opacity;
      const pulse = (state === "speaking" || state === "thinking")
        ? baseOpacity * (0.85 + 0.2 * Math.sin(uniforms.uTime.value * 3.5 + rIdx * 1.2))
        : baseOpacity;
      ring.uniforms.uAlpha.value = pulse;

      ring.nodeAngles.forEach((angle, nIdx) => {
        const newAngle = angle + delta * speed * ringDefs[rIdx].rotSpeed * 0.9;
        ring.nodeAngles[nIdx] = newAngle;
        const r = ring.ringRadius;
        ring.nodeObjs[nIdx].position.set(
          Math.cos(newAngle) * r,
          0,
          Math.sin(newAngle) * r
        );
      });
    });

    composer.render();
  }

  function dispose(): void {
    resizeObserver.disconnect();
    geoSphere.dispose();
    matSphere.dispose();
    rings.forEach((ring) => {
      ring.group.traverse((child) => {
        if ((child as THREE.Mesh).geometry) (child as THREE.Mesh).geometry.dispose();
        if ((child as THREE.Mesh).material)
          ((child as THREE.Mesh).material as THREE.Material).dispose();
      });
    });
    renderer.dispose();
    composer.dispose();
    if (renderer.domElement.parentNode === container) {
      container.removeChild(renderer.domElement);
    }
  }

  return { update, dispose, composer };
}
