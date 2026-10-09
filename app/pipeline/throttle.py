import asyncio
import time


class ThrottledProvider:
    """Wraps a provider: keeps at least `gap` seconds between the START of one LLM call and the start of the next
    (a call that itself takes a while already uses up part of the pause), and counts every call incl. retries."""

    def __init__(self, inner, gap: int, doc: dict, emit):
        self.inner, self.gap, self.doc, self.emit = inner, gap, doc, emit
        self._lock = asyncio.Lock()
        # A new run (e.g. the user pressed Retry) resumes the pause from the last call of the previous run.
        last = doc.get("llm", {}).get("last_call_at")
        self._last_start: float | None = time.monotonic() - max(0.0, time.time() - last) if last else None

    async def generate(self, *args, **kwargs) -> str:
        async with self._lock:
            llm = self.doc["llm"]
            if self.gap and self._last_start is not None:
                wait = self._last_start + self.gap - time.monotonic()
                if wait > 0:
                    llm["waiting_until"] = time.time() + wait
                    await self.emit(self.doc)
                    await asyncio.sleep(wait)
                    llm["waiting_until"] = None
            self._last_start = time.monotonic()
            llm["last_call_at"] = time.time()
            llm["calls"] += 1
            await self.emit(self.doc)
        return await self.inner.generate(*args, **kwargs)

    async def list_models(self):
        return await self.inner.list_models()
