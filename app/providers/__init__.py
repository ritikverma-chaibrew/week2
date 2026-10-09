import json

from fastapi import Header

from ..errors import ProviderError
from .aistudio import AIStudio
from .base import ROLES, GemmaProvider, ProviderConfig
from .lmstudio import LMStudio

KINDS = ("aistudio", "lmstudio")


def make_provider(cfg: ProviderConfig, story_id: str = "") -> GemmaProvider:
    if cfg.kind == "lmstudio":
        return LMStudio(cfg.lm_url)
    if not cfg.api_key:
        raise ProviderError("no_key", "No Google AI Studio API key set. Add it in step 1 on the Create page.", status=401)
    return AIStudio(cfg.api_key)


def get_cfg(
    x_provider: str = Header("aistudio"),
    x_api_key: str = Header(""),
    x_lm_url: str = Header(""),
    x_models: str = Header(""),
    x_call_gap: str = Header(""),
) -> ProviderConfig:
    """FastAPI dependency: provider settings come from request headers and are never stored."""
    cfg = ProviderConfig(kind=x_provider if x_provider in KINDS else "aistudio", api_key=x_api_key.strip())
    if x_call_gap.strip().isdigit():
        cfg.gap_override = int(x_call_gap)
    if x_lm_url:
        cfg.lm_url = x_lm_url
    try:
        picked = json.loads(x_models) if x_models else {}
        cfg.models = {r: str(picked[r])[:120] for r in ROLES if isinstance(picked, dict) and picked.get(r)}
    except ValueError:
        pass
    return cfg


__all__ = ["ProviderConfig", "GemmaProvider", "make_provider", "get_cfg"]
