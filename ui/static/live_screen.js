/* F.R.Y.I.Vs — Painel "Tela ao Vivo" v2
 * Mostra a área de trabalho em tempo real (MJPEG) enquanto a IA navega,
 * pesquisa ou cria arquivos Word/Excel. Independente do bundle React.
 * Melhorias v2: minimização em pílula, docking em cantos, sem obstrução da orbe.
 */
(function () {
  const css = `
  /* ── Janela principal ── */
  #fry-live {
    position: fixed;
    z-index: 9000;
    width: 440px;
    background: rgba(6,10,22,.92);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(80,160,255,.30);
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 16px 48px rgba(0,0,0,.80), 0 0 28px rgba(40,120,255,.18), inset 0 0 18px rgba(40,120,255,.06);
    font-family: 'JetBrains Mono', Consolas, monospace;
    color: #cfe3ff;
    transition: opacity .25s ease, transform .25s ease;
    /* Posição padrão: canto inferior esquerdo (não obstrui a orbe central) */
    bottom: 24px;
    left: 24px;
  }
  #fry-live.fry-hidden {
    opacity: 0;
    transform: translateY(10px);
    pointer-events: none;
  }
  #fry-live.fry-big { width: min(72vw, 960px); }

  /* ── Header da janela ── */
  #fry-live header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    font-size: 10px;
    letter-spacing: .1em;
    text-transform: uppercase;
    border-bottom: 1px solid rgba(80,160,255,.18);
    cursor: move;
    user-select: none;
    background: rgba(10,18,40,.60);
  }
  /* Dot de status */
  #fry-live .dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: #ff3b5c;
    box-shadow: 0 0 7px #ff3b5c;
    animation: fryPulse 1.2s infinite;
    flex-shrink: 0;
  }
  #fry-live .dot.off { background: #445; box-shadow: none; animation: none; }
  #fry-live header .fry-title { flex: 1; font-size: 10px; color: #93c5fd; }

  /* ── Botões do header ── */
  #fry-live .fry-btn {
    background: none;
    border: 1px solid rgba(80,160,255,.25);
    color: #93c5fd;
    border-radius: 6px;
    font-size: 11px;
    width: 22px; height: 22px;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer;
    transition: background .2s, border-color .2s;
    flex-shrink: 0;
  }
  #fry-live .fry-btn:hover { background: rgba(80,160,255,.20); border-color: rgba(80,160,255,.55); }

  /* ── Menu de docking ── */
  #fry-dock-menu {
    position: absolute;
    top: 34px; right: 0;
    width: 148px;
    background: rgba(6,10,22,.97);
    backdrop-filter: blur(16px);
    border: 1px solid rgba(80,160,255,.25);
    border-radius: 10px;
    padding: 6px;
    z-index: 9001;
    display: none;
    box-shadow: 0 8px 24px rgba(0,0,0,.7);
  }
  #fry-dock-menu.open { display: block; }
  #fry-dock-menu button {
    display: flex; align-items: center; gap: 7px;
    width: 100%; padding: 6px 8px;
    background: none; border: none; border-radius: 6px;
    color: #93c5fd; font-size: 10px; font-family: inherit;
    cursor: pointer; transition: background .15s;
    text-align: left; letter-spacing: .06em;
  }
  #fry-dock-menu button:hover { background: rgba(80,160,255,.18); }
  #fry-dock-menu hr { border: none; border-top: 1px solid rgba(80,160,255,.15); margin: 4px 0; }

  /* ── Área de vídeo ── */
  #fry-live .view {
    position: relative;
    background: #000;
    aspect-ratio: 16/9;
    overflow: hidden;
  }
  #fry-live img { width: 100%; height: 100%; object-fit: contain; display: block; }
  #fry-live .msg {
    position: absolute; inset: 0;
    display: flex; align-items: center; justify-content: center;
    text-align: center; padding: 20px;
    font-size: 11px; line-height: 1.6; color: #ffb4c0;
  }

  /* ── Pílula flutuante (minimizado) ── */
  #fry-mini-pill {
    position: fixed;
    bottom: 24px; left: 24px;
    z-index: 9000;
    display: none;
    align-items: center;
    gap: 7px;
    padding: 7px 14px;
    background: rgba(6,10,22,.88);
    backdrop-filter: blur(14px);
    border: 1px solid rgba(80,160,255,.30);
    border-radius: 9999px;
    font: 600 10px 'JetBrains Mono', Consolas, monospace;
    letter-spacing: .1em;
    color: #93c5fd;
    cursor: pointer;
    box-shadow: 0 0 16px rgba(40,120,255,.22);
    transition: background .2s, box-shadow .2s;
  }
  #fry-mini-pill:hover { background: rgba(20,40,80,.95); box-shadow: 0 0 22px rgba(59,130,246,.40); }
  #fry-mini-pill .fry-mini-dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: #ff3b5c;
    box-shadow: 0 0 6px #ff3b5c;
    animation: fryPulse 1.2s infinite;
  }

  /* ── Toggle de abertura inicial ── */
  #fry-live-toggle {
    position: fixed;
    bottom: 24px; left: 24px;
    z-index: 9000;
    background: rgba(6,12,28,.78);
    border: 1px solid rgba(80,160,255,.28);
    color: #93c5fd;
    border-radius: 9999px;
    padding: 6px 14px;
    font: 600 10px 'JetBrains Mono', Consolas, monospace;
    letter-spacing: .1em;
    cursor: pointer;
    box-shadow: 0 0 14px rgba(40,120,255,.18);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    transition: all .2s ease;
    display: flex; align-items: center; gap: 6px;
  }
  #fry-live-toggle:hover {
    background: rgba(20,40,80,.90);
    border-color: rgba(120,190,255,.55);
    color: #fff;
    box-shadow: 0 0 20px rgba(59,130,246,.38);
  }

  @keyframes fryPulse { 0%,100%{opacity:1}50%{opacity:.35} }

  @media (max-width: 1024px) {
    #fry-live { width: calc(100vw - 32px); bottom: 90px; left: 16px; right: 16px; }
    #fry-mini-pill { bottom: 90px; left: 16px; }
    #fry-live-toggle { bottom: 90px; left: 16px; }
  }`;

  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  /* ── Estrutura HTML da janela ── */
  const panel = document.createElement("div");
  panel.id = "fry-live";
  panel.className = "fry-hidden";
  panel.innerHTML = `
    <header id="fry-live-head">
      <i class="dot off" id="fry-live-dot"></i>
      <span class="fry-title">TELA AO VIVO · F.R.Y.I.VS</span>
      <button class="fry-btn" id="fry-live-size" title="Expandir / Reduzir">⤢</button>
      <button class="fry-btn" id="fry-live-min"  title="Minimizar">─</button>
      <div style="position:relative">
        <button class="fry-btn" id="fry-live-dock" title="Acoplar em canto">⊞</button>
        <div id="fry-dock-menu">
          <button id="fry-dock-bl">↙ Inferior Esquerdo</button>
          <button id="fry-dock-br">↘ Inferior Direito</button>
          <button id="fry-dock-tl">↖ Superior Esquerdo</button>
          <button id="fry-dock-tr">↗ Superior Direito</button>
          <hr/>
          <button id="fry-dock-free">⊹ Livre (arrastar)</button>
        </div>
      </div>
      <button class="fry-btn" id="fry-live-close" title="Fechar">✕</button>
    </header>
    <div class="view">
      <img id="fry-live-img" alt="Tela ao vivo da área de trabalho"/>
      <div class="msg" id="fry-live-msg" style="display:none"></div>
    </div>`;
  document.body.appendChild(panel);

  /* ── Pílula minimizada ── */
  const miniPill = document.createElement("button");
  miniPill.id = "fry-mini-pill";
  miniPill.innerHTML = `<span class="fry-mini-dot"></span>AO VIVO · MINIMIZADO`;
  document.body.appendChild(miniPill);

  /* ── Botão inicial de abertura (controlado pelo CommandRail React) ── */
  const toggle = document.createElement("button");
  toggle.id = "fry-live-toggle";
  toggle.style.display = "none";
  toggle.innerHTML = `◉ TELA AO VIVO`;
  document.body.appendChild(toggle);

  function getStreamUrl() {
    let token = "";
    try {
      token = sessionStorage.getItem("fryivs_e2ee_session_token") || "";
    } catch (e) {}
    const qs = token ? `&e2ee_token=${encodeURIComponent(token)}` : "";
    return "/api/screen/stream?fps=6&t=" + Date.now() + qs;
  }

  /* ── Referências ── */
  const img   = panel.querySelector("#fry-live-img");
  const msg   = panel.querySelector("#fry-live-msg");
  const dot   = panel.querySelector("#fry-live-dot");
  const dockMenu = panel.querySelector("#fry-dock-menu");
  let aberto     = false;
  let minimizado = false;

  /* ── Posições de acoplamento (respeitando CommandRail de 62px à esquerda) ── */
  const DOCK = {
    bl: () => ({ bottom: "24px", left: "84px",   top: "auto", right: "auto" }),
    br: () => ({ bottom: "24px", right: "24px",  top: "auto", left: "auto"  }),
    tl: () => ({ top: "76px",   left: "84px",   bottom: "auto", right: "auto" }),
    tr: () => ({ top: "76px",   right: "24px",  bottom: "auto", left: "auto"  }),
  };
  function aplicarDock(pos) {
    const s = panel.style;
    s.top = ""; s.bottom = ""; s.left = ""; s.right = "";
    Object.assign(s, pos());
    // Sincroniza pílula com mesma posição
    const ms = miniPill.style;
    ms.top = s.top; ms.bottom = s.bottom; ms.left = s.left; ms.right = s.right;
  }
  // Posição padrão: inferior esquerdo
  aplicarDock(DOCK.bl);

  function notifyState() {
    window.dispatchEvent(
      new CustomEvent("fryvis-live-screen-change", {
        detail: { active: aberto && !minimizado, open: aberto, minimized: minimizado },
      }),
    );
  }

  /* ── Abrir ── */
  async function abrir() {
    aberto = true;
    minimizado = false;
    panel.classList.remove("fry-hidden");
    miniPill.style.display  = "none";
    toggle.style.display    = "none";
    notifyState();
    try {
      const r = await fetch("/api/screen/status");
      const s = await r.json();
      if (!s.screen_available) {
        msg.textContent = s.detail;
        msg.style.display = "flex";
        dot.classList.add("off");
        return;
      }
    } catch (e) { /* tenta o stream mesmo assim */ }
    msg.style.display = "none";
    img.src = getStreamUrl();
    dot.classList.remove("off");
  }

  /* ── Fechar ── */
  function fechar() {
    aberto     = false;
    minimizado = false;
    img.removeAttribute("src");
    panel.classList.add("fry-hidden");
    miniPill.style.display = "none";
    toggle.style.display   = "none";
    dot.classList.add("off");
    notifyState();
  }

  /* ── Minimizar (pílula) ── */
  function minimizar() {
    if (!aberto) return;
    minimizado = true;
    img.removeAttribute("src"); // libera CPU/rede
    panel.classList.add("fry-hidden");
    miniPill.style.display = "flex";
    dot.classList.add("off");
    notifyState();
  }

  /* ── Restaurar da pílula ── */
  function restaurar() {
    minimizado = false;
    miniPill.style.display = "none";
    panel.classList.remove("fry-hidden");
    msg.style.display = "none";
    img.src = getStreamUrl();
    dot.classList.remove("off");
    notifyState();
  }

  window.__fryvisLiveScreen = {
    open: abrir,
    close: fechar,
    toggle: () => {
      if (aberto && !minimizado) fechar();
      else if (minimizado) restaurar();
      else abrir();
    },
    isActive: () => aberto && !minimizado,
  };

  /* ── Eventos dos botões ── */
  toggle.onclick = abrir;
  miniPill.onclick = restaurar;
  panel.querySelector("#fry-live-close").onclick = fechar;
  panel.querySelector("#fry-live-min").onclick   = minimizar;
  panel.querySelector("#fry-live-size").onclick  = () => panel.classList.toggle("fry-big");

  const dockBtn = panel.querySelector("#fry-live-dock");
  dockBtn.onclick = (e) => {
    e.stopPropagation();
    dockMenu.classList.toggle("open");
  };
  document.addEventListener("click", () => dockMenu.classList.remove("open"));

  panel.querySelector("#fry-dock-bl").onclick   = () => { aplicarDock(DOCK.bl); dockMenu.classList.remove("open"); };
  panel.querySelector("#fry-dock-br").onclick   = () => { aplicarDock(DOCK.br); dockMenu.classList.remove("open"); };
  panel.querySelector("#fry-dock-tl").onclick   = () => { aplicarDock(DOCK.tl); dockMenu.classList.remove("open"); };
  panel.querySelector("#fry-dock-tr").onclick   = () => { aplicarDock(DOCK.tr); dockMenu.classList.remove("open"); };
  panel.querySelector("#fry-dock-free").onclick = () => { dockMenu.classList.remove("open"); }; // só fecha o menu; usuário usa arrastar

  /* ── Abre automaticamente quando a IA executar ação visual ── */
  const GATILHOS = /navegador|edge|chrome|pesquis|google|youtube|word|excel|planilha|documento|aberto|abrindo/i;
  function verificarTexto(t) {
    if (!aberto && !minimizado && t && GATILHOS.test(t)) abrir();
  }

  const fetchOriginal = window.fetch;
  window.fetch = async function (...args) {
    const resp = await fetchOriginal.apply(this, args);
    try {
      const url = String(args[0] && args[0].url ? args[0].url : args[0]);
      if (/\/api\/(chat|voice\/listen)/.test(url)) {
        resp.clone().json().then((d) => {
          const tools = d && (d.tools_executed || d.tools || []);
          if (tools && tools.length) {
            if (minimizado) restaurar();
            else if (!aberto) abrir();
          } else {
            verificarTexto(d && (d.response || d.resposta));
          }
        }).catch(() => {});
      }
    } catch (e) {}
    return resp;
  };

  /* ── Arrastar pelo cabeçalho ── */
  const head = panel.querySelector("#fry-live-head");
  let dx = 0, dy = 0, arrastando = false;
  head.addEventListener("mousedown", (e) => {
    if (e.target.tagName === "BUTTON" || e.target.closest("#fry-dock-menu")) return;
    arrastando = true;
    const r = panel.getBoundingClientRect();
    dx = e.clientX - r.left;
    dy = e.clientY - r.top;
  });
  window.addEventListener("mousemove", (e) => {
    if (!arrastando) return;
    panel.style.left   = (e.clientX - dx) + "px";
    panel.style.top    = (e.clientY - dy) + "px";
    panel.style.right  = "auto";
    panel.style.bottom = "auto";
    // Sincroniza pílula com mesma posição ao arrastar
    miniPill.style.left   = panel.style.left;
    miniPill.style.top    = panel.style.top;
    miniPill.style.right  = "auto";
    miniPill.style.bottom = "auto";
  });
  window.addEventListener("mouseup", () => (arrastando = false));
})();
