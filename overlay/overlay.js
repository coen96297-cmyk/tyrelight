/* tyrelight overlay client: one WebSocket, ~20 frames/s, plain DOM updates. */
(() => {
  const params = new URLSearchParams(location.search);
  if (params.get("bg")) document.body.classList.add("solid");
  if (params.get("scale")) document.documentElement.style.zoom = params.get("scale");
  const wsUrl = params.get("ws") || `ws://${location.hostname || "127.0.0.1"}:${params.get("wsport") || 8765}/`;

  const $ = (id) => document.getElementById(id);
  const overlay = $("overlay");
  const ledsEl = $("leds");
  const tyreEls = [...document.querySelectorAll(".tyre")];
  let ledEls = [];

  const fmtLap = (ms) => {
    if (!ms || ms <= 0) return "—";
    const m = Math.floor(ms / 60000);
    const s = ((ms % 60000) / 1000).toFixed(3).padStart(6, "0");
    return `${m}:${s}`;
  };
  const fmtDelta = (ms) => {
    const sign = ms < 0 ? "−" : "+";
    return `${sign}${(Math.abs(ms) / 1000).toFixed(2)}`;
  };

  function buildLeds(count, layout) {
    ledsEl.innerHTML = "";
    ledEls = [];
    for (let i = 0; i < count; i++) {
      const el = document.createElement("span");
      el.className = "led";
      // Small gap between tyre groups so the strip reads as four blocks.
      if (i > 0 && layout[i] !== layout[i - 1]) el.classList.add("gap");
      ledsEl.appendChild(el);
      ledEls.push(el);
    }
  }

  function render(d) {
    overlay.dataset.live = String(d.live);
    $("status").textContent = d.live
      ? (d.wheel.connected ? `live · LEDs on ${d.wheel.port}` : "live · overlay only")
      : "waiting for telemetry";
    $("car").textContent = d.car || "—";
    $("track").textContent = d.track || "—";
    $("compound").textContent = d.compound || "—";
    $("speed").textContent = Math.round(d.speedKmh);
    $("gear").textContent = d.gear === 0 ? "N" : d.gear < 0 ? "R" : d.gear;

    // LEDs mirror exactly what the wheel is showing.
    if (ledEls.length !== d.leds.count) buildLeds(d.leds.count, d.leds.layout);
    d.leds.colours.forEach(([r, g, b], i) => {
      const el = ledEls[i];
      const on = d.leds.lit[i] && (r || g || b);
      el.classList.toggle("on", !!on);
      el.style.setProperty("--led", `rgb(${r},${g},${b})`);
    });

    d.tyres.forEach((t, i) => {
      const el = tyreEls[i];
      el.dataset.cond = t.condition;
      el.querySelector(".temp").textContent = Math.round(t.core);
      el.querySelector(".cond").textContent = t.condition;
      el.querySelector(".detail").textContent =
        `I ${Math.round(t.inner)}  M ${Math.round(t.middle)}  O ${Math.round(t.outer)}   ${t.pressure.toFixed(1)} psi   wear ${Math.round(t.wear)}%`;
    });

    const dt = $("deltaTile");
    if (d.delta.ms === null || d.delta.ms === undefined) {
      $("delta").textContent = "—";
      $("deltaFoot").textContent = d.delta.refLapMs ? "in pit / no reference yet" : "complete a clean lap to set a reference";
      dt.classList.remove("ahead", "behind");
    } else {
      $("delta").textContent = fmtDelta(d.delta.ms);
      $("deltaFoot").textContent = `vs ${fmtLap(d.delta.refLapMs)}`;
      dt.classList.toggle("ahead", d.delta.ms < 0);
      dt.classList.toggle("behind", d.delta.ms > 0);
    }

    const f = d.fuel;
    $("fuel").textContent = f.litres.toFixed(1);
    $("fuelFoot").textContent = f.perLap
      ? `${f.perLap.toFixed(2)} L/lap · ${f.lapsLeft.toFixed(1)} laps left`
      : "measuring consumption…";
    $("fuelBar").style.width = `${f.maxLitres ? Math.min(100, (100 * f.litres) / f.maxLitres) : 0}%`;
    $("fuelTile").classList.toggle("warning", !!f.warning);

    $("lapNo").textContent = d.lap.completed + 1;
    $("lapTime").textContent = fmtLap(d.lap.currentMs);
    $("lastTime").textContent = fmtLap(d.lap.lastMs);
    $("bestTime").textContent = fmtLap(d.lap.bestMs);
    $("window").textContent = `ideal ${d.window.cold_below}–${d.window.hot_above}° · overheat ≥${d.window.overheat_above}°`;
  }

  function connect() {
    const ws = new WebSocket(wsUrl);
    ws.onmessage = (ev) => {
      try { render(JSON.parse(ev.data)); } catch (e) { console.error("bad frame", e); }
    };
    ws.onclose = () => {
      overlay.dataset.live = "false";
      $("status").textContent = "reconnecting…";
      setTimeout(connect, 1000);
    };
    ws.onerror = () => ws.close();
  }
  connect();
})();
