"""Time estimates for the UI. Seconds are typical model latencies per LLM call on a hosted API."""

KINDS = ("story", "poem", "comic")
PARTS = {"story": 6, "poem": 4, "comic": 6}  # scenes / stanzas / panels, one small call each
REVISIONS = {"story": 3, "poem": 2, "comic": 0}  # at most this many weak parts get rewritten after the review
NON_LLM = {"illustrate", "finalize"}  # steps that make no model call
SECONDS = {
    "vision": 8,
    "outline": 18,
    "part": {"story": 12, "poem": 7, "comic": 8},
    "critique": 14,
    "revise": 12,
}


def llm_step_names(n_photos: int, kind: str = "story") -> list[str]:
    """Model calls in order. The revise calls only happen when the review finds problems (upper bound shown)."""
    names = [f"vision_{i + 1}" for i in range(n_photos)] + ["outline"] + [f"part_{i + 1}" for i in range(PARTS[kind])]
    if REVISIONS[kind]:
        names += ["critique"] + [f"revise_{k + 1}" for k in range(REVISIONS[kind])]
    return names


def _secs(name: str, kind: str) -> int:
    base = name.rsplit("_", 1)[0] if name[-1].isdigit() else name
    s = SECONDS[base]
    return s[kind] if isinstance(s, dict) else s


def total_seconds(names: list[str], gap: int, factor: float = 1.0, kind: str = "story") -> int:
    """Calls start at least `gap` seconds apart (start to start), so a slow call absorbs the pause."""
    ts = [_secs(n, kind) * factor for n in names]
    return round(sum(max(t, gap) for t in ts[:-1]) + ts[-1]) if ts else 0


def eta_seconds(remaining: list[str], gap: int, factor: float = 1.0, kind: str = "story") -> int:
    return total_seconds(remaining, gap, factor, kind)
