from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .errors import ProviderError
from .providers.base import close_http
from .routes import gallery, images, providers, stories

FRONTEND = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_ok = await init_db()
    yield
    await close_http()


app = FastAPI(title="Touch Grass Tales", lifespan=lifespan)
class SmartGZip(GZipMiddleware):
    """Gzip everything except the SSE stream, which gzip would buffer (breaking live progress)."""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].endswith("/events"):
            return await self.app(scope, receive, send)
        await super().__call__(scope, receive, send)


app.add_middleware(SmartGZip, minimum_size=1024)


@app.exception_handler(ProviderError)
async def provider_error(_: Request, e: ProviderError):
    return JSONResponse({"error": e.as_dict()}, status_code=e.status)


@app.get("/api/health")
async def health(request: Request):
    return {"ok": True, "db": request.app.state.db_ok}


app.include_router(images.router)
app.include_router(stories.router)
app.include_router(gallery.router)
app.include_router(providers.router)
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
