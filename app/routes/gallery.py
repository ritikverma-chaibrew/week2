from fastapi import APIRouter, HTTPException, Query

from .. import db

router = APIRouter(prefix="/api/gallery")


@router.get("")
async def list_gallery(limit: int = Query(12, ge=1, le=48), skip: int = Query(0, ge=0)):
    """Public stories, newest first. Only stories whose author ticked 'share' appear."""
    cur = (
        db.stories.find(
            {"public": True, "status": "done"},
            {"result.title": 1, "result.genre": 1, "result.kind": 1, "result.text": 1, "image_ids": 1, "created_at": 1},
        )
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    items = []
    async for d in cur:
        text = d["result"]["text"]
        items.append(
            {
                "id": d["_id"],
                "title": d["result"]["title"],
                "genre": d["result"]["genre"],
                "kind": d["result"].get("kind", "story"),
                "excerpt": text[:240].rsplit(" ", 1)[0] + "…" if len(text) > 240 else text,
                "words": len(text.split()),
                "thumbs": d["image_ids"][:3],
                "created_at": d["created_at"].isoformat(),
            }
        )
    return {"items": items}


@router.get("/{story_id}")
async def gallery_story(story_id: str):
    d = await db.stories.find_one({"_id": story_id, "public": True, "status": "done"}, {"result": 1})
    if not d:
        raise HTTPException(404, "That story isn't in the gallery.")
    return d["result"]
