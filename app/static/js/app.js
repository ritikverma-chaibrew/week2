import { createStory, estimate, eventsUrl, imageUrl, retryStory, uploadPhotos } from "./api.js";
import { PROVIDERS, getKeyStatus, getSettings, readiness, setKeyStatus } from "./keystore.js";
import { fmtDuration, renderProgress } from "./progress.js";
import { isPublished, publishLocal } from "./published.js";
import { mountSettings } from "./settings.js";
import { GENRE_LABEL, renderStory } from "./story-view.js";
import { mountDropzone } from "./upload.js";

const MISSIONS = [
  "Find something red that isn't a stop sign.", "Photograph the oldest-looking thing within 100 steps.",
  "Find a door that isn't yours.", "Capture a shadow doing something suspicious.",
  "Photograph something that looks like a face.", "Find the smallest living thing you can.",
  "Shoot the weirdest sign you can find.", "Capture something that is out of place.",
  "Photograph a tree, a cloud, and one stranger's pet (ask nicely).", "Find a pattern in nature.",
  "Take a photo of the sky from the ground.", "Find something abandoned.",
];
const MIN_PHOTOS = 5, MAX_PHOTOS = 10;
const KIND_NAME = { story: "story", poem: "poem", comic: "comic" };
const $ = (id) => document.getElementById(id);
let genre = "funny", kind = "story", storyId = null, es = null;
let running = false, photoCount = 0, lastResult = null;

mountSettings($("settings"));

/** Step 1: one-line summary of the AI connection. Open the box while something still needs doing. */
function renderAi() {
  const r = readiness();
  const name = PROVIDERS[r.provider];
  let text;
  if (r.provider === "lmstudio") text = `✓ Using ${name} on this computer. Make sure its server is running.`;
  else if (!r.key) text = r.reason ? `⚠️ Your ${name} key was disconnected. Add it again.` : `Paste your free ${name} key to start.`;
  else if (!r.ready) text = `⚠️ ${name} rejected the key. Check it below.`;
  else text = r.connected ? `✓ ${name} connected.` : `✓ ${name} key saved. Press Connect to check it.`;
  $("ai-summary").textContent = text;
  $("step-ai").classList.toggle("done", r.ready);
  $("step-ai").classList.toggle("attn", !r.ready);
  if (!r.ready) $("ai-box").open = true;
  return r.ready;
}

/** Step 5: the Make button, plus a short list of what is still missing. */
function renderMake() {
  const aiOk = renderAi();
  const photosOk = photoCount >= MIN_PHOTOS;
  const todo = [];
  if (!aiOk) todo.push('Connect the AI in <a href="#step-ai">step 1</a>.');
  if (!photosOk) {
    const n = MIN_PHOTOS - photoCount;
    todo.push(`Add ${n} more photo${n === 1 ? "" : "s"} in <a href="#step-photos">step 3</a>.`);
  }
  $("todo").innerHTML = todo.length && !running ? todo.map((t) => `<li>${t}</li>`).join("") : "";
  $("step-make").classList.toggle("done", !todo.length);
  const go = $("go");
  go.disabled = running || !!todo.length;
  go.textContent = running ? `Writing your ${KIND_NAME[kind]}…` : `Make my ${GENRE_LABEL[genre].toLowerCase()} ${KIND_NAME[kind]} ✨`;
  renderEstimate();
}
["tg:settings", "tg:key", "tg:keystats", "storage"].forEach((t) => window.addEventListener(t, renderMake));
setInterval(renderAi, 30000); // notices when the key expires

/** Before starting: roughly how long the chosen format takes (the server knows the provider's pacing). */
const estimates = {};
async function refreshEstimate() {
  try {
    const n = Math.min(MAX_PHOTOS, Math.max(MIN_PHOTOS, photoCount));
    const res = await Promise.all(["story", "poem", "comic"].map((k) => estimate(n, k)));
    res.forEach((r) => (estimates[r.kind] = { ...r, n }));
  } catch {
    Object.keys(estimates).forEach((k) => delete estimates[k]);
  }
  renderEstimate();
}
function renderEstimate() {
  const e = estimates[kind];
  $("estimate").textContent = e
    ? `⏱ About ${fmtDuration(e.seconds)} for ${e.n} photos` +
      // Hidden from the UI: the number of AI calls. Kept for reference:
      // ` (${e.calls} AI calls)` +
      (e.gap ? `, with a ${e.gap}s pause between AI steps to respect free limits` : "") + ". Keep this tab open while it works."
    : "";
}
window.addEventListener("tg:settings", refreshEstimate);
refreshEstimate();

/** Per-key stats shown in the key card: stories made with this key, and whether it still works.
 *  AI calls are still counted here, but the count is no longer shown in the UI. */
const seenCalls = {};
function recordUsage(st) {
  const p = getSettings().provider;
  if (p !== "aistudio") return;
  const prev = getKeyStatus(p);
  const delta = (st.llm?.calls || 0) - (seenCalls[st.id] || 0);
  const first = !(st.id in seenCalls);
  seenCalls[st.id] = st.llm?.calls || 0;
  const patch = { calls: (prev.calls || 0) + Math.max(0, delta), stories: (prev.stories || 0) + (first && st.status === "done" ? 1 : 0) };
  if (st.status === "done") Object.assign(patch, { connected: true, reason: "", checkedAt: Date.now() });
  else if (st.error?.code === "bad_key") Object.assign(patch, { connected: false, reason: st.error.message });
  setKeyStatus(p, patch);
  window.dispatchEvent(new Event("tg:keystats"));
}

/** Step 2: mission. */
const nextMission = () => ($("mission").textContent = MISSIONS[Math.floor(Math.random() * MISSIONS.length)]);
$("shuffle").onclick = nextMission;
nextMission();

/** Step 3: photos, with a fill meter toward the minimum. */
const dz = mountDropzone($("drop"), $("file"), $("thumbs"), (n) => {
  photoCount = n;
  const left = MIN_PHOTOS - n;
  $("count").textContent =
    n >= MAX_PHOTOS ? `${n} of ${MAX_PHOTOS} photos. That's the maximum.`
    : left > 0 ? `${n} of ${MAX_PHOTOS} photos. Add ${left} more (at least ${MIN_PHOTOS}).`
    : `${n} of ${MAX_PHOTOS} photos. Great, that's enough! You can add up to ${MAX_PHOTOS - n} more.`;
  $("meter").querySelector("i").style.width = Math.round((n / MAX_PHOTOS) * 100) + "%";
  $("meter").classList.toggle("ok", n >= MIN_PHOTOS);
  $("step-photos").classList.toggle("done", n >= MIN_PHOTOS);
  renderMake();
  refreshEstimate(); // more photos take a little longer
});

/** Step 4: mood and format are two independent single-choice groups. */
function choose(attr, value) {
  document.querySelectorAll(`.genre[data-${attr}]`).forEach((x) => {
    const on = x.dataset[attr] === value;
    x.classList.toggle("on", on);
    x.setAttribute("aria-pressed", on);
  });
}
document.querySelectorAll(".genre[data-g]").forEach((b) =>
  b.addEventListener("click", () => {
    genre = b.dataset.g;
    choose("g", genre);
    renderMake();
  })
);
document.querySelectorAll(".genre[data-k]").forEach((b) =>
  b.addEventListener("click", () => {
    kind = b.dataset.k;
    choose("k", kind);
    renderMake();
  })
);

function showError(msg) {
  const el = $("error");
  el.textContent = msg;
  el.className = "status " + (msg ? "err" : "");
}

/** Retry button: shown only while the story is failed (or briefly after a click, disabled). After a click it stays
 *  disabled until the API answers (a step finishes, fails again, or the story ends) or 45 s pass, whichever is first. */
const RETRY_COOLDOWN_MS = 45000;
let lastState = null, cooldown = null;
const doneCount = (st) => (st ? st.steps.filter((s) => s.status === "done").length : 0);

function endCooldown() {
  if (cooldown) clearInterval(cooldown.timer);
  cooldown = null;
}

function renderRetry(st) {
  lastState = st ?? lastState;
  const s = lastState;
  if (cooldown && s) {
    const answered =
      s.status === "failed" || s.status === "done" || doneCount(s) > cooldown.doneAtClick || s.steps.some((x) => x.status === "retrying");
    if (answered) endCooldown(); // the API responded: stop waiting
  }
  const btn = $("retry");
  btn.hidden = s?.status === "done" || !(s?.status === "failed" || cooldown); // never shown once the story exists
  btn.disabled = !!cooldown;
  btn.textContent = cooldown
    ? `Retrying… wait ${Math.max(0, Math.ceil((cooldown.until - Date.now()) / 1000))}s`
    : "↻ Retry from the failed step";
}

function startCooldown() {
  endCooldown();
  const until = Date.now() + RETRY_COOLDOWN_MS;
  const doneAtClick = doneCount(lastState);
  // The stored snapshot is still the old "failed" one; treat the story as running again so that stale failure
  // isn't mistaken for the API's answer.
  if (lastState) lastState = { ...lastState, status: "pending", steps: lastState.steps.map((x) => (x.status === "failed" ? { ...x, status: "pending" } : x)) };
  cooldown = {
    until,
    doneAtClick,
    timer: setInterval(() => {
      if (Date.now() >= until) endCooldown();
      renderRetry();
    }, 1000),
  };
  renderRetry();
}

function busy(on) {
  running = on;
  renderMake();
}

function watch(id) {
  es?.close();
  es = new EventSource(eventsUrl(id));
  es.onmessage = (ev) => {
    const st = JSON.parse(ev.data);
    renderProgress($("progress"), st);
    renderRetry(st);
    if (st.status === "failed" || st.status === "done") recordUsage(st);
    if (st.status === "failed") {
      showError(st.error?.message || "Something went wrong.");
      es.close();
      busy(false);
    } else if (st.status === "done") {
      es.close();
      showError("");
      renderStory($("result"), st.result, (sc) => (sc.image_id ? imageUrl(sc.image_id, "full") : null));
      lastResult = st.result;
      renderPublish(isPublished(st.id));
      $("result-card").hidden = false;
      $("result-card").scrollIntoView({ behavior: "smooth" });
      busy(false);
    }
  };
  es.onerror = () => {
    // EventSource auto-reconnects and the server replays current state; only report if closed for good.
    if (es.readyState === EventSource.CLOSED) showError("Lost connection to the server. Press Retry.");
  };
}

$("go").onclick = async () => {
  showError("");
  $("result-card").hidden = true;
  endCooldown();
  lastState = null;
  renderRetry();
  busy(true);
  try {
    $("progress-card").hidden = false;
    $("progress-card").scrollIntoView({ behavior: "smooth", block: "start" });
    renderProgress($("progress"), { steps: [{ label: "Uploading photos", status: "running", attempts: 1 }] });
    const up = await uploadPhotos(dz.blobs());
    ({ id: storyId } = await createStory(up.image_ids, genre, false, kind)); // private until the author presses Publish
    watch(storyId);
  } catch (e) {
    showError(e.message);
    $("progress-card").hidden = true;
    busy(false);
  }
};

/** Publish box under a finished tale: one click saves it to this browser's local storage, shown in the gallery. */
function renderPublish(isPublic, msg = "") {
  $("publish").hidden = isPublic;
  $("publish").disabled = false;
  $("publish").textContent = "📚 Publish my tale";
  $("private-note").hidden = isPublic;
  $("publish-box").classList.toggle("done", isPublic);
  $("publish-msg").className = "status " + (isPublic ? "ok" : msg ? "err" : "");
  $("publish-msg").innerHTML = isPublic
    ? `✓ Published! Your tale is saved to your browser's local storage. Find it any time in the <a href="gallery.html">gallery</a> on this device.`
    : msg;
}

$("publish").onclick = async () => {
  $("publish").disabled = true;
  $("publish").textContent = "Saving…";
  try {
    await publishLocal(storyId, lastResult, imageUrl);
    renderPublish(true);
  } catch (e) {
    renderPublish(false, "");
    $("publish-msg").className = "status err";
    $("publish-msg").textContent = `Couldn't publish: ${e.message}`;
  }
};

$("retry").onclick = async () => {
  showError("");
  busy(true);
  startCooldown(); // disabled until the API answers or 45 s, whichever is shorter
  try {
    await retryStory(storyId); // the server also waits out the pause since the last AI call
    watch(storyId);
  } catch (e) {
    endCooldown();
    renderRetry();
    showError(e.message);
    busy(false);
  }
};

renderMake();
