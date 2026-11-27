import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { Icons8Icon } from "@/components/Icons8Icon";
import type { HermesProfileName } from "@/components/AgentsControlPanel";

export interface OfficeJobSummary {
  job_id: string;
  profile: HermesProfileName;
  task: string;
  status: string;
  progress_pct: number;
  steps_completed: number;
  max_steps: number;
  kb_status?: string;
}

export interface OfficeExternalCommand {
  seq: number;
  action: string;
  profile?: HermesProfileName | null;
  activity?: string | null;
}

export interface AgentsOffice3DProps {
  jobs: OfficeJobSummary[];
  selectedProfile: HermesProfileName;
  onSelectProfile: (profile: HermesProfileName) => void;
  celebrationSignal: number;
  externalCommand?: OfficeExternalCommand | null;
}

type AgentVisualState = "idle" | "work" | "err";

interface AgentDef {
  key: HermesProfileName;
  short: "pes" | "org" | "ide" | "eng";
  name: string;
  tagline: string;
  color: number;
  hex: string;
  x: number;
  workSpeech: string;
  phrases: [string, string, string];
}

const AGENT_DEFS: AgentDef[] = [
  {
    key: "pesquisador",
    short: "pes",
    name: "Pesquisador",
    tagline: "Radar curioso: varre fontes externas com lupa e antena.",
    color: 0x3b82f6,
    hex: "#3b82f6",
    x: -4.8,
    workSpeech: "🔎 buscando fontes...",
    phrases: ["Achei uma fonte valiosa!", "Radar ligado 📡", "Pronto para indexar!"],
  },
  {
    key: "organizador",
    short: "org",
    name: "Organizador de Dados",
    tagline: "Metódico: classifica cubos, tabelas e documentos em ordem.",
    color: 0x10b981,
    hex: "#10b981",
    x: -1.6,
    workSpeech: "🗂 organizando dados...",
    phrases: ["Cada dado no seu lugar.", "Planilha estruturada ✔", "Tudo catalogado!"],
  },
  {
    key: "ideias",
    short: "ide",
    name: "Agente de Ideias",
    tagline: "Criativo: a lâmpada acende quando nasce uma evolução para a IA.",
    color: 0xa855f7,
    hex: "#a855f7",
    x: 1.6,
    workSpeech: "💡 gerando ideias...",
    phrases: ["E se criássemos essa skill?", "💡 Tive uma ideia!", "Evolução mapeada!"],
  },
  {
    key: "engenheiro",
    short: "eng",
    name: "Engenheiro",
    tagline: "Arquiteto: audita o grafo de código e sistemas em holograma 3D.",
    color: 0x06b6d4,
    hex: "#06b6d4",
    x: 4.8,
    workSpeech: "⚙ auditando código...",
    phrases: ["Grafo verificado ✔", "Zero gargalos no módulo!", "Arquitetura sólida 🔧"],
  },
];

const STATE_COLORS: Record<AgentVisualState, string> = {
  idle: "#64748b",
  work: "#22c55e",
  err: "#ef4444",
};

const SHORT_NAMES: Record<HermesProfileName, string> = {
  pesquisador: "Pesquisador",
  organizador: "Organizador",
  ideias: "Ideias",
  engenheiro: "Engenheiro",
};

let officeDoorSeenInSession = false;

export const AgentsOffice3D: React.FC<AgentsOffice3DProps> = ({
  jobs,
  selectedProfile,
  onSelectProfile,
  celebrationSignal,
  externalCommand,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const labelsContainerRef = useRef<HTMLDivElement>(null);
  const [doorPhase, setDoorPhase] = useState<"closed" | "opening" | "open">(() =>
    officeDoorSeenInSession ? "open" : "closed",
  );
  const [demoMode, setDemoMode] = useState(false);

  const jobsRef = useRef<OfficeJobSummary[]>(jobs);
  jobsRef.current = jobs;

  const selectedRef = useRef<HermesProfileName>(selectedProfile);
  selectedRef.current = selectedProfile;

  const onSelectRef = useRef(onSelectProfile);
  onSelectRef.current = onSelectProfile;

  const demoModeRef = useRef(demoMode);
  demoModeRef.current = demoMode;

  const sceneApiRef = useRef<{
    triggerParty: (seconds?: number, customMsg?: string) => void;
    welcomeWave: () => void;
    focusAgent: (profile: HermesProfileName) => void;
    forceActivity: (activity: string) => void;
    setDemoRandom: () => void;
  } | null>(null);

  // Abertura cinematográfica automática da porta validada via E2EE
  useEffect(() => {
    if (doorPhase === "open") {
      officeDoorSeenInSession = true;
      return;
    }
    if (doorPhase === "closed") {
      const t1 = window.setTimeout(() => setDoorPhase("opening"), 320);
      return () => window.clearTimeout(t1);
    }
    if (doorPhase === "opening") {
      const t2 = window.setTimeout(() => {
        officeDoorSeenInSession = true;
        setDoorPhase("open");
        sceneApiRef.current?.welcomeWave();
      }, 1250);
      return () => window.clearTimeout(t2);
    }
  }, [doorPhase]);

  // Celebração automática quando o usuário indexa conhecimento na Base da IA
  useEffect(() => {
    if (celebrationSignal > 0) {
      sceneApiRef.current?.triggerParty(7, "📚 Indexado na Base da IA!");
    }
  }, [celebrationSignal]);

  // Modo Demo opcional
  useEffect(() => {
    if (!demoMode) return;
    sceneApiRef.current?.setDemoRandom();
    const id = window.setInterval(() => {
      sceneApiRef.current?.setDemoRandom();
    }, 3200);
    return () => window.clearInterval(id);
  }, [demoMode]);

  useEffect(() => {
    const mountEl = containerRef.current;
    const labelsRoot = labelsContainerRef.current;
    if (!mountEl || !labelsRoot) return;

    const canvas = document.createElement("canvas");
    canvas.style.display = "block";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    canvas.style.touchAction = "none";
    mountEl.appendChild(canvas);

    const renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      powerPreference: "high-performance",
    });
    renderer.shadowMap.enabled = true;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

    const sc = new THREE.Scene();
    sc.background = new THREE.Color(0x0d1324);
    sc.fog = new THREE.Fog(0x0d1324, 22, 54);

    const cam = new THREE.PerspectiveCamera(48, 1, 0.1, 80);
    let th = officeDoorSeenInSession ? 0 : 1.05;
    let ph = 0.42;
    let rad = officeDoorSeenInSession ? 13.4 : 23.0;
    let rt = 13.4;
    let tth = 0;
    let tph = 0.42;
    let T = 0;

    const M = (c: number, e = 0, ei = 1) =>
      new THREE.MeshStandardMaterial({
        color: c,
        roughness: 0.58,
        metalness: 0.12,
        emissive: e,
        emissiveIntensity: ei,
      });

    const box = (
      w: number,
      h: number,
      d: number,
      m: THREE.Material,
      p: THREE.Object3D,
      x = 0,
      y = 0,
      z = 0,
    ) => {
      const o = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m);
      o.position.set(x, y, z);
      p.add(o);
      return o;
    };

    const makeTextSprite = (txt: string, col: string, s: number) => {
      const c = document.createElement("canvas");
      c.width = 64;
      c.height = 64;
      const x = c.getContext("2d")!;
      x.font = "bold 46px sans-serif";
      x.textAlign = "center";
      x.textBaseline = "middle";
      x.fillStyle = col;
      x.fillText(txt, 32, 34);
      const tex = new THREE.CanvasTexture(c);
      tex.colorSpace = THREE.SRGBColorSpace;
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true }));
      sp.scale.set(s, s, s);
      return sp;
    };

    // Iluminação calibrada para Three.js v0.186
    sc.add(new THREE.HemisphereLight(0xc7dbff, 0x232942, 1.85));
    const dl = new THREE.DirectionalLight(0xffffff, 2.1);
    dl.position.set(5, 11, 7);
    dl.castShadow = true;
    dl.shadow.camera.left = -13;
    dl.shadow.camera.right = 13;
    dl.shadow.camera.top = 9;
    dl.shadow.camera.bottom = -9;
    dl.shadow.mapSize.set(1024, 1024);
    sc.add(dl);

    const disco = new THREE.PointLight(0xff00ff, 0, 18, 0);
    disco.position.set(0, 4.2, 1);
    sc.add(disco);

    // Sala 21.6m x 12.6m para 4 estações confortáveis
    const fl = new THREE.Mesh(new THREE.PlaneGeometry(21.6, 12.6), M(0x252e4a));
    fl.rotation.x = -Math.PI / 2;
    fl.position.z = -0.1;
    fl.receiveShadow = true;
    sc.add(fl);

    box(21.6, 5.2, 0.2, M(0x1e2640), sc, 0, 2.6, -5.8);
    box(0.2, 5.2, 12.6, M(0x1a2138), sc, -10.8, 2.6, -0.1);
    box(0.2, 5.2, 12.6, M(0x1a2138), sc, 10.8, 2.6, -0.1);

    const rug = new THREE.Mesh(new THREE.PlaneGeometry(13.6, 2.4), M(0x312c56));
    rug.rotation.x = -Math.PI / 2;
    rug.position.set(0, 0.01, 1.9);
    sc.add(rug);

    // Planta
    const plant = new THREE.Group();
    box(0.42, 0.42, 0.42, M(0x6b4a2f), plant, 0, 0.21, 0);
    const lf = new THREE.Mesh(new THREE.SphereGeometry(0.48, 12, 10), M(0x22c55e));
    lf.position.y = 0.82;
    plant.add(lf);
    plant.position.set(8.3, 0, -1.5);
    sc.add(plant);

    // Relógio de parede
    const clk = new THREE.Mesh(
      new THREE.CircleGeometry(0.5, 24),
      new THREE.MeshBasicMaterial({ color: 0xf1f5f9 }),
    );
    clk.position.set(-7.6, 3.7, -5.68);
    sc.add(clk);
    const hand = new THREE.Group();
    hand.position.set(-7.6, 3.7, -5.66);
    box(0.04, 0.38, 0.02, M(0x111827), hand, 0, 0.19, 0);
    sc.add(hand);

    // Mesa de Ping-Pong
    const pt = new THREE.Group();
    pt.position.set(-6.9, 0, -3.5);
    box(2.4, 0.07, 1.3, M(0x15803d), pt, 0, 0.82, 0);
    box(2.4, 0.075, 0.03, M(0xffffff), pt, 0, 0.82, 0);
    [
      [-1, -0.5],
      [1, -0.5],
      [-1, 0.5],
      [1, 0.5],
    ].forEach((p) => box(0.06, 0.8, 0.06, M(0x222222), pt, p[0] * 1.1, 0.4, p[1] * 0.55));
    box(0.02, 0.17, 1.4, M(0xe2e8f0), pt, 0, 0.95, 0);
    sc.add(pt);

    const ball = new THREE.Mesh(
      new THREE.SphereGeometry(0.06, 10, 8),
      new THREE.MeshBasicMaterial({ color: 0xfff7e0 }),
    );
    ball.visible = false;
    sc.add(ball);

    // Sofá + TV Central
    const sf = new THREE.Group();
    sf.position.set(0, 0, -4.1);
    box(3.1, 0.45, 0.95, M(0x6d28d9), sf, 0, 0.25, 0);
    box(3.1, 0.9, 0.22, M(0x5b21b6), sf, 0, 0.7, 0.45);
    box(0.25, 0.7, 0.95, M(0x4c1d95), sf, -1.55, 0.45, 0);
    box(0.25, 0.7, 0.95, M(0x4c1d95), sf, 1.55, 0.45, 0);
    sc.add(sf);

    box(3.4, 1.95, 0.1, M(0x090d16), sc, 0, 2.35, -5.65);
    const tc = document.createElement("canvas");
    tc.width = 256;
    tc.height = 144;
    const tx = tc.getContext("2d")!;
    const ttx = new THREE.CanvasTexture(tc);
    ttx.colorSpace = THREE.SRGBColorSpace;
    const tv = new THREE.Mesh(
      new THREE.PlaneGeometry(3.2, 1.75),
      new THREE.MeshBasicMaterial({ map: ttx }),
    );
    tv.position.set(0, 2.35, -5.58);
    sc.add(tv);

    interface AgentActor {
      d: AgentDef;
      i: number;
      k: "pes" | "org" | "ide" | "eng";
      state: AgentVisualState;
      progressPct: number;
      pendingReview: boolean;
      taskLabel: string;
      q: [number, number][];
      tr: number;
      ty: number;
      act: { type: string } | null;
      jump: number;
      hit: number;
      bbT: number;
      bo: boolean;
      waveT: number;
      wk: boolean;
      sq: number;
      hr: [number, number, number];
      hx: number;
      cv: HTMLCanvasElement;
      cx: CanvasRenderingContext2D;
      tex: THREE.CanvasTexture;
      g: THREE.Group;
      body: THREE.Mesh;
      legL: THREE.Mesh;
      legR: THREE.Mesh;
      head: THREE.Group;
      em: THREE.MeshBasicMaterial;
      eyes: THREE.Mesh[];
      mouth: THREE.Mesh;
      aL: THREE.Group;
      aR: THREE.Group;
      inst: THREE.Group;
      pad: THREE.Group;
      cup: THREE.Mesh;
      ctl: THREE.Mesh[];
      st: THREE.Mesh[];
      bc: THREE.Mesh;
      rl: THREE.PointLight;
      sm: THREE.Mesh[];
      ex: THREE.Sprite;
      okSp: THREE.Sprite;
      selRing: THREE.Mesh;
      dish?: THREE.Group;
      mag?: THREE.Group;
      glass?: THREE.Mesh;
      scan?: THREE.Mesh;
      cubes?: THREE.Mesh[];
      bulb?: THREE.Group;
      bm?: THREE.MeshStandardMaterial;
      bl?: THREE.PointLight;
      zs?: THREE.Sprite[];
      sp?: THREE.Mesh[];
      visor?: THREE.Mesh;
      holo?: THREE.Mesh;
      wrench?: THREE.Group;
      lb: HTMLDivElement;
      bb: HTMLDivElement;
    }

    const AG: AgentActor[] = [];

    AGENT_DEFS.forEach((d, i) => {
      const hx = d.x - 0.72;
      const dx = d.x + 0.62;

      // Estação de trabalho (Mesa + Monitor)
      const ds = new THREE.Group();
      box(1.65, 0.08, 0.8, M(0x4a3b2c), ds, 0, 0.9, 0);
      [
        [-0.72, -0.32],
        [0.72, -0.32],
        [-0.72, 0.32],
        [0.72, 0.32],
      ].forEach((p) => box(0.06, 0.9, 0.06, M(0x1f2937), ds, p[0], 0.45, p[1]));
      box(0.12, 0.25, 0.1, M(0x1f2937), ds, 0, 1.05, -0.1);
      box(1.12, 0.72, 0.06, M(0x0b1120), ds, 0, 1.5, -0.1);

      const cv = document.createElement("canvas");
      cv.width = 256;
      cv.height = 160;
      const cx = cv.getContext("2d")!;
      const tex = new THREE.CanvasTexture(cv);
      tex.colorSpace = THREE.SRGBColorSpace;
      const scr = new THREE.Mesh(
        new THREE.PlaneGeometry(1.02, 0.62),
        new THREE.MeshBasicMaterial({ map: tex }),
      );
      scr.position.set(0, 1.5, -0.065);
      ds.add(scr);
      ds.position.set(dx, 0, -0.5);
      sc.add(ds);

      // Personagem 3D em terno
      const g = new THREE.Group();
      const bm = M(d.color);
      const dk = M(0x1b2233);
      g.position.set(hx, 0, 0.2);
      g.rotation.y = 0.45;
      sc.add(g);

      const body = box(0.8, 0.85, 0.5, bm, g, 0, 0.95, 0);
      box(0.5, 0.12, 0.52, dk, body, 0, -0.2, 0);
      const legL = box(0.22, 0.5, 0.25, dk, g, -0.2, 0.25, 0);
      const legR = box(0.22, 0.5, 0.25, dk, g, 0.2, 0.25, 0);

      const head = new THREE.Group();
      head.position.set(0, 1.75, 0);
      g.add(head);
      box(0.62, 0.5, 0.5, bm, head, 0, 0, 0);

      const em = new THREE.MeshBasicMaterial({ color: 0x7dd3fc });
      const eyes = [-0.14, 0.14].map((xPos) => box(0.12, 0.12, 0.04, em, head, xPos, 0.04, 0.26));
      const mouth = box(
        0.2,
        0.05,
        0.03,
        new THREE.MeshBasicMaterial({ color: 0x0b1020 }),
        head,
        0,
        -0.13,
        0.26,
      );

      const mkArm = (side: number) => {
        const p = new THREE.Group();
        p.position.set(side * 0.55, 1.3, 0);
        box(0.18, 0.7, 0.18, bm, p, 0, -0.35, 0);
        g.add(p);
        return p;
      };
      const aL = mkArm(-1);
      const aR = mkArm(1);

      // Terno executivo + gravata da cor do agente
      const su = M(0x1f2937);
      const su2 = M(0x0f172a);
      const wh = M(0xf8fafc);
      box(0.86, 0.86, 0.54, su, body, 0, 0, 0);
      box(0.22, 0.8, 0.02, wh, body, 0, 0, 0.28);
      box(0.09, 0.55, 0.02, M(d.color), body, 0, -0.06, 0.29);
      [-1, 1].forEach((s) => {
        const lp = box(0.15, 0.5, 0.02, su2, body, s * 0.14, 0.12, 0.285);
        lp.rotation.z = -s * 0.35;
      });
      box(0.1, 0.07, 0.02, wh, body, 0.27, 0.2, 0.285);
      [aL, aR].forEach((p) => box(0.22, 0.52, 0.22, su, p, 0, -0.28, 0));
      [legL, legR].forEach((p) => box(0.25, 0.08, 0.32, M(0x050505), p, 0, -0.27, 0.04));

      // Anel de seleção no chão
      const selRing = new THREE.Mesh(
        new THREE.RingGeometry(0.58, 0.68, 32),
        new THREE.MeshBasicMaterial({
          color: d.color,
          transparent: true,
          opacity: 0.75,
          side: THREE.DoubleSide,
        }),
      );
      selRing.rotation.x = -Math.PI / 2;
      selRing.position.set(0, 0.025, 0);
      g.add(selRing);

      // Instrumentos da banda para os 4 agentes
      const inst = new THREE.Group();
      g.add(inst);
      inst.visible = false;
      if (d.short === "pes") {
        const gb = box(0.5, 0.4, 0.08, M(0xb45309), inst, 0.15, 0.9, 0.34);
        gb.rotation.z = 0.4;
        const nk = box(0.08, 0.8, 0.05, M(0x3b2a1a), inst, -0.3, 1.1, 0.36);
        nk.rotation.z = 1.2;
      } else if (d.short === "org") {
        box(1.0, 0.08, 0.4, M(0x111827), inst, 0, 0.85, 0.5);
        box(0.95, 0.02, 0.3, M(0xf8fafc), inst, 0, 0.9, 0.52);
        [-0.4, 0.4].forEach((xPos) => box(0.05, 0.8, 0.05, M(0x444444), inst, xPos, 0.42, 0.5));
      } else if (d.short === "ide") {
        box(0.03, 1.2, 0.03, M(0x444444), inst, 0, 0.7, 0.6);
        box(0.3, 0.03, 0.3, M(0x222222), inst, 0, 0.02, 0.6);
        const mc = new THREE.Mesh(new THREE.SphereGeometry(0.06, 10, 8), M(0x111111));
        mc.position.set(0, 1.6, 0.55);
        inst.add(mc);
      } else if (d.short === "eng") {
        const drum = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.28, 0.24, 16), M(0x0891b2));
        drum.position.set(0, 0.72, 0.56);
        inst.add(drum);
        const topHead = new THREE.Mesh(new THREE.CylinderGeometry(0.27, 0.27, 0.02, 16), M(0xf8fafc));
        topHead.position.set(0, 0.85, 0.56);
        inst.add(topHead);
        box(0.04, 0.7, 0.04, M(0x475569), inst, 0, 0.36, 0.56);
        const cymb = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 0.015, 16), M(0xfacc15));
        cymb.position.set(0.34, 1.05, 0.52);
        cymb.rotation.z = -0.2;
        inst.add(cymb);
      }

      // Adereços compartilhados
      const pad = new THREE.Group();
      pad.position.set(0, -0.78, 0.12);
      aR.add(pad);
      const pd = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.17, 0.03, 16), M(0xdc2626));
      pd.rotation.z = Math.PI / 2;
      pd.position.y = -0.1;
      pad.add(pd);
      box(0.04, 0.18, 0.04, M(0x8b5a2b), pad, 0, 0.05, 0);
      pad.visible = false;

      const cup = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.06, 0.15, 10), M(0xffffff));
      cup.position.set(0, -0.78, 0.14);
      aR.add(cup);
      cup.visible = false;

      const ctl = [aL, aR].map((h) => box(0.22, 0.07, 0.12, M(0x111827), h, 0, -0.76, 0.1));
      ctl.forEach((o) => (o.visible = false));

      const st = [0, 1, 2].map(() => {
        const s = new THREE.Mesh(
          new THREE.SphereGeometry(0.05, 6, 6),
          new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.5 }),
        );
        s.visible = false;
        sc.add(s);
        return s;
      });

      const bc = new THREE.Mesh(
        new THREE.CylinderGeometry(0.08, 0.1, 0.14, 10),
        new THREE.MeshBasicMaterial({ color: 0xff2222 }),
      );
      bc.position.set(-0.22, 0.32, 0);
      head.add(bc);
      bc.visible = false;

      const rl = new THREE.PointLight(0xff2222, 0, 4.5, 0);
      head.add(rl);

      const sm: THREE.Mesh[] = [];
      for (let j = 0; j < 8; j++) {
        const s = new THREE.Mesh(
          new THREE.SphereGeometry(0.12, 8, 6),
          new THREE.MeshBasicMaterial({ color: 0x888c99, transparent: true, opacity: 0.5 }),
        );
        s.visible = false;
        sc.add(s);
        sm.push(s);
      }

      const ex = makeTextSprite("!", "#ff4444", 0.8);
      ex.visible = false;
      sc.add(ex);

      const okSp = makeTextSprite("★", "#34d399", 0.72);
      okSp.visible = false;
      sc.add(okSp);

      const lb = document.createElement("div");
      lb.className =
        "pointer-events-none absolute left-0 top-0 -translate-x-1/2 -translate-y-full rounded-full bg-[#090e1c]/90 border border-white/15 px-2.5 py-0.5 text-[11px] font-medium text-slate-100 whitespace-nowrap shadow-lg";
      labelsRoot.appendChild(lb);

      const bb = document.createElement("div");
      bb.className =
        "pointer-events-none absolute left-0 top-0 -translate-x-1/2 -translate-y-full rounded-xl bg-white text-slate-900 px-2.5 py-1 text-[11.5px] font-semibold whitespace-nowrap shadow-xl transition-opacity duration-200 opacity-0";
      labelsRoot.appendChild(bb);

      const actor: AgentActor = {
        d,
        i,
        k: d.short,
        state: "idle",
        progressPct: 0,
        pendingReview: false,
        taskLabel: "",
        q: [],
        tr: 0.45,
        ty: 0.45,
        act: null,
        jump: 0,
        hit: 0,
        bbT: 0,
        bo: false,
        waveT: 0,
        wk: false,
        sq: 0,
        hr: [0, 0, 0],
        hx,
        cv,
        cx,
        tex,
        g,
        body,
        legL,
        legR,
        head,
        em,
        eyes,
        mouth,
        aL,
        aR,
        inst,
        pad,
        cup,
        ctl,
        st,
        bc,
        rl,
        sm,
        ex,
        okSp,
        selRing,
        lb,
        bb,
      };

      // Adereços exclusivos de cada um dos 4 agentes
      if (d.short === "pes") {
        const dish = new THREE.Group();
        dish.position.set(0.1, 0.3, 0);
        head.add(dish);
        const cn = new THREE.Mesh(
          new THREE.ConeGeometry(0.3, 0.18, 16, 1, true),
          M(0xcbd5e1),
        );
        cn.rotation.x = Math.PI;
        cn.position.y = 0.22;
        dish.add(cn);
        box(0.04, 0.2, 0.04, dk, dish, 0, 0.1, 0);
        box(0.04, 0.12, 0.04, M(0xff5555), dish, 0.14, 0.34, 0);

        const mag = new THREE.Group();
        mag.position.set(0, -0.75, 0.12);
        aR.add(mag);
        const rg = new THREE.Mesh(new THREE.TorusGeometry(0.2, 0.035, 8, 20), M(0x1e293b));
        rg.position.y = -0.25;
        mag.add(rg);
        const glass = new THREE.Mesh(
          new THREE.CircleGeometry(0.19, 20),
          new THREE.MeshBasicMaterial({ color: 0x93c5fd, transparent: true, opacity: 0.38 }),
        );
        glass.position.y = -0.25;
        mag.add(glass);
        box(0.04, 0.28, 0.04, dk, mag, 0, -0.05, 0);

        const scan = new THREE.Mesh(
          new THREE.RingGeometry(0.2, 0.25, 28),
          new THREE.MeshBasicMaterial({
            color: 0x60a5fa,
            transparent: true,
            opacity: 0,
            side: THREE.DoubleSide,
          }),
        );
        scan.rotation.x = -Math.PI / 2;
        scan.position.set(hx, 0.03, 0.2);
        sc.add(scan);

        actor.dish = dish;
        actor.mag = mag;
        actor.glass = glass;
        actor.scan = scan;
      } else if (d.short === "org") {
        [0, 1, 2].forEach((j) =>
          box(0.38, 0.06, 0.38, M(0x475569), sc, hx - 0.48 + j * 0.48, 0.03, 1.3),
        );
        const cubes: THREE.Mesh[] = [];
        const cc = [0xef4444, 0x22c55e, 0x3b82f6];
        for (let j = 0; j < 6; j++) {
          const cb = new THREE.Mesh(
            new THREE.BoxGeometry(0.19, 0.19, 0.19),
            M(cc[j % 3], cc[j % 3], 0.25),
          );
          cb.position.set(hx - 0.48 + (j % 3) * 0.48, 0.16 + Math.floor(j / 3) * 0.21, 1.3);
          sc.add(cb);
          cubes.push(cb);
        }
        box(0.35, 0.45, 0.04, M(0xe2e8f0), aL, 0, -0.78, 0.1);
        actor.cubes = cubes;
      } else if (d.short === "ide") {
        const bulb = new THREE.Group();
        bulb.position.set(0, 0.8, 0);
        head.add(bulb);
        const bulbMat = M(0xfde047, 0xfacc15, 0.15);
        const bs = new THREE.Mesh(new THREE.SphereGeometry(0.22, 14, 12), bulbMat);
        bs.position.y = 0.15;
        bulb.add(bs);
        box(0.16, 0.12, 0.16, M(0x94a3b8), bulb, 0, -0.05, 0);
        const bl = new THREE.PointLight(0xfde047, 0, 5.5, 0);
        bl.position.y = 0.2;
        bulb.add(bl);
        box(0.03, 0.5, 0.03, M(0x94a3b8), head, 0, 0.38, 0);
        const zs = [0, 1, 2].map(() => {
          const s = makeTextSprite("Z", "#c4b5fd", 0.4);
          sc.add(s);
          return s;
        });
        const sp = [0, 1, 2, 3, 4, 5].map(() => {
          const s = new THREE.Mesh(
            new THREE.SphereGeometry(0.05, 6, 6),
            new THREE.MeshBasicMaterial({ color: 0xfde047 }),
          );
          s.visible = false;
          sc.add(s);
          return s;
        });
        actor.bulb = bulb;
        actor.bm = bulbMat;
        actor.bl = bl;
        actor.zs = zs;
        actor.sp = sp;
      } else if (d.short === "eng") {
        // Visor holográfico ciano + chave técnica + holograma 3D sobre a mesa
        const visor = box(
          0.54,
          0.14,
          0.06,
          new THREE.MeshBasicMaterial({ color: 0x22d3ee, transparent: true, opacity: 0.72 }),
          head,
          0,
          0.05,
          0.27,
        );
        const wrench = new THREE.Group();
        wrench.position.set(0, -0.76, 0.12);
        box(0.06, 0.34, 0.04, M(0xcbd5e1), wrench, 0, -0.06, 0);
        const jaw = new THREE.Mesh(new THREE.TorusGeometry(0.09, 0.028, 8, 14, Math.PI * 1.4), M(0x94a3b8));
        jaw.position.y = -0.24;
        wrench.add(jaw);
        aR.add(wrench);

        const holo = new THREE.Mesh(
          new THREE.OctahedronGeometry(0.28, 0),
          new THREE.MeshBasicMaterial({
            color: 0x22d3ee,
            wireframe: true,
            transparent: true,
            opacity: 0.85,
          }),
        );
        holo.position.set(dx, 1.38, -0.1);
        sc.add(holo);

        actor.visor = visor;
        actor.wrench = wrench;
        actor.holo = holo;
      }

      AG.push(actor);
    });

    sc.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (
        mesh.isMesh &&
        mesh.geometry.type !== "PlaneGeometry" &&
        mesh.geometry.type !== "CircleGeometry" &&
        mesh.geometry.type !== "RingGeometry"
      ) {
        mesh.castShadow = true;
      }
    });

    // Partículas de luz, luminárias, letreiro neon, drone e confetes
    const dustGeo = new THREE.BufferGeometry();
    const dustArr = new Float32Array(130 * 3);
    for (let i = 0; i < 130; i++) {
      dustArr[i * 3] = (Math.random() - 0.5) * 19;
      dustArr[i * 3 + 1] = Math.random() * 4.6;
      dustArr[i * 3 + 2] = (Math.random() - 0.5) * 10.5;
    }
    dustGeo.setAttribute("position", new THREE.BufferAttribute(dustArr, 3));
    const dust = new THREE.Points(
      dustGeo,
      new THREE.PointsMaterial({ color: 0xfff3c4, size: 0.05, transparent: true, opacity: 0.55 }),
    );
    sc.add(dust);

    const lamps = [-4.8, -1.6, 1.6, 4.8].map((xPos) => {
      const g = new THREE.Group();
      g.position.set(xPos + 0.5, 5.0, -0.5);
      box(0.02, 1.0, 0.02, M(0x334155), g, 0, -0.5, 0);
      const sh = new THREE.Mesh(new THREE.ConeGeometry(0.35, 0.3, 14, 1, true), M(0xe2e8f0));
      (sh.material as THREE.MeshStandardMaterial).side = THREE.DoubleSide;
      sh.position.y = -1.0;
      g.add(sh);
      const bl = new THREE.Mesh(
        new THREE.SphereGeometry(0.1, 8, 8),
        new THREE.MeshBasicMaterial({ color: 0xfff2b0 }),
      );
      bl.position.y = -1.05;
      g.add(bl);
      sc.add(g);
      return g;
    });

    const neon = box(3.2, 0.36, 0.05, M(0x111827, 0x22d3ee, 1.2), sc, 5.8, 4.3, -5.65);

    const drone = new THREE.Group();
    box(0.3, 0.24, 0.3, M(0xe2e8f0), drone, 0, 0, 0);
    const droneRotor = box(0.62, 0.02, 0.08, M(0x94a3b8), drone, 0, 0.19, 0);
    box(0.1, 0.1, 0.04, new THREE.MeshBasicMaterial({ color: 0x22d3ee }), drone, 0, 0, 0.17);
    sc.add(drone);

    const gl = new THREE.PointLight(0x8888ff, 0, 9, 0);
    gl.position.set(0, 2, -4.7);
    sc.add(gl);

    const conf = Array.from({ length: 55 }, () => {
      const c = new THREE.Mesh(
        new THREE.BoxGeometry(0.08, 0.02, 0.12),
        new THREE.MeshBasicMaterial({
          color: new THREE.Color().setHSL(Math.random(), 0.9, 0.6),
        }),
      );
      c.position.set((Math.random() - 0.5) * 18, Math.random() * 5, -4 + Math.random() * 8);
      c.userData.v = 0.6 + Math.random();
      c.visible = false;
      sc.add(c);
      return c;
    });

    const say = (a: AgentActor, txt: string, dur = 2.8) => {
      a.bb.textContent = txt;
      a.bbT = T + dur;
    };

    const buildPath = (a: AgentActor, txPos: number, tzPos: number): [number, number][] => {
      const p = a.g.position;
      const cb = p.z < -1;
      const tb = tzPos < -1;
      const Q: [number, number][] = [];
      const inSofa = (x: number, z: number) => Math.abs(x) < 1.8 && z < -3.3;
      const ln = (tb ? txPos : p.x) > -2 ? 7.3 : -7.5;
      const sd = ln > 0 ? 2.2 : -2.2;

      if (cb) {
        if (inSofa(p.x, p.z)) Q.push([sd, p.z], [sd, -2.4]);
        else Q.push([p.x, -2.4]);
        Q.push([ln, -2.4]);
        if (!tb) {
          Q.push([ln, 1.9]);
          if (tzPos < 1.5) Q.push([txPos, 1.9]);
        }
      } else {
        if (p.z < 1.5) Q.push([p.x, 1.9]);
        if (tb) Q.push([ln, 1.9], [ln, -2.4]);
        else if (tzPos < 1.5) Q.push([txPos, 1.9]);
      }
      if (tb) {
        if (inSofa(txPos, tzPos)) Q.push([sd, -2.4], [sd, tzPos]);
        else Q.push([txPos, -2.4]);
      }
      Q.push([txPos, tzPos]);
      return Q;
    };

    const go = (a: AgentActor, txPos: number, tzPos: number, rot: number, act?: string) => {
      const p = a.g.position;
      a.act = act ? { type: act } : null;
      a.tr = rot;
      a.q = Math.hypot(p.x - txPos, p.z - tzPos) < 0.15 ? [] : buildPath(a, txPos, tzPos);
    };

    let sig = "";
    let nextPlan = 0;
    let forcedActivity: string | null = null;
    let pp: AgentActor[] | null = null;
    let cur: string | null = null;
    let party = 0;

    const plan = (force = false) => {
      const free = AG.filter((a) => a.state === "idle");
      const sg = free.map((a) => a.i).join(",");
      if (!force && sg === sig && T < nextPlan) return;
      sig = sg;
      nextPlan = T + 14 + Math.random() * 8;
      pp = null;
      cur = null;

      AG.forEach((a) => {
        if (a.state !== "idle") go(a, a.hx, 0.2, 0.45);
      });

      const n = free.length;
      if (!n) return;
      const r = Math.random();
      let ty =
        forcedActivity ||
        (n === 1
          ? r < 0.65
            ? "coffee"
            : r < 0.85
              ? "plant"
              : "dance"
          : n === 2
            ? r < 0.65
              ? "pingpong"
              : r < 0.85
                ? "chat"
                : "dance"
            : r < 0.35
              ? "game"
              : r < 0.72
                ? "band"
                : "conga");
      forcedActivity = null;
      if (party > T) {
        ty = "dance";
        nextPlan = party;
      }
      cur = ty;

      free.forEach((a, j) => {
        if (ty === "coffee") go(a, (j - (n - 1) / 2) * 0.7, -4.1, Math.PI, ty);
        else if (ty === "plant") go(a, 7.4, -1.0, 2.13, ty);
        else if (ty === "game") go(a, (j - (n - 1) / 2) * 0.78, -4.1, Math.PI, ty);
        else if (ty === "pingpong") {
          if (j < 2) go(a, j ? -5.2 : -8.6, -3.5, j ? -Math.PI / 2 : Math.PI / 2, ty);
          else go(a, -6.9 + (j - 2.5) * 0.8, -2.3, Math.PI, "chat");
        } else if (ty === "chat") {
          go(a, (j - (n - 1) / 2) * 1.2, 1.9, j % 2 ? -Math.PI / 2 : Math.PI / 2, ty);
        } else if (ty === "band") {
          go(a, (j - (n - 1) / 2) * 1.95, 2.05, 0, ty);
        } else if (ty === "conga") {
          const sxPos = -4.5 + (n - 1 - j) * 1.15;
          go(a, sxPos, 2.4, Math.PI / 2, ty);
          for (let k = 0; k < 3; k++) {
            a.q.push([4.8, 2.4], [4.8, 3.7], [-4.8, 3.7], [-4.8, 2.4]);
          }
        } else {
          go(a, (j - (n - 1) / 2) * 1.45, 1.9, 0, ty);
        }

        const bubbleMap: Record<string, string> = {
          coffee: "☕ hora do café",
          plant: "🌱 cuidando da planta",
          game: `🎮 player ${j + 1}`,
          pingpong: "🏓 bora jogar!",
          chat: "💬 trocando ideia",
          dance: "🎵 festa no escritório!",
          band: "🎸 ensaio do esquadrão!",
          conga: "🐍 trenzinho!",
        };
        say(a, bubbleMap[ty] || "👋 pronto!", 3.2);
      });

      if (ty === "pingpong" && free.length >= 2) {
        pp = [free[0], free[1]];
      }
    };

    const setActorState = (a: AgentActor, nextState: AgentVisualState, customBubble?: string) => {
      if (a.state === nextState && !customBubble) return;
      a.state = nextState;
      a.act = null;
      if (customBubble) say(a, customBubble, 3.5);
      else if (nextState === "work") say(a, a.d.workSpeech, 3.2);
      else if (nextState === "err") say(a, "⚠ atenção na missão!", 3.2);
      plan(true);
    };

    const drawMonitor = (a: AgentActor, t: number) => {
      const x = a.cx;
      const W = 256;
      const H = 160;
      const s = a.state;

      if (s === "err") {
        x.fillStyle = Math.floor(t * 4) % 2 ? "#7f1d1d" : "#2a0a0a";
        x.fillRect(0, 0, W, H);
        x.fillStyle = "#ffffff";
        x.font = "bold 30px monospace";
        x.textAlign = "center";
        x.fillText("FALHA", W / 2, 72);
        x.font = "15px monospace";
        x.fillText("verifique o card", W / 2, 104);
      } else if (s === "idle") {
        x.fillStyle = "#09101f";
        x.fillRect(0, 0, W, H);
        if (a.pendingReview) {
          x.fillStyle = "#064e3b";
          x.fillRect(12, 20, W - 24, H - 40);
          x.fillStyle = "#34d399";
          x.font = "bold 20px monospace";
          x.textAlign = "center";
          x.fillText("CONCLUÍDO ✔", W / 2, 72);
          x.fillStyle = "#a7f3d0";
          x.font = "14px monospace";
          x.fillText("Indexar na Base?", W / 2, 102);
        } else {
          x.fillStyle = "#64748b";
          x.font = "bold 18px monospace";
          x.textAlign = "center";
          x.fillText("STANDBY" + (Math.floor(t * 1.5) % 2 ? " _" : ""), W / 2, H / 2 + 6);
        }
      } else {
        x.fillStyle = "#09101f";
        x.fillRect(0, 0, W, H);
        const col = a.d.hex;
        const o = (t * 40) % 20;
        x.fillStyle = col;

        if (a.k === "pes") {
          for (let r = 0; r < 7; r++) {
            const w = 60 + (((r * 53 + Math.floor(t * 3 + r)) % 7) * 20);
            x.fillRect(14, r * 18 - o + 14, w, 7);
          }
        } else if (a.k === "org") {
          for (let r = 0; r < 5; r++) {
            for (let c = 0; c < 9; c++) {
              x.globalAlpha = ((Math.sin(t * 3 + r * c) + 1) / 2) * 0.75 + 0.2;
              x.fillRect(14 + c * 25, 10 + r * 22, 19, 16);
            }
          }
          x.globalAlpha = 1;
        } else if (a.k === "ide") {
          for (let j = 0; j < 6; j++) {
            x.globalAlpha = 0.75;
            x.beginPath();
            x.arc(34 + j * 36, 68 + Math.sin(t * 2.2 + j) * 30, 9 + (j % 3) * 5, 0, 7);
            x.fill();
          }
          x.globalAlpha = 1;
        } else {
          x.strokeStyle = col;
          x.lineWidth = 2;
          const pts: [number, number][] = [
            [40, 42],
            [128, 30],
            [212, 48],
            [80, 96],
            [176, 98],
          ];
          pts.forEach(([px0, py0], idx) => {
            const nx = px0 + Math.sin(t * 2 + idx) * 6;
            const ny = py0 + Math.cos(t * 2 + idx) * 6;
            if (idx > 0) {
              x.beginPath();
              x.moveTo(pts[idx - 1][0], pts[idx - 1][1]);
              x.lineTo(nx, ny);
              x.stroke();
            }
            x.beginPath();
            x.arc(nx, ny, 7, 0, Math.PI * 2);
            x.fill();
          });
        }

        // Barra inferior com progresso real
        x.fillStyle = "#0f172a";
        x.fillRect(12, H - 28, W - 24, 16);
        x.fillStyle = col;
        x.fillRect(12, H - 28, ((W - 24) * Math.max(15, a.progressPct)) / 100, 16);
        x.fillStyle = "#ffffff";
        x.font = "bold 11px monospace";
        x.textAlign = "center";
        x.fillText(`${a.progressPct || 35}% ATIVO`, W / 2, H - 16);
      }

      a.tex.needsUpdate = true;
    };

    const drawTV = (t: number) => {
      const W = 256;
      const H = 144;
      tx.clearRect(0, 0, W, H);
      const activeCount = AG.filter((a) => a.state === "work").length;

      if (party > T) {
        tx.fillStyle = `hsl(${(t * 200) % 360}, 80%, 38%)`;
        tx.fillRect(0, 0, W, H);
        tx.fillStyle = "#ffffff";
        tx.font = "bold 23px monospace";
        tx.textAlign = "center";
        tx.fillText("🎉 FESTA F.R.Y.I.Vs 🎉", W / 2, H / 2 + 8);
      } else if (activeCount > 0) {
        tx.fillStyle = "#071324";
        tx.fillRect(0, 0, W, H);
        tx.fillStyle = "#22d3ee";
        tx.font = "bold 16px monospace";
        tx.textAlign = "center";
        tx.fillText(`⚡ ${activeCount} AGENTE(S) EM MISSÃO`, W / 2, 58);
        tx.fillStyle = "#94a3b8";
        tx.font = "13px monospace";
        tx.fillText("TELEMETRIA EM TEMPO REAL", W / 2, 92);
      } else if (cur === "band") {
        tx.fillStyle = "#111827";
        tx.fillRect(0, 0, W, H);
        for (let j = 0; j < 16; j++) {
          tx.fillStyle = `hsl(${(j * 22 + t * 80) % 360}, 80%, 55%)`;
          const h = 20 + Math.abs(Math.sin(t * 5 + j * 0.7)) * 90;
          tx.fillRect(10 + j * 15, H - h, 11, h);
        }
        tx.fillStyle = "#ffffff";
        tx.font = "bold 14px monospace";
        tx.textAlign = "center";
        tx.fillText("🎸 ESQUADRÃO LIVE", W / 2, 18);
      } else if (cur === "game") {
        tx.fillStyle = "#1e1b4b";
        tx.fillRect(0, 0, W, H);
        tx.fillStyle = "#22c55e";
        tx.fillRect(0, 110, W, 34);
        for (let j = 0; j < 3; j++) {
          tx.fillStyle = "#ef4444";
          tx.fillRect((((j * 110 - t * 80) % 330) + 330) % 330 - 40, 86, 22, 24);
        }
        tx.fillStyle = "#fde047";
        tx.fillRect(40, 86 - Math.abs(Math.sin(t * 3)) * 40, 22, 24);
        tx.fillStyle = "#ffffff";
        tx.font = "bold 14px monospace";
        tx.textAlign = "left";
        tx.fillText("SCORE " + String(Math.floor(t * 13)).padStart(5, "0"), 10, 20);
      } else if (cur === "coffee") {
        const g = tx.createLinearGradient(0, 0, 0, H);
        g.addColorStop(0, "#fb923c");
        g.addColorStop(1, "#4c1d95");
        tx.fillStyle = g;
        tx.fillRect(0, 0, W, H);
        tx.fillStyle = "#ffffff";
        tx.font = "bold 18px monospace";
        tx.textAlign = "center";
        tx.fillText("lo-fi ☕ relax", W / 2, H / 2);
      } else {
        tx.fillStyle = "#0b1220";
        tx.fillRect(0, 0, W, H);
        tx.fillStyle = "#38bdf8";
        tx.font = "bold 22px monospace";
        tx.textAlign = "center";
        const now = new Date();
        tx.fillText(now.toTimeString().slice(0, 5), W / 2, H / 2 - 4);
        tx.fillStyle = "#94a3b8";
        tx.font = "12px monospace";
        tx.fillText("F.R.Y.I.Vs · AGENTS HQ", W / 2, H / 2 + 20);
      }
      ttx.needsUpdate = true;
    };

    const syncRealJobsToActors = () => {
      if (demoModeRef.current) return;
      const currentJobs = jobsRef.current || [];

      AG.forEach((a) => {
        const profileJobs = currentJobs.filter((j) => j.profile === a.d.key);
        const activeJob = profileJobs.find(
          (j) => j.status === "running" || j.status === "queued",
        );
        const pendingReviewJob = profileJobs.find(
          (j) => j.status === "completed" && j.kb_status !== "indexed" && j.kb_status !== "discarded",
        );
        const failedJob =
          !activeJob && !pendingReviewJob
            ? profileJobs.find((j) => j.status === "failed")
            : undefined;

        a.pendingReview = Boolean(pendingReviewJob);

        if (activeJob) {
          a.progressPct = activeJob.progress_pct || 35;
          const shortTask =
            activeJob.task.length > 26 ? `${activeJob.task.slice(0, 26)}…` : activeJob.task;
          if (a.state !== "work") {
            setActorState(a, "work", `⚡ ${shortTask}`);
          }
          a.taskLabel = shortTask;
        } else if (failedJob) {
          a.progressPct = 0;
          a.taskLabel = "";
          if (a.state !== "err") {
            setActorState(a, "err", "⚠ Falha na missão");
          }
        } else {
          const wasWorking = a.state === "work";
          a.progressPct = 0;
          a.taskLabel = "";
          if (a.state !== "idle") {
            setActorState(
              a,
              "idle",
              wasWorking && pendingReviewJob
                ? "✔ Pronto! Indexar na Base?"
                : undefined,
            );
            if (wasWorking && pendingReviewJob) {
              a.jump = 1;
            }
          }
        }
      });
    };

    const updActor = (a: AgentActor, t: number, dt: number) => {
      const g = a.g;
      const P = g.position;
      const s = a.state;
      const id = s === "idle";
      const w = s === "work";
      const e = s === "err";
      let walk = false;

      if (a.q.length) {
        const q = a.q[0];
        const dx = q[0] - P.x;
        const dz = q[1] - P.z;
        const dist = Math.hypot(dx, dz);
        if (dist < 0.08) a.q.shift();
        else {
          walk = true;
          const sp = Math.min(dist, 2.8 * dt);
          P.x += (dx / dist) * sp;
          P.z += (dz / dist) * sp;
          a.ty = Math.atan2(dx, dz);
        }
      } else {
        a.ty = a.tr;
      }

      let df = a.ty - g.rotation.y;
      df = Math.atan2(Math.sin(df), Math.cos(df));
      g.rotation.y += df * Math.min(1, dt * 8);

      const ac = !walk && a.act && id ? a.act.type : null;
      const home = !walk && !a.act;
      let hxRot = 0;
      let hyRot = 0;
      let hzRot = 0;
      let l = 0;
      let r = 0;
      let by = 0.95 + Math.sin(t * 2 + a.i) * 0.015;
      let gy = 0;
      const wk = Math.sin(t * 10);

      a.legL.rotation.x = 0;
      a.legR.rotation.x = 0;

      if (walk) {
        a.legL.rotation.x = wk * 0.6;
        a.legR.rotation.x = -wk * 0.6;
        l = -wk * 0.5;
        r = wk * 0.5;
        hxRot = 0.12;
        if (a.act && a.act.type === "conga") {
          l = -2.3 + wk * 0.4;
          r = -2.3 - wk * 0.4;
          by += Math.abs(wk) * 0.06;
        }
        by += Math.abs(wk) * 0.04;
      } else if (ac) {
        if (ac === "coffee") {
          gy = -0.2;
          hxRot = 0.1;
          hyRot = Math.sin(t * 0.5) * 0.2;
          r = -1.2 - Math.max(0, Math.sin(t * 0.7)) * 1.1;
        } else if (ac === "game") {
          gy = -0.2;
          hxRot = -0.1;
          hyRot = Math.sin(t * 2 + a.i) * 0.1;
          l = r = -1 + Math.sin(t * 9 + a.i) * 0.12;
          if (Math.sin(t * 1.1 + a.i * 2.3) > 0.94) {
            l = r = -2.8;
            gy = 0.05 + Math.abs(Math.sin(t * 12)) * 0.2;
            if (T > a.bbT) say(a, "GOOOL! 🎉", 1.5);
          }
        } else if (ac === "pingpong") {
          hxRot = 0.1;
          by -= 0.05;
          l = 0.3;
          r = -0.9 - a.hit * 1.2;
          hyRot = Math.sin(t * 3) * 0.25;
        } else if (ac === "band") {
          hyRot = Math.sin(t * 2 + a.i) * 0.25;
          hxRot = 0.1 + Math.abs(Math.sin(t * 4 + a.i)) * 0.15;
          by += Math.abs(Math.sin(t * 4 + a.i)) * 0.03;
          a.legR.rotation.x = Math.max(0, Math.sin(t * 4 + a.i)) * 0.3;
          if (a.k === "pes") {
            l = -1.3;
            r = -0.9 + Math.sin(t * 9) * 0.45;
          } else if (a.k === "org" || a.k === "eng") {
            l = -1.1 + Math.sin(t * 8) * 0.35;
            r = -1.1 - Math.sin(t * 8) * 0.35;
          } else {
            r = -1.7;
            l = -0.2 + Math.sin(t * 3) * 0.6;
            hxRot = -0.2;
            if (a.bm && a.bl) {
              a.bm.emissiveIntensity = 0.9 + 0.6 * Math.sin(t * 6);
              a.bl.intensity = 1.2;
            }
          }
        } else if (ac === "dance" || ac === "conga") {
          const k = Math.sin(t * 6 + a.i);
          by += Math.abs(k) * 0.1;
          l = -2.4 + k * 0.6;
          r = -2.4 - k * 0.6;
          hzRot = k * 0.15;
          a.legL.rotation.x = k * 0.4;
          a.legR.rotation.x = -k * 0.4;
          g.rotation.y += Math.sin(t * 3 + a.i) * 0.03;
        } else if (ac === "chat") {
          l = -0.5 + Math.sin(t * 3 + a.i) * 0.4;
          r = -0.8 - Math.sin(t * 3.4) * 0.4;
          hyRot = Math.sin(t * 2) * 0.2;
        } else if (ac === "plant") {
          hxRot = 0.3;
          r = -1.2 + Math.sin(t * 3) * 0.4;
        }
      } else {
        if (a.k === "pes" && a.dish && a.glass) {
          if (id) {
            hyRot = Math.sin(t * 0.8) * 0.8;
            l = 0.1;
            r = -0.3;
            a.dish.rotation.y = t * 0.7;
          }
          if (w) {
            hxRot = 0.3;
            hyRot = -0.5 + Math.sin(t * 2) * 0.15;
            l = 0.3;
            r = -1.1 + Math.sin(t * 5) * 0.45;
            a.dish.rotation.y = t * 7;
          }
          (a.glass.material as THREE.MeshBasicMaterial).color.setHex(e ? 0xff4444 : 0x93c5fd);
        } else if (a.k === "org") {
          if (id) {
            l = -0.5;
            r = -0.5;
            a.legR.rotation.x = Math.max(0, Math.sin(t * 6)) * 0.5;
            hyRot = Math.sin(t * 0.6) * 0.2;
          }
          if (w) {
            hxRot = 0.2;
            l = -1.1 + Math.sin(t * 8) * 0.5;
            r = -1.1 - Math.sin(t * 8) * 0.5;
            by += Math.abs(Math.sin(t * 4)) * 0.04;
          }
        } else if (a.k === "ide" && a.bm && a.bl) {
          if (id) {
            hxRot = 0.45;
            by -= 0.03;
            a.bm.emissiveIntensity = 0.1;
            a.bl.intensity = 0;
          }
          if (w) {
            hxRot = -0.15;
            r = -2.7 + Math.sin(t * 4) * 0.3;
            l = Math.sin(t * 3) * 0.3;
            by += Math.abs(Math.sin(t * 5)) * 0.1;
            const p = 0.6 + 0.4 * Math.sin(t * 6);
            a.bm.emissiveIntensity = p * 1.5;
            a.bl.intensity = p * 1.8;
          }
          if (e) {
            a.bm.emissiveIntensity = Math.random() > 0.6 ? 1 : 0.1;
            a.bl.intensity = 0;
          }
        } else if (a.k === "eng") {
          if (id) {
            hyRot = Math.sin(t * 0.7) * 0.3;
            l = -0.2;
            r = -0.4;
          }
          if (w) {
            hxRot = 0.22;
            l = -1.0 + Math.sin(t * 7) * 0.35;
            r = -1.25 - Math.sin(t * 7) * 0.4;
            by += Math.abs(Math.sin(t * 4)) * 0.03;
          }
        }
      }

      if (a.wk && !walk) a.sq = 1;
      a.wk = walk;
      a.sq = Math.max(0, a.sq - dt * 3);
      const sqv = a.sq * 0.1 * Math.sin(a.sq * Math.PI);
      g.scale.set(1 + sqv, 1 - sqv, 1);

      if (a.waveT > T && home) {
        r = -2.6 + Math.sin(t * 10) * 0.5;
        hyRot = Math.sin(t * 3) * 0.3;
      }

      a.aL.rotation.z = -0.05 + Math.sin(t * 2 + a.i) * 0.04;
      a.aR.rotation.z = 0.05 - Math.sin(t * 2 + a.i) * 0.04;
      a.body.rotation.z = Math.sin(t * 0.8 + a.i) * 0.03;
      a.mouth.scale.set(
        e ? 0.6 : w ? 0.7 : 1.2,
        T < a.bbT ? 0.5 + Math.abs(Math.sin(t * 14)) * 1.6 : e ? 0.4 : 1,
        1,
      );
      a.eyes.forEach((y, j) => (y.position.x = (j ? 0.14 : -0.14) + Math.sin(t * 0.7 + a.i) * 0.025));

      if (a.k === "pes" && a.dish && a.scan && a.mag) {
        a.dish.rotation.z = Math.sin(t * 2) * 0.1;
        (a.scan.material as THREE.MeshBasicMaterial).opacity =
          w && home ? 0.5 + 0.4 * Math.sin(t * 6) : 0;
        a.scan.scale.setScalar(1 + ((t * 1.2) % 1) * 3);
        a.mag.visible = !ac;
      }

      if (a.k === "org" && a.cubes) {
        a.cubes.forEach((cb, j) => {
          const c = j % 3;
          const stIdx = Math.floor(j / 3);
          const sl = new THREE.Vector3(a.hx - 0.48 + c * 0.48, 0.16 + stIdx * 0.21, 1.3);
          if (w && home) {
            const p = (t * 0.7 + j / 6) % 1;
            const tg = new THREE.Vector3(a.hx + 0.85 + (j % 2) * 0.25, 1, 0.6).lerp(sl, p);
            tg.y += Math.sin(Math.PI * p) * 0.7;
            cb.position.lerp(tg, 0.35);
            cb.rotation.y += 0.05;
          } else if (e) {
            cb.position.lerp(
              new THREE.Vector3(
                a.hx - 1.1 + ((j * 37) % 9) * 0.28,
                0.11,
                0.7 + ((j * 53) % 5) * 0.35,
              ),
              0.12,
            );
            cb.rotation.y = j * 1.3;
          } else {
            cb.position.lerp(sl, 0.12);
            cb.rotation.y *= 0.9;
          }
        });
      }

      if (a.k === "ide" && a.bulb && a.zs && a.sp && a.bm && a.bl) {
        a.bulb.position.y = 0.8 + Math.sin(t * 3) * (w ? 0.06 : 0.02);
        a.bulb.rotation.y = t * (w ? 4 : 0.5);
        if (!walk && ac && ac !== "band" && ac !== "dance") {
          a.bm.emissiveIntensity = 0.2;
          a.bl.intensity = 0;
        }
        a.zs.forEach((z, j) => {
          z.visible = id && home && !a.pendingReview;
          const p = (t * 0.4 + j / 3) % 1;
          z.position.set(P.x + 0.3 + p * 0.5, 2.3 + p * 0.9, P.z);
          (z.material as THREE.SpriteMaterial).opacity = 1 - p;
        });
        a.sp.forEach((pMesh, j) => {
          pMesh.visible = (w && home) || ac === "dance";
          if (pMesh.visible) {
            const q = (t * 0.9 + j / 6) % 1;
            const ang = j * 1.1 + t;
            pMesh.position.set(
              P.x + Math.cos(ang) * 0.5 * q,
              2.5 + q * 0.9,
              P.z + Math.sin(ang) * 0.5 * q,
            );
            pMesh.scale.setScalar(1 - q);
          }
        });
      }

      if (a.k === "eng" && a.holo && a.wrench) {
        a.holo.rotation.y = t * (w ? 2.6 : 0.6);
        a.holo.rotation.x = t * (w ? 1.4 : 0.3);
        a.holo.scale.setScalar(w ? 1.15 + Math.sin(t * 5) * 0.12 : 0.8);
        (a.holo.material as THREE.MeshBasicMaterial).color.setHex(e ? 0xff4444 : 0x22d3ee);
        a.wrench.visible = !ac;
      }

      a.st.forEach((sMesh, j) => {
        sMesh.visible = ac === "coffee";
        if (sMesh.visible) {
          const q = (t * 0.6 + j / 3) % 1;
          sMesh.position.set(
            P.x - Math.sin(g.rotation.y) * 0.15,
            1.25 + q * 0.6,
            P.z - Math.cos(g.rotation.y) * 0.3,
          );
          sMesh.scale.setScalar(1 + q);
          (sMesh.material as THREE.MeshBasicMaterial).opacity = 0.5 * (1 - q);
        }
      });

      a.pad.visible = ac === "pingpong";
      a.inst.visible = ac === "band";
      a.cup.visible = ac === "coffee";
      a.ctl.forEach((o) => (o.visible = ac === "game"));

      // Anel de seleção ativo quando este agente está selecionado no HUD
      const isSelected = selectedRef.current === a.d.key;
      a.selRing.visible = isSelected || a.pendingReview;
      (a.selRing.material as THREE.MeshBasicMaterial).opacity = isSelected
        ? 0.65 + Math.sin(t * 4) * 0.2
        : 0.45 + Math.sin(t * 6) * 0.3;

      // Estrela verde flutuante quando tem pesquisa pronta para indexar
      a.okSp.visible = a.pendingReview && !e;
      if (a.okSp.visible) {
        a.okSp.position.set(P.x, (a.k === "ide" ? 3.2 : 2.75) + Math.sin(t * 4) * 0.12, P.z);
      }

      if (a.jump > 0) {
        a.jump -= dt * 1.5;
        gy += Math.sin((1 - Math.max(a.jump, 0)) * Math.PI) * 0.6;
        l = r = -2.6;
      }

      if (e) {
        g.rotation.z = Math.sin(t * 45) * 0.05;
        hzRot = Math.sin(t * 30) * 0.12;
        l = -2.6 + Math.sin(t * 12) * 0.35;
        r = -2.6 - Math.sin(t * 12) * 0.35;
        hyRot = Math.sin(t * 20) * 0.2;
      } else {
        g.rotation.z = 0;
      }

      P.y += (gy - P.y) * 0.3;
      a.body.position.y += (by - a.body.position.y) * 0.25;
      a.body.scale.y = 1 + Math.sin(t * 2 + a.i) * 0.015;
      a.hr[0] += (hxRot - a.hr[0]) * 0.15;
      a.hr[1] += (hyRot - a.hr[1]) * 0.15;
      a.hr[2] += (hzRot - a.hr[2]) * 0.15;
      a.head.rotation.set(a.hr[0], a.hr[1], a.hr[2]);
      a.aL.rotation.x += (l - a.aL.rotation.x) * 0.2;
      a.aR.rotation.x += (r - a.aR.rotation.x) * 0.2;
      a.em.color.setHex(e ? 0xff2222 : w ? 0xffffff : 0x7dd3fc);

      const blink =
        (id && Math.sin(t * 1.7 + a.i * 2) > 0.97) ||
        (a.k === "ide" && id && home && !a.pendingReview);
      a.eyes.forEach((y) => (y.scale.y = blink ? 0.15 : 1));

      a.bc.visible = e;
      const bk = Math.sin(t * 14) > 0;
      a.rl.intensity = e ? (bk ? 2.2 : 0.2) : 0;
      (a.bc.material as THREE.MeshBasicMaterial).color.setHex(bk ? 0xff2222 : 0x661111);
      a.ex.visible = e;
      a.ex.position.set(P.x, 2.9 + Math.abs(Math.sin(t * 6)) * 0.15, P.z);

      a.sm.forEach((m, j) => {
        m.visible = e;
        if (e) {
          const p = (t * 0.6 + j / 8) % 1;
          m.position.set(P.x + Math.sin(j * 2 + t) * 0.25, 2.1 + p * 1.2, P.z);
          m.scale.setScalar(0.6 + p * 1.4);
          (m.material as THREE.MeshBasicMaterial).opacity = 0.55 * (1 - p);
        }
      });
    };

    const updAmbient = (t: number) => {
      lamps.forEach((g, idx) => (g.rotation.z = Math.sin(t * 0.9 + idx * 1.7) * 0.04));
      (neon.material as THREE.MeshStandardMaterial).emissiveIntensity =
        0.9 + Math.sin(t * 3) * 0.3;
      drone.position.set(
        Math.sin(t * 0.35) * 7.5,
        3.8 + Math.sin(t * 1.3) * 0.25,
        -1.6 + Math.cos(t * 0.35) * 2.2,
      );
      drone.rotation.y = -t * 0.35;
      droneRotor.rotation.y = t * 40;
      gl.intensity = cur === "game" || cur === "band" ? 1.4 + Math.sin(t * 9) * 0.6 : 0;
      gl.color.setHSL((t * 0.4) % 1, 0.8, 0.5);

      conf.forEach((c) => {
        c.visible = party > T;
        if (c.visible) {
          c.position.y -= (c.userData.v as number) * 0.035;
          c.rotation.x += 0.1;
          c.rotation.z += 0.07;
          if (c.position.y < 0) {
            c.position.set((Math.random() - 0.5) * 18, 5.2, -4 + Math.random() * 8);
          }
        }
      });
    };

    const updPong = (t: number) => {
      AG.forEach((a) => (a.hit = 0));
      const ok =
        pp &&
        pp.length === 2 &&
        pp.every((a) => a.act && a.act.type === "pingpong" && !a.q.length && a.state === "idle");
      ball.visible = Boolean(ok);
      if (!ok || !pp) return;
      const phase = t * 0.95;
      const idx = Math.floor(phase) % 2;
      const f = phase % 1;
      const A = idx ? -5.8 : -8.0;
      const B = idx ? -8.0 : -5.8;
      ball.position.set(A + (B - A) * f, 1.0 + Math.sin(Math.PI * f) * 0.45, -3.5);
      pp[idx].hit = Math.max(0, 1 - f * 4);
    };

    // Controles de câmera & Raycasting nos 4 agentes
    let width = mountEl.clientWidth || 960;
    let height = mountEl.clientHeight || 600;
    const resize = () => {
      width = Math.max(1, mountEl.clientWidth);
      height = Math.max(1, mountEl.clientHeight);
      renderer.setSize(width, height, false);
      cam.aspect = width / height;
      cam.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(mountEl);

    let dragging = false;
    let px = 0;
    let py = 0;
    let sx = 0;
    let sy = 0;
    const rc = new THREE.Raycaster();
    const ndc = new THREE.Vector2();

    const onPointerDown = (e: PointerEvent) => {
      dragging = true;
      px = sx = e.clientX;
      py = sy = e.clientY;
    };

    const onPointerMove = (e: PointerEvent) => {
      if (!dragging) return;
      tth = Math.max(-1.05, Math.min(1.05, tth - (e.clientX - px) * 0.006));
      tph = Math.max(0.08, Math.min(0.88, tph + (e.clientY - py) * 0.004));
      px = e.clientX;
      py = e.clientY;
    };

    const onPointerUp = (e: PointerEvent) => {
      if (dragging && Math.hypot(e.clientX - sx, e.clientY - sy) < 6 && e.target === canvas) {
        const rect = canvas.getBoundingClientRect();
        ndc.set(
          ((e.clientX - rect.left) / rect.width) * 2 - 1,
          -((e.clientY - rect.top) / rect.height) * 2 + 1,
        );
        rc.setFromCamera(ndc, cam);
        const hit = rc.intersectObjects(
          AG.map((a) => a.g),
          true,
        )[0];
        if (hit) {
          let obj: THREE.Object3D | null = hit.object;
          while (obj && !AG.some((a) => a.g === obj)) obj = obj.parent;
          const actor = AG.find((a) => a.g === obj);
          if (actor) {
            actor.jump = 1;
            say(actor, actor.d.phrases[Math.floor(Math.random() * actor.d.phrases.length)], 2.8);
            onSelectRef.current(actor.d.key);
          }
        }
      }
      dragging = false;
    };

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      rt = Math.max(7.5, Math.min(19.5, rt + e.deltaY * 0.01));
    };

    canvas.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("wheel", onWheel, { passive: false });

    sceneApiRef.current = {
      triggerParty: (seconds = 10, customMsg) => {
        party = T + seconds;
        AG.forEach((a) => {
          if (a.state === "idle") {
            a.jump = 1;
            say(a, customMsg || "🎉 Festa no Escritório!", 3.2);
          } else if (customMsg) {
            say(a, customMsg, 3.2);
          }
        });
        plan(true);
      },
      welcomeWave: () => {
        th = 1.05;
        rad = 22.5;
        rt = 13.4;
        tth = 0;
        AG.forEach((a) => {
          a.waveT = T + 2.6;
          say(a, "👋 Bem-vindo, senhor!", 2.8);
        });
      },
      focusAgent: (profile) => {
        const target = AG.find((a) => a.d.key === profile);
        if (target) {
          target.jump = 0.85;
          tth = THREE.MathUtils.clamp(-target.d.x * 0.06, -0.5, 0.5);
        }
      },
      forceActivity: (activity) => {
        forcedActivity = activity;
        plan(true);
      },
      setDemoRandom: () => {
        const actor = AG[Math.floor(Math.random() * AG.length)];
        const q = Math.random();
        const st: AgentVisualState = q < 0.45 ? "work" : q < 0.88 ? "idle" : "err";
        actor.progressPct = st === "work" ? 30 + Math.floor(Math.random() * 65) : 0;
        setActorState(actor, st);
      },
    };

    plan(true);

    const clock = new THREE.Clock();
    const projVec = new THREE.Vector3();
    let lastTick = 0;
    let rafId = 0;

    const animate = () => {
      rafId = requestAnimationFrame(animate);
      const dt = Math.min(clock.getDelta(), 0.05);
      T += dt;
      const t = T;

      th += (tth - th) * 0.05;
      ph += (tph - ph) * 0.1;
      rad += (rt - rad) * 0.04;
      const aspect = Math.max(0.5, width / height);
      const rr = rad * Math.max(1, 1.45 / aspect);

      cam.position.set(
        Math.sin(th) * Math.cos(ph) * rr,
        1.1 + Math.sin(ph) * rr,
        -1.2 + Math.cos(th) * Math.cos(ph) * rr,
      );
      cam.lookAt(0, 1.05, -1.2);

      plan(false);
      updPong(t);
      updAmbient(t);
      hand.rotation.z = -t * 0.5;
      plant.rotation.z = Math.sin(t) * 0.02;
      lf.scale.y = 1 + Math.sin(t * 2) * 0.03;

      disco.intensity = party > T ? 2.4 : 0;
      if (party > T) disco.color.setHSL((t * 0.5) % 1, 1, 0.55);

      const tick = t - lastTick > 0.12;
      if (tick) {
        syncRealJobsToActors();
      }

      AG.forEach((a) => {
        updActor(a, t, dt);
        if (tick) drawMonitor(a, t);

        projVec.set(a.g.position.x, a.k === "ide" ? 3.55 : 2.55, a.g.position.z);
        projVec.project(cam);
        const X = (projVec.x * 0.5 + 0.5) * width;
        const Y = (-projVec.y * 0.5 + 0.5) * height;

        a.lb.style.left = `${X}px`;
        a.lb.style.top = `${Y}px`;
        const dotColor = a.pendingReview && a.state === "idle" ? "#10b981" : STATE_COLORS[a.state];
        const suffix =
          a.state === "work" && a.progressPct > 0
            ? ` · ${a.progressPct}%`
            : a.pendingReview && a.state === "idle"
              ? " ★"
              : "";
        a.lb.innerHTML = `<span style="display:inline-block;width:7px;height:7px;border-radius:999px;background:${dotColor};margin-right:5px"></span>${SHORT_NAMES[a.d.key]}${suffix}`;

        a.bb.style.left = `${X}px`;
        a.bb.style.top = `${Y - 28}px`;
        const showBubble = t < a.bbT;
        if (showBubble !== a.bo) {
          a.bo = showBubble;
          a.bb.style.opacity = showBubble ? "1" : "0";
        }
      });

      if (tick) {
        drawTV(t);
        lastTick = t;
      }

      renderer.render(sc, cam);
    };

    animate();

    return () => {
      cancelAnimationFrame(rafId);
      ro.disconnect();
      canvas.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("wheel", onWheel);
      labelsRoot.innerHTML = "";
      sc.traverse((obj) => {
        const mesh = obj as THREE.Mesh;
        if (mesh.geometry) mesh.geometry.dispose();
        const mat = (mesh as any).material;
        if (Array.isArray(mat)) mat.forEach((m) => m?.dispose?.());
        else mat?.dispose?.();
      });
      renderer.dispose();
      if (canvas.parentNode === mountEl) {
        mountEl.removeChild(canvas);
      }
      sceneApiRef.current = null;
    };
  }, []);

  useEffect(() => {
    sceneApiRef.current?.focusAgent(selectedProfile);
  }, [selectedProfile]);

  useEffect(() => {
    if (!externalCommand) return;
    if (externalCommand.action === "party") {
      sceneApiRef.current?.triggerParty(10);
    } else if (externalCommand.action === "focus" && externalCommand.profile) {
      sceneApiRef.current?.focusAgent(externalCommand.profile);
    } else if (externalCommand.action === "activity" && externalCommand.activity) {
      sceneApiRef.current?.forceActivity(externalCommand.activity);
    }
  }, [externalCommand]);

  return (
    <div className="relative w-full h-full overflow-hidden select-none bg-[#0d1324]">
      <div ref={containerRef} className="absolute inset-0" />

      <div
        ref={labelsContainerRef}
        className={`pointer-events-none absolute inset-0 overflow-hidden transition-opacity duration-500 ${
          doorPhase === "open" ? "opacity-100" : "opacity-0"
        }`}
      />

      {doorPhase === "open" && (
        <div className="absolute top-3 left-3 z-20 flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => sceneApiRef.current?.triggerParty(10)}
            title="Festa"
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-[#060c1a]/82 hover:bg-purple-500/25 border border-white/12 text-slate-200 text-xs font-medium backdrop-blur-xl transition-all cursor-pointer"
          >
            <Icons8Icon name="party" className="w-3.5 h-3.5 text-amber-300" />
            Festa
          </button>

          <button
            type="button"
            onClick={() => setDemoMode((v) => !v)}
            title="Modo demonstração"
            className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl border text-xs font-mono backdrop-blur-xl transition-all cursor-pointer ${
              demoMode
                ? "bg-amber-500/22 border-amber-400/50 text-amber-100"
                : "bg-[#060c1a]/82 border-white/12 text-slate-300 hover:text-white"
            }`}
          >
            {demoMode ? (
              <Icons8Icon name="stop-square" className="w-3 h-3 text-amber-300" />
            ) : (
              <Icons8Icon name="play" className="w-3 h-3" />
            )}
            Demo
          </button>

          <button
            type="button"
            onClick={() => {
              officeDoorSeenInSession = false;
              setDoorPhase("closed");
            }}
            title="Porta"
            className="p-2 rounded-xl bg-[#060c1a]/82 hover:bg-white/10 border border-white/12 text-slate-300 backdrop-blur-xl transition-all cursor-pointer"
          >
            <Icons8Icon name="door" className="w-3.5 h-3.5 text-cyan-300" />
          </button>
        </div>
      )}

      {doorPhase !== "open" && (
        <div
          onClick={() => {
            officeDoorSeenInSession = true;
            setDoorPhase("open");
            sceneApiRef.current?.welcomeWave();
          }}
          className={`absolute inset-0 z-30 flex flex-col items-center justify-center gap-3 bg-[radial-gradient(circle_at_50%_35%,#1e294b,#060913)] transition-all duration-700 cursor-pointer ${
            doorPhase === "opening" ? "opacity-0 scale-150 pointer-events-none" : "opacity-100 scale-100"
          }`}
        >
          <div
            className="w-[210px] h-[320px] border-[9px] border-[#3a2f24] border-b-0 rounded-t-lg bg-[radial-gradient(circle,#fffbe6,#ffc94d)] relative shadow-[0_0_60px_rgba(255,200,90,0.22)]"
            style={{ perspective: "800px" }}
          >
            <div
              className="absolute inset-0 bg-gradient-to-r from-[#6b4a2f] to-[#52391f] border-2 border-[#2d2015] flex flex-col items-center justify-start transition-transform duration-1000 ease-in-out"
              style={{
                transformOrigin: "left center",
                transform: doorPhase === "opening" ? "rotateY(-105deg)" : "rotateY(0deg)",
              }}
            >
              <span className="mt-7 text-[10px] tracking-[0.2em] text-[#e8d3a8] border border-[#a98d5c] px-3 py-1.5 text-center font-mono">
                ESCRITÓRIO
              </span>
              <div className="mt-6 bg-[#10151f] border border-emerald-400/50 rounded-xl px-3.5 py-2.5 flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
                <span className="inline-flex items-center gap-1 font-mono text-[10.5px] text-emerald-300 tracking-wider">
                  E2EE
                  <Icons8Icon name="shield-check" className="w-3 h-3 text-emerald-300" />
                </span>
              </div>
              <span className="absolute right-4 bottom-8 w-3.5 h-3.5 rounded-full bg-[#e5b94b]" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AgentsOffice3D;

