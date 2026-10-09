// API keys live in localStorage for 5 hours only (one slot per provider), then they are purged.
const SETTINGS = "tg.settings.v5";
export const TTL_MS = 5 * 60 * 60 * 1000;
export const TTL_LABEL = "5 hours";

export const PROVIDERS = {
  aistudio: "Google AI Studio",
  lmstudio: "LM Studio",
};

// One model per task. Mirrors app/providers/base.py DEFAULT_MODELS (the server is the source of truth).
export const ROLES = [
  ["vision", "Look at each photo (needs vision)"],
  ["outline", "Plan the plot and pick scenes (JSON)"],
  ["story", "Write, review and fix the story (prose)"],
];
const AI_BIG = "gemma-4-31b-it", AI_FAST = "gemma-4-26b-a4b-it";
export const DEFAULT_MODELS = {
  aistudio: { vision: AI_FAST, outline: AI_FAST, story: AI_BIG },
  lmstudio: {},
};
// The only models offered in the model pickers. LM Studio's list comes from the app: only loaded Gemma models are shown.
export const RECOMMENDED_MODELS = {
  aistudio: [
    { id: AI_FAST, name: "Gemma 4 26B-A4B", note: "fast" },
    { id: AI_BIG, name: "Gemma 4 31B", note: "best writing" },
  ],
};
export const isRecommendedLocal = (id) => /gemma/i.test(id);

const DEFAULTS = { provider: "aistudio", lmUrl: "http://localhost:1234/v1", models: {}, gaps: {} };

// Pause between AI calls (seconds). AI Studio has per-minute limits; local models don't.
export const DEFAULT_GAP = { aistudio: 0, lmstudio: 0 }; // no pause after a successful call; the server backs off after failures
export const MAX_GAP = 120;
export const gapFor = (provider) => {
  const g = getSettings().gaps?.[provider];
  return Number.isFinite(g) ? g : DEFAULT_GAP[provider] ?? 30;
};
const keyName = (p) => "tg.key." + p;

export function getKey(provider) {
  try {
    const o = JSON.parse(localStorage.getItem(keyName(provider)));
    if (!o) return null;
    if (Date.now() > o.exp) {
      localStorage.removeItem(keyName(provider));
      return null;
    }
    return o; // {key, exp}
  } catch {
    return null;
  }
}

export function setKey(provider, key) {
  try {
    localStorage.setItem(keyName(provider), JSON.stringify({ key, exp: Date.now() + TTL_MS }));
  } catch {
    /* storage blocked: key just won't persist */
  }
}

export function clearKey(provider) {
  try {
    localStorage.removeItem(keyName(provider));
  } catch {}
}

/** Connection status + usage stats for a saved key, kept next to the key (same browser only). */
const statName = (p) => "tg.keystat." + p;
export function getKeyStatus(provider) {
  try {
    return JSON.parse(localStorage.getItem(statName(provider))) || {};
  } catch {
    return {};
  }
}
export function setKeyStatus(provider, patch) {
  try {
    localStorage.setItem(statName(provider), JSON.stringify({ ...getKeyStatus(provider), ...patch }));
  } catch {}
}
export function clearKeyStatus(provider) {
  try {
    localStorage.removeItem(statName(provider));
  } catch {}
}
export const maskKey = (k) => (k.length <= 10 ? "••••••••" : k.slice(0, 4) + "•".repeat(Math.min(k.length - 8, 24)) + k.slice(-4));

export function getSettings() {
  try {
    const s = JSON.parse(localStorage.getItem(SETTINGS) || "{}");
    const provider = s.provider in PROVIDERS ? s.provider : DEFAULTS.provider;
    return { ...DEFAULTS, ...s, provider, models: { ...(s.models || {}) }, gaps: { ...(s.gaps || {}) } };
  } catch {
    return { ...DEFAULTS, models: {}, gaps: {} };
  }
}

export function saveSettings(s) {
  try {
    localStorage.setItem(SETTINGS, JSON.stringify(s));
  } catch {}
}

/** The model for a task: the user's pick if any, else the recommended default ("" = auto for LM Studio). */
export function modelFor(provider, role) {
  const picked = getSettings().models?.[provider]?.[role];
  const allowed = RECOMMENDED_MODELS[provider];
  // An old hand-typed model that is not on the recommended list is ignored in favour of the default.
  if (picked && (!allowed || allowed.some((m) => m.id === picked))) return picked;
  return DEFAULT_MODELS[provider]?.[role] || "";
}

/** Is the chosen provider ready to make a story? LM Studio needs nothing stored here; AI Studio needs a live key. */
export function readiness() {
  const p = getSettings().provider;
  if (p === "lmstudio") return { ready: true, provider: p };
  const key = getKey(p), st = getKeyStatus(p);
  return { ready: !!key && st.connected !== false, provider: p, key, connected: !!st.connected, reason: st.reason || "" };
}
