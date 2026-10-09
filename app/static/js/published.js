/** Published tales live only in this browser's localStorage, never on the server. The server deletes uploaded photos
 *  after 24 hours, so each tale keeps its own small copies of its photos (data URLs, ~480px JPEG). */
import { compress } from "./upload.js";

const KEY = "tg.published.v1";
const PHOTO_PX = 480;

export function listPublished() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || [];
  } catch {
    return [];
  }
}

export const isPublished = (id) => listPublished().some((t) => t.id === id);

function save(list) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    throw new Error("Your browser's local storage is full or blocked. Remove an older tale in the Gallery and try again.");
  }
}

const toDataUrl = (blob) =>
  new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(r.result);
    r.onerror = () => rej(new Error("Couldn't read a photo."));
    r.readAsDataURL(blob);
  });

/** Save a finished tale (and copies of its photos) under its story id. Publishing again replaces the old copy. */
export async function publishLocal(id, result, imageUrl) {
  const items = [...(result.scenes || []), ...(result.panels || [])];
  const ids = [...new Set(items.map((s) => s.image_id).filter(Boolean))];
  const photos = {};
  for (const imgId of ids) {
    const r = await fetch(imageUrl(imgId, "full"));
    if (!r.ok) throw new Error("Your photos are no longer on the server (they are deleted after 24 hours).");
    photos[imgId] = await toDataUrl(await compress(await r.blob(), PHOTO_PX));
  }
  save([{ id, savedAt: Date.now(), result, photos }, ...listPublished().filter((t) => t.id !== id)]);
}

export function removePublished(id) {
  save(listPublished().filter((t) => t.id !== id));
}
