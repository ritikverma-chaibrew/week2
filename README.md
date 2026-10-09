# Touch Grass Tales 🌳

Go outside, photograph 5 to 10 random things, and Gemma AI turns them into a children's **story**, a rhyming **poem** or a **comic strip** (funny, spooky or mystery), illustrated with your own photos. Everything is written in simple words: short sentences, no idioms, about CEFR A2, so young readers and beginner English learners can follow it.

## Using the site
1. **Connect the AI once.** Paste a free [Google AI Studio](https://aistudio.google.com/api-keys) key, or run Gemma locally with [LM Studio](https://lmstudio.ai). `/setup.html` walks through both.
2. **Go for a walk.** The Create page gives you a random photo mission (optional).
3. **Add 5 to 10 photos.**
4. **Pick a mood** (Funny, Spooky, Mystery) **and a format** (Story, Poem, Comic).
5. **Press Make.** Progress and time left stream live, a **photo check** panel shows each photo being checked and the items found in it, and a **sneak peek** shows each scene, verse or panel as soon as it is written. A tale takes about 2 to 4 minutes on AI Studio. Read it as a book or as slides, then try another mood or format with the same photos.
6. **Publish (optional).** **Publish my tale** saves the tale, with ~480px copies of its photos, to the browser's **local storage** (`tg.published.v1`). It then shows under **Your published tales** in the gallery, on that device and browser only. Nothing is uploaded, so other visitors can't see it, and clearing browser data deletes it. Tales can be removed from the gallery.

No key yet? `/demo.html` replays a pre-made walk with no setup, and `/gallery.html` has three sample tales.

## Pages
Header: **Make a tale · How it works · Gallery · Setup**.

| Page | What it is for |
| --- | --- |
| `/` | What the site does, an example, how it works, FAQ |
| `/create.html` | The 5 numbered steps above. The Make button lists what is still missing (key, photos) |
| `/setup.html` | Choose AI Studio or LM Studio, connect and test, troubleshooting |
| `/demo.html` | A sped-up canned run, no key needed (linked from the home page only, not the header or footer) |
| `/gallery.html` | Your published tales (from local storage), then sample tales |

## Project structure
```
week2/
├── app/                    # the FastAPI application (run as app.main:app)
│   ├── main.py             # app setup, /api/health, serves static/
│   ├── config.py           # settings from .env
│   ├── db.py               # MongoDB collections and indexes
│   ├── bus.py              # live progress fan-out to SSE streams
│   ├── errors.py           # ProviderError: failures safe to show in the UI
│   ├── providers/          # Google AI Studio and LM Studio clients, per-task model defaults
│   ├── pipeline/           # the writing steps, prompts, throttling and time estimates
│   ├── routes/             # /api/sessions + /api/images (photos), /api/stories, /api/provider, /api/gallery
│   └── static/             # the website: HTML pages, css/, js/
├── tests/test_core.py
├── requirements.txt
└── .env.example
```

## Run
```bash
pip install -r requirements.txt
cp .env.example .env        # MONGODB_URI defaults to mongodb://localhost:27017
uvicorn app.main:app --reload
```
Open http://localhost:8000. For MongoDB Atlas, set `MONGODB_URI=mongodb+srv://...` in `.env`.

## Deploy on Render
`render.yaml` describes the web service. If you created the service by hand in the dashboard, set these in **Settings**:

| Setting | Value |
| --- | --- |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/health` |
| Environment | `MONGODB_URI` = your MongoDB Atlas string (Render has no local MongoDB) |

The `--host 0.0.0.0 --port $PORT` part is required: without it uvicorn listens on `127.0.0.1:8000` and the deploy fails with *"Port scan timeout reached, no open ports detected on 0.0.0.0"*. In Atlas, allow connections from Render (Network Access → `0.0.0.0/0`, or Render's outbound IPs). `/api/health` reports `"db": true` once the database is reachable.

| `.env` setting | Default | What it does |
| --- | --- | --- |
| `MONGODB_URI` | `mongodb://localhost:27017` | Database connection |
| `MONGODB_DB` | `touchgrass` | Database name |
| `MIN_IMAGES` / `MAX_IMAGES` | `5` / `10` | Photos allowed per tale |
| `LLM_CALL_GAP_SECONDS` | `0` | Pause between successful AI calls on Google AI Studio (0 = back-to-back) |
| `LLM_RETRY_SECONDS` | `30` | After a failed AI Studio call, wait attempt × this: 30 s, 60 s, 90 s (LM Studio: 5 s base) |

## How it works
- **Stack:** FastAPI + uvicorn + MongoDB (motor). The frontend is plain HTML/CSS/JS in `app/static/`, served by FastAPI, so there is one thing to deploy.
- **AI providers:** only two, **Google AI Studio** (your own key) and **LM Studio** (local). Any other `X-Provider` value falls back to AI Studio.
- **Models:** Gemma 4, a different one per task: 26B-A4B for reading each photo and planning; 31B for writing and proofreading. Under **Advanced settings** each task has a select box that offers only recommended models: on AI Studio the two Gemma 4 models (the recommended one preselected), on LM Studio only the Gemma models loaded in the app (or Auto: the first Gemma loaded).
- **Small calls, never one long reply.** One small photo (384px) per call; a plot call; then a story is six ~170-word scenes, a poem is four 4-line stanzas, a comic is six panels (caption + speech bubbles); then an editor call reviews the whole piece and up to 3 weak parts are rewritten. A readability check always rewrites scenes that are too hard.
- **Pipeline:** `vision_1…n → outline → part_1…n → critique → revise_1…k → illustrate → finalize` (comics skip the review). One LLM call at a time per tale, in order (`VISION_PARALLEL = 1` in `app/pipeline/estimate.py`; raise it to look at several photos at once). Each step is saved in MongoDB and progress streams over SSE, including what was found in each photo and the parts written so far (`preview` in the story state). Transient errors (429, 5xx, timeouts, bad JSON) retry up to 3 times. If a step still fails, the UI shows why and **Retry** resumes from that step without redoing earlier ones.
- **Pacing:** successful calls go back-to-back. Google AI Studio doesn't say how long to wait after a rate limit, so after a failed call the app waits attempt × 30 s (30 s, 60 s, 90 s); once a call succeeds, the next one goes straight away again. There is no server-wide lock: each tale only paces itself, so several people can make tales at the same time. Pauses are never mentioned in the UI; the old slider, estimate text and "pausing…" message are kept but commented out in `js/settings.js`, `js/app.js`, `js/progress.js` and `js/api.js`.
- **AI-call counts are not shown in the UI.** The server still tracks them (`llm.calls` in the story state) and the browser still counts them per key; the display code is kept but commented out in `js/progress.js`, `js/settings.js`, `js/app.js`, `create.html` and `setup.html`.

## Privacy
- The Google AI Studio key is kept in browser local storage for **5 hours**, then deleted automatically (or right away with **Forget**). It is sent per request in a header; the server never stores or logs it.
- Uploaded photos are re-encoded (EXIF stripped) and auto-deleted after 24 hours. Tales on the server are private and deleted after 7 days.
- Publishing never writes to the database: published tales live only in the browser's local storage.

## Tests
```bash
python -m pytest
```
