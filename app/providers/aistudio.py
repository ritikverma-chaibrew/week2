import base64

import httpx

from ..errors import ProviderError
from .base import GemmaProvider, http

BASE = "https://generativelanguage.googleapis.com/v1beta"
# Gemma 4 may spend output tokens on hidden reasoning; leave room so the visible answer is not starved.
THINK_HEADROOM = 2048


def _message(r: httpx.Response) -> str:
    try:
        return r.json().get("error", {}).get("message", "") or r.text[:200]
    except Exception:  # noqa: BLE001
        return r.text[:200]


def map_error(r: httpx.Response) -> ProviderError:
    s, msg = r.status_code, _message(r)
    low = msg.lower()
    if s in (400, 401, 403) and ("api key" in low or "api_key" in low or s in (401, 403)):
        return ProviderError(
            "bad_key",
            "Google AI Studio rejected your API key. Check it on the Setup page or create a new one.",
            status=401,
        )
    if s == 400 and ("modality" in low or "image" in low):
        return ProviderError(
            "no_vision", "This Gemma model can't read images. Pick a vision-capable Gemma 4 model.", status=400
        )
    if s == 404:
        return ProviderError(
            "model_not_found", f"Model not available for your key. ({msg[:120]})", status=404
        )
    if s == 429:
        return ProviderError(
            "quota",
            "Free quota reached on AI Studio. Wait a minute and retry, or switch to LM Studio.",
            retryable=True,
            status=429,
        )
    if s >= 500:
        return ProviderError("upstream", "Google AI Studio is having trouble. Retrying…", retryable=True)
    return ProviderError("bad_request", f"AI Studio error: {msg[:200]}", status=400)


class AIStudio(GemmaProvider):
    def __init__(self, api_key: str):
        self.key = api_key
        self.no_thinking = True  # ask for thinkingLevel "minimal"; dropped automatically if the API rejects it
        self.headroom = THINK_HEADROOM  # extra output tokens; doubled whenever a reply runs out of budget

    async def generate(self, prompt, images, model, temperature, top_p, max_tokens) -> str:
        # Gemma on the Gemini API has no system-instruction or JSON mode: everything goes in the user turn.
        parts = [{"text": prompt}]
        parts += [
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(b).decode()}}
            for b in images
        ]
        config = {"temperature": temperature, "topP": top_p, "maxOutputTokens": max_tokens + self.headroom}
        if self.no_thinking: 
            # Gemma 4 "thinks" by default and hidden reasoning eats the output budget (finish reason MAX_TOKENS,
            # empty answer). "minimal" turns it off; our tasks (JSON, prose) don't need it.
            config["thinkingConfig"] = {"thinkingLevel": "minimal"}
        body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": config}
        try:
            r = await http().post(
                f"{BASE}/models/{model}:generateContent", json=body, headers={"x-goog-api-key": self.key}
            )
        except httpx.TimeoutException:
            raise ProviderError("timeout", "The model took too long to answer. Retrying…", retryable=True)
        except httpx.HTTPError:
            raise ProviderError(
                "network", "Can't reach Google AI Studio. Check your internet connection.", retryable=True
            )
        if r.status_code == 404:
            err = map_error(r)
            try:  # tell the user what their key can actually use
                avail = await self.list_models()
            except ProviderError:
                avail = []
            hint = f" Available Gemma models: {', '.join(avail)}." if avail else ""
            raise ProviderError(
                err.code, f"Model '{model}' isn't available for your key.{hint} Change it under Advanced on the Setup page.",
                status=404,
            )
        if r.status_code == 400 and self.no_thinking and "think" in _message(r).lower():
            self.no_thinking = False  # this model doesn't accept thinkingConfig: retry once without it
            return await self.generate(prompt, images, model, temperature, top_p, max_tokens)
        if r.status_code != 200:
            raise map_error(r)
        data = r.json()
        if data.get("promptFeedback", {}).get("blockReason"):
            raise ProviderError("safety", "Gemma declined this content. Try a different photo.", status=422)
        cands = data.get("candidates") or []
        parts = cands[0].get("content", {}).get("parts", []) if cands else []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))  # skip reasoning parts
        if not text.strip():
            reason = (cands[0].get("finishReason") if cands else None) or "no candidates"
            if reason == "MAX_TOKENS":
                self.headroom = min(self.headroom * 2, 16000)  # the retry gets a bigger budget
                msg = ("The model used up its whole output budget on hidden reasoning before answering "
                       "(finish reason: MAX_TOKENS). Retrying with a bigger budget…")
            else:
                msg = f"The model returned an empty answer (finish reason: {reason}). Retrying…"
            raise ProviderError("empty", msg, retryable=True)
        return text

    async def list_models(self) -> list[str]:
        try:
            r = await http().get(f"{BASE}/models", params={"pageSize": 200}, headers={"x-goog-api-key": self.key})
        except httpx.HTTPError:
            raise ProviderError("network", "Can't reach Google AI Studio. Check your internet connection.")
        if r.status_code != 200:
            raise map_error(r)
        names = [m["name"].removeprefix("models/") for m in r.json().get("models", [])]
        return sorted(n for n in names if n.startswith("gemma"))
