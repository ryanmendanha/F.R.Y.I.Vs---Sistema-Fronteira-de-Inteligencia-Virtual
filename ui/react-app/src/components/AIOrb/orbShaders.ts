/**
 * Shaders GLSL para o componente AIOrb.
 * Implementa ruído procedural Simplex 3D, deformação por áudio,
 * gradiente polar neon e cálculo de aro luminoso (rim/crescent light).
 */

export const orbVertexShader = /* glsl */ `
  uniform float uTime;
  uniform float uNoiseSpeed;
  uniform float uNoiseStrength;
  uniform float uAudioLevel;
  uniform float uArcSpread;      // 0.0 (crescente/parcial) a 1.0 (anel completo)
  uniform float uLightAngle;     // Rotação do ponto focal de luz
  uniform float uPointSize;
  uniform vec3 uColorRoyalBlue;
  uniform vec3 uColorViolet;
  uniform vec3 uColorMagenta;
  uniform vec3 uColorHotspot;
  uniform vec3 uColorAccent;     // Cor dinâmica de estado (ex: azul em thinking, magenta em speaking)
  uniform float uAccentMix;      // Peso da cor dinâmica

  attribute float aRandom;
  attribute float aLayer;        // 0.0 = superfície externa, 1.0 = filamentos internos

  varying vec3 vColor;
  varying float vAlpha;

  // --- Algoritmo Simplex Noise 3D em GLSL ---
  vec4 permute(vec4 x) { return mod(((x*34.0)+1.0)*x, 289.0); }
  vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

  float snoise(vec3 v) {
    const vec2 C = vec2(1.0/6.0, 1.0/3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);

    vec3 i  = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);

    vec3 g = step(x0.yzx, x0.xyz);
    vec3 l = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);

    vec3 x1 = x0 - i1 + 1.0 * C.xxx;
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

    vec4 x = x_ *ns.x + ns.yyyy;
    vec4 y = y_ *ns.x + ns.yyyy;
    vec4 h = 1.0 - abs(x) - abs(y);

    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);

    vec4 s0 = floor(b0)*2.0 + 1.0;
    vec4 s1 = floor(b1)*2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));

    vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww;

    vec3 p0 = vec3(a0.xy, h.x);
    vec3 p1 = vec3(a0.zw, h.y);
    vec3 p2 = vec3(a1.xy, h.z);
    vec3 p3 = vec3(a1.zw, h.w);

    vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2, p2), dot(p3,p3)));
    p0 *= norm.x;
    p1 *= norm.y;
    p2 *= norm.z;
    p3 *= norm.w;

    vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
  }

  void main() {
    vec3 pos = position;
    vec3 norm = normalize(position);

    // 1. Deformação por ruído Simplex (ondas na superfície e filamentos internos)
    float timeVal = uTime * uNoiseSpeed;
    float noiseFreq = 1.4 + aLayer * 1.0;
    float noise1 = snoise(norm * noiseFreq + vec3(0.0, timeVal, 0.0));
    float noise2 = snoise(norm * (noiseFreq * 2.2) - vec3(timeVal * 0.6, 0.0, timeVal * 0.4));
    
    float displacement = (noise1 * 0.65 + noise2 * 0.35) * (uNoiseStrength + uAudioLevel * 0.25);
    
    // Filamentos internos ondulando
    if (aLayer > 0.5) {
      displacement += sin(norm.y * 5.0 + timeVal * 2.0) * 0.06 * (1.0 + uAudioLevel * 1.5);
    }

    vec3 displacedPos = pos + norm * displacement;

    // Pulso suave de respiração (±3%)
    float breath = sin(uTime * 1.6) * 0.03 + uAudioLevel * 0.08;
    displacedPos *= (1.0 + breath);

    // 2. Projeção de posição para espaço da câmera
    vec4 mvPosition = modelViewMatrix * vec4(displacedPos, 1.0);
    gl_Position = projectionMatrix * mvPosition;

    // 3. Efeito Rim / Fresnel (centro escuro/vazio e anel luminoso perimetral)
    vec3 eyeVector = normalize(-mvPosition.xyz);
    vec3 transformedNormal = normalize(normalMatrix * norm);
    float rimFactor = 1.0 - abs(dot(transformedNormal, eyeVector));
    rimFactor = pow(rimFactor, 2.5); // Foco muito maior na borda externa

    // 4. Ângulo polar para cálculo do degradê circular e arco de luz
    float angle = atan(mvPosition.y, mvPosition.x);
    float normAngle = (angle + 3.14159265) / (2.0 * 3.14159265);

    // Gradiente de cores: Azul-Royal -> Violeta -> Magenta -> Azul-Royal
    vec3 gradColor;
    if (normAngle < 0.333) {
      float t = normAngle / 0.333;
      gradColor = mix(uColorRoyalBlue, uColorViolet, smoothstep(0.0, 1.0, t));
    } else if (normAngle < 0.666) {
      float t = (normAngle - 0.333) / 0.333;
      gradColor = mix(uColorViolet, uColorMagenta, smoothstep(0.0, 1.0, t));
    } else {
      float t = (normAngle - 0.666) / 0.334;
      gradColor = mix(uColorMagenta, uColorRoyalBlue, smoothstep(0.0, 1.0, t));
    }

    // 5. Arco Luminoso / Ponto Focal Rotativo (Crescente vs Anel Completo)
    float angleDiff = abs(mod(angle - uLightAngle + 3.14159265, 6.2831853) - 3.14159265);
    float arcIntensity = 1.0 - smoothstep(0.0, 3.14159265 * (1.0 - uArcSpread * 0.85), angleDiff);
    arcIntensity = mix(arcIntensity, 1.0, uArcSpread);

    // Hotspot sutil no topo do arco (branco quente/rosa)
    float hotspotGlow = pow(max(0.0, 1.0 - angleDiff / 0.9), 3.5) * (1.0 - uArcSpread * 0.5);
    gradColor = mix(gradColor, uColorHotspot, hotspotGlow * 0.8);

    // Mistura com cor temática do estado atual
    gradColor = mix(gradColor, uColorAccent, uAccentMix * 0.55);

    // 6. Transparência e Atenuação do Miolo
    // Garante que o interior fique bem escuro e apenas o contorno e filamentos apareçam
    float coreHollowness = smoothstep(0.25, 0.95, rimFactor);
    float filamentAlpha = aLayer > 0.5 ? 0.25 * (1.0 + uAudioLevel * 2.0) : 1.0;
    
    float alphaVal = (coreHollowness * 0.8 + 0.15 * arcIntensity) * filamentAlpha;
    alphaVal *= (0.4 + 0.5 * arcIntensity + uAudioLevel * 0.4);

    vColor = gradColor * (0.85 + hotspotGlow * 0.8 + uAudioLevel * 0.3);
    vAlpha = clamp(alphaVal * (0.15 + rimFactor * 0.85), 0.0, 0.85);

    // 7. Tamanho fino e delicado das partículas (evita o efeito 'estourado')
    float pSize = uPointSize * (0.7 + rimFactor * 0.7 + uAudioLevel * 0.4);
    if (aLayer > 0.5) pSize *= 0.65;
    // Escalonamento por profundidade controlado
    gl_PointSize = clamp(pSize * (160.0 / -mvPosition.z), 1.0, 7.0);
  }
`;

export const orbFragmentShader = /* glsl */ `
  varying vec3 vColor;
  varying float vAlpha;

  void main() {
    vec2 coord = gl_PointCoord - vec2(0.5);
    float distSq = dot(coord, coord);

    // Descarta fora do círculo
    if (distSq > 0.25) {
      discard;
    }

    // Suavização do ponto circular
    float dist = sqrt(distSq) * 2.0; // 0.0 no centro a 1.0 na borda
    float soft = smoothstep(1.0, 0.05, dist);

    gl_FragColor = vec4(vColor, vAlpha * soft);
  }
`;
