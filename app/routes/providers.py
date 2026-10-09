from fastapi import APIRouter, Depends, Query

from ..errors import ProviderError
from ..providers import ProviderConfig, get_cfg, make_provider
from ..pipeline.estimate import KINDS, llm_step_names, total_seconds
from ..providers.base import ROLES

router = APIRouter(prefix="/api/provider")


@router.post("/test")
async def test(cfg: ProviderConfig = Depends(get_cfg)):
    """Round trip per distinct chosen model, so Setup can say exactly which model or key is wrong."""
    try:
        provider = make_provider(cfg)
        models = list(dict.fromkeys(cfg.model(r) for r in ROLES))
        for m in models:
            await provider.generate("Reply with the single word OK.", [], m, 0, 1, 8)
    except ProviderError as e:
        return {"ok": False, **e.as_dict()}
    n = len(models)
    return {"ok": True, "message": f"Connected! {n} model{'s' if n != 1 else ''} checked: {', '.join(m or 'auto' for m in models)}."}


@router.get("/models")
async def models(cfg: ProviderConfig = Depends(get_cfg)):
    return {"models": await make_provider(cfg).list_models()}


@router.get("/estimate")
async def estimate(
    photos: int = Query(5, ge=5, le=10), kind: str = Query("story"), cfg: ProviderConfig = Depends(get_cfg)
):
    """Planned AI calls and typical total time for a story / poem / comic, shown before starting."""
    kind = kind if kind in KINDS else "story"
    names = llm_step_names(photos, kind)
    return {"kind": kind, "calls": len(names), "gap": cfg.call_gap, "seconds": total_seconds(names, cfg.call_gap, cfg.speed, kind)}
