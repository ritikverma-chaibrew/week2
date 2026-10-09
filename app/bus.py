import asyncio

# story_id -> queues of the SSE streams watching it. Items are story snapshots.
BUS: dict[str, set[asyncio.Queue]] = {}


def publish(story_id: str, item: dict) -> None:
    for q in list(BUS.get(story_id, ())):
        q.put_nowait(item)
