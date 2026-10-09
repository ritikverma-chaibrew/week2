# Touch Grass Tales 🌱

Go outside, photograph 5 to 10 random things, and Gemma turns them into a children's story, a rhyming poem or a comic strip (funny, spooky or mystery), illustrated with your own photos. Everything is written in simple words: short sentences, no idioms, about CEFR A2, so young readers and beginner English learners can follow it.

## Using the site
1. **Connect the AI once.** Paste a free [Google AI Studio](https://aistudio.google.com/apikey) key, or run Gemma locally with [LM Studio](https://lmstudio.ai). `/setup.html` walks through both.
2. **Go for a walk.** The Create page gives you a random photo mission (optional).
3. **Add 5 to 10 photos.**
4. **Pick a mood** (Funny, Spooky, Mystery) **and a format** (Story, Poem, Comic).
5. **Press Make.** Progress and time left stream live. The tale takes about 6 to 10 minutes on AI Studio. Read it as a book or as slides, then try another mood or format with the same photos.
6. **Publish (optional).** **Publish my tale** saves the tale, with ~480px copies of its photos, to the browser's **local storage** (`tg.published.v1`). It then shows under **Your published tales** in the gallery, on that device and browser only. Nothing is uploaded, so other visitors can't see it, and clearing browser data deletes it. Tales can be removed from the gallery.

No key yet? `/demo.html` replays a pre-made walk with no setup, and `/gallery.html` has three sample tales.

## Pages
| Page | What it is for |
| --- | --- |
| `/` | What the site does, an example, how it works, FAQ |
| `/create.html` | The 5 numbered steps above. The Make button lists what is still missing (key, photos) |
| `/setup.html` | Choose AI Studio or LM Studio, connect and test, troubleshooting |
| `/demo.html` | A sped-up canned run, no key needed |
| `/gallery.html` | Your published tales (from local storage), then server-shared tales or 3 samples |

## Stack
- **Backend:** FastAPI + uvicorn + MongoDB (motor). **Frontend:** plain HTML/CSS/JS in `backend/static/`, served by FastAPI, so there is a single repo to deploy.
- **AI providers:** only two, **Google AI Studio** (your own key) and **LM Studio** (local). Any other `X-Provider` value falls back to AI Studio.
- **Models:** Gemma 4, a different one per task: 26B-A4B for reading each photo and planning (JSON); 31B for writing and proofreading. On LM Studio you pick the models (or it uses the first Gemma loaded). Per-task models and the pause between calls are under **Advanced settings**.
- **How it is written:** many small calls, never one long reply. One small photo (384px) per call; a plot call; then a story is six ~170-word scenes, a poem is four 4-line stanzas, a comic is six panels (caption + speech bubbles); then an editor call reviews the whole piece and up to 3 weak parts are rewritten. A readability check always rewrites scenes that are too hard. On AI Studio calls start at least 30 s apart (slider; `LLM_CALL_GAP_SECONDS`) and a failed call retries after 1x, 2x, 3x that pause.
- **AI-call counts are not shown in the UI.** The server still tracks them (`llm.calls` in the story state) and the browser still counts them per key; the display code is kept but commented out in `js/progress.js`, `js/settings.js`, `js/app.js`, `create.html` and `setup.html`.

## Run
```bash
pip install -r requirements.txt
cp .env.example .env        # MONGODB_URI defaults to mongodb://localhost:27017
uvicorn backend.main:app --reload
```
Open http://localhost:8000. For MongoDB Atlas, set `MONGODB_URI=mongodb+srv://...` in `.env`.

## Pipeline
`prepare → vision → outline → story → art_plan → art_svg → finalize`. Each step is saved in MongoDB. Transient errors (429, 5xx, timeouts, bad JSON) retry up to 3 times with backoff. If a step still fails, the UI shows the reason and **Retry** resumes from that step without redoing earlier ones. Progress streams over SSE.

## Privacy
The Google AI Studio key is kept in browser localStorage for **5 hours**, then deleted automatically (or right away with **Forget**). It is sent per request in a header; the server never stores or logs it. Uploaded photos are re-encoded (EXIF stripped) and auto-deleted after 24 hours. Tales are private on the server and deleted after 7 days. Publishing never writes to the database: published tales live only in the browser's local storage.

## Tests
`python -m pytest`
