/* DROPZERO landing page interactions. No dependencies. */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const clamp = (v, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));
  const lerp = (a, b, k) => a + (b - a) * k;
  const seg = (t, a, b) => clamp((t - a) / (b - a));
  const easeInOut = (k) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2);
  const easeOut = (k) => 1 - Math.pow(1 - k, 3);
  const easeIn = (k) => k * k * k;
  const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.round(s % 60)).padStart(2, "0")}`;

  // Deterministic PRNG so the decorative layout is identical on every load.
  function mulberry32(seed) {
    return () => {
      seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  const cardInner = (progress) =>
    `<span class="vc-chip"></span><span class="vc-stripes"></span><span class="vc-bar"><i style="width:${progress}%"></i></span>`;

  /* ============================== HERO: headline reveal ============================== */

  const hero = $(".hero");
  const title = $("[data-reveal-words]");
  const words = title.textContent.trim().split(/\s+/);
  title.setAttribute("aria-label", title.textContent.trim());
  title.innerHTML = words
    .map((w, i) => `<span class="w" aria-hidden="true" style="transition-delay:${i * 90}ms">${w}</span>`)
    .join(" ");
  // Flush the hidden start state, then reveal. A timer (not rAF) so it also fires in throttled/background tabs.
  void title.offsetWidth;
  setTimeout(() => {
    title.classList.add("is-in");
    hero.classList.add("is-ready");
  }, 80);

  /* ============================== HERO: card pile ============================== */

  // x: card centre as % of pile width · y: bottom offset as % of pile height
  const PILE = [
    { v: "copper", x: 3, y: 24, rx: 56, ry: 0, rz: -8, s: 1.05, z: 1, p: 30 },
    { v: "graphite", x: -3, y: -12, rx: 24, ry: 0, rz: 14, s: 1, z: 2, p: 65 },
    { v: "black", x: 17, y: 20, rx: 14, ry: -18, rz: -28, s: 1.05, z: 3, p: 15 },
    { v: "graphite", x: 30, y: 2, rx: 56, ry: 0, rz: 6, s: 1, z: 4, p: 80 },
    { v: "silver", x: 41, y: -16, rx: 60, ry: 0, rz: -4, s: 1.1, z: 6, p: 50 },
    { v: "black", x: 57, y: 6, rx: 58, ry: 0, rz: 10, s: 1, z: 5, p: 22 },
    { v: "copper", x: 65, y: -14, rx: 62, ry: 0, rz: -6, s: 1.1, z: 7, p: 70 },
    { v: "silver", x: 78, y: 22, rx: 18, ry: 20, rz: 24, s: 1, z: 3, p: 40 },
    { v: "graphite", x: 88, y: -8, rx: 56, ry: 0, rz: -10, s: 1.05, z: 4, p: 90 },
    { v: "white", x: 99, y: 14, rx: 50, ry: 0, rz: 16, s: 0.95, z: 2, p: 55 },
  ];
  $("#pile").innerHTML = PILE.map((c) =>
    `<div class="vcard vc-${c.v}" style="left:calc(${c.x}% - var(--cw) / 2);bottom:${c.y}%;z-index:${c.z};` +
    `transform:perspective(900px) rotateX(${c.rx}deg) rotateY(${c.ry}deg) rotateZ(${c.rz}deg) scale(${c.s})">${cardInner(c.p)}</div>`
  ).join("");

  /* ============================== HERO: claw ============================== */

  // Copper spring next to the rod: back half-arcs first, front half-arcs over the top.
  let dBack = "", dFront = "";
  for (let y = -900; y <= 186; y += 8) {
    dBack += `M320 ${y} A16 5 0 0 1 352 ${y} `;
    dFront += `M320 ${y} A16 5 0 0 0 352 ${y} `;
  }
  $("#coil-back").innerHTML = `<path d="${dBack}" fill="none" stroke="#4a1c08" stroke-width="3.2"/>`;
  $("#coil-front").innerHTML = `<path d="${dFront}" fill="none" stroke="url(#g-copper)" stroke-width="3.6" stroke-linecap="round"/>`;

  const stage = $(".stage");
  const rig = $("#rig");
  const claw = $("#claw");
  const armL = $("#arm-l");
  const armR = $("#arm-r");
  const target = $("#target");

  const fitRig = () => rig.style.setProperty("--rig-s", (stage.clientHeight / 800).toFixed(4));
  fitRig();
  new ResizeObserver(fitRig).observe(stage);

  // Rig coordinates (600×800). Arms pivot on the hub at (300, 266).
  const T = 10000;
  const TY_GRAB = 270;      // claw drop needed to reach the resting card
  const TY_UP = -10;        // lifted height
  const CARD_REST_Y = 690;  // resting card centre
  const CARD_IN_CLAW = 420; // card centre relative to an un-moved claw when held
  const REST = { rx: 58, rz: -12 };
  const HELD = { rx: 8, rz: -7 };
  const bob = (t) => 6 * Math.sin((t - 5200) / 500);

  function pose(t) {
    let ty = 0, a = 0, card = { dy: 0, ...REST }, flag = false;
    const held = (k, tyNow) => ({
      dy: CARD_IN_CLAW + tyNow - CARD_REST_Y,
      rx: lerp(REST.rx, HELD.rx, k),
      rz: lerp(REST.rz, HELD.rz, k),
    });

    if (t < 1400) {
      a = 1.2 * Math.sin(t / 400);
    } else if (t < 3000) {
      const k = easeInOut(seg(t, 1400, 3000));
      ty = TY_GRAB * k;
      a = lerp(1.2 * Math.sin(1400 / 400), 7, k);
    } else if (t < 3500) {
      ty = TY_GRAB;
      a = lerp(7, -6, easeOut(seg(t, 3000, 3500)));
    } else if (t < 5200) {
      const k = easeInOut(seg(t, 3500, 5200));
      ty = lerp(TY_GRAB, TY_UP, k);
      a = -6;
      card = held(k, ty);
    } else if (t < 8300) {
      ty = TY_UP + bob(t);
      a = -6;
      card = held(1, ty);
      flag = t < 8000;
    } else {
      const tyRelease = TY_UP + bob(8300);
      a = t < 9300 ? lerp(-6, 7, easeOut(seg(t, 8300, 8600))) : lerp(7, 0, easeInOut(seg(t, 9300, 10000)));
      ty = lerp(tyRelease, 0, easeInOut(seg(t, 8600, 9300)));
      const from = held(1, tyRelease);
      const k = easeIn(seg(t, 8400, 9100));
      card = { dy: lerp(from.dy, 0, k), rx: lerp(from.rx, REST.rx, k), rz: lerp(from.rz, REST.rz, k) };
    }
    return { ty, a, card, flag };
  }

  function applyPose({ ty, a, card, flag }) {
    claw.setAttribute("transform", `translate(0 ${ty.toFixed(2)})`);
    armL.setAttribute("transform", `rotate(${a.toFixed(3)} 300 266)`);
    armR.setAttribute("transform", `rotate(${(-a).toFixed(3)} 300 266)`);
    target.style.transform = `translateY(${card.dy.toFixed(2)}px) perspective(900px) rotateX(${card.rx.toFixed(2)}deg) rotateZ(${card.rz.toFixed(2)}deg)`;
    target.classList.toggle("show-flag", flag);
  }

  if (reduceMotion) {
    applyPose(pose(6000));
  } else {
    let raf = 0, t0 = performance.now() - 200;
    const tick = (now) => {
      applyPose(pose((now - t0) % T));
      raf = requestAnimationFrame(tick);
    };
    new IntersectionObserver(([entry]) => {
      cancelAnimationFrame(raf);
      if (entry.isIntersecting) raf = requestAnimationFrame(tick);
    }).observe(hero);
  }

  /* ============================== SCAN TRANSITION ============================== */

  const scan = $("#scan");
  const field = $("#scan-field");
  const rnd = mulberry32(7);
  const VARIANTS = ["silver", "graphite", "black", "copper", "white"];
  const flyers = Array.from({ length: 28 }, (_, i) => {
    let x = (rnd() * 2 - 1) * 820;
    const y = (rnd() * 2 - 1) * 420;
    if (Math.abs(x) < 300 && Math.abs(y) < 160) x = Math.sign(x || 1) * (300 + rnd() * 240);
    return { x, y, z: 200 - rnd() * 2900, rx: (rnd() * 2 - 1) * 60, ry: (rnd() * 2 - 1) * 50, rz: (rnd() * 2 - 1) * 40, v: VARIANTS[i % VARIANTS.length] };
  });
  field.innerHTML =
    flyers.map((c, i) => `<div class="vcard vc-${c.v}">${cardInner(20 + ((i * 37) % 70))}</div>`).join("") +
    `<div class="vcard vcard-target vc-hero">${cardInner(40)}</div>`;
  const flyerEls = [...field.children];
  const heroCard = flyerEls.pop();

  for (const line of scan.querySelectorAll("[data-reveal-letters]")) {
    const text = line.textContent;
    line.setAttribute("aria-label", text);
    line.innerHTML = [...text].map((ch, i) => `<span class="ch" aria-hidden="true" style="--i:${i}">${ch}</span>`).join("");
  }
  const line1 = $(".scan-line-1");
  const line2 = $(".scan-line-2");

  function updateScan() {
    const rect = scan.getBoundingClientRect();
    const travel = scan.offsetHeight - innerHeight;
    const p = reduceMotion ? 1 : clamp(-rect.top / travel);
    const spread = Math.min(1, field.clientWidth / 1400);

    flyers.forEach((c, i) => {
      const z = c.z + p * 2600;
      const opacity = z > 250 ? clamp(1 - (z - 250) / 350) : clamp((z + 2900) / 900);
      const el = flyerEls[i];
      el.style.opacity = opacity.toFixed(3);
      el.style.transform = `translate3d(${(c.x * spread).toFixed(1)}px, ${(c.y * spread).toFixed(1)}px, ${z.toFixed(1)}px) rotateX(${(c.rx + p * 40).toFixed(1)}deg) rotateY(${c.ry.toFixed(1)}deg) rotateZ(${(c.rz + p * 30).toFixed(1)}deg)`;
    });

    // The one orange segment drifts forward and settles under the final line.
    const k = easeOut(seg(p, 0.35, 1));
    heroCard.style.opacity = clamp(p * 3 - 0.6).toFixed(3);
    heroCard.style.transform = `translate3d(0, ${(lerp(60, 170, k) * spread + 30).toFixed(1)}px, ${lerp(-2600, 60, k).toFixed(1)}px) rotateX(${lerp(60, 16, k).toFixed(1)}deg) rotateZ(${lerp(-30, -6, k).toFixed(1)}deg)`;

    line1.classList.toggle("is-in", p > 0.04 && p < 0.5);
    line2.classList.toggle("is-in", p >= 0.56);
  }

  let scanQueued = false;
  const queueScan = () => {
    if (scanQueued) return;
    scanQueued = true;
    requestAnimationFrame(() => { scanQueued = false; updateScan(); });
  };
  addEventListener("scroll", queueScan, { passive: true });
  addEventListener("resize", queueScan);
  updateScan();

  /* ============================== PRODUCT MOCK ============================== */
  // Illustrative data only, built with the same survival formulation the product uses:
  // R(0) = 1, R(t) = R(t-1) * (1 - p_drop(t)). Not a real prediction.

  const DUR = 312;            // 05:12
  const CUT = [123, 140];     // 02:03–02:20

  const ZONES = [
    {
      id: "intro", a: 0, b: 45, sev: "med", sevLabel: "Medium",
      reason: "Intro runs 45 s before the hook",
      evidence: [
        "The title's promise (“AI agent”) is first addressed at 00:44",
        "Speech rate 1.9 words/s, below this video's average of 2.6",
        "6 filler words in the first 30 s",
      ],
      action: { type: "Rewrite", text: "Replace 00:00–00:15 with a one-line hook that shows the finished agent." },
    },
    {
      id: "rep", a: 123, b: 151, sev: "high", sevLabel: "High",
      reason: "Repeats the explanation from 01:10–01:30",
      evidence: [
        "Semantic similarity 0.89 to 01:10–01:30",
        "Low new information for 28 s",
        "No visual change in this range",
      ],
      action: { type: "Cut + move", text: "Cut 02:03–02:20, then move the demo from 03:18 to 02:21." },
      cut: CUT,
    },
    {
      id: "pay", a: 185, b: 214, sev: "high", sevLabel: "High",
      reason: "Demo promised at 00:12, first shown at 03:18",
      evidence: [
        "Payoff delay of 3 m 06 s after the promise",
        "The open question from the hook is still unanswered",
        "Attention debt rising since 02:40",
      ],
      action: { type: "Move", text: "Preview the result at 03:05, then explain how it works." },
    },
  ];

  function hazard(t, simulated) {
    let h = 0.0024 + 0.012 * Math.exp(-t / 12); // category baseline: early drop
    if (t >= 15 && t < 45) h += simulated ? 0.0012 : 0.003;
    if (t >= 123 && t < 151) h += simulated ? 0.0015 : 0.0065;
    if (t >= 185 && t < 214) h += simulated ? 0.0015 : 0.0055;
    return h;
  }
  function curve(simulated) {
    const out = [];
    let r = 1;
    for (let t = 0; t <= DUR; t++) {
      if (simulated && t >= CUT[0] && t < CUT[1]) continue; // removed seconds
      out.push(r);
      r *= 1 - hazard(t, simulated);
    }
    return out;
  }
  const SERIES = {
    original: { id: "original", label: "Original", color: "var(--s-pred)", data: curve(false) },
    simulated: { id: "simulated", label: "Simulated", color: "var(--s-sim)", data: curve(true) },
  };

  const state = { view: "original", zone: "rep", showCut: false };
  const chartEl = $("#chart");
  const svg = $("#chart-svg");
  const tooltip = $("#tooltip");
  const legend = $("#legend");
  const chartTitle = $("#chart-title");
  let geom = null;

  const activeSeries = () => (state.view === "simulated" ? [SERIES.original, SERIES.simulated] : [SERIES.original]);

  function renderChart() {
    const W = Math.max(280, chartEl.clientWidth);
    const H = W < 560 ? 230 : 290;
    const m = { l: 42, r: 40, t: 22, b: 28 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const x = (t) => m.l + (t / DUR) * iw;
    const y = (v) => m.t + (1 - v) * ih;
    geom = { W, H, m, iw, ih, x, y };

    let s = `<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="2" height="6" fill="rgba(255,91,31,.45)"/></pattern></defs>`;

    for (const z of ZONES) {
      const sel = z.id === state.zone;
      s += `<rect x="${x(z.a)}" y="${m.t}" width="${x(z.b) - x(z.a)}" height="${ih}" fill="var(--risk-${z.sev})" fill-opacity="${sel ? 0.16 : 0.07}"/>`;
      if (sel) s += `<rect x="${x(z.a)}" y="${m.t - 2}" width="${x(z.b) - x(z.a)}" height="2" fill="var(--risk-${z.sev})"/>`;
      s += `<text x="${x(z.a) + 5}" y="${m.t - 7}">${z.sevLabel}</text>`;
    }
    for (const v of [0, 0.25, 0.5, 0.75, 1]) {
      s += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}" stroke="rgba(255,255,255,.07)"/>`;
      s += `<text x="${m.l - 8}" y="${y(v) + 4}" text-anchor="end">${v * 100}%</text>`;
    }
    for (let t = 0; t <= DUR; t += 60) s += `<text x="${x(t)}" y="${H - 8}" text-anchor="middle">${fmt(t)}</text>`;

    if (state.showCut) {
      s += `<rect x="${x(CUT[0])}" y="${m.t}" width="${x(CUT[1]) - x(CUT[0])}" height="${ih}" fill="url(#hatch)" stroke="var(--accent)" stroke-width="1.5"/>`;
      s += `<text x="${x(CUT[1]) + 6}" y="${m.t + 14}" style="fill:var(--ink)">Cut 02:03–02:20</text>`;
    }

    for (const se of activeSeries()) {
      const d = se.data.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join("");
      s += `<path d="${d}" fill="none" stroke="${se.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
      const end = se.data.length - 1;
      s += `<circle cx="${x(end)}" cy="${y(se.data[end])}" r="4" fill="${se.color}" stroke="var(--panel)" stroke-width="2"/>`;
      s += `<text x="${x(end) + 8}" y="${y(se.data[end]) + 4}" style="fill:var(--ink-2)">${Math.round(se.data[end] * 100)}%</text>`;
    }

    s += `<line id="xh" y1="${m.t}" y2="${m.t + ih}" stroke="rgba(255,255,255,.35)" visibility="hidden"/><g id="xh-dots"></g>`;
    s += `<rect id="hit" x="${m.l}" y="${m.t}" width="${iw}" height="${ih}" fill="transparent"/>`;

    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);
    svg.innerHTML = s;
  }

  function onHover(ev) {
    if (!geom) return;
    const box = svg.getBoundingClientRect();
    const px = ev.clientX - box.left;
    const t = Math.round(clamp((px - geom.m.l) / geom.iw) * DUR);
    const cx = geom.x(t);
    const xh = svg.querySelector("#xh");
    xh.setAttribute("x1", cx);
    xh.setAttribute("x2", cx);
    xh.setAttribute("visibility", "visible");

    let dots = "", rows = "";
    for (const se of activeSeries()) {
      if (t >= se.data.length) continue;
      dots += `<circle cx="${cx}" cy="${geom.y(se.data[t])}" r="4" fill="${se.color}" stroke="var(--panel)" stroke-width="2"/>`;
      rows += `<div class="tt-row"><i class="key" style="background:${se.color}"></i>${se.label}<b>${Math.round(se.data[t] * 100)}%</b></div>`;
    }
    svg.querySelector("#xh-dots").innerHTML = dots;
    const zone = ZONES.find((z) => t >= z.a && t < z.b);
    tooltip.innerHTML =
      `<div class="tt-time">${fmt(t)}</div>${rows}` +
      (zone ? `<div class="tt-row" style="margin-top:4px"><span class="sev sev-${zone.sev}">${zone.sevLabel}</span>${zone.reason}</div>` : "");
    tooltip.hidden = false;
    const tw = tooltip.offsetWidth;
    tooltip.style.left = `${cx + 14 + tw > geom.W ? cx - 14 - tw : cx + 14}px`;
    tooltip.style.top = `${geom.m.t + 6}px`;
  }
  function onLeave() {
    tooltip.hidden = true;
    const xh = svg.querySelector("#xh");
    if (xh) xh.setAttribute("visibility", "hidden");
    const dots = svg.querySelector("#xh-dots");
    if (dots) dots.innerHTML = "";
  }
  svg.addEventListener("pointermove", onHover);
  svg.addEventListener("pointerleave", onLeave);

  function renderZones() {
    $("#zones").innerHTML = ZONES.map((z) =>
      `<button type="button" role="tab" class="zone-btn" data-zone="${z.id}" aria-selected="${z.id === state.zone}">` +
      `<span class="sev sev-${z.sev}">${z.sevLabel.toUpperCase()}</span>${fmt(z.a)}–${fmt(z.b)}</button>`
    ).join("");
  }

  function renderDrawer() {
    const z = ZONES.find((zz) => zz.id === state.zone);
    $("#drawer").innerHTML = `
      <div class="dr-top"><span class="sev sev-${z.sev}">${z.sevLabel.toUpperCase()} RISK</span><span class="dr-time">${fmt(z.a)} – ${fmt(z.b)}</span></div>
      <div>
        <p class="dr-q">Why would I leave?</p>
        <p class="dr-reason">${z.reason}</p>
      </div>
      <ul class="dr-evidence">${z.evidence.map((e) => `<li>${e}</li>`).join("")}</ul>
      <div class="dr-action"><b>${z.action.type}</b>${z.action.text}</div>
      <div class="dr-buttons">
        ${z.cut ? `<button type="button" class="btn btn-ghost" data-act="cut" aria-pressed="${state.showCut}">${state.showCut ? "Hide cut" : "Show me what to cut"}</button>` : ""}
        <button type="button" class="btn btn-solid" data-act="simulate">${state.view === "simulated" ? "Showing simulation" : "Simulate fix"}</button>
      </div>
      <p class="dr-note">Simulation applies all three suggested edits and reruns the model. Model-estimated, not guaranteed.</p>`;
  }

  function renderTable() {
    const sim = state.view === "simulated";
    let rows = "";
    for (let t = 0; t <= DUR; t += 15) {
      const o = Math.round(SERIES.original.data[t] * 100) + "%";
      const s = t < SERIES.simulated.data.length ? Math.round(SERIES.simulated.data[t] * 100) + "%" : "—";
      rows += `<tr><td>${fmt(t)}</td><td>${o}</td>${sim ? `<td>${s}</td>` : ""}</tr>`;
    }
    $("#chart-table").innerHTML =
      `<table><thead><tr><th>Time</th><th>Predicted, original</th>${sim ? "<th>Simulated (model-estimated)</th>" : ""}</tr></thead><tbody>${rows}</tbody></table>`;
  }

  function renderAll() {
    const sim = state.view === "simulated";
    legend.hidden = !sim;
    chartTitle.textContent = sim ? "Predicted audience remaining — original vs simulated" : "Predicted audience remaining";
    for (const b of document.querySelectorAll(".seg-btn")) {
      const on = b.dataset.view === state.view;
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-pressed", on);
    }
    renderChart();
    renderZones();
    renderDrawer();
    renderTable();
  }

  document.addEventListener("click", (ev) => {
    const viewBtn = ev.target.closest(".seg-btn");
    const zoneBtn = ev.target.closest(".zone-btn");
    const actBtn = ev.target.closest("[data-act]");
    if (viewBtn) state.view = viewBtn.dataset.view;
    else if (zoneBtn) { state.zone = zoneBtn.dataset.zone; state.showCut = false; }
    else if (actBtn && actBtn.dataset.act === "cut") state.showCut = !state.showCut;
    else if (actBtn && actBtn.dataset.act === "simulate") state.view = "simulated";
    else return;
    renderAll();
  });

  new ResizeObserver(() => renderChart()).observe(chartEl);
  renderAll();

  /* ============================== VALIDATION SCHEMATIC ============================== */

  (function renderValidation() {
    const W = 520, H = 240, m = { l: 12, r: 12, t: 30, b: 26 };
    const N = 200;
    const x = (i) => m.l + (i / N) * (W - m.l - m.r);
    const y = (v) => m.t + (1 - v) * (H - m.t - m.b);
    const actual = [], predicted = [];
    let ra = 1, rp = 1;
    for (let i = 0; i <= N; i++) {
      actual.push(ra);
      predicted.push(rp);
      ra *= 1 - (0.0022 + 0.02 * Math.exp(-i / 8) + (i >= 60 && i < 70 ? 0.026 : 0) + (i >= 140 && i < 148 ? 0.03 : 0));
      rp *= 1 - (0.0024 + 0.019 * Math.exp(-i / 8) + (i >= 62 && i < 72 ? 0.023 : 0));
    }
    const path = (arr, c) =>
      `<path d="${arr.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join("")}" fill="none" stroke="${c}" stroke-width="2" stroke-linejoin="round"/>`;
    let s = "";
    for (const v of [0, 0.5, 1]) s += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}" stroke="rgba(255,255,255,.07)"/>`;
    s += `<rect x="${x(58)}" y="${m.t}" width="${x(76) - x(58)}" height="${H - m.t - m.b}" fill="rgba(255,255,255,.05)"/>`;
    s += `<rect x="${x(138)}" y="${m.t}" width="${x(152) - x(138)}" height="${H - m.t - m.b}" fill="rgba(255,255,255,.05)"/>`;
    s += path(actual, "var(--s-actual)") + path(predicted, "var(--s-pred)");
    s += `<circle cx="${x(66)}" cy="${y(actual[66])}" r="4" fill="var(--s-actual)" stroke="var(--surface)" stroke-width="2"/>`;
    s += `<circle cx="${x(145)}" cy="${y(actual[145])}" r="4" fill="var(--s-actual)" stroke="var(--surface)" stroke-width="2"/>`;
    s += `<text x="${x(58)}" y="${m.t - 10}">✓ Drop caught</text>`;
    s += `<text x="${x(138)}" y="${m.t - 10}">✕ Drop missed — shown, not hidden</text>`;
    s += `<text x="${m.l}" y="${H - 6}">Start</text><text x="${W - m.r}" y="${H - 6}" text-anchor="end">End</text>`;
    $("#val-svg").innerHTML = s;
  })();
})();
