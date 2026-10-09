import base64

import httpx

from ..errors import ProviderError
from .base import GemmaProvider, http


class LMStudio(GemmaProvider):
    """LM Studio's OpenAI-compatible local server. Model ids come from what the user has downloaded."""

    def __init__(self, base_url: str):
        self.base = (base_url or "http://localhost:1234/v1").rstrip("/")
        self._auto: str | None = None

    def _unreachable(self) -> ProviderError:
        return ProviderError(
            "lm_unreachable",
            f"LM Studio server not reachable at {self.base}. Start the Local Server in LM Studio (see Setup).",
        )

    async def _pick(self, model: str) -> str:
        if model:
            return model
        if self._auto is None:
            models = await self.list_models()
            if not models:
                raise ProviderError("model_not_found", "No model is available in LM Studio. Download a Gemma model first.")
            self._auto = next((m for m in models if "gemma" in m.lower()), models[0])
        return self._auto

    async def generate(self, prompt, images, model, temperature, top_p, max_tokens) -> str:
        content = prompt
        if images:
            content = [{"type": "text", "text": prompt}] + [
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b).decode()}}
                for b in images
            ]
        model = await self._pick(model)
        body = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            r = await http().post(f"{self.base}/chat/completions", json=body)
        except httpx.ConnectError:
            raise self._unreachable()
        except httpx.TimeoutException:
            raise ProviderError("timeout", "The local model took too long to answer. Retrying…", retryable=True)
        except httpx.HTTPError:
            raise self._unreachable()
        if r.status_code != 200:
            msg = r.text[:200]
            if r.status_code in (400, 404):
                low = msg.lower()
                if "image" in low or "vision" in low:
                    raise ProviderError(
                        "no_vision",
                        f"'{model}' can't read images. Pick a vision-capable Gemma for the photo step.",
                    )
                raise ProviderError("model_not_found", f"LM Studio could not use model '{model}'. {msg}")
            raise ProviderError("upstream", f"LM Studio error: {msg}", retryable=r.status_code >= 500)
        try:
            text = r.json()["choices"][0]["message"]["content"] or ""
        except Exception:  # noqa: BLE001
            text = ""
        if not text.strip():
            raise ProviderError("empty", "The model returned an empty answer. Retrying…", retryable=True)
        return text

    async def list_models(self) -> list[str]:
        try:
            r = await http().get(f"{self.base}/models")
        except httpx.HTTPError:
            raise self._unreachable()
        if r.status_code != 200:
            raise self._unreachable()
        return [m["id"] for m in r.json().get("data", []) if "embed" not in m["id"].lower()]
