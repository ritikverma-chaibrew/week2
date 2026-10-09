/** Render a finished story, poem or comic as a read-through or as slides.
 *  Pictures are the author's own photos at their natural proportions (never cropped), scaled by CSS, tinted per
 *  genre. `photoUrl(item)` returns an image URL; the bundled demo scenes carry an `svg` instead. */
const VIEW_KEY = "tg.view";
const getView = () => {
  try {
    return localStorage.getItem(VIEW_KEY) === "slides" ? "slides" : "read";
  } catch {
    return "read";
  }
};
const setView = (v) => {
  try {
    localStorage.setItem(VIEW_KEY, v);
  } catch {}
};

/** Split an array into k contiguous, nearly equal parts. */
const chunk = (arr, k) => Array.from({ length: k }, (_, j) => arr.slice(Math.round((j * arr.length) / k), Math.round(((j + 1) * arr.length) / k)));
const el = (tag, cls, text) => Object.assign(document.createElement(tag), cls ? { className: cls } : {}, text != null ? { textContent: text } : {});

const KIND_LABEL = { story: "story", poem: "poem", comic: "comic" };
/** What each mood is called in the UI (the API keeps its original ids). */
export const GENRE_LABEL = { funny: "Funny", horror: "Spooky", suspense: "Mystery" };

/** A photo with its caption printed on the picture. */
function picture(sc, url) {
  if (!sc.svg && !url) return null;
  const fig = el("figure", "scene");
  const box = el("div", "shot");
  if (sc.svg) {
    box.classList.add("svg");
    box.innerHTML = sc.svg;
  } else {
    const img = el("img");
    img.alt = sc.caption || "";
    img.loading = "lazy";
    img.src = url;
    box.append(img);
  }
  if (sc.caption) box.append(el("figcaption", "cap", sc.caption));
  fig.append(box);
  return fig;
}

/** One comic panel: narration box on top, the photo, speech bubbles underneath. */
function panelEl(p, url) {
  const fig = el("figure", "panel");
  if (p.caption) fig.append(el("div", "pcap", p.caption));
  if (url) {
    const shot = el("div", "pshot");
    const img = el("img");
    img.alt = p.caption || "Comic panel";
    img.loading = "lazy";
    img.src = url;
    shot.append(img);
    fig.append(shot);
  }
  if (p.speech?.length) {
    const b = el("div", "bubbles");
    p.speech.forEach((s) => {
      const bub = el("div", "bubble");
      if (s.who) bub.append(el("b", null, s.who));
      bub.append(document.createTextNode(s.text));
      b.append(bub);
    });
    fig.append(b);
  }
  return fig;
}

/** Slides: one item per slide with prev/next buttons and arrow keys. */
function deckOf(items) {
  const slides = el("div", "slides");
  slides.tabIndex = 0;
  const nav = el("div", "slidenav");
  nav.innerHTML = `<button class="btn sm ghost" type="button" data-d="-1" aria-label="Previous slide">‹ Prev</button><span class="count"></span><button class="btn sm ghost" type="button" data-d="1" aria-label="Next slide">Next ›</button>`;
  let at = 0;
  const show = (i) => {
    at = (i + items.length) % items.length;
    items.forEach((s, k) => (s.hidden = k !== at));
    nav.querySelector(".count").textContent = `${at + 1} / ${items.length}`;
  };
  nav.addEventListener("click", (e) => {
    const d = e.target.closest("[data-d]")?.dataset.d;
    if (d) show(at + +d);
  });
  slides.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") show(at + 1);
    if (e.key === "ArrowLeft") show(at - 1);
  });
  slides.append(...items, nav);
  show(0);
  return slides;
}

function header(r) {
  const head = el("div");
  head.innerHTML = `<span class="badge ${r.genre}">${GENRE_LABEL[r.genre] || r.genre}</span> <span class="muted">${KIND_LABEL[r.kind] || "story"}</span>${r.polished ? ' <span class="muted">· ✨ revised after review</span>' : ""}<h2></h2><div class="chips"></div>
    <div class="seg viewtoggle" role="tablist"><button type="button" data-v="read">📖 Read</button><button type="button" data-v="slides">🎞 Slides</button></div>`;
  head.querySelector("h2").textContent = r.title;
  (r.objects || []).forEach((o) => head.querySelector(".chips").append(el("span", null, o)));
  return head;
}

/** Wire the Read / Slides toggle between two views. */
function toggle(head, read, slides) {
  const setMode = (v) => {
    read.hidden = v !== "read";
    slides.hidden = v !== "slides";
    head.querySelectorAll(".viewtoggle button").forEach((b) => b.classList.toggle("on", b.dataset.v === v));
    setView(v);
  };
  head.querySelector(".viewtoggle").addEventListener("click", (e) => {
    const v = e.target.closest("[data-v]")?.dataset.v;
    if (v) setMode(v);
  });
  setMode(getView());
}

function renderComic(host, r, photoUrl) {
  const out = el("article", `story comic-story ${r.genre}`);
  const head = header(r);
  const panels = r.panels || [];
  const read = el("div", "comic");
  panels.forEach((p) => read.append(panelEl(p, photoUrl(p))));
  const slide = (p) => {
    const s = el("section", "slide single");
    s.append(panelEl(p, photoUrl(p)));
    return s;
  };
  const slides = deckOf(panels.map(slide));
  toggle(head, read, slides);
  out.append(head, read, slides);
  host.replaceChildren(out);
}

export function renderStory(host, r, photoUrl = () => null) {
  if (r.kind === "comic") return renderComic(host, r, photoUrl);
  const poem = r.kind === "poem";
  const parts = r.text.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean); // scenes of a story / stanzas of a poem
  const scenes = r.scenes || [];
  const sections = chunk(parts, Math.max(1, scenes.length)); // each picture illustrates its own stretch
  const text = (t) => el("p", poem ? "verse" : "", t);

  const out = el("article", `story ${poem ? "poem " : ""}${r.genre}`);
  const head = header(r);

  // Read view: the picture sits right after the first part of the stretch it illustrates.
  const read = el("div", "read");
  sections.forEach((sec, i) => {
    sec.forEach((t, k) => {
      read.append(text(t));
      if (k === 0 && scenes[i]) {
        const fig = picture(scenes[i], photoUrl(scenes[i]));
        if (fig) read.append(fig);
      }
    });
    if (!sec.length && scenes[i]) {
      const fig = picture(scenes[i], photoUrl(scenes[i]));
      if (fig) read.append(fig);
    }
  });

  // Slides view: one slide per picture = the photo with its caption, plus that part of the text.
  const deck = sections.map((sec, i) => {
    const s = el("section", "slide");
    const pic = scenes[i] ? picture(scenes[i], photoUrl(scenes[i])) : null;
    if (pic) {
      const wrapPic = el("div", "pic");
      wrapPic.append(pic);
      s.append(wrapPic);
    }
    const txt = el("div", "txt");
    sec.forEach((t) => txt.append(text(t)));
    s.append(txt);
    return s;
  });
  const slides = deckOf(deck);

  toggle(head, read, slides);
  out.append(head, read, slides);
  host.replaceChildren(out);
}
