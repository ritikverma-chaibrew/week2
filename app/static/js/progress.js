const ICON = { done: "✓", failed: "!", skipped: "–", pending: "", running: "", retrying: "" };
let tick = null;

export function fmtDuration(s) {
  s = Math.max(0, Math.round(s));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60), r = s % 60;
  return r ? `${m} min ${r}s` : `${m} min`;
}

/** Estimated time left and the pause between calls. Counts down locally between updates.
 *  The live "AI calls made" counter is hidden from the UI; its code is kept below, commented out. */
function renderLlm(root, llm, status) {
  const eta = root.querySelector("#llm-eta");
  if (!eta) return; // e.g. the demo page has no counter
  // const calls = root.querySelector("#llm-calls");
  clearInterval(tick);
  const at = Date.now();
  const paint = () => {
    const el = (Date.now() - at) / 1000;
    // calls.textContent = llm.calls;
    // root.querySelector("#llm-planned").textContent = llm.planned;
    const left = status === "done" ? 0 : Math.max(0, llm.eta - el);
    eta.textContent = status === "done" ? "done" : status === "failed" ? "stopped" : `~${fmtDuration(left)} left`;
    const w = Math.max(0, llm.waiting - el);
    root.querySelector("#llm-wait").textContent =
      status === "running" || status === "pending"
        ? w > 0 ? `Pausing ${fmtDuration(w)} before the next AI call (rate limits)…` : llm.gap ? `${llm.gap}s pause between AI calls to stay within rate limits.` : ""
        : "";
  };
  paint();
  if (status === "running" || status === "pending") tick = setInterval(paint, 1000);
}

export function renderProgress(root, state) {
  const done = state.steps.filter((s) => s.status === "done" || s.status === "skipped").length;
  root.querySelector(".bar i").style.width = Math.round((done / state.steps.length) * 100) + "%";
  const ul = root.querySelector(".steps");
  ul.replaceChildren(
    ...state.steps.map((s) => {
      const li = document.createElement("li");
      li.className = "s-" + s.status;
      const meta =
        s.status === "retrying" ? `retrying in ~${s.attempts * (state.llm?.gap || 5)}s (attempt ${s.attempts}/4): ${s.error || ""}`
        : s.status === "failed" ? s.error || "failed"
        : s.status === "skipped" ? "skipped, story kept as written"
        : s.status === "done" && s.ms ? (s.ms / 1000).toFixed(1) + "s"
        : s.status === "running" && s.attempts > 1 ? `attempt ${s.attempts}/4` : "";
      li.innerHTML = `<span class="dot">${ICON[s.status] || ""}</span><span></span><span class="meta"></span>`;
      li.children[1].textContent = s.label;
      li.children[2].textContent = meta;
      return li;
    })
  );
  if (state.llm) renderLlm(root, state.llm, state.status);
}
