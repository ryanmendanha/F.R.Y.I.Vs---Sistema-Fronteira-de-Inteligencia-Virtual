/**
 * AIOrb.tsx — Componente principal do orbe holográfico da IA F.R.Y.I.Vs
 *
 * Suporta dois modelos visuais intercambiáveis:
 *   "orbital-hud"      → Novo: esfera densa + anéis orbitais HUD segmentados (default)
 *   "neural-fibonacci"  → Clássico: anel Fibonacci em partículas com shaders GLSL originais
 *
 * A troca de modelo destrói e recria o contexto Three.js completo de forma limpa.
 */

import React, { useEffect, useRef } from "react";
import * as THREE from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { orbVertexShader, orbFragmentShader } from "./orbShaders";
import { createOrbitalHUDScene, DEFAULT_HUD_CONFIG } from "./OrbitalHUDVisual";
import type { AIOrbProps, AIOrbConfig } from "./types";

// ─────────────────────────────────────────────────────────────────────────────
// CONFIGURAÇÃO PADRÃO — Modelo Neural Fibonacci (original)
// ─────────────────────────────────────────────────────────────────────────────
export const DEFAULT_ORB_CONFIG: AIOrbConfig = {
  particleCount:       10000,
  particleCountMobile: 5000,
  radius:              1.2,
  basePointSize:       2.2,
  colors: {
    royalBlue:       "#2a1fff",
    violet:          "#8a2be2",
    magenta:         "#ff2fd6",
    hotspot:         "#ffeaf7",
    thinkingBlue:    "#00d4ff",
    speakingMagenta: "#ff2a9d",
  },
  bloom: {
    strength:  0.9,
    radius:    0.5,
    threshold: 0.35,
  },
  rotationSpeed: {
    idle:      0.25,
    listening: 0.35,
    thinking:  1.1,
    speaking:  0.5,
  },
  noiseSpeed: {
    idle:      0.4,
    listening: 0.6,
    thinking:  1.6,
    speaking:  0.85,
  },
  noiseStrength: {
    idle:      0.05,
    listening: 0.1,
    thinking:  0.16,
    speaking:  0.12,
  },
  arcSpread: {
    idle:      0.25,
    listening: 0.85,
    thinking:  0.45,
    speaking:  0.95,
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// Componente React
// ─────────────────────────────────────────────────────────────────────────────
export const AIOrb: React.FC<AIOrbProps> = ({
  model     = "orbital-hud",
  state     = "idle",
  audioLevel = 0,
  className  = "",
  style      = {},
  orbConfig,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);

  // Mantém valores atuais acessíveis dentro do loop sem re-montar
  const statePropsRef = useRef({ state, audioLevel });
  useEffect(() => {
    statePropsRef.current = { state, audioLevel };
  }, [state, audioLevel]);

  // Re-cria o motor 3D sempre que `model` mudar
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const isMobile = window.innerWidth < 768;
    const width  = Math.max(10, container.clientWidth  || 400);
    const height = Math.max(10, container.clientHeight || 400);

    let animationFrameId: number;
    let isVisible = true;
    let lastTime  = performance.now();

    const onVisibilityChange = () => {
      isVisible = document.visibilityState === "visible";
      if (isVisible) lastTime = performance.now();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    // ──────────────────────────────────────────────────────────────────
    // MODO: ORBITAL HUD (novo visual — padrão)
    // ──────────────────────────────────────────────────────────────────
    if (model === "orbital-hud") {
      const mergedCfg: AIOrbConfig = {
        ...DEFAULT_HUD_CONFIG,
        ...(orbConfig ?? {}),
        colors:         { ...DEFAULT_HUD_CONFIG.colors,         ...(orbConfig?.colors         ?? {}) },
        bloom:          { ...DEFAULT_HUD_CONFIG.bloom,          ...(orbConfig?.bloom          ?? {}) },
        rotationSpeed:  { ...DEFAULT_HUD_CONFIG.rotationSpeed,  ...(orbConfig?.rotationSpeed  ?? {}) },
        noiseSpeed:     { ...DEFAULT_HUD_CONFIG.noiseSpeed,     ...(orbConfig?.noiseSpeed     ?? {}) },
        noiseStrength:  { ...DEFAULT_HUD_CONFIG.noiseStrength,  ...(orbConfig?.noiseStrength  ?? {}) },
        arcSpread:      { ...DEFAULT_HUD_CONFIG.arcSpread,      ...(orbConfig?.arcSpread      ?? {}) },
      };

      const hud = createOrbitalHUDScene(container, width, height, mergedCfg, isMobile, prefersReducedMotion);

      const animate = (currentTime: number) => {
        animationFrameId = requestAnimationFrame(animate);
        if (!isVisible) return;
        const delta = Math.min((currentTime - lastTime) / 1000, 0.1);
        lastTime = currentTime;
        const { state: curState, audioLevel: curAudio } = statePropsRef.current;
        hud.update(delta, curState, curAudio);
      };

      animationFrameId = requestAnimationFrame(animate);

      return () => {
        cancelAnimationFrame(animationFrameId);
        document.removeEventListener("visibilitychange", onVisibilityChange);
        hud.dispose();
      };
    }

    // ──────────────────────────────────────────────────────────────────
    // MODO: NEURAL FIBONACCI (modelo clássico original — personalizável)
    // ──────────────────────────────────────────────────────────────────
    const cfg: AIOrbConfig = {
      ...DEFAULT_ORB_CONFIG,
      ...(orbConfig ?? {}),
      colors:         { ...DEFAULT_ORB_CONFIG.colors,         ...(orbConfig?.colors         ?? {}) },
      bloom:          { ...DEFAULT_ORB_CONFIG.bloom,          ...(orbConfig?.bloom          ?? {}) },
      rotationSpeed:  { ...DEFAULT_ORB_CONFIG.rotationSpeed,  ...(orbConfig?.rotationSpeed  ?? {}) },
      noiseSpeed:     { ...DEFAULT_ORB_CONFIG.noiseSpeed,     ...(orbConfig?.noiseSpeed     ?? {}) },
      noiseStrength:  { ...DEFAULT_ORB_CONFIG.noiseStrength,  ...(orbConfig?.noiseStrength  ?? {}) },
      arcSpread:      { ...DEFAULT_ORB_CONFIG.arcSpread,      ...(orbConfig?.arcSpread      ?? {}) },
    };

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
    renderer.toneMappingExposure = 1.0;
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

    // Geometria Fibonacci
    const geometry  = new THREE.BufferGeometry();
    const positions2 = new Float32Array(particleTotal * 3);
    const randoms   = new Float32Array(particleTotal);
    const layers    = new Float32Array(particleTotal);

    const phiGolden = Math.PI * (1 + Math.sqrt(5));

    for (let i = 0; i < particleTotal; i++) {
      const y    = 1 - (i / (particleTotal - 1)) * 2;
      const rAtY = Math.sqrt(Math.max(0, 1 - y * y));
      const theta = phiGolden * i;
      const x = Math.cos(theta) * rAtY;
      const z = Math.sin(theta) * rAtY;
      const isInternalFilament = i % 7 === 0;
      const r = isInternalFilament ? cfg.radius * (0.7 + Math.random() * 0.2) : cfg.radius;
      positions2[i * 3]     = x * r;
      positions2[i * 3 + 1] = y * r;
      positions2[i * 3 + 2] = z * r;
      randoms[i] = Math.random();
      layers[i]  = isInternalFilament ? 1.0 : 0.0;
    }

    geometry.setAttribute("position", new THREE.BufferAttribute(positions2, 3));
    geometry.setAttribute("aRandom",  new THREE.BufferAttribute(randoms, 1));
    geometry.setAttribute("aLayer",   new THREE.BufferAttribute(layers, 1));

    const uniforms = {
      uTime:         { value: 0 },
      uNoiseSpeed:   { value: cfg.noiseSpeed.idle },
      uNoiseStrength:{ value: cfg.noiseStrength.idle },
      uAudioLevel:   { value: 0.0 },
      uArcSpread:    { value: cfg.arcSpread.idle },
      uLightAngle:   { value: 0.0 },
      uPointSize:    { value: cfg.basePointSize },
      uColorRoyalBlue:{ value: new THREE.Color(cfg.colors.royalBlue) },
      uColorViolet:  { value: new THREE.Color(cfg.colors.violet) },
      uColorMagenta: { value: new THREE.Color(cfg.colors.magenta) },
      uColorHotspot: { value: new THREE.Color(cfg.colors.hotspot) },
      uColorAccent:  { value: new THREE.Color(cfg.colors.royalBlue) },
      uAccentMix:    { value: 0.0 },
    };

    const material = new THREE.ShaderMaterial({
      vertexShader:   orbVertexShader,
      fragmentShader: orbFragmentShader,
      uniforms,
      transparent:    true,
      depthWrite:     false,
      blending:       THREE.AdditiveBlending,
    });

    const points = new THREE.Points(geometry, material);
    scene.add(points);

    // Estado animado com lerp (mantido do original)
    const animStateRef = {
      currentRotSpeed:      cfg.rotationSpeed.idle,
      currentNoiseSpeed:    cfg.noiseSpeed.idle,
      currentNoiseStrength: cfg.noiseStrength.idle,
      currentArcSpread:     cfg.arcSpread.idle,
      currentAccentMix:     0.0,
      currentAudioLevel:    0.0,
      targetAccentColor:    new THREE.Color(cfg.colors.royalBlue),
      currentAccentColor:   new THREE.Color(cfg.colors.royalBlue),
    };

    let lightAngleAcc = 0;
    const lerp = (s: number, e: number, f: number) => s + (e - s) * f;

    const animate = (currentTime: number) => {
      animationFrameId = requestAnimationFrame(animate);
      if (!isVisible) return;

      const delta = Math.min((currentTime - lastTime) / 1000, 0.1);
      lastTime = currentTime;

      const { state: curState, audioLevel: curAudio } = statePropsRef.current;
      const anim = animStateRef;

      const targetRotSpeed     = prefersReducedMotion ? 0.05 : cfg.rotationSpeed[curState] || 0.25;
      const targetNoiseSpeed   = prefersReducedMotion ? 0.1  : cfg.noiseSpeed[curState]    || 0.4;
      const targetNoiseStr     = prefersReducedMotion ? 0.03 : cfg.noiseStrength[curState]  || 0.05;
      const targetArcSpread    = cfg.arcSpread[curState] ?? 0.25;

      if (curState === "thinking")       anim.targetAccentColor.set(cfg.colors.thinkingBlue);
      else if (curState === "speaking")  anim.targetAccentColor.set(cfg.colors.speakingMagenta);
      else if (curState === "listening") anim.targetAccentColor.set(cfg.colors.royalBlue);
      else                               anim.targetAccentColor.set(cfg.colors.violet);

      const targetAccentMix = (curState === "thinking" || curState === "speaking") ? 0.75 : 0.0;
      const lerpSpeed = Math.min(delta * 5.0, 1.0);

      anim.currentRotSpeed      = lerp(anim.currentRotSpeed, targetRotSpeed, lerpSpeed);
      anim.currentNoiseSpeed    = lerp(anim.currentNoiseSpeed, targetNoiseSpeed, lerpSpeed);
      anim.currentNoiseStrength = lerp(anim.currentNoiseStrength, targetNoiseStr, lerpSpeed);
      anim.currentArcSpread     = lerp(anim.currentArcSpread, targetArcSpread, lerpSpeed);
      anim.currentAccentMix     = lerp(anim.currentAccentMix, targetAccentMix, lerpSpeed);
      anim.currentAudioLevel    = lerp(anim.currentAudioLevel, curAudio || 0, Math.min(delta * 12, 1));
      anim.currentAccentColor.lerp(anim.targetAccentColor, lerpSpeed);

      uniforms.uTime.value         += delta;
      uniforms.uNoiseSpeed.value    = anim.currentNoiseSpeed;
      uniforms.uNoiseStrength.value = anim.currentNoiseStrength;
      uniforms.uAudioLevel.value    = anim.currentAudioLevel;
      uniforms.uArcSpread.value     = anim.currentArcSpread;
      uniforms.uColorAccent.value.copy(anim.currentAccentColor);
      uniforms.uAccentMix.value     = anim.currentAccentMix;

      lightAngleAcc += delta * (anim.currentRotSpeed * 1.4 + anim.currentAudioLevel * 0.5);
      uniforms.uLightAngle.value = lightAngleAcc;

      if (!prefersReducedMotion) {
        points.rotation.y += delta * anim.currentRotSpeed * 0.6;
        points.rotation.x  = Math.sin(uniforms.uTime.value * 0.35) * 0.12;
        points.rotation.z  = Math.cos(uniforms.uTime.value * 0.25) * 0.10;
      }

      composer.render();
    };

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const newW = Math.max(10, Math.floor(entry.contentRect.width));
        const newH = Math.max(10, Math.floor(entry.contentRect.height));
        camera.aspect = newW / newH;
        camera.updateProjectionMatrix();
        renderer.setSize(newW, newH);
        composer.setSize(newW, newH);
        bloomPass.setSize(newW, newH);
      }
    });
    resizeObserver.observe(container);

    animationFrameId = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(animationFrameId);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      resizeObserver.disconnect();
      geometry.dispose();
      material.dispose();
      renderer.dispose();
      composer.dispose();
      if (renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [model]); // Re-montar apenas quando o modelo mudar

  return (
    <div
      ref={containerRef}
      className={`relative w-full h-full flex items-center justify-center overflow-hidden bg-black ${className}`}
      style={{
        minHeight: "250px",
        minWidth:  "250px",
        ...style,
      }}
    />
  );
};
