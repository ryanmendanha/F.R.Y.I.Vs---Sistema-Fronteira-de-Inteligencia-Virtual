/**
 * Captura de voz no navegador (MediaRecorder + VAD de silêncio) e
 * Detector WebAudio de Duas Palmas (Clap on Jarvis) para F.R.Y.I.Vs Web Mode.
 */

let activeStopFn: (() => void) | null = null;

export function isBrowserRecording(): boolean {
  return activeStopFn !== null;
}

export function stopActiveBrowserRecording(): void {
  if (activeStopFn) {
    const fn = activeStopFn;
    activeStopFn = null;
    fn();
  }
}

function pickSupportedAudioMime(): string {
  if (typeof MediaRecorder === "undefined") return "";
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
  for (const m of candidates) {
    try {
      if (MediaRecorder.isTypeSupported(m)) return m;
    } catch {
      // ignore
    }
  }
  return "";
}

export async function recordBrowserUtterance(options?: {
  maxDurationMs?: number;
  silenceHoldMs?: number;
  onLevel?: (level: number) => void;
}): Promise<Blob | null> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Seu navegador não suporta captura de microfone (exige HTTPS ou localhost).");
  }

  const maxDurationMs = options?.maxDurationMs ?? 9000;
  const silenceHoldMs = options?.silenceHoldMs ?? 1150;

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  const mimeType = pickSupportedAudioMime();
  const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
  const chunks: BlobPart[] = [];

  const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const ctx = new AudioCtx();
  const source = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  source.connect(analyser);
  const timeBuf = new Float32Array(analyser.fftSize);

  return new Promise<Blob | null>((resolve) => {
    let settled = false;
    let speechStarted = false;
    let silenceSince = 0;
    let rafId = 0;
    const startedAt = performance.now();

    const cleanup = () => {
      activeStopFn = null;
      if (rafId) cancelAnimationFrame(rafId);
      try {
        source.disconnect();
      } catch {}
      try {
        void ctx.close();
      } catch {}
      stream.getTracks().forEach((t) => t.stop());
    };

    const finish = () => {
      if (settled) return;
      settled = true;
      if (recorder.state !== "inactive") {
        try {
          recorder.stop();
        } catch {
          cleanup();
          resolve(null);
        }
      } else {
        cleanup();
        resolve(null);
      }
    };

    activeStopFn = finish;

    recorder.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) chunks.push(ev.data);
    };

    recorder.onstop = () => {
      const finalMime = recorder.mimeType || mimeType || "audio/webm";
      cleanup();
      if (chunks.length === 0) {
        resolve(null);
        return;
      }
      resolve(new Blob(chunks, { type: finalMime }));
    };

    const monitorVad = () => {
      if (settled) return;
      analyser.getFloatTimeDomainData(timeBuf);
      let sumSq = 0;
      for (let i = 0; i < timeBuf.length; i++) {
        sumSq += timeBuf[i] * timeBuf[i];
      }
      const rms = Math.sqrt(sumSq / timeBuf.length);
      options?.onLevel?.(Math.min(1, rms * 5.5));

      const now = performance.now();
      if (rms > 0.024) {
        speechStarted = true;
        silenceSince = 0;
      } else if (speechStarted) {
        if (!silenceSince) silenceSince = now;
        else if (now - silenceSince >= silenceHoldMs) {
          finish();
          return;
        }
      }

      if (now - startedAt >= maxDurationMs) {
        finish();
        return;
      }
      rafId = requestAnimationFrame(monitorVad);
    };

    recorder.start(200);
    rafId = requestAnimationFrame(monitorVad);
  });
}

/**
 * Wake word "FRYIVS" no navegador (Web Speech API contínua, pt-BR).
 * Detecta o nome da IA e, se vier um comando junto ("Fryivs, que horas são?"),
 * entrega o comando direto; se vier só o nome, pede para abrir a escuta.
 */
const WAKE_RE =
  /\b(fr?[aey]?[iy]+v[iy]?e?s|fra[iy]+v[ei]?s|fryivs|fryvis|frives|fraives|frayvis|fraivis|prays|praise|frei\s?vis|fry\s?vis|fly\s?vis)\b/i;

export function isWakeWordSupported(): boolean {
  const w = window as unknown as Record<string, unknown>;
  return Boolean(w.SpeechRecognition || w.webkitSpeechRecognition);
}

export class BrowserWakeWordListener {
  private recog: any = null;
  private running = false;
  private suppressed = false;
  private restartTimer: ReturnType<typeof setTimeout> | null = null;
  private lastFireAt = 0;

  start(onWake: (commandAfterWake: string) => void): boolean {
    const w = window as unknown as Record<string, any>;
    const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Ctor) return false;
    this.running = true;
    const recog = new Ctor();
    recog.lang = "pt-BR";
    recog.continuous = true;
    recog.interimResults = false;
    recog.maxAlternatives = 3;

    recog.onresult = (ev: any) => {
      if (this.suppressed) return;
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const res = ev.results[i];
        if (!res.isFinal) continue;
        for (let a = 0; a < res.length; a++) {
          const txt: string = (res[a]?.transcript || "").trim();
          const m = txt.match(WAKE_RE);
          if (!m) continue;
          const now = Date.now();
          if (now - this.lastFireAt < 2500) return;
          this.lastFireAt = now;
          const rest = txt
            .slice((m.index ?? 0) + m[0].length)
            .replace(/^[\s,.!?:;-]+/, "")
            .trim();
          onWake(rest);
          return;
        }
      }
    };

    const scheduleRestart = () => {
      if (!this.running) return;
      if (this.restartTimer) clearTimeout(this.restartTimer);
      this.restartTimer = setTimeout(() => {
        if (!this.running || this.suppressed) return;
        try {
          recog.start();
        } catch {}
      }, 400);
    };
    recog.onend = scheduleRestart;
    recog.onerror = (e: any) => {
      if (e?.error === "not-allowed" || e?.error === "service-not-allowed") {
        this.running = false;
      }
    };

    this.recog = recog;
    try {
      recog.start();
    } catch {}
    return true;
  }

  setSuppressed(value: boolean): void {
    if (this.suppressed === value) return;
    this.suppressed = value;
    if (!this.recog) return;
    if (value) {
      try {
        this.recog.abort();
      } catch {}
    } else if (this.running) {
      try {
        this.recog.start();
      } catch {}
    }
  }

  stop(): void {
    this.running = false;
    if (this.restartTimer) clearTimeout(this.restartTimer);
    try {
      this.recog?.abort();
    } catch {}
    this.recog = null;
  }
}

export class BrowserClapMonitor {
  private stream: MediaStream | null = null;
  private ctx: AudioContext | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private clapTimes: number[] = [];
  private lastClapAt = 0;
  private lastTriggerAt = 0;
  private suppressed = false;
  private hotStreak = 0;

  async start(onDoubleClap: () => void): Promise<boolean> {
    if (this.timer) return true;
    if (!navigator.mediaDevices?.getUserMedia) return false;
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: false,
          autoGainControl: false,
        },
      });
      const AudioCtx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      this.ctx = new AudioCtx();
      const src = this.ctx.createMediaStreamSource(this.stream);
      const analyser = this.ctx.createAnalyser();
      analyser.fftSize = 512;
      src.connect(analyser);

      const timeData = new Float32Array(analyser.fftSize);
      const freqData = new Uint8Array(analyser.frequencyBinCount);
      const binHz = this.ctx.sampleRate / analyser.fftSize;
      const hfStartBin = Math.max(1, Math.floor(1400 / binHz));

      this.timer = setInterval(() => {
        if (this.suppressed || !this.ctx) return;
        if (this.ctx.state === "suspended") {
          this.ctx.resume().catch(() => {});
          return;
        }

        analyser.getFloatTimeDomainData(timeData);
        let peak = 0;
        let sumSq = 0;
        for (let i = 0; i < timeData.length; i++) {
          const a = Math.abs(timeData[i]);
          if (a > peak) peak = a;
          sumSq += a * a;
        }
        const rms = Math.sqrt(sumSq / timeData.length) + 1e-6;

        if (rms > 0.05) {
          this.hotStreak += 1;
        } else {
          this.hotStreak = 0;
        }
        // Rejeita fala contínua (> 120ms sustentados)
        if (this.hotStreak > 3) return;

        const now = performance.now() / 1000;
        if (now - this.lastTriggerAt < 2.6) return;
        if (peak < 0.14 || peak / rms < 2.9) {
          this.clapTimes = this.clapTimes.filter((t) => now - t <= 0.8);
          return;
        }

        analyser.getByteFrequencyData(freqData);
        let totalF = 0;
        let hf = 0;
        for (let i = 1; i < freqData.length; i++) {
          const e = freqData[i] * freqData[i];
          totalF += e;
          if (i >= hfStartBin) hf += e;
        }
        if (totalF <= 0 || hf / totalF < 0.18) return;

        if (now - this.lastClapAt < 0.14) return;
        this.lastClapAt = now;
        this.clapTimes = this.clapTimes.filter((t) => now - t <= 0.8);
        this.clapTimes.push(now);

        if (this.clapTimes.length >= 2) {
          const gap = this.clapTimes[this.clapTimes.length - 1] - this.clapTimes[this.clapTimes.length - 2];
          if (gap >= 0.14 && gap <= 0.8) {
            this.clapTimes = [];
            this.lastTriggerAt = now;
            onDoubleClap();
          }
        }
      }, 40);
      return true;
    } catch {
      this.stop();
      return false;
    }
  }

  setSuppressed(value: boolean): void {
    this.suppressed = value;
    if (value) this.clapTimes = [];
  }

  stop(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    try {
      void this.ctx?.close();
    } catch {}
    this.ctx = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.clapTimes = [];
  }
}

