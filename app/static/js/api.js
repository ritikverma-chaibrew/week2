import { ROLES, gapFor, getKey, getSettings, modelFor, setKeyStatus } from "./keystore.js";

export class ApiError extends Error {
  constructor(message, code = "error") {
    super(message);
    this.code = code;
  }
}

/** Provider, key and chosen models travel as headers on every call; the server never stores them. */
export function providerHeaders() {
  const s = getSettings();
  const h = { "X-Provider": s.provider, "X-Call-Gap": String(gapFor(s.provider)) };
  if (s.provider === "lmstudio") h["X-Lm-Url"] = s.lmUrl;
  if (s.provider === "aistudio") h["X-Api-Key"] = getKey(s.provider)?.key || "";
  const m = {};
  for (const [role] of ROLES) {
    const v = modelFor(s.provider, role);
    if (v) m[role] = v;
  }
  h["X-Models"] = JSON.stringify(m);
  return h;
}

async function call(path, opts = {}) {
  let r;
  try {
    r = await fetch(path, opts);
  } catch {
    throw new ApiError("Can't reach the Touch Grass server. Is uvicorn running?", "offline");
  }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const e = data.error || {};
    const detail = typeof data.detail === "string" ? data.detail : "";
    const code = e.code || "http_" + r.status;
    if (code === "bad_key") setKeyStatus(getSettings().provider, { connected: false, reason: e.message });
    throw new ApiError(e.message || detail || `Request failed (${r.status})`, code);
  }
  return data;
}

const json = (body, headers = providerHeaders()) => ({
  method: "POST",
  headers: { "Content-Type": "application/json", ...headers },
  body: JSON.stringify(body),
});

export const estimate = (photos, kind = "story") =>
  call(`/api/provider/estimate?photos=${photos}&kind=${kind}`, { headers: providerHeaders() });
export const health = () => call("/api/health");
export const testProvider = () => call("/api/provider/test", { method: "POST", headers: providerHeaders() });
export const listModels = () => call("/api/provider/models", { headers: providerHeaders() });

export function uploadPhotos(blobs) {
  const fd = new FormData();
  blobs.forEach((b, i) => fd.append("files", b, `photo${i}.jpg`));
  return call("/api/sessions", { method: "POST", body: fd });
}

export const createStory = (image_ids, genre, share, kind = "story") =>
  call("/api/stories", json({ image_ids, genre, share, kind }));
export const retryStory = (id) => call(`/api/stories/${id}/retry`, { method: "POST", headers: providerHeaders() });
export const imageUrl = (id, size = "full") => `/api/images/${id}?size=${size}`;
export const eventsUrl = (id) => `/api/stories/${id}/events`;
export const galleryList = (skip = 0) => call(`/api/gallery?limit=12&skip=${skip}`);
export const galleryStory = (id) => call(`/api/gallery/${id}`);
