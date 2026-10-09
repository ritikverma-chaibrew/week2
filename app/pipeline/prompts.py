GENRES = {
    "funny": "a funny, silly children's picture-book piece with playful surprises, gentle jokes and a happy ending",
    "horror": "a spooky bedtime piece for children: strange shadows and mysterious sounds that turn out to be kind and safe in the end (nothing violent, nothing truly scary)",
    "suspense": "an exciting mystery piece for children: a puzzle to solve, clues to follow and a surprise ending that makes everyone happy",
}
NAMES = {"story": "short story", "poem": "rhyming poem", "comic": "comic strip"}

# Every writing and editing prompt carries this, so everything stays easy to read.
READING_LEVEL = (
    "Write like a children's picture book for young readers and for people who are just learning English "
    "(about CEFR level A2). Use short sentences (most under 12 words) and everyday words that a child already knows. "
    "One idea per sentence. No idioms, slang, long difficult words or complicated grammar. If a special word is "
    "needed, make its meaning clear from the sentence. Use the simple past tense, simple names, and a warm, friendly "
    "voice. A little repetition and rhythm is good. Keep it gentle and kind."
)
POEM_STYLE = (
    "Children's poem rules (about CEFR level A2): each stanza has exactly 4 short lines of 5 to 8 simple words; "
    "rhyme AABB (line 1 rhymes with line 2, line 3 rhymes with line 4); a bouncy rhythm that is fun to read aloud; "
    "everyday words a child knows; no idioms, slang or hard words; gentle and kind."
)

VISION_ONE = (
    "Look at this photo someone took while walking outside. "
    "Reply with ONLY a JSON object, no markdown: "
    '{"objects": [up to 6 short concrete nouns clearly visible], '
    '"setting": "where this is, 5 words max", "mood": "one word"}'
)


def _objects(photos: list[dict], limit: int = 24) -> str:
    """Distinct photo objects, capped so a 10-photo prompt stays small."""
    seen: list[str] = []
    for p in photos:
        for o in p.get("objects", []):
            if o not in seen:
                seen.append(o)
    return ", ".join(seen[:limit])


def _photo_lines(photos: list[dict]) -> str:
    return "\n".join(
        f"Photo {i + 1}: objects={', '.join(p.get('objects', []))}; setting={p.get('setting', '')}; mood={p.get('mood', '')}"
        for i, p in enumerate(photos)
    )


def _scenes_json(n: int) -> str:
    return (
        f'"scenes": [{n} key moments to illustrate with the photos, spread from the start to the end, using a different '
        'photo for each, each {"caption": "max 6 simple words", "source_image": <number of the photo that best matches>}]}'
    )


def outline(kind: str, genre: str, photos: list[dict], n_scenes: int, n_parts: int) -> str:
    head = f"{_photo_lines(photos)}\n\n{READING_LEVEL}\nReply with ONLY a JSON object, no markdown: "
    if kind == "poem":
        return (
            f"Plan {GENRES[genre]}, as a rhyming poem. Use the real objects seen in these photos.\n" + head
            + '{"title": "a short, simple title of at most 6 words", "theme": "what the poem is about, in simple words", '
            '"rhyme": "AABB", "refrain": "an optional short line that can come back", '
            f'"beats": [exactly {n_parts} one-sentence ideas, one per stanza, in a clear order from beginning to a happy '
            'end, each using at least one photo object], ' + _scenes_json(n_scenes)
        )
    if kind == "comic":
        return (
            f"Plan {GENRES[genre]}, as a {n_parts}-panel comic strip. Use the real objects seen in these photos.\n" + head
            + '{"title": "a short, simple title of at most 6 words", "hero": "main character: an easy name and one trait", '
            '"setting": "where and when it happens", '
            f'"beats": [exactly {n_parts} one-sentence descriptions of what happens in each panel, with a clear '
            'beginning, middle and happy end, each using a photo object], '
            f'"panels": [exactly {n_parts} items, one per beat, each {{"source_image": <number of the photo that best '
            "shows that panel; use as many different photos as you can>}]}"
        )
    return (
        f"Plan {GENRES[genre]}, as a short story. Use the real objects seen in these photos as important parts of the "
        "story.\n" + head
        + '{"title": "a short, simple title of at most 6 words", '
        '"hero": "main character: an easy name, one trait and what they want", '
        '"setting": "where and when it happens", "conflict": "the central problem, kept simple", '
        '"voice": "a warm storybook narrator, third person, simple past tense", '
        '"twist": "a gentle surprise near the end", '
        f'"beats": [exactly {n_parts} one-sentence plot beats in simple words, one per scene, forming a clear beginning, '
        'middle and end, each using at least one photo object], ' + _scenes_json(n_scenes)
    )


def scene(genre: str, plan: dict, photos: list[dict], idx: int, total: int, beat: str, next_beat: str, previous: str) -> str:
    """One short story scene (~170 words). Small replies stay focused and keep the model on a tight leash."""
    objs = _objects(photos)
    if idx == 0:
        role = "Open with an interesting hook that drops us into the action and introduces the hero."
    elif idx == total - 1:
        role = "Deliver the happy climax, reveal the twist and end on a warm, memorable final sentence."
    else:
        role = "Move the story forward with a clear change or small problem; do not wrap anything up yet."
    before = f"\nThe story so far (continue seamlessly, never repeat it):\n{previous}\n" if previous else ""
    after = f"\nThe next scene will cover (do not write it, just lead into it): {next_beat}\n" if next_beat else ""
    return (
        f"You are writing scene {idx + 1} of {total} of one short story: {GENRES[genre]}.\n"
        f"Title: {plan.get('title', '')}. Hero: {plan.get('hero', '')}. Setting: {plan.get('setting', '')}. "
        f"Central problem: {plan.get('conflict', '')}. Narration: {plan.get('voice', '')}. "
        f"Gentle twist (only reveal it in the final scene): {plan.get('twist', '')}.\n"
        f"THIS scene: {beat}\n{before}{after}"
        f"Real objects from the photos you can use: {objs}.\n"
        f"{role}\n{READING_LEVEL}\n"
        "Requirements: 140 to 200 words, 1 to 3 short paragraphs, clear pictures in the reader's mind, a little "
        "simple dialogue, the same voice and names as before. Show, don't summarize. Output ONLY this scene's prose: "
        "no heading, no scene number, no markdown, no commentary."
    )


def stanza(genre: str, plan: dict, photos: list[dict], idx: int, total: int, idea: str, next_idea: str, previous: str) -> str:
    """One 4-line stanza."""
    if idx == 0:
        role = "Start the poem with a catchy, cheerful opening."
    elif idx == total - 1:
        role = "Finish the poem with a warm, happy ending that feels complete."
    else:
        role = "Move the poem forward; do not finish it yet."
    before = f"\nThe poem so far (continue it, never repeat it):\n{previous}\n" if previous else ""
    after = f"\nThe next stanza will be about (do not write it): {next_idea}\n" if next_idea else ""
    return (
        f"You are writing stanza {idx + 1} of {total} of one {NAMES['poem']}: {GENRES[genre]}.\n"
        f"Title: {plan.get('title', '')}. Theme: {plan.get('theme', '')}. Optional refrain: {plan.get('refrain', '')}.\n"
        f"THIS stanza is about: {idea}\n{before}{after}"
        f"Real objects from the photos you can use: {_objects(photos)}.\n"
        f"{role}\n{POEM_STYLE}\n"
        "Output ONLY the 4 lines of this stanza, one line per row: no title, no stanza number, no markdown, no commentary."
    )


def panel(genre: str, plan: dict, photos: list[dict], idx: int, total: int, beat: str, previous: list[str]) -> str:
    """The words for one comic panel: a narration box and up to two speech bubbles."""
    before = ("Captions of the earlier panels (keep the story flowing): " + " | ".join(previous) + "\n") if previous else ""
    ending = " This is the last panel: end with a happy, funny or warm line." if idx == total - 1 else ""
    return (
        f"You are writing the words for panel {idx + 1} of {total} of a children's comic strip: {GENRES[genre]}.\n"
        f"Title: {plan.get('title', '')}. Hero: {plan.get('hero', '')}. Setting: {plan.get('setting', '')}.\n"
        f"THIS panel shows: {beat}\n{before}"
        f"Real objects from the photos you can use: {_objects(photos)}.\n{READING_LEVEL}\n"
        "Reply with ONLY a JSON object, no markdown: "
        '{"caption": "narration box, at most 12 simple words, or an empty string", '
        '"speech": [0 to 2 speech bubbles, each {"who": "speaker name", "text": "at most 8 simple words"}]}\n'
        f"Use at least a caption or one speech bubble. Speakers can be the hero, other simple names, or a talking "
        f"object.{ending}"
    )


def critique(kind: str, genre: str, plan: dict, parts: list[str]) -> str:
    word = "stanza" if kind == "poem" else "scene"
    body = "\n\n".join(f"[{word.title()} {i + 1}]\n{t}" for i, t in enumerate(parts))
    if kind == "poem":
        judge = (
            "Judge it: does every stanza have 4 short lines with AABB rhyme, is the rhythm bouncy, do the stanzas "
            "flow in a clear order, are the words simple enough for young children and beginner English learners "
            "(no hard words or idioms), and does it end warmly?"
        )
    else:
        judge = (
            "Judge it: continuity (names, places, facts, tense), repetition, pacing, clear and lively pictures, "
            "whether the twist lands and the ending is satisfying. ALSO check the language: it must be easy for young "
            "children and beginner English learners (short sentences, everyday words, no idioms or slang). Flag any "
            "scene with hard words or long, complicated sentences."
        )
    return (
        f"You are a sharp editor of children's books reviewing a {NAMES[kind]} titled \"{plan.get('title', '')}\", "
        f"written in {len(parts)} {word}s. {judge}\n"
        "Reply with ONLY a JSON object, no markdown: "
        '{"verdict": "great" | "ok" | "weak", "fixes": [up to 3 of the most important problems, worst first, each '
        f'{{"part": <{word} number>, "problem": "what is wrong", "instruction": "how to rewrite that {word}"}}]}}\n'
        'If it is already strong and easy to read, use verdict "great" and an empty fixes list. Only list real '
        f"problems, at most one fix per {word}.\n\n" + body
    )


def revise(kind: str, genre: str, plan: dict, before: str, text: str, after: str, number: int, fix: dict) -> str:
    word = "stanza" if kind == "poem" else "scene"
    rules = POEM_STYLE if kind == "poem" else READING_LEVEL
    length = "exactly 4 lines" if kind == "poem" else "about 140 to 220 words"
    return (
        f"You are editing one {word} of a children's {genre} {NAMES[kind]} titled \"{plan.get('title', '')}\".\n"
        f"{word.title()} before it:\n{before or '(none, this is the opening)'}\n\n"
        f"{word.upper()} {number} TO REWRITE:\n{text}\n\n"
        f"{word.title()} after it:\n{after or '(none, this is the ending)'}\n\n"
        f"Problem: {fix.get('problem', '')}\nInstruction: {fix.get('instruction', '')}\n"
        f"{rules}\n"
        f"Rewrite ONLY this {word} to fix the problem. Keep the same events, names and facts, keep it consistent with "
        f"the parts around it, and keep the length {length}. "
        f"Output ONLY the rewritten {word}: no heading, no notes, no markdown."
    )
