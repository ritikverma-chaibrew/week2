import asyncio
import json
import re

from .. import db
from ..errors import ProviderError
from . import prompts
from .estimate import KINDS, PARTS, REVISIONS

# step kind -> (temperature, top_p, max output tokens). Every reply is small on purpose: short answers come back
# sooner, stay on topic and are cheap to retry. Output is built from many calls, never one long one.
PARAMS = {
    "vision": (0.2, 0.9, 350),  # one photo -> a few nouns
    "outline": (0.8, 0.95, 1500),  # JSON plan
    "scene": (0.95, 0.95, 500),  # ~170 words of story
    "stanza": (0.9, 0.95, 220),  # 4 short lines
    "panel": (0.8, 0.95, 300),  # caption + up to 2 speech bubbles (JSON)
    "critique": (0.3, 0.9, 500),  # JSON list of at most 3 problems
    "revise": (0.8, 0.95, 500),  # one rewritten part
}
# which model does it: the fast one reads photos, plans and letters comic panels; the big one writes, judges, edits
ROLE = {"vision": "vision", "outline": "outline", "scene": "story", "stanza": "story", "panel": "outline",
        "critique": "story", "revise": "story"}
PART_KIND = {"story": "scene", "poem": "stanza", "comic": "panel"}
MAX_PHOTOS = 10
MAX_PARTS = max(PARTS.values())
MAX_REVISIONS = max(REVISIONS.values())
# if these still fail after all retries, the output continues without them
OPTIONAL = {"critique"} | {f"revise_{k + 1}" for k in range(MAX_REVISIONS)}


def scene_count(n_photos: int) -> int:
    """How many moments get an illustration: more photos -> more pictures."""
    return 3 if n_photos <= 6 else 4 if n_photos <= 8 else 5


# Playful progress messages. The polish steps only do work if the editor found something, so they say "if needed".
REVIEW_LABEL = {
    "story": "Our story editor is reading every page with a magnifying glass 🔍",
    "poem": "Our poem editor is tapping along to every rhyme 🔍",
    "comic": "Checking the comic strip",
}
POLISH_LABELS = {
    "story": [
        "Sprinkling extra magic on a scene ✨ (if needed)",
        "Giving a few words a shiny new coat 🪄 (if needed)",
        "Tucking in the last loose threads 🧵 (if needed)",
    ],
    "poem": [
        "Teaching a line to sing a little sweeter 🎵 (if needed)",
        "Making a rhyme sparkle ✨ (if needed)",
    ],
    "comic": [],
}


def step_defs(n_photos: int = 3, kind: str = "story") -> list[tuple[str, str]]:
    n, rev = PARTS[kind], REVISIONS[kind]
    word = {"story": "scene", "poem": "stanza", "comic": "panel"}[kind]
    steps = (
        [(f"vision_{i + 1}", f"Looking at photo {i + 1} of {n_photos}") for i in range(n_photos)]
        + [("outline", {"story": "Plotting the tale and picking scenes", "poem": "Planning the poem",
                        "comic": "Planning the comic strip"}[kind])]
        + [(f"part_{i + 1}", f"Writing {word} {i + 1} of {n}") for i in range(n)]
    )
    if rev:
        steps += [("critique", REVIEW_LABEL[kind])]
        steps += [(f"revise_{k + 1}", POLISH_LABELS[kind][k]) for k in range(rev)]
    return steps + [("illustrate", "Matching your photos"), ("finalize", "Binding the book")]


def parse_json(text: str) -> dict:
    """Lenient JSON extraction from a model reply (fences, chatter, trailing commas)."""
    s = re.sub(r"```(?:json)?", "", text)
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        raise ProviderError("bad_json", "The model didn't return structured data. Retrying…", retryable=True)
    s = re.sub(r",\s*([}\]])", r"\1", s[a : b + 1])
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        raise ProviderError("bad_json", "The model returned malformed data. Retrying…", retryable=True)


async def _gen(provider, cfg, kind: str, prompt: str, images=None) -> str:
    temp, top_p, max_tokens = PARAMS[kind]
    return await provider.generate(prompt, images or [], cfg.model(ROLE[kind]), temp, top_p, max_tokens)


async def _image(image_id: str, field: str) -> bytes:
    """One stored rendition of a photo: 'llm' (384px, what the model sees) or 'thumb' (240px)."""
    d = await db.images.find_one({"_id": image_id}, {field: 1, "data": 1})
    if not d:
        raise ProviderError("images_gone", "Your uploaded photos expired. Please upload them again.")
    return bytes(d.get(field) or d["data"])


def photos(ctx, doc) -> list[dict]:
    return [ctx[f"vision_{i + 1}"] for i in range(len(doc["image_ids"]))]


def kind_of(doc) -> str:
    k = doc.get("kind", "story")
    return k if k in KINDS else "story"


def clean_prose(raw: str) -> str:
    """Drop fences, a leading heading/label line and trailing notes from a model's prose reply."""
    lines = re.sub(r"```\w*", "", raw).strip().splitlines()
    while lines and (not lines[0].strip() or re.match(r"^\s*(#+|\*\*)?\s*(title|scene|stanza|chapter|part|here('s| is))\b[^\n]*$", lines[0], re.I)):
        lines.pop(0)
    for i, line in enumerate(lines):
        if i > 0 and re.match(r"^\s*(\*\*|#+)?\s*(notes?|changes( made)?|edits)\b", line, re.I):
            lines = lines[:i]
            break
    return "\n".join(lines).strip()


# Every step is `async (ctx, doc, provider, cfg) -> output` where ctx holds earlier outputs.
def _vision(i: int):
    async def run(ctx, doc, provider, cfg):
        """One small photo per call."""
        img = await _image(doc["image_ids"][i], "llm")
        data = parse_json(await _gen(provider, cfg, "vision", prompts.VISION_ONE, [img]))
        data["objects"] = [str(o) for o in data.get("objects", [])][:6]
        return data

    run.__name__ = f"vision_{i + 1}"
    return run


async def outline(ctx, doc, provider, cfg):
    kind = kind_of(doc)
    prompt = prompts.outline(kind, doc["genre"], photos(ctx, doc), scene_count(len(doc["image_ids"])), PARTS[kind])
    plan = parse_json(await _gen(provider, cfg, "outline", prompt))
    if kind == "comic" and not plan.get("beats"):
        plan["beats"] = [str(p.get("scene", "")) for p in plan.get("panels") or [] if isinstance(p, dict)]
    if not plan.get("beats"):
        raise ProviderError("bad_json", "The outline was empty. Retrying…", retryable=True)
    return plan


def beat_for(beats: list[str], i: int, total: int) -> str:
    """The plot beat(s) for part i, even if the model returned more or fewer beats than parts."""
    n = len(beats)
    sl = beats[round(i * n / total) : round((i + 1) * n / total)]
    return " ".join(str(b) for b in sl) if sl else str(beats[min(n - 1, int(i * n / total))])


def _part(i: int):
    """Part i of the output: a story scene, a poem stanza or a comic panel (always one small call)."""

    async def run(ctx, doc, provider, cfg):
        kind, plan = kind_of(doc), ctx["outline"]
        total = PARTS[kind]
        beats = plan["beats"]
        beat = beat_for(beats, i, total)
        nxt = beat_for(beats, i + 1, total) if i + 1 < total else ""
        ph = photos(ctx, doc)
        if kind == "comic":
            prev = [ctx[f"part_{k + 1}"].get("caption", "") for k in range(i)]
            data = parse_json(await _gen(provider, cfg, "panel", prompts.panel(doc["genre"], plan, ph, i, total, beat, prev)))
            speech = [
                {"who": str(s.get("who", ""))[:24], "text": str(s.get("text", ""))[:80]}
                for s in (data.get("speech") or [])
                if isinstance(s, dict) and str(s.get("text", "")).strip()
            ][:2]
            caption = str(data.get("caption") or "").strip()[:120]
            if not caption and not speech:
                raise ProviderError("short", "That panel came out empty. Asking again…", retryable=True)
            return {"caption": caption, "speech": speech}
        previous = "\n\n".join(ctx[f"part_{k + 1}"]["text"] for k in range(max(0, i - 2), i))  # the last two parts
        if kind == "poem":
            text = clean_prose(await _gen(provider, cfg, "stanza", prompts.stanza(doc["genre"], plan, ph, i, total, beat, nxt, previous)))
            if len([x for x in text.splitlines() if x.strip()]) < 3:
                raise ProviderError("short", "That stanza came out too short. Asking again…", retryable=True)
            return {"text": text}
        text = clean_prose(await _gen(provider, cfg, "scene", prompts.scene(doc["genre"], plan, ph, i, total, beat, nxt, previous)))
        if len(text.split()) < max(40, cfg.min_words // total):
            raise ProviderError("short", "That scene came out too short. Asking for a fuller version…", retryable=True)
        return {"text": text}

    run.__name__ = f"part_{i + 1}"
    return run


def segments(ctx, doc) -> list[str]:
    """The story scenes / poem stanzas in order, with any accepted rewrites applied."""
    kind = kind_of(doc)
    segs = [ctx[f"part_{i + 1}"]["text"] for i in range(PARTS[kind])]
    for k in range(REVISIONS[kind]):
        r = ctx.get(f"revise_{k + 1}") or {}
        if r.get("text") and 1 <= r.get("part", 0) <= len(segs):
            segs[r["part"] - 1] = r["text"]
    return segs


def story_text(ctx, doc) -> str:
    if kind_of(doc) == "comic":
        return "\n".join(
            " ".join([ctx[f"part_{i + 1}"].get("caption", "")] + [s["text"] for s in ctx[f"part_{i + 1}"].get("speech", [])]).strip()
            for i in range(PARTS["comic"])
        )
    return "\n\n".join(segments(ctx, doc))


MAX_AVG_SENTENCE = 14  # words per sentence; picture-book prose stays under this
MAX_LONG_WORDS = 0.07  # share of words with 9+ letters


def reading_difficulty(text: str) -> tuple[float, float]:
    """(average sentence length in words, share of long words): a cheap readability check, no model needed."""
    sentences = [s for s in re.split(r"[.!?]+[\"”')\]]*\s+", text.strip()) if s.strip()]
    words = re.findall(r"[A-Za-z']+", text)
    return len(words) / max(1, len(sentences)), sum(1 for w in words if len(w) >= 9) / max(1, len(words))


async def critique(ctx, doc, provider, cfg):
    """An editor's pass over the whole piece that returns a SMALL list of fixes (input is big, output is tiny)."""
    kind, segs = kind_of(doc), segments(ctx, doc)
    data = parse_json(await _gen(provider, cfg, "critique", prompts.critique(kind, doc["genre"], ctx["outline"], segs)))
    fixes, seen = [], set()
    for f in data.get("fixes") or []:
        try:
            n = int(f.get("part", f.get("scene")))
        except (AttributeError, TypeError, ValueError):
            continue
        if 1 <= n <= len(segs) and n not in seen and (f.get("problem") or f.get("instruction")):
            seen.add(n)
            fixes.append({"part": n, "problem": str(f.get("problem", ""))[:300], "instruction": str(f.get("instruction", ""))[:300]})
    verdict = str(data.get("verdict", "ok")).lower()
    fixes = [] if verdict == "great" else fixes
    easy = []
    if kind == "story":
        # Safety net for the children's-book rule: scenes that are measurably too hard to read are always rewritten
        # first, even if the model called the story great.
        hard = []
        for n, text in enumerate(segs, 1):
            avg, long_share = reading_difficulty(text)
            if avg > MAX_AVG_SENTENCE or long_share > MAX_LONG_WORDS:
                hard.append((avg / MAX_AVG_SENTENCE + long_share / MAX_LONG_WORDS, n, avg))
        easy = [
            {
                "part": n,
                "problem": f"Too hard for young or beginner readers (sentences average {avg:.0f} words, many long words).",
                "instruction": "Rewrite with very short sentences (under 12 words) and simple everyday words. Keep every event the same.",
            }
            for _, n, avg in sorted(hard, reverse=True)
        ]
    merged = easy + [f for f in fixes if f["part"] not in {e["part"] for e in easy}]
    return {"verdict": verdict, "fixes": merged[: REVISIONS[kind]]}


def _revise(k: int):
    async def run(ctx, doc, provider, cfg):
        """Rewrite one flagged part. Makes no model call at all when the review found nothing left to fix."""
        kind = kind_of(doc)
        fixes = (ctx.get("critique") or {}).get("fixes") or []
        if k >= len(fixes):
            return {"skipped": True}
        fix = fixes[k]
        n = fix["part"]
        segs = segments(ctx, doc)  # includes earlier rewrites
        prompt = prompts.revise(
            kind, doc["genre"], ctx["outline"], segs[n - 2] if n > 1 else "", segs[n - 1], segs[n] if n < len(segs) else "", n, fix
        )
        text = clean_prose(await _gen(provider, cfg, "revise", prompt))
        old = segs[n - 1]
        if kind == "poem":
            ok = 3 <= len([x for x in text.splitlines() if x.strip()]) <= 6
        else:
            ok = 0.5 * len(old.split()) <= len(text.split()) <= 2.5 * len(old.split())
        return {"part": n, "text": text} if ok else {"skipped": True}  # truncated or runaway: keep the original

    run.__name__ = f"revise_{k + 1}"
    return run


def _photo_index(value, fallback: int, n: int) -> int:
    try:
        return max(0, min(int(value) - 1, n - 1))
    except (TypeError, ValueError):
        return fallback % n


async def illustrate(ctx, doc, provider, cfg):
    """No model call. The plan already says which photo fits each moment; the UI sizes the photo with CSS."""
    ids, plan, kind = doc["image_ids"], ctx["outline"], kind_of(doc)
    if kind == "comic":  # one photo per panel, with the words the panel call wrote
        panels = plan.get("panels") or []
        out = []
        for i in range(PARTS["comic"]):
            src = panels[i].get("source_image") if i < len(panels) and isinstance(panels[i], dict) else None
            part = ctx[f"part_{i + 1}"]
            out.append({"image_id": ids[_photo_index(src, i, len(ids))], "caption": part["caption"], "speech": part["speech"]})
        return out
    out = []
    for i, sc in enumerate((plan.get("scenes") or [])[:5]):
        if isinstance(sc, dict):
            out.append({"caption": str(sc.get("caption", ""))[:80], "image_id": ids[_photo_index(sc.get("source_image"), i, len(ids))]})
    if not out:  # the model skipped the scenes: spread a few beats across the piece instead
        beats = plan["beats"]
        k = min(scene_count(len(ids)), len(beats))
        for i in range(k):
            beat = beats[round(i * (len(beats) - 1) / max(1, k - 1))]
            out.append({"caption": str(beat)[:70].rstrip(" ,.;"), "image_id": ids[i % len(ids)]})
    return out


async def finalize(ctx, doc, provider, cfg):
    kind = kind_of(doc)
    objects = sorted({o for p in photos(ctx, doc) for o in p.get("objects", [])})[:16]
    result = {
        "kind": kind,
        "title": ctx["outline"].get("title", "Untitled"),
        "genre": doc["genre"],
        "text": story_text(ctx, doc),
        "objects": objects,
        "image_ids": doc["image_ids"],
        "polished": any((ctx.get(f"revise_{k + 1}") or {}).get("text") for k in range(REVISIONS[kind])),
    }
    result["panels" if kind == "comic" else "scenes"] = ctx["illustrate"]
    if kind == "comic":
        result["scenes"] = []
    return result


STEP_FUNCS = {
    f.__name__: f
    for f in (
        *(_vision(i) for i in range(MAX_PHOTOS)),
        outline,
        *(_part(i) for i in range(MAX_PARTS)),
        critique,
        *(_revise(k) for k in range(MAX_REVISIONS)),
        illustrate,
        finalize,
    )
}
