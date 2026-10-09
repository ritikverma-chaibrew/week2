import { listModels, testProvider } from "./api.js";
import {
  DEFAULT_GAP, DEFAULT_MODELS, MAX_GAP, PROVIDERS, RECOMMENDED_MODELS, ROLES, TTL_LABEL, isRecommendedLocal, modelFor,
  clearKey, clearKeyStatus, gapFor, getKey, getKeyStatus, getSettings, maskKey, saveSettings, setKey, setKeyStatus,
} from "./keystore.js";

const KEYED = {
  aistudio: { label: "Google AI Studio API key", link: "https://aistudio.google.com/apikey", hint: "AIza…" },
};
const INTRO = {
  aistudio: `Use your own free Google AI Studio key with Gemma 4. Works in any browser, nothing to install. The key stays in this browser for ${TTL_LABEL}.`,
  lmstudio: "Fully local and free, no key. Models come from the LM Studio app. The app server must run on the same computer as LM Studio.",
};
// How each task is shown in the model picker.
const TASKS = {
  vision: { icon: "📷", title: "Look at each photo", hint: "Needs a model that can see images" },
  outline: { icon: "🗺️", title: "Plan the plot", hint: "Builds the plan and picks a photo for each part" },
  story: { icon: "✍️", title: "Write and proofread", hint: "Writes every scene, verse or panel, then fixes weak spots" },
};
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const ago = (t) => {
  const s = Math.round((Date.now() - t) / 1000);
  return s < 60 ? "just now" : s < 3600 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`;
};
/** Time left before the key is forgotten, e.g. "4 h 12 min" or "35 min". */
const timeLeft = (ms) => {
  const m = Math.max(0, Math.ceil(ms / 60000)), h = Math.floor(m / 60);
  return h ? `${h} h ${m % 60} min` : `${m} min`;
};

/** Provider tabs, key card (connect/status/stats), a connection test and (folded away) per-task models. */
export function mountSettings(el) {
  el.innerHTML = `
    <div class="seg" role="group" aria-label="How to run the AI" id="tabs">${Object.entries(PROVIDERS)
      .map(([k, v]) => `<button type="button" data-p="${k}">${v}</button>`)
      .join("")}</div>
    <p class="muted" id="intro" style="margin:10px 0 0"></p>
    <div id="keybox" hidden>
      <div id="keyempty">
        <label class="f" for="key"><span id="keylabel"></span> <a id="keylink" target="_blank" rel="noopener">(get one free)</a></label>
        <div class="row"><input id="key" type="password" autocomplete="off" style="flex:1;min-width:200px">
          <button class="btn sm" id="save" type="button">Save key</button></div>
        <p class="muted" id="exp-none" style="margin:6px 0 0">The key is kept in this browser for ${TTL_LABEL} only and never stored on the server.</p>
      </div>
      <div id="keycard" class="keycard" hidden>
        <div class="row" style="justify-content:space-between">
          <span class="pill" id="pill"></span>
          <span class="row"><button class="btn sm" id="connect" type="button">Connect</button>
            <button class="btn sm ghost" id="forget" type="button">Forget</button></span>
        </div>
        <div class="row" style="margin:10px 0 0">
          <code id="keytext"></code>
          <button class="btn sm ghost" id="reveal" type="button">Show</button>
        </div>
        <p class="muted" id="reason" style="margin:8px 0 0"></p>
        <div class="stats" id="stats"></div>
      </div>
    </div>
    <div id="lmbox" hidden>
      <label class="f" for="lmUrl">LM Studio server URL</label>
      <input id="lmUrl" type="url">
    </div>
    <div class="row" style="margin-top:14px">
      <button class="btn sm" id="test" type="button">Test connection</button>
    </div>
    <div class="status" id="msg" role="status"></div>
    <details class="adv" id="adv" open>
      <summary>Advanced settings <span class="muted">(optional: the defaults work well)</span></summary>
      <!-- The pause slider is hidden from the UI; the default pause (30 s on AI Studio) still applies. Remove "hidden" to show it again. -->
      <div class="gap" id="gapbox" hidden>
        <label for="gap">Pause between AI calls: <b id="gapv"></b></label>
        <input type="range" id="gap" min="0" max="${MAX_GAP}" step="5">
        <p class="muted" id="gapnote" style="margin:4px 0 0"></p>
      </div>
      <div class="models">
        <div class="mhead"><b>AI model for each task</b><span class="muted" id="mnote"></span></div>
        <div id="models"></div>
        <div class="row" style="margin-top:12px">
          <button class="btn sm ghost" id="reset" type="button">↺ Use recommended models</button>
          <button class="btn sm ghost" id="load" type="button">⟳ Refresh LM Studio models</button>
        </div>
      </div>
    </details>`;

  const $ = (id) => el.querySelector("#" + id);
  const provider = () => getSettings().provider;
  const changed = () => window.dispatchEvent(new Event("tg:settings"));
  const keyChanged = () => window.dispatchEvent(new Event("tg:key")); // the Create page re-checks if it is ready
  let revealed = false;
  const show = (msg, ok) => {
    $("msg").textContent = msg;
    $("msg").className = "status " + (ok ? "ok" : "err");
  };

  /** Gemma models loaded in LM Studio (fetched from the app; null until loaded). */
  let lmModels = null;

  /** Options for one task's select box: only recommended models, the default marked "recommended". */
  function optionsFor(p, role) {
    if (p === "lmstudio") {
      const auto = { id: "", name: "Auto: first Gemma loaded in LM Studio" };
      return [auto, ...(lmModels || []).map((id) => ({ id, name: id }))];
    }
    return (RECOMMENDED_MODELS[p] || []).map((m) => ({
      id: m.id,
      name: `${m.name} (${m.note})${m.id === DEFAULT_MODELS[p]?.[role] ? " ★" : ""}`,
    }));
  }

  function renderModels() {
    const p = provider();
    $("mnote").textContent =
      p === "lmstudio"
        ? lmModels === null ? "Loading the Gemma models loaded in LM Studio…" : lmModels.length ? "Gemma models loaded in LM Studio." : "No Gemma model is loaded in LM Studio yet. Auto is used."
        : "★ marks the recommended model for each task. It is already selected.";
    $("load").hidden = p !== "lmstudio";
    $("models").innerHTML = ROLES.map(([role]) => {
      const t = TASKS[role], val = modelFor(p, role);
      const opts = optionsFor(p, role);
      if (val && !opts.some((o) => o.id === val)) opts.push({ id: val, name: `${val} (not loaded)` }); // keep an LM Studio pick visible
      return `<div class="mrow">
          <span class="mic" aria-hidden="true">${t.icon}</span>
          <label for="m-${role}"><b>${t.title}</b><span class="muted">${t.hint}</span></label>
          <select id="m-${role}" data-role="${role}">${opts
            .map((o) => `<option value="${esc(o.id)}"${o.id === val ? " selected" : ""}>${esc(o.name)}</option>`)
            .join("")}</select></div>`;
    }).join("");
    $("models").querySelectorAll("select").forEach((sel) =>
      sel.addEventListener("change", () => {
        const cur = getSettings();
        const m = { ...(cur.models[p] || {}) };
        if (sel.value && sel.value !== DEFAULT_MODELS[p]?.[sel.dataset.role]) m[sel.dataset.role] = sel.value;
        else delete m[sel.dataset.role];
        saveSettings({ ...cur, models: { ...cur.models, [p]: m } });
        changed();
      })
    );
  }

  /** LM Studio: fetch the loaded models and keep only Gemma ones. */
  async function loadLmModels(announce = false) {
    try {
      const { models } = await listModels();
      lmModels = models.filter(isRecommendedLocal);
      if (announce) show(`${lmModels.length} Gemma model${lmModels.length === 1 ? "" : "s"} found in LM Studio.`, true);
    } catch (e) {
      lmModels = [];
      if (announce) show(e.message, false);
    }
    if (provider() === "lmstudio") renderModels();
  }

  /** The key card: detected key -> Connect button; shows status (not connected / connected / disconnected) and stats. */
  function renderKey() {
    const p = provider();
    if (!KEYED[p]) return;
    const k = getKey(p);
    const st = getKeyStatus(p);
    if (!k && st.connected) {
      // The key was purged after its lifetime: show that it got disconnected.
      setKeyStatus(p, { connected: false, reason: `The key expired after ${TTL_LABEL} and was removed from this browser.` });
    }
    const st2 = getKeyStatus(p);
    $("keycard").hidden = !k;
    $("keyempty").hidden = !!k;
    $("reason").textContent = "";
    if (!k) {
      if (st2.reason && st2.connected === false)
        $("exp-none").innerHTML = `<b style="color:var(--red)">Key disconnected.</b> ${st2.reason} Paste a key to connect again.`;
      return;
    }
    const state = st2.connected ? "connected" : st2.connected === false && st2.reason ? "disconnected" : "saved";
    $("pill").className = "pill " + state;
    $("pill").textContent = { connected: "● Connected", disconnected: "● Key disconnected", saved: "● Key saved: not checked yet" }[state];
    $("connect").textContent = state === "connected" ? "Re-check" : state === "disconnected" ? "Reconnect" : "Connect";
    $("keytext").textContent = revealed ? k.key : maskKey(k.key);
    $("reveal").textContent = revealed ? "Hide" : "Show";
    if (state === "saved") $("reason").textContent = "Press Connect to check the key with Google.";
    if (state === "disconnected") $("reason").textContent = st2.reason;
    const stat = (label, value) => `<div><span>${label}</span><b>${value}</b></div>`;
    $("stats").innerHTML = [
      stat("Forgotten in", timeLeft(k.exp - Date.now())),
      stat("Gemma models", st2.models ?? "–"),
      stat("Response time", st2.latencyMs ? `${st2.latencyMs} ms` : "–"),
      stat("Last checked", st2.checkedAt ? ago(st2.checkedAt) : "never"),
      stat("Stories made", st2.stories || 0),
      // Hidden from the UI: the number of AI (LLM) calls made with this key. Still counted in app.js recordUsage().
      // stat("AI calls made", st2.calls || 0),
    ].join("");
  }

  /** Slider for the time between AI calls: longer avoids rate limits, shorter finishes sooner. */
  function renderGap() {
    const p = provider(), g = gapFor(p);
    $("gap").value = g;
    $("gapv").textContent = g === 0 ? "none" : `${g} s`;
    $("gapnote").textContent =
      `Default ${DEFAULT_GAP[p] ?? 30} s. A longer pause avoids "too many requests" errors. It is also the wait before a failed step is retried.`;
  }

  function render() {
    const p = provider(), s = getSettings();
    el.querySelectorAll("#tabs button").forEach((b) => {
      b.classList.toggle("on", b.dataset.p === p);
      b.setAttribute("aria-pressed", b.dataset.p === p);
    });
    $("intro").innerHTML = INTRO[p];
    $("keybox").hidden = !KEYED[p];
    if (KEYED[p]) {
      $("keylabel").textContent = KEYED[p].label;
      $("keylink").href = KEYED[p].link;
      $("key").placeholder = KEYED[p].hint;
    }
    $("lmbox").hidden = p !== "lmstudio";
    $("lmUrl").value = s.lmUrl;
    renderGap();
    $("test").textContent = "Test connection";
    $("msg").textContent = "";
    $("msg").className = "status";
    renderModels();
    renderKey();
    if (p === "lmstudio" && lmModels === null) loadLmModels();
  }

  el.querySelectorAll("#tabs button").forEach((b) =>
    b.addEventListener("click", () => {
      saveSettings({ ...getSettings(), provider: b.dataset.p });
      render();
      changed();
      keyChanged();
    })
  );

  $("save").addEventListener("click", () => {
    const v = $("key").value.trim();
    if (!v) return show("Paste your API key first.", false);
    const p = provider();
    if (getKey(p)?.key !== v) clearKeyStatus(p); // a different key starts with fresh stats
    setKey(p, v);
    $("key").value = "";
    revealed = false;
    renderKey();
    keyChanged();
    show("Key saved. Press Connect to check it.", true);
  });
  $("forget").addEventListener("click", () => {
    clearKey(provider());
    clearKeyStatus(provider());
    revealed = false;
    renderKey();
    keyChanged();
    show("Key removed from this browser.", true);
  });
  $("reveal").addEventListener("click", () => {
    revealed = !revealed;
    renderKey();
  });
  $("connect").addEventListener("click", async () => {
    const p = provider();
    $("connect").disabled = true;
    $("pill").className = "pill saved";
    $("pill").textContent = "● Connecting…";
    const t0 = performance.now();
    try {
      const { models } = await listModels(); // lists models only: uses no generation quota
      setKeyStatus(p, { connected: true, reason: "", models: models.length, latencyMs: Math.round(performance.now() - t0), checkedAt: Date.now() });
      show("Connected. Your key works.", true);
    } catch (e) {
      setKeyStatus(p, { connected: false, reason: e.message, checkedAt: Date.now() });
      show(e.message, false);
    } finally {
      $("connect").disabled = false;
      renderKey();
      keyChanged();
    }
  });

  $("gap").addEventListener("input", () => {
    $("gapv").textContent = +$("gap").value === 0 ? "none" : `${$("gap").value} s`;
  });
  $("gap").addEventListener("change", () => {
    const cur = getSettings();
    saveSettings({ ...cur, gaps: { ...cur.gaps, [cur.provider]: +$("gap").value } });
    changed(); // refreshes the estimated time
  });
  $("lmUrl").addEventListener("change", () => {
    saveSettings({ ...getSettings(), lmUrl: $("lmUrl").value.trim() });
    changed();
    loadLmModels();
  });
  $("reset").addEventListener("click", () => {
    const cur = getSettings();
    saveSettings({ ...cur, models: { ...cur.models, [cur.provider]: {} } });
    renderModels();
    changed();
  });
  $("load").addEventListener("click", () => {
    show("Loading models…", true);
    loadLmModels(true);
  });

  $("test").addEventListener("click", async () => {
    $("test").disabled = true;
    try {
      show("Testing…", true);
      const r = await testProvider();
      show(r.message, r.ok);
      if (KEYED[provider()]) {
        setKeyStatus(provider(), r.ok ? { connected: true, reason: "", checkedAt: Date.now() } : { connected: false, reason: r.message, checkedAt: Date.now() });
        renderKey();
        keyChanged();
      }
    } catch (e) {
      show(e.message, false);
    } finally {
      $("test").disabled = false;
    }
  });

  // Keep the countdown fresh and notice when the key expires or another tab/page changes its status.
  setInterval(renderKey, 15000);
  window.addEventListener("storage", renderKey);
  window.addEventListener("tg:keystats", renderKey);
  render();
}
