import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import db
from ..config import settings
from ..pipeline import runner
from ..pipeline.estimate import KINDS
from ..pipeline.prompts import GENRES
from ..providers import ProviderConfig, get_cfg, make_provider

router = APIRouter(prefix="/api/stories")
_tasks: set[asyncio.Task] = set()
PRIVATE_TTL = timedelta(days=7)


class StoryIn(BaseModel):
    image_ids: list[str]
    genre: str
    kind: str = "story"  # story | poem | comic
    share: bool = False  # show in the public gallery


def _launch(story_id: str, cfg: ProviderConfig) -> None:
    task = asyncio.create_task(runner.run_story(story_id, cfg))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


@router.post("")
async def create_story(body: StoryIn, cfg: ProviderConfig = Depends(get_cfg)):
    if body.genre not in GENRES:
        raise HTTPException(400, f"Genre must be one of: {', '.join(GENRES)}")
    if body.kind not in KINDS:
        raise HTTPException(400, f"Kind must be one of: {', '.join(KINDS)}")
    if not settings.min_images <= len(body.image_ids) <= settings.max_images:
        raise HTTPException(400, f"Provide {settings.min_images} to {settings.max_images} images.")
    make_provider(cfg)  # fail fast (e.g. missing key) before any work is queued
    found = await db.images.count_documents({"_id": {"$in": body.image_ids}})
    if found != len(body.image_ids):
        raise HTTPException(400, "Some photos expired. Please upload them again.")
    story_id, now = uuid.uuid4().hex, datetime.now(timezone.utc)
    await db.stories.insert_one(
        {
            "_id": story_id,
            "genre": body.genre,
            "kind": body.kind,
            "image_ids": body.image_ids,
            "tier": cfg.kind,
            "share": body.share,
            "public": False,
            "status": "pending",
            "llm": {"calls": 0, "gap": cfg.call_gap, "factor": cfg.speed, "waiting_until": None},
            "steps": runner.new_steps(len(body.image_ids), body.kind),
            "error": None,
            "result": None,
            "created_at": now,
            "expire_at": now + PRIVATE_TTL,  # private stories are auto-deleted; shared ones are kept
        }
    )
    _launch(story_id, cfg)
    return {"id": story_id}


async def _get(story_id: str) -> dict:
    doc = await db.stories.find_one({"_id": story_id})
    if not doc:
        raise HTTPException(404, "Story not found.")
    return doc


@router.get("/{story_id}")
async def get_story(story_id: str):
    return runner.public(await _get(story_id))


@router.post("/{story_id}/retry")
async def retry(story_id: str, cfg: ProviderConfig = Depends(get_cfg)):
    """Resume from the first step that is not done. Finished steps are never re-run."""
    doc = await _get(story_id)
    if story_id in runner.RUNNING:
        raise HTTPException(409, "This story is already being generated.")
    if doc["status"] == "done":
        raise HTTPException(409, "This story is already finished.")
    make_provider(cfg)
    for s in doc["steps"]:
        if s["status"] != "done":
            s.update(status="pending", error=None, attempts=0)
    await db.stories.update_one(
        {"_id": story_id}, {"$set": {"steps": doc["steps"], "status": "pending", "error": None, "tier": cfg.kind}}
    )
    _launch(story_id, cfg)
    return {"id": story_id}


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, separators=(',', ':'))}\n\n"


@router.get("/{story_id}/events")
async def events(story_id: str):
    doc = await _get(story_id)
    q: asyncio.Queue = asyncio.Queue()
    runner.BUS.setdefault(story_id, set()).add(q)

    async def stream():
        try:
            snap = runner.public(doc)
            yield _sse(snap)
            while snap["status"] not in runner.TERMINAL:
                try:
                    item = await asyncio.wait_for(q.get(), 15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                snap = item
                yield _sse(snap)
        finally:
            runner.BUS.get(story_id, set()).discard(q)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
    )
