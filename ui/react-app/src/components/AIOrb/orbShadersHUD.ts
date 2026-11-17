/**
 * Shaders GLSL para o modo visual "Orbital HUD" do componente AIOrb.
 *
 * Visual inspirado na segunda imagem de referência:
 * - Esfera densa de partículas neon magenta/violeta/ciano (star-core)
 * - Flare/hotspot branco quente na base inferior da esfera
 * - Anéis HUD orbitais concêntricos com segmentos e nós de telemetria
 * - Efeito Fresnel + Bloom forte para uma aparência sci-fi holográfica
 */

/* ──────────────────────────────────────────────────────────────────────
   VERTEX SHADER — Esfera densa de partículas com flare inferior
   ────────────────────────────────────────────────────────────────────── */
export const hudVertexShader = /* glsl */ `
  uniform float uTime;
  uniform float uNoiseSpeed;
  uniform float uNoiseStrength;
  uniform float uAudioLevel;
  uniform float uPointSize;
  uniform float uArcSpread;
  uniform float uLightAngle;
  uniform float uAccentMix;

  // Cores do gradiente neon (magenta -> violeta -> ciano)
  uniform vec3 uColorCore;       // #ff28d4 magenta intenso
  uniform vec3 uColorMid;        // #9d32ff violeta
  uniform vec3 uColorOuter;      // #38b2fc ciano/azul
  uniform vec3 uColorFlare;      // #ffffff branco quente (flare inferior)
  uniform vec3 uColorAccent;

  attribute float aRandom;
  attribute float aLayer;   // 0 = superfície, 1 = camada interna de partículas

  varying vec3 vColor;
  varying float vAlpha;

  // Simplex Noise 3D (otimizado)
  vec4 permute(vec4 x) { return mod(((x * 34.0) + 1.0) * x, 289.0); }
  vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

  float snoise(vec3 v) {
    const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
    vec3 i  = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);
    vec3 g = step(x0.yzx, x0.xyz);
    vec3 l = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);
    vec3 x1 = x0 - i1 + C.xxx;
    vec3 x2 = x0 - i2 + 2.0 * C.xxx;
    vec3 x3 = x0 - 1.0 + 3.0 * C.xxx;
    i = mod(i, 289.0);
    vec4 p = permute(permute(permute(
              i.z + vec4(0.0, i1.z, i2.z, 1.0))
            + i.y + vec4(0.0, i1.y, i2.y, 1.0))
            + i.x + vec4(0.0, i1.x, i2.x, 1.0));
    float n_ = 0.142857142857;
    vec3  ns = n_ * D.wyz - D.xzx;
    vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
    vec4 x_ = floor(j * ns.z);
    vec4 y_ = floor(j - 7.0 * x_);
    vec4 x = x_ * ns.x + ns.yyyy;
    vec4 y = y_ * ns.x + ns.yyyy;
    vec4 h = 1.0 - abs(x) - abs(y);
    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);
    vec4 s0 = floor(b0) * 2.0 + 1.0;
    vec4 s1 = floor(b1) * 2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));
    vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
    vec3 p0 = vec3(a0.xy, h.x);
    vec3 p1 = vec3(a0.zw, h.y);
    vec3 p2 = vec3(a1.xy, h.z);
    vec3 p3 = vec3(a1.zw, h.w);
    vec4 norm = taylorInvSqrt(vec4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
    p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
    vec4 m = max(0.6 - vec4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m * m, vec4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
  }

  void main() {
    vec3 norm = normalize(position);
    float timeVal = uTime * uNoiseSpeed;

    // Deformação procedural
    float n1 = snoise(norm * 1.8 + vec3(0.0, timeVal, 0.0));
    float n2 = snoise(norm * 3.5 - vec3(timeVal * 0.5, 0.0, timeVal * 0.3));
    float displacement = (n1 * 0.6 + n2 * 0.4) * (uNoiseStrength + uAudioLevel * 0.2);

    // Respiração suave
    float breath = sin(uTime * 1.8) * 0.025 + uAudioLevel * 0.07;
    vec3 pos = position * (1.0 + breath) + norm * displacement;

    vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
    gl_Position = projectionMatrix * mvPosition;

    // Fresnel / Rim para hollow center clássico
    vec3 eyeVec = normalize(-mvPosition.xyz);
    vec3 tNorm = normalize(normalMatrix * norm);
    float rim = pow(1.0 - abs(dot(tNorm, eyeVec)), 2.8);

    // ─── GRADIENTE DE COR: BASE (flare branco) → EQUADOR (magenta) → TOPO (ciano) ───
    // norm.y varia de -1 (base) a +1 (topo)
    float yNorm = norm.y * 0.5 + 0.5; // 0 = base, 1 = topo

    // Flare inferior: pontos perto da base ficam levemente mais quentes (reduzido)
    float flareFactor = smoothstep(0.18, 0.0, yNorm);

    // Gradiente principal: magenta (base) → violeta (meio) → ciano (topo)
    vec3 gradColor;
    if (yNorm < 0.5) {
      gradColor = mix(uColorCore, uColorMid, smoothstep(0.0, 0.5, yNorm));
    } else {
      gradColor = mix(uColorMid, uColorOuter, smoothstep(0.5, 1.0, yNorm));
    }

    // Aplica flare branco na base — intensidade reduzida
    gradColor = mix(gradColor, uColorFlare, flareFactor * 0.42);

    // Cor de estado (thinking=cyan, speaking=magenta pulsante)
    gradColor = mix(gradColor, uColorAccent, uAccentMix * 0.45);

    // Intensidade e tamanho das partículas
    float coreHollow = smoothstep(0.15, 0.85, rim);
    float alpha = coreHollow * (0.6 + flareFactor * 0.4) + 0.12;
    alpha *= (0.5 + uAudioLevel * 0.6);

    // Camada interna levemente mais tênue
    float layerFade = aLayer > 0.5 ? 0.35 : 1.0;

    vColor = gradColor * (0.9 + flareFactor * 0.28 + uAudioLevel * 0.25);
    vAlpha = clamp(alpha * layerFade, 0.0, 0.95);

    float pSize = uPointSize * (0.55 + rim * 0.65 + flareFactor * 0.25 + uAudioLevel * 0.35);
    if (aLayer > 0.5) pSize *= 0.6;
    gl_PointSize = clamp(pSize * (180.0 / -mvPosition.z), 0.8, 8.0);
  }
`;

/* ──────────────────────────────────────────────────────────────────────
   FRAGMENT SHADER — Pontos suaves circulares com brilho central
   ────────────────────────────────────────────────────────────────────── */
export const hudFragmentShader = /* glsl */ `
  varying vec3 vColor;
  varying float vAlpha;

  void main() {
    vec2 coord = gl_PointCoord - vec2(0.5);
    float d = dot(coord, coord);
    if (d > 0.25) discard;

    float dist = sqrt(d) * 2.0;
    // Core brilhante no centro + queda suave para as bordas
    float softCore = 1.0 - smoothstep(0.0, 0.6, dist);
    float softEdge = smoothstep(1.0, 0.05, dist);
    float soft = max(softCore * 1.4, softEdge);

    gl_FragColor = vec4(vColor, clamp(vAlpha * soft, 0.0, 1.0));
  }
`;

/* ──────────────────────────────────────────────────────────────────────
   SHADERS DOS ANÉIS ORBITAIS HUD (segmentos e nós de telemetria)
   ────────────────────────────────────────────────────────────────────── */

/** Vertex shader simples para as linhas dos anéis orbitais */
export const ringVertexShader = /* glsl */ `
  uniform float uTime;
  uniform float uAlpha;
  uniform float uAudioLevel;
  varying float vProgress;  // 0.0→1.0 ao longo do anel

  attribute float aProgress;

  void main() {
    vProgress = aProgress;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

/** Fragment shader para os anéis — suporte a dash pattern e glow */
export const ringFragmentShader = /* glsl */ `
  uniform vec3 uRingColor;
  uniform float uAlpha;
  uniform float uDashLen;   // comprimento normalizado do segmento ativo
  uniform float uGapLen;    // comprimento normalizado do gap
  uniform float uOffset;    // offset de animação (drive de rotação)
  uniform float uAudioLevel;

  varying float vProgress;

  void main() {
    // Padrão de dash: usa mod para criar segmentos interrompidos
    float period = uDashLen + uGapLen;
    float pos = mod(vProgress + uOffset, period);
    float onSegment = step(pos, uDashLen);

    if (onSegment < 0.5) discard;

    // Leve glow nas pontas do segmento (falloff)
    float edgeFade = smoothstep(0.0, 0.12, pos / uDashLen) *
                     smoothstep(1.0, 0.88, pos / uDashLen);

    float glow = 0.6 + edgeFade * 0.5 + uAudioLevel * 0.4;
    gl_FragColor = vec4(uRingColor * glow, uAlpha * (0.7 + edgeFade * 0.3));
  }
`;
