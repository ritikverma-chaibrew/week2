import asyncio
import time

import pytest

from app.errors import ProviderError
from app.pipeline.runner import execute, new_steps
from app.pipeline.steps import parse_json


# ---------------------------------------------------------------- JSON parsing
def test_parse_json_is_lenient():
    assert parse_json('Sure!\n```json\n{"a": [1, 2,],}\n```') == {"a": [1, 2]}
    with pytest.raises(ProviderError):
        parse_json("nothing")


# ---------------------------------------------------------------- runner: retries, resume, optional steps
class Fake:
    def __init__(self, fail_at=None, times=1, retryable=True):
        self.calls, self.fail_at, self.times, self.retryable = [], fail_at, times, retryable


def _funcs(fake, kind="story", n=3):
    def build(name):
        async def f(ctx, doc, provider, cfg):
            fake.calls.append(name)
            if name == fake.fail_at and fake.times > 0:
                fake.times -= 1
                raise ProviderError("quota", "limit", retryable=fake.retryable)
            return {"title": "t"} if name == "finalize" else {"ok": name}

        return f

    return {s["name"]: build(s["name"]) for s in new_steps(n, kind)}


def _doc(kind="story"):
    return {"_id": "s", "genre": "funny", "kind": kind, "status": "pending", "steps": new_steps(3, kind)}


def _run(doc, fake, cfg=None):
    async def save(_):
        pass

    async def nosleep(_):
        pass

    asyncio.run(execute(doc, None, cfg, _funcs(fake, doc["kind"]), save, nosleep))


def test_transient_failure_retries_same_step_only():
    fake, doc = Fake(fail_at="part_3", times=2), _doc()
    _run(doc, fake)
    assert doc["status"] == "done" and fake.calls.count("part_3") == 3
    assert fake.calls.count("vision_1") == 1  # earlier steps are not repeated


def test_hard_failure_then_resume_skips_done_steps():
    fake, doc = Fake(fail_at="outline", times=1, retryable=False), _doc()
    _run(doc, fake)
    assert doc["status"] == "failed" and doc["error"]["code"] == "quota"
    assert [s["status"] for s in doc["steps"]][:5] == ["done", "done", "done", "failed", "pending"]
    fake.calls.clear()
    _run(doc, fake)  # "retry": same doc, the failed step runs again
    assert doc["status"] == "done"
    assert "vision_1" not in fake.calls and "vision_3" not in fake.calls and fake.calls[0] == "outline"


def test_optional_review_failure_does_not_fail_the_story():
    fake, doc = Fake(fail_at="critique", times=99, retryable=True), _doc()
    _run(doc, fake)
    status = {s["name"]: s["status"] for s in doc["steps"]}
    assert doc["status"] == "done" and status["critique"] == "skipped" and status["finalize"] == "done"
    assert fake.calls.count("critique") == 4  # all attempts used first


def test_retry_wait_grows_with_each_failed_attempt_then_resets():
    from app.providers.base import ProviderConfig

    fake, doc, sleeps = Fake(fail_at="part_1", times=3, retryable=True), _doc(), []

    async def save(_):
        pass

    async def rec(s):
        sleeps.append(s)

    asyncio.run(execute(doc, None, ProviderConfig(kind="aistudio"), _funcs(fake), save, rec))
    assert doc["status"] == "done" and sleeps == [30, 60, 90] and fake.calls.count("part_1") == 4

    fake2, doc2, sleeps2 = Fake(fail_at="outline", times=2), _doc(), []

    async def rec2(s):
        sleeps2.append(s)

    asyncio.run(execute(doc2, None, ProviderConfig(kind="lmstudio"), _funcs(fake2), save, rec2))
    assert sleeps2 == [5, 10]  # local models use a short base pause


def test_steps_differ_per_kind():
    from app.pipeline.steps import STEP_FUNCS, step_defs

    story = [n for n, _ in step_defs(5, "story")]
    poem = [n for n, _ in step_defs(5, "poem")]
    comic = [n for n, _ in step_defs(5, "comic")]
    assert story.count("part_6") == 1 and "critique" in story and "revise_3" in story
    assert "part_4" in poem and "part_5" not in poem and "revise_2" in poem and "revise_3" not in poem
    assert "part_6" in comic and "critique" not in comic  # comics are lettered panel by panel, no review pass
    for kind in ("story", "poem", "comic"):
        assert {n for n, _ in step_defs(10, kind)} <= set(STEP_FUNCS)


# ---------------------------------------------------------------- pacing
def test_throttle_spaces_calls_and_counts_them():
    from app.pipeline.throttle import ThrottledProvider

    class Inner:
        async def generate(self, *a, **k):
            return "ok"

    async def scenario():
        doc, emitted = {"llm": {"calls": 0, "waiting_until": None}}, []

        async def emit(d):
            emitted.append(d["llm"]["waiting_until"])

        tp = ThrottledProvider(Inner(), 1, doc, emit)
        t0 = time.monotonic()
        await tp.generate("a")
        await tp.generate("b")
        assert time.monotonic() - t0 >= 1.0 and doc["llm"]["calls"] == 2
        assert any(w for w in emitted)  # the UI was told it is waiting

    asyncio.run(scenario())


def test_throttle_counts_pause_from_call_start():
    from app.pipeline.throttle import ThrottledProvider

    class Slow:
        async def generate(self, *a, **k):
            await asyncio.sleep(0.6)
            return "ok"

    async def scenario():
        doc = {"llm": {"calls": 0, "waiting_until": None}}

        async def emit(d):
            pass

        tp = ThrottledProvider(Slow(), 1, doc, emit)  # calls start >= 1 s apart
        t0 = time.monotonic()
        await tp.generate("a")  # runs 0.6 s
        await tp.generate("b")  # may only start at 1.0 s, so waits just 0.4 s (not a full extra second)
        assert 1.55 <= time.monotonic() - t0 <= 1.95, time.monotonic() - t0

    asyncio.run(scenario())


def test_manual_retry_respects_pause_since_last_call():
    from app.pipeline.throttle import ThrottledProvider

    class Inner:
        async def generate(self, *a, **k):
            return "ok"

    async def scenario():
        async def emit(d):
            pass

        doc = {"llm": {"calls": 3, "waiting_until": None, "last_call_at": time.time() - 0.4}}
        t0 = time.monotonic()
        await ThrottledProvider(Inner(), 1, doc, emit).generate("retry")
        assert 0.45 <= time.monotonic() - t0 <= 0.9, time.monotonic() - t0
        assert doc["llm"]["last_call_at"] > time.time() - 1  # remembered for the next run

        old = {"llm": {"calls": 3, "waiting_until": None, "last_call_at": time.time() - 100}}
        t0 = time.monotonic()
        await ThrottledProvider(Inner(), 1, old, emit).generate("x")
        assert time.monotonic() - t0 < 0.2  # long ago: no wait at all

    asyncio.run(scenario())


def test_estimates():
    from app.pipeline.estimate import eta_seconds, llm_step_names, total_seconds

    story = llm_step_names(5, "story")
    assert len(story) == 5 + 1 + 6 + 1 + 3 and story[5] == "outline" and story[-4] == "critique"
    # 5 photos are looked at 4 at a time: 2 batches, each as long as one call
    assert total_seconds(story, 30) == (2 + 1 + 6 + 1 + 3 - 1) * 30 + 12  # every call is shorter than the pause
    assert total_seconds(story, 0) == 8 * 2 + 18 + 12 * 6 + 14 + 12 * 3
    assert len(llm_step_names(5, "poem")) == 5 + 1 + 4 + 1 + 2
    comic = llm_step_names(5, "comic")
    assert len(comic) == 5 + 1 + 6 and "critique" not in comic
    assert eta_seconds(["revise_3"], 30) == 12 and eta_seconds(["critique", "revise_1"], 30) == 30 + 12
    assert eta_seconds([], 30) == 0
    assert total_seconds(llm_step_names(5, "poem"), 0, kind="poem") < total_seconds(story, 0)


def test_no_pause_after_success_and_30s_backoff_after_failure():
    from app.providers.base import ProviderConfig

    assert ProviderConfig(kind="aistudio").call_gap == 0 and ProviderConfig(kind="lmstudio").call_gap == 0
    assert ProviderConfig(kind="aistudio").retry_delay == 30  # Google doesn't say how long: 30 s, 60 s, 90 s
    assert ProviderConfig(kind="aistudio", gap_override=10).retry_delay == 30  # independent of any gap
    assert ProviderConfig(kind="lmstudio").retry_delay == 5  # local: no rate limits
    assert ProviderConfig(kind="aistudio", gap_override=999).call_gap == 120  # an explicit gap is still clamped


# ---------------------------------------------------------------- content: story, poem, comic
class P:
    """A scripted provider that records every call."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    async def generate(self, prompt, images, model, *a):
        self.calls.append((prompt, images, model))
        return self.replies.pop(0)


def _cfg():
    from app.providers.base import ProviderConfig

    return ProviderConfig(kind="aistudio")


EASY = "The cat sat on the mat. It was a sunny day. The cat was happy and she smiled. " * 4


def _story_ctx(n=6):
    ctx = {"outline": {"title": "T", "voice": "warm"}, "vision_1": {"objects": ["bench"]}}
    ctx.update({f"part_{i}": {"text": EASY} for i in range(1, n + 1)})
    return ctx


def test_story_is_built_from_small_calls_then_reviewed_and_fixed():
    from app.pipeline import steps

    ctx, doc, cfg = _story_ctx(), {"genre": "funny", "kind": "story", "image_ids": ["a"]}, _cfg()
    review = P('{"verdict":"weak","fixes":[{"part":2,"problem":"flat","instruction":"add action"},'
               '{"part":2,"problem":"dup","instruction":"x"},{"part":9,"problem":"bad","instruction":"x"},'
               '{"scene":4,"problem":"repeats","instruction":"vary"}]}')
    out = asyncio.run(steps.critique(ctx, doc, review, cfg))
    assert [f["part"] for f in out["fixes"]] == [2, 4]  # deduped, invalid scene dropped, old key accepted
    assert review.calls[0][1] == []  # the review sends text only, never images
    ctx["critique"] = out

    fix = P("The cat ran to the big red kite. " * 10)
    r1 = asyncio.run(steps._revise(0)(ctx, doc, fix, cfg))
    assert r1["part"] == 2 and len(fix.calls) == 1 and fix.calls[0][1] == []
    assert "SCENE 2 TO REWRITE" in fix.calls[0][0] and "CEFR" in fix.calls[0][0]
    ctx["revise_1"] = r1
    idle = P()
    assert asyncio.run(steps._revise(2)(ctx, doc, idle, cfg)) == {"skipped": True} and idle.calls == []  # no call
    assert steps.segments(ctx, doc)[1].startswith("The cat ran")
    assert steps.story_text(ctx, doc).count("\n\n") == 5

    ctx2 = {**ctx, "critique": {"fixes": [{"part": 3, "problem": "p", "instruction": "i"}]}}
    assert asyncio.run(steps._revise(0)(ctx2, doc, P("Too short."), cfg)) == {"skipped": True}  # bad rewrite ignored


def test_hard_to_read_scenes_are_always_sent_for_a_simplifying_rewrite():
    from app.pipeline import steps

    hard = ("Notwithstanding the extraordinary circumstances surrounding the mysterious disappearance, the "
            "investigator methodically examined everything, contemplating considerable possibilities. ") * 3
    ctx = _story_ctx()
    ctx["part_5"] = {"text": hard}
    doc = {"genre": "funny", "kind": "story", "image_ids": ["a"]}
    out = asyncio.run(steps.critique(ctx, doc, P('{"verdict":"great","fixes":[]}'), _cfg()))
    assert [f["part"] for f in out["fixes"]] == [5] and "very short sentences" in out["fixes"][0]["instruction"]
    assert steps.reading_difficulty(EASY)[0] < steps.MAX_AVG_SENTENCE < steps.reading_difficulty(hard)[0]


def test_poem_is_written_stanza_by_stanza_and_stanzas_are_checked():
    from app.pipeline import steps

    doc = {"genre": "funny", "kind": "poem", "image_ids": ["a"]}
    ctx = {"outline": {"title": "T", "beats": ["a", "b", "c", "d"]}, "vision_1": {"objects": ["bench"]}}
    stanza = "The cat sat on the mat,\nHer hat was big and flat,\nShe saw a bird so gray,\nIt flew off far away."
    prov = P("Stanza 1\n" + stanza)
    s1 = asyncio.run(steps._part(0)(ctx, doc, prov, _cfg()))
    assert s1["text"] == stanza and "exactly 4" in prov.calls[0][0] and "AABB" in prov.calls[0][0]
    assert prov.calls[0][1] == []  # text only
    with pytest.raises(ProviderError):  # a one-line "stanza" is retried
        asyncio.run(steps._part(1)({**ctx, "part_1": s1}, doc, P("Just one line."), _cfg()))
    ctx.update({f"part_{i}": {"text": stanza} for i in range(1, 5)})
    assert steps.story_text(ctx, doc).count("\n\n") == 3  # four stanzas
    # poem review asks about rhyme, and a good rewrite must still be 3-6 lines
    review = P('{"verdict":"ok","fixes":[{"part":3,"problem":"no rhyme","instruction":"rhyme lines 3 and 4"}]}')
    ctx["critique"] = asyncio.run(steps.critique(ctx, doc, review, _cfg()))
    assert "AABB rhyme" in review.calls[0][0] and ctx["critique"]["fixes"][0]["part"] == 3
    fixed = asyncio.run(steps._revise(0)(ctx, doc, P(stanza.replace("gray", "day")), _cfg()))
    assert fixed["part"] == 3 and "day" in fixed["text"]
    assert asyncio.run(steps._revise(0)(ctx, doc, P("one line only"), _cfg())) == {"skipped": True}


def test_comic_panels_carry_a_caption_and_speech_bubbles_over_your_photos():
    from app.pipeline import steps

    doc = {"genre": "funny", "kind": "comic", "image_ids": ["p1", "p2", "p3", "p4", "p5"]}
    plan = {"title": "T", "hero": "Ben", "beats": [f"beat {i}" for i in range(6)],
            "panels": [{"source_image": 5}, {"source_image": 2}, {"source_image": "x"}, {}, {"source_image": 99}, {"source_image": 1}]}
    ctx = {"outline": plan, **{f"vision_{i}": {"objects": ["bench"]} for i in range(1, 6)}}
    reply = ('{"caption": "Ben saw a big bench.", "speech": [{"who": "Ben", "text": "Wow, a bench!"}, '
             '{"who": "Bench", "text": ""}, {"who": "Pip", "text": "Hi!"}, {"who": "X", "text": "third"}]}')
    prov = P(reply)
    p1 = asyncio.run(steps._part(0)(ctx, doc, prov, _cfg()))
    assert p1["caption"] == "Ben saw a big bench." and [s["who"] for s in p1["speech"]] == ["Ben", "Pip"]  # max 2, no empty
    assert "panel 1 of 6" in prov.calls[0][0] and prov.calls[0][1] == []
    with pytest.raises(ProviderError):  # a blank panel is retried
        asyncio.run(steps._part(1)({**ctx, "part_1": p1}, doc, P('{"caption": "", "speech": []}'), _cfg()))
    ctx.update({f"part_{i}": p1 for i in range(1, 7)})
    panels = asyncio.run(steps.illustrate(ctx, doc, None, _cfg()))
    # source_image 5 -> p5, 2 -> p2, junk -> falls back by panel position, 99 -> clamped to the last photo
    assert [p["image_id"] for p in panels] == ["p5", "p2", "p3", "p4", "p5", "p1"]
    assert panels[0]["speech"][0]["text"] == "Wow, a bench!"
    result = asyncio.run(steps.finalize({**ctx, "illustrate": panels}, doc, None, _cfg()))
    assert result["kind"] == "comic" and len(result["panels"]) == 6 and result["scenes"] == [] and result["text"]


def test_beats_map_to_parts_even_if_the_model_returns_the_wrong_count():
    from app.pipeline.steps import beat_for

    for n in (3, 6, 9):
        beats = [f"b{i}" for i in range(n)]
        picked = [beat_for(beats, i, 6) for i in range(6)]
        assert all(picked) and picked[0].startswith("b0") and picked[-1].split()[-1] == f"b{n - 1}"


def test_reading_level_rules_are_in_every_writing_prompt():
    from app.pipeline import prompts

    plan = {"title": "T", "hero": "Ben", "voice": "warm"}
    ph = [{"objects": ["bench"]}]
    texts = [prompts.outline("story", "funny", ph, 3, 6), prompts.outline("poem", "funny", ph, 3, 4),
             prompts.outline("comic", "funny", ph, 3, 6), prompts.scene("horror", plan, ph, 0, 6, "b", "n", ""),
             prompts.panel("funny", plan, ph, 0, 6, "b", []), prompts.revise("story", "suspense", plan, "", "x", "", 1, {})]
    assert all("CEFR level A2" in t and "short sentences" in t for t in texts)
    assert "CEFR level A2" in prompts.stanza("funny", plan, ph, 0, 4, "i", "n", "") and "children" in prompts.critique("story", "funny", plan, ["a"])
    assert "exactly 4 panels" not in prompts.outline("comic", "funny", ph, 3, 6) and "exactly 6" in prompts.outline("comic", "funny", ph, 3, 6)


# ---------------------------------------------------------------- providers, models, uploads
def test_each_task_has_its_own_model():
    from app.providers.base import ProviderConfig

    ai = ProviderConfig(kind="aistudio")
    assert ai.model("vision") == ai.model("outline")  # the fast model reads photos and plans
    assert ai.model("story") != ai.model("outline")  # the big model writes and edits
    byok = ProviderConfig(kind="aistudio", models={"story": "gemma-x"})
    assert byok.model("story") == "gemma-x" and byok.model("outline") == "gemma-4-26b-a4b-it"
    assert ProviderConfig(kind="lmstudio").model("story") == ""  # auto-detect


def test_images_are_compressed_in_three_sizes():
    import io

    from PIL import Image

    from app.routes.images import _normalize

    buf = io.BytesIO()
    Image.new("RGB", (3000, 2000), (10, 120, 40)).save(buf, "PNG")
    full, llm, thumb = _normalize(buf.getvalue())
    imgs = [Image.open(io.BytesIO(b)) for b in (full, llm, thumb)]
    assert [max(i.size) for i in imgs] == [1024, 384, 240] and len(thumb) < len(llm) < len(full)
    assert all(abs(i.size[0] / i.size[1] - 1.5) < 0.02 for i in imgs)  # resized, never cropped


def test_photo_count_limits_and_kind_validation():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.pipeline.steps import scene_count

    c = TestClient(app)  # no lifespan: these requests are rejected before touching the database
    one = ("files", ("a.jpg", b"x", "image/jpeg"))
    r = c.post("/api/sessions", files=[one] * 4)
    assert r.status_code == 400 and "between 5 and 10" in r.json()["detail"]
    assert c.post("/api/sessions", files=[one] * 11).status_code == 400
    h = {"X-Provider": "lmstudio"}
    r = c.post("/api/stories", json={"image_ids": list("abcd"), "genre": "funny"}, headers=h)
    assert r.status_code == 400 and "5 to 10" in r.json()["detail"]
    r = c.post("/api/stories", json={"image_ids": list("abcde"), "genre": "funny", "kind": "novel"}, headers=h)
    assert r.status_code == 400 and "Kind must be" in r.json()["detail"]
    assert [scene_count(n) for n in (5, 6, 7, 8, 9, 10)] == [3, 3, 4, 4, 5, 5]


def test_aistudio_disables_thinking_and_grows_budget_on_max_tokens():
    import httpx

    from app.providers import aistudio
    from app.providers.aistudio import AIStudio

    sent, replies = [], []

    class FakeHttp:
        async def post(self, url, json=None, headers=None):
            sent.append(json["generationConfig"])
            return replies.pop(0)

    def reply(status, body):
        return httpx.Response(status, json=body, request=httpx.Request("POST", "http://x"))

    empty = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "thinking...", "thought": True}]}}]}
    ok = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "OK"}]}}]}
    rejected = {"error": {"message": "Thinking config is not supported for this model"}}

    async def scenario():
        aistudio.http = lambda: FakeHttp()
        p = AIStudio("k")
        replies[:] = [reply(200, empty), reply(200, ok)]
        with pytest.raises(ProviderError) as e:
            await p.generate("hi", [], "m", 0, 1, 100)
        assert "MAX_TOKENS" in e.value.message and e.value.retryable
        assert await p.generate("hi", [], "m", 0, 1, 100) == "OK"
        assert sent[0]["thinkingConfig"] == {"thinkingLevel": "minimal"}
        assert sent[1]["maxOutputTokens"] > sent[0]["maxOutputTokens"]  # retry got a bigger budget

        sent.clear()
        q = AIStudio("k")
        replies[:] = [reply(400, rejected), reply(200, ok)]
        assert await q.generate("hi", [], "m", 0, 1, 100) == "OK"  # falls back to no thinkingConfig
        assert "thinkingConfig" in sent[0] and "thinkingConfig" not in sent[1]

    asyncio.run(scenario())


def test_progress_labels_are_playful_and_match_the_step_counts():
    from app.pipeline.estimate import REVISIONS
    from app.pipeline.steps import step_defs

    for kind in ("story", "poem", "comic"):
        labels = dict(step_defs(5, kind))
        assert not any("weak spot" in v.lower() or "fixing" in v.lower() for v in labels.values())
        polish = [labels[f"revise_{k + 1}"] for k in range(REVISIONS[kind])]
        assert len(set(polish)) == len(polish)  # each polish step has its own message
    assert "✨" in dict(step_defs(5, "story"))["revise_1"] and "if needed" in dict(step_defs(5, "story"))["revise_1"]


def test_only_ai_studio_and_lm_studio_are_offered():
    from app.providers import KINDS, get_cfg

    assert KINDS == ("aistudio", "lmstudio")
    assert get_cfg("openrouter", "", "", "", "").kind == "aistudio"  # unknown providers fall back to AI Studio


def test_photos_are_looked_at_in_parallel_and_other_steps_in_order():
    from app.pipeline.estimate import VISION_PARALLEL

    live, peak, order = [0], [0], []

    def build(name):
        async def f(ctx, doc, provider, cfg):
            live[0] += 1
            peak[0] = max(peak[0], live[0])
            await asyncio.sleep(0.05)
            live[0] -= 1
            order.append(name)
            return {"title": "t"} if name == "finalize" else {"text": name}

        return f

    async def save(_):
        pass

    doc = {"_id": "s", "genre": "funny", "kind": "story", "status": "pending", "steps": new_steps(6, "story")}
    funcs = {s["name"]: build(s["name"]) for s in doc["steps"]}
    t0 = time.monotonic()
    asyncio.run(execute(doc, None, None, funcs, save))
    assert doc["status"] == "done" and peak[0] == VISION_PARALLEL  # 4 photos at once, never more
    assert order.index("outline") > max(order.index(f"vision_{i}") for i in range(1, 7))  # plan waits for all photos
    assert order[order.index("outline"):][:3] == ["outline", "part_1", "part_2"]  # writing stays in order


def test_progress_shows_finished_parts_until_the_tale_is_done():
    from app.pipeline.runner import public

    doc = {"_id": "s", "genre": "funny", "kind": "story", "status": "running", "steps": new_steps(5, "story")}
    steps = {s["name"]: s for s in doc["steps"]}
    assert public(doc)["preview"] is None  # nothing written yet
    steps["outline"].update(status="done", output={"title": "Gus and the Big Bench", "beats": ["a"]})
    steps["part_1"].update(status="done", output={"text": "Gus had a plan."})
    steps["part_2"].update(status="running")
    snap = public(doc)["preview"]
    assert snap == {"title": "Gus and the Big Bench", "parts": [{"text": "Gus had a plan."}]}
    doc["status"] = "done"
    assert public(doc)["preview"] is None  # the finished result replaces the preview


def test_successful_calls_go_back_to_back():
    from app.pipeline.throttle import ThrottledProvider

    class Inner:
        async def generate(self, *a, **k):
            return "ok"

    async def scenario():
        async def emit(d):
            pass

        doc = {"llm": {"calls": 0, "waiting_until": None}}
        tp = ThrottledProvider(Inner(), 0, doc, emit)
        t0 = time.monotonic()
        for _ in range(5):
            await tp.generate("x")
        assert time.monotonic() - t0 < 0.2 and doc["llm"]["calls"] == 5

    asyncio.run(scenario())
