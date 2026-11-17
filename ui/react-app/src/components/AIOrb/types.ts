export type AIOrbState = "idle" | "listening" | "thinking" | "speaking";

export type AIOrbModel = "orbital-hud" | "neural-fibonacci";

export interface AIOrbColors {
  royalBlue: string;
  violet: string;
  magenta: string;
  hotspot: string;
  thinkingBlue: string;
  speakingMagenta: string;
}

export interface AIOrbConfig {
  particleCount: number;
  particleCountMobile: number;
  radius: number;
  basePointSize: number;
  colors: AIOrbColors;
  bloom: {
    strength: number;
    radius: number;
    threshold: number;
  };
  rotationSpeed: {
    idle: number;
    listening: number;
    thinking: number;
    speaking: number;
  };
  noiseSpeed: {
    idle: number;
    listening: number;
    thinking: number;
    speaking: number;
  };
  noiseStrength: {
    idle: number;
    listening: number;
    thinking: number;
    speaking: number;
  };
  arcSpread: {
    idle: number;      // 0.0 to 1.0 (partially open arc/crescent)
    listening: number; // expanded ring
    thinking: number;  // rotating dynamic crescent
    speaking: number;  // pulsating ring
  };
}

export interface AIOrbProps {
  model?: AIOrbModel;
  state?: AIOrbState;
  audioLevel?: number; // 0.0 to 1.0
  className?: string;
  style?: React.CSSProperties;
  enableAudioReaction?: boolean;
  orbConfig?: Partial<AIOrbConfig>;
}
