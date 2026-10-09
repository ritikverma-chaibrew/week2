import { galleryList, galleryStory, imageUrl } from "./api.js";
import { DEMO } from "./demo-data.js";
import { listPublished, removePublished } from "./published.js";
import { GENRE_LABEL, renderStory } from "./story-view.js";

const $ = (id) => document.getElementById(id);
let skip = 0, shownReal = 0;

const excerptOf = (text = "") => (text.length > 220 ? text.slice(0, 220).replace(/\s+\S*$/, "") + "…" : text);

function card(item) {
  const a = document.createElement("button");
  a.type = "button";
  a.className = "gcard";
  const strip = document.createElement("div");
  strip.className = "strip";
  const srcs = item.thumbSrcs || (item.thumbs || []).map((id) => imageUrl(id, "thumb"));
  if (srcs.length) {
    srcs.forEach((src) => {
      const img = document.createElement("img");
      img.loading = "lazy";
      img.alt = "";
      img.src = src;
      strip.append(img);
    });
  } else if (item.art) {
    strip.innerHTML = item.art; // demo illustration (trusted, bundled)
  }
  const body = document.createElement("div");
  body.className = "gbody";
  body.innerHTML = `<span class="badge ${item.genre}">${GENRE_LABEL[item.genre] || item.genre}</span> <span class="muted">${item.kind || "story"}</span><h3></h3><p class="muted"></p><small class="muted"></small>`;
  body.querySelector("h3").textContent = item.title;
  body.querySelector("p").textContent = item.excerpt;
  body.querySelector("small").textContent =
    `${item.words} words` + (item.demo ? " · sample" : "") + (item.local ? ` · saved ${new Date(item.savedAt).toLocaleDateString()}` : "");
  a.append(strip, body);
  a.onclick = () => open(item);
  return a;
}

async function open(item) {
  const dlg = $("dlg");
  $("read").textContent = "Loading…";
  dlg.showModal();
  try {
    if (item.demo) return renderStory($("read"), DEMO[item.genre]);
    if (item.local) return openLocal(item);
    const r = await galleryStory(item.id);
    renderStory($("read"), r, (sc) => (sc.image_id ? imageUrl(sc.image_id, "full") : null));
  } catch (e) {
    $("read").textContent = e.message;
  }
}

/** A tale saved in this browser: its photos are stored with it. Offers to remove it from local storage. */
function openLocal(item) {
  const t = listPublished().find((x) => x.id === item.id);
  if (!t) return ($("read").textContent = "This tale is no longer saved in this browser.");
  const story = document.createElement("div");
  renderStory(story, t.result, (sc) => t.photos[sc.image_id] || null);
  const bar = document.createElement("div");
  bar.className = "row top";
  bar.innerHTML = `<span class="muted">📚 Saved in this browser's local storage</span><button class="btn sm ghost" type="button">🗑 Remove</button>`;
  bar.querySelector("button").onclick = () => {
    if (!confirm("Remove this tale from this browser? This can't be undone.")) return;
    removePublished(t.id);
    $("dlg").close();
    renderLocal();
  };
  $("read").replaceChildren(bar, story);
}

function localItems() {
  return listPublished().map((t) => ({
    local: true,
    id: t.id,
    savedAt: t.savedAt,
    genre: t.result.genre,
    kind: t.result.kind,
    title: t.result.title,
    excerpt: excerptOf(t.result.text),
    words: (t.result.text || "").split(/\s+/).filter(Boolean).length,
    thumbSrcs: Object.values(t.photos).slice(0, 3),
  }));
}

function demoItems() {
  return Object.values(DEMO).map((d) => ({
    demo: true,
    genre: d.genre,
    title: d.title,
    excerpt: excerptOf(d.text),
    words: d.text.split(/\s+/).length,
    art: d.scenes[0].svg,
  }));
}

/** "Your published tales" section, read from this browser's local storage. */
function renderLocal() {
  const items = localItems();
  $("mine").hidden = !items.length;
  $("mine-grid").replaceChildren(...items.map(card));
  $("mine-empty").hidden = !!items.length;
}

async function load() {
  try {
    const { items } = await galleryList(skip);
    skip += items.length;
    shownReal += items.length;
    items.forEach((it) => $("grid").append(card(it)));
    $("more").hidden = items.length < 12;
  } catch (e) {
    $("note").textContent = e.message;
  }
  if (!shownReal && !$("grid").children.length) {
    $("note").textContent = "Here are three sample tales to show what you can make.";
    demoItems().forEach((it) => $("grid").append(card(it)));
  }
}

$("more").onclick = load;
$("close").onclick = () => $("dlg").close();
$("dlg").addEventListener("click", (e) => e.target === $("dlg") && $("dlg").close());
renderLocal();
load();
