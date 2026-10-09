import asyncio
import logging
import time

from .estimate import NON_LLM, VISION_PARALLEL, eta_seconds, total_seconds
from .throttle import ThrottledProvider

from .. import db
from ..bus import BUS, publish
from ..errors import ProviderError
from ..providers import make_provider
from .steps import OPTIONAL, STEP_FUNCS, step_defs

log = logging.getLogger("touchgrass.runner")

MAX_ATTEMPTS = 4
RUNNING: set[str] = set()
TERMINAL = ("done", "failed")


def new_steps(n_photos: int = 3, kind: str = "story") -> list[dict]:
    return [
        {"name": n, "label": l, "status": "pending", "attempts": 0, "error": None, "output": None, "ms": None}
        for n, l in step_defs(n_photos, kind)
    ]


def llm_state(doc: dict) -> dict:
    llm = doc.get("llm") or {}
    kind = doc.get("kind", "story")
    gap, factor, calls = llm.get("gap", 0), llm.get("factor", 1.0), llm.get("calls", 0)
    names = [s["name"] for s in doc["steps"] if s["name"] not in NON_LLM]
    left = [s["name"] for s in doc["steps"] if s["name"] not in NON_LLM and s["status"] not in ("done", "skipped")]
    waiting = llm.get("waiting_until")
    return {
        "calls": calls,
        "planned": len(names),
        "gap": gap,
        "total": total_seconds(names, gap, factor, kind),
        "eta": 0 if doc["status"] == "done" else eta_seconds(left, gap, factor, kind),
        "waiting": max(0, round(waiting - time.time())) if waiting else 0,
    }


def preview(doc: dict) -> dict | None:
    """The title and the parts written so far (scenes, stanzas or panels), so the page can show them while the
    rest is still being written. Gone once the tale is done: the finished result replaces it."""
    if doc.get("status") == "done":
        return None
    out = {s["name"]: s.get("output") or {} for s in doc["steps"] if s["status"] == "done"}
    parts = [
        {k: o[k] for k in ("text", "caption", "speech") if k in o}
        for name, o in out.items()
        if name.startswith("part_")
    ]
    title = (out.get("outline") or {}).get("title", "")
    return {"title": str(title)[:120], "parts": parts} if parts or title else None


def public(doc: dict) -> dict:
    """What the browser sees: step status and a preview of the finished parts, never anything secret."""
    return {
        "llm": llm_state(doc),
        "id": doc["_id"],
        "status": doc["status"],
        "genre": doc["genre"],
        "kind": doc.get("kind", "story"),
        "error": doc.get("error"),
        "result": doc.get("result"),
        "preview": preview(doc),
        "steps": [
            {k: s.get(k) for k in ("name", "label", "status", "attempts", "error", "ms")} for s in doc["steps"]
        ],
    }


async def _persist_and_publish(doc: dict) -> None:
    await db.stories.update_one(
        {"_id": doc["_id"]},
        {"$set": {k: doc.get(k) for k in ("status", "steps", "error", "result", "llm")}},
    )
    publish(doc["_id"], public(doc))


async def _run_step(step, ctx, doc, provider, cfg, funcs, save, sleep) -> bool:
    """One step with retries. Returns False when it failed for good (and the tale with it)."""
    step["error"] = None
    started = time.perf_counter()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        step["attempts"], step["status"] = attempt, "running"
        await save(doc)
        try:
            step["output"] = await funcs[step["name"]](ctx, doc, provider, cfg)
            step["status"] = "done"
            step["ms"] = int((time.perf_counter() - started) * 1000)
            ctx[step["name"]] = step["output"]
            await save(doc)
            return True
        except ProviderError as e:
            err = e
        except Exception:  # noqa: BLE001
            log.exception("step %s crashed", step["name"])
            err = ProviderError("internal", "Something went wrong on our side.")
        step["error"] = err.message
        if err.retryable and attempt < MAX_ATTEMPTS:
            step["status"] = "retrying"
            await save(doc)
            # Back off only after a failure: attempt-number x the base wait (30 s, 60 s, 90 s on AI Studio).
            # A successful call needs no wait, so the next one goes straight away.
            delay = attempt * getattr(cfg, "retry_delay", 30)
            llm = doc.get("llm")
            if llm is not None:
                llm["waiting_until"] = time.time() + delay
                await save(doc)
            await sleep(delay)
            if llm is not None:
                llm["waiting_until"] = None
            continue
        if step["name"] in OPTIONAL:  # e.g. proofreading: ship the story as written
            step["status"] = "skipped"
            await save(doc)
            return True
        step["status"], doc["status"], doc["error"] = "failed", "failed", err.as_dict()
        await save(doc)
        return False
    return False


async def execute(doc, provider, cfg, funcs, save, sleep=asyncio.sleep) -> None:
    """Run pending steps in order. Done steps are skipped, so a retry resumes where it failed.
    Photos don't depend on each other, so they are looked at VISION_PARALLEL at a time."""
    ctx = {s["name"]: s["output"] for s in doc["steps"] if s["status"] == "done"}
    doc["status"], doc["error"] = "running", None
    await save(doc)
    steps, i = doc["steps"], 0
    while i < len(steps):
        if steps[i]["name"].startswith("vision_"):
            group = []
            while i < len(steps) and steps[i]["name"].startswith("vision_"):
                if steps[i]["status"] != "done":
                    group.append(steps[i])
                i += 1
            gate = asyncio.Semaphore(VISION_PARALLEL)

            async def one(step):
                async with gate:
                    return await _run_step(step, ctx, doc, provider, cfg, funcs, save, sleep)

            ok = all(await asyncio.gather(*(one(s) for s in group)))
        else:
            step = steps[i]
            i += 1
            if step["status"] == "done":
                continue
            ok = await _run_step(step, ctx, doc, provider, cfg, funcs, save, sleep)
        if not ok:
            return
    doc["status"], doc["result"] = "done", ctx["finalize"]
    await save(doc)


async def publish_to_gallery(doc: dict) -> None:
    """Keep a shared story's photos (no TTL) and drop the model-sized copies to save space."""
    await db.images.update_many(
        {"_id": {"$in": doc["image_ids"]}}, {"$unset": {"created_at": "", "llm": ""}}
    )
    await db.stories.update_one({"_id": doc["_id"]}, {"$set": {"public": True}, "$unset": {"expire_at": ""}})


async def run_story(story_id: str, cfg) -> None:
    RUNNING.add(story_id)
    try:
        doc = await db.stories.find_one({"_id": story_id})
        llm = doc.setdefault("llm", {"calls": 0})
        llm.update(gap=cfg.call_gap, factor=cfg.speed, waiting_until=None)
        provider = ThrottledProvider(make_provider(cfg, story_id), cfg.call_gap, doc, _persist_and_publish)
        await execute(doc, provider, cfg, STEP_FUNCS, _persist_and_publish)
        if doc["status"] == "done" and doc.get("share"):
            await publish_to_gallery(doc)
    except ProviderError as e:  # e.g. no API key
        await db.stories.update_one({"_id": story_id}, {"$set": {"status": "failed", "error": e.as_dict()}})
        doc = await db.stories.find_one({"_id": story_id})
        publish(story_id, public(doc))
    except Exception:  # noqa: BLE001
        log.exception("story %s crashed", story_id)
    finally:
        RUNNING.discard(story_id)
