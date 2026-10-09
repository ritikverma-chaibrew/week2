from dataclasses import dataclass, field

import httpx

from ..config import settings

# One model per task: the fast MoE model reads single small photos and plans (JSON), the big dense model
# writes and edits the prose. LM Studio has no defaults: it uses whatever the user picks or has loaded.
ROLES = ("vision", "outline", "story")
_AI_BIG, _AI_FAST = "gemma-4-31b-it", "gemma-4-26b-a4b-it"
DEFAULT_MODELS = {
    "aistudio": {"vision": _AI_FAST, "outline": _AI_FAST, "story": _AI_BIG},
    "lmstudio": {},
}

_client: httpx.AsyncClient | None = None


def http() -> httpx.AsyncClient:
    """One shared connection pool for all provider calls."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(180, connect=10))
    return _client


async def close_http() -> None:
    if _client is not None and not _client.is_closed:
        await _client.aclose()


@dataclass
class ProviderConfig:
    """Per-request provider settings. Held in memory only, never persisted."""

    kind: str = "aistudio"  # aistudio | lmstudio
    api_key: str = ""
    lm_url: str = "http://localhost:1234/v1"
    models: dict = field(default_factory=dict)  # role -> user-chosen model id
    gap_override: int | None = None  # seconds between AI calls chosen with the UI slider
    min_words: int = 350  # shortest acceptable story

    @property
    def call_gap(self) -> int:
        """Seconds to keep between LLM calls: hosted APIs have per-minute limits, local models don't."""
        if self.gap_override is not None:
            return max(0, min(self.gap_override, 120))
        return settings.llm_call_gap_seconds if self.kind == "aistudio" else 0

    @property
    def retry_delay(self) -> int:
        """Seconds to wait before retrying a failed step."""
        return self.call_gap or 5

    @property
    def speed(self) -> float:
        """Rough latency multiplier for time estimates (local models are slower than hosted ones)."""
        return 2.5 if self.kind == "lmstudio" else 1.0

    def model(self, role: str) -> str:
        return self.models.get(role) or DEFAULT_MODELS[self.kind].get(role, "")


class GemmaProvider:
    async def generate(
        self,
        prompt: str,
        images: list[bytes],
        model: str,
        temperature: float,
        top_p: float,
        max_tokens: int,
    ) -> str:
        raise NotImplementedError

    async def list_models(self) -> list[str]:
        raise NotImplementedError
