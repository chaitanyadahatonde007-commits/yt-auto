from __future__ import annotations

import hashlib
import re
from typing import Any

from app.services.llm import generate_script_llm

WORDS_PER_MINUTE = 148

STYLES = {
    "explainer": "Clear documentary explainer. Teach one idea so a smart teenager gets it.",
    "listicle": "Numbered revelations. Each point earns the next.",
    "story": "Narrative tension. A person, a problem, a turn, a meaning.",
    "documentary": "Slow-burn investigation. Context, then consequence.",
    "motivation": "Direct address. Challenge, reframe, one action.",
    "news": "Tight briefing. What happened, why it matters, what to watch.",
}

MOODS = ("ember", "navy", "teal", "violet", "amber", "steel", "forest", "magenta")


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text or ""))


def estimate_seconds(text: str) -> float:
    return max(1.6, word_count(text) / WORDS_PER_MINUTE * 60.0)


def _hash_pick(seed: str, options: list[str]) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return options[int(digest[:8], 16) % len(options)]


def _title_case_topic(topic: str) -> str:
    small = {"a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "vs", "vs."}
    words = re.split(r"\s+", topic.strip())
    out = []
    for i, w in enumerate(words):
        low = w.lower()
        if i > 0 and i < len(words) - 1 and low in small:
            out.append(low)
        else:
            out.append(w[:1].upper() + w[1:] if w else w)
    return " ".join(out)


def _slug_words(topic: str, n: int = 3) -> str:
    words = [w for w in re.findall(r"[A-Za-z0-9']+", topic) if len(w) > 2]
    if not words:
        return topic.upper()[:18]
    return " ".join(words[:n]).upper()


def _on_screen(text: str, fallback: str) -> str:
    words = re.findall(r"[A-Za-z0-9']+", text)
    if not words:
        return fallback.upper()
    if len(words) <= 5:
        return " ".join(words).upper()
    start = 0
    while start < len(words) - 2 and words[start].lower() in STOP:
        start += 1
    phrase = words[start : start + 4]
    return " ".join(phrase).upper()


STOP = {
    "this", "that", "with", "from", "have", "what", "when", "where", "which",
    "your", "about", "into", "just", "like", "they", "them", "then", "than",
    "will", "would", "could", "should", "there", "their", "been", "being",
    "because", "while", "after", "before", "over", "under", "most", "more",
    "some", "every", "those", "these", "here", "make", "made", "does",
}


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _pack_scenes(sentences: list[str], kind: str = "narration") -> list[dict[str, Any]]:
    scenes: list[dict[str, Any]] = []
    bucket: list[str] = []
    for sent in sentences:
        bucket.append(sent)
        words = word_count(" ".join(bucket))
        if words >= 22 or len(bucket) >= 2:
            text = " ".join(bucket).strip()
            scenes.append(
                {
                    "kind": kind,
                    "text": text,
                    "on_screen": _on_screen(text, "LISTEN"),
                }
            )
            bucket = []
    if bucket:
        text = " ".join(bucket).strip()
        scenes.append({"kind": kind, "text": text, "on_screen": _on_screen(text, "NEXT")})
    return scenes


def _fact_lines(research: dict[str, Any] | None) -> list[str]:
    if not research:
        return []
    facts = []
    for item in research.get("facts") or []:
        clean = re.sub(r"\s+", " ", item).strip()
        if 40 <= len(clean) <= 320:
            facts.append(clean)
    return facts[:12]


def _brief(project: dict[str, Any], research: dict[str, Any] | None) -> str:
    facts = _fact_lines(research)
    fact_block = "\n".join(f"- {f}" for f in facts) or "- No verified source facts. Stay honest and avoid fake numbers."
    fmt = "YouTube Short (vertical, under 60 seconds)" if project.get("format") == "short" else "long-form 16:9 video"
    return f"""
Topic: {project.get('topic')}
Working title: {project.get('title')}
Format: {fmt}
Target length: {project.get('target_seconds')} seconds
Style: {project.get('style')} — {STYLES.get(project.get('style') or 'explainer', '')}
Creator notes: {project.get('notes') or 'None'}
Research source: {(research or {}).get('source')}
Research summary: {(research or {}).get('summary') or 'n/a'}
Known facts:
{fact_block}

Write a complete narration that fits the target length at about 148 words per minute.
Open with a hook in the first two sentences. Close with a clean subscribe / comment CTA.
""".strip()


def _local_script(project: dict[str, Any], research: dict[str, Any] | None) -> dict[str, Any]:
    topic = (project.get("topic") or "this idea").strip()
    nice = _title_case_topic(topic)
    style = project.get("style") or "explainer"
    fmt = project.get("format") or "long"
    target = int(project.get("target_seconds") or (45 if fmt == "short" else 180))
    facts = _fact_lines(research)
    seed = f"{topic}|{style}|{fmt}"

    hooks = [
        f"Most people think they understand {topic}. They don't.",
        f"If {topic} disappeared tomorrow, the world would not look the way you expect.",
        f"There is a version of {topic} that never makes the thumbnail. This is that version.",
        f"You have heard the simple story about {topic}. The real one is sharper.",
        f"Stop scrolling. {nice} is not what the comment section says it is.",
    ]
    hook = _hash_pick(seed + "hook", hooks)

    titles = {
        "explainer": [
            f"How {nice} Actually Works",
            f"{nice}: The Part Nobody Explains",
            f"The Real Mechanism Behind {nice}",
        ],
        "listicle": [
            f"{_count_for(target)} Things About {nice} That Change the Picture",
            f"The {nice} List You Were Not Given",
            f"{nice} — Numbered, Not Watered Down",
        ],
        "story": [
            f"The Night {nice} Stopped Being Abstract",
            f"A Story Hidden Inside {nice}",
            f"What {nice} Did to One Simple Assumption",
        ],
        "documentary": [
            f"Inside {nice}",
            f"A Brief History of {nice}",
            f"{nice}, Without the Myth",
        ],
        "motivation": [
            f"What {nice} Is Trying to Teach You",
            f"Do This Before You Talk About {nice}",
            f"{nice} as a Decision, Not a Vibe",
        ],
        "news": [
            f"{nice}: What Matters Right Now",
            f"The {nice} Briefing",
            f"Catch Up on {nice} in One Sitting",
        ],
    }
    title = _hash_pick(seed + "title", titles.get(style, titles["explainer"]))

    if fmt == "short":
        scenes = _short_script(nice, topic, hook, facts, target, style)
    elif style == "listicle":
        scenes = _listicle_script(nice, topic, hook, facts, target)
    elif style == "story":
        scenes = _story_script(nice, topic, hook, facts, target)
    elif style == "motivation":
        scenes = _motivation_script(nice, topic, hook, facts, target)
    elif style == "news":
        scenes = _news_script(nice, topic, hook, facts, target)
    else:
        scenes = _explainer_script(nice, topic, hook, facts, target, documentary=style == "documentary")

    scenes = _fit_to_duration(scenes, target)
    full = " ".join(s["text"] for s in scenes)
    tags = _tags(topic, style)
    description = _description(nice, topic, full, research, tags)
    return {
        "title": title[:70],
        "hook": hook,
        "description": description,
        "tags": tags,
        "scenes": scenes,
        "full_text": full,
        "engine": "studio",
        "word_count": word_count(full),
        "estimated_seconds": round(estimate_seconds(full), 1),
    }


def _count_for(target: int) -> int:
    if target < 50:
        return 3
    if target < 120:
        return 5
    if target < 240:
        return 7
    return 10


def _explainer_script(
    nice: str, topic: str, hook: str, facts: list[str], target: int, documentary: bool = False
) -> list[dict[str, Any]]:
    scenes: list[dict[str, Any]] = [
        {
            "kind": "title",
            "text": f"{hook} In the next few minutes, we are going to take {topic} apart until the moving pieces are visible.",
            "on_screen": _slug_words(topic),
        }
    ]
    frames = [
        f"Start with the plain version. When people say {topic}, they usually mean a headline, not a mechanism. The headline is easy to repeat. The mechanism is what changes how you act.",
        f"Here is the useful question: what has to be true for {topic} to exist at all? If you can answer that without jargon, you already understand more than most comment threads.",
        f"Context matters. {nice} did not arrive fully formed. It is the current shape of older pressures — tools, incentives, fear, and curiosity stacked on top of each other.",
        f"A lot of confusion is just mixed timescales. People argue about {topic} as if every effect happens this afternoon. Some effects are immediate. The important ones compound.",
        f"Watch for the decoy debate. Loud arguments about {topic} often fight over a symbol, while the real leverage sits in a boring constraint almost nobody wants to film.",
        f"If you only remember one cut: {topic} is not a single object. It is a system. Change one input and a different output shows up later, usually somewhere you were not looking.",
        f"That is why simple takes age badly. A take that ignores tradeoffs will sound confident for a week and naive for a year.",
    ]
    if documentary:
        frames.insert(
            1,
            f"Treat this like a field report, not a TED talk. We are not here to worship {topic} or to bury it. We are here to see it clearly.",
        )
    if facts:
        frames = _weave_facts(frames, facts)
    scenes.extend(_pack_scenes(frames))
    scenes.append(_outro(topic, nice))
    return scenes


def _listicle_script(nice: str, topic: str, hook: str, facts: list[str], target: int) -> list[dict[str, Any]]:
    n = _count_for(target)
    scenes = [
        {
            "kind": "title",
            "text": f"{hook} Here are {n} things about {topic} that make the usual summary feel unfinished.",
            "on_screen": f"{n} ON { _slug_words(topic, 2)}",
        }
    ]
    stems = [
        f"First. Definitions are doing more work than people admit. Two people can say {topic} and mean opposite machines.",
        f"Second. Incentives beat opinions. Follow who gets paid, protected, or praised when {topic} grows, and the story gets less mystical.",
        f"Third. Scale changes the moral. What is harmless at a kitchen table can be dangerous when {topic} is applied to millions of people at once.",
        f"Fourth. History already ran a cheaper version of this experiment. The names were different. The failure modes rhyme.",
        f"Fifth. The missing skill is not more content. It is better questions. Ask what would falsify your current view of {topic}.",
        f"Sixth. Expertise is lumpy. The person who understands one slice of {topic} may be lost in the slice that actually decides outcomes.",
        f"Seventh. Speed is a special effect. Fast takes on {topic} travel. Slow measurements do not. Guess which one shapes your feed.",
        f"Eighth. Tradeoffs are not a vibe. If a plan around {topic} has no loser, you have not found the cost yet.",
        f"Ninth. Language launders power. Soft words around {topic} can hide hard consequences. Listen for verbs, not adjectives.",
        f"Tenth. You do not need a final opinion today. You need a working model you are willing to update when {topic} moves.",
    ]
    if facts:
        for i, fact in enumerate(facts[:n]):
            stems[i] = f"{stems[i]} Hold this against the record: {fact}"
    scenes.extend(
        {
            "kind": "stat" if i % 2 == 0 else "narration",
            "text": stems[i],
            "on_screen": f"{i + 1} / {n}",
        }
        for i in range(n)
    )
    scenes.append(_outro(topic, nice))
    return scenes


def _story_script(nice: str, topic: str, hook: str, facts: list[str], target: int) -> list[dict[str, Any]]:
    frames = [
        hook,
        f"Picture someone competent, not a cartoon villain, walking into {topic} with a clean plan and a good night of sleep.",
        f"The plan works — at first. That is the trap. Early success around {topic} feels like proof, when it is often just a quiet weather window.",
        f"Then the hidden variable shows up. A delay. A person who does not care. A rule that was never written down. {nice} stops being a slide and becomes a room.",
        f"This is the turn. The hero does not need more motivation. They need a better map. They have to throw out the slogan that got them into the room.",
        f"If there is a lesson, it is unromantic. {topic} rewards people who can hold two truths: the story that gets you started, and the mechanism that decides who lasts.",
    ]
    if facts:
        frames.insert(3, f"The public record already hints at this. {facts[0]}")
        if len(facts) > 1:
            frames.insert(5, f"And then there is this detail, easy to skip: {facts[1]}")
    scenes = [{"kind": "title", "text": frames[0], "on_screen": _slug_words(topic)}]
    scenes.extend(_pack_scenes(frames[1:]))
    scenes.append(_outro(topic, nice))
    return scenes


def _motivation_script(nice: str, topic: str, hook: str, facts: list[str], target: int) -> list[dict[str, Any]]:
    frames = [
        f"{hook} I am not here to decorate {topic}. I am here to make it usable.",
        f"You do not rise to the version of {topic} you consume. You fall to the version you practice when nobody is watching.",
        f"Drop the identity argument. For the next week, treat {topic} as a craft: one constraint, one rep, one review.",
        f"Most people quit at the ugly middle, where {topic} stops being inspiring and starts being administrative. That middle is the job.",
        f"Pick a scoreboard you cannot lie to. Not vibes. Not a streak screenshot. A number that moves only if you did the work {topic} actually requires.",
        f"Then tell someone specific. Accountability is not aesthetic. It is a person who will ask you about {topic} on Thursday.",
    ]
    if facts:
        frames.insert(2, f"Keep the romance in check. {facts[0]}")
    scenes = [{"kind": "title", "text": frames[0], "on_screen": "DO THE WORK"}]
    scenes.extend(_pack_scenes(frames[1:]))
    scenes.append(
        {
            "kind": "outro",
            "text": f"If this landed, subscribe and comment with the one action you will take on {topic} in the next 24 hours. Make it embarrassingly small. Then do it.",
            "on_screen": "YOUR MOVE",
        }
    )
    return scenes


def _news_script(nice: str, topic: str, hook: str, facts: list[str], target: int) -> list[dict[str, Any]]:
    frames = [
        f"{hook} This is the briefing on {topic}: what changed, why it matters, what to ignore.",
        f"The signal is not the hottest clip. The signal is the constraint that just moved — money, law, infrastructure, or attention.",
        f"Why it matters: {topic} sits upstream of decisions people will pretend are personal later. If you understand the upstream, the downstream is less surprising.",
        f"What to ignore: theatrical certainty. Anyone who can explain {topic} in a single villain is selling you a merch table, not a model.",
        f"What to watch next: the boring implementation. The press conference is not the event. The event is what still works on a Monday morning.",
    ]
    if facts:
        frames.insert(1, "Here is what we can actually say. " + " ".join(facts[:3]))
    scenes = [{"kind": "title", "text": frames[0], "on_screen": "BRIEFING"}]
    scenes.extend(_pack_scenes(frames[1:]))
    scenes.append(_outro(topic, nice))
    return scenes


def _short_script(
    nice: str, topic: str, hook: str, facts: list[str], target: int, style: str
) -> list[dict[str, Any]]:
    lines = [
        hook,
        f"Here is the cut on {topic} that usually gets skipped.",
    ]
    if facts:
        lines.extend(facts[:3])
    else:
        lines.extend(
            [
                f"{nice} looks simple from far away. Up close it is a chain of rules, not a single object.",
                f"The useful question is not what {topic} is called. It is what has to be true for it to happen at all.",
                f"If you can explain {topic} without a metaphor, you actually understand it. Most people are still on the metaphor.",
            ]
        )
    lines.append(f"Follow for the longer cut on {topic}. Comment the part that surprised you.")
    scenes = []
    for i, line in enumerate(lines):
        kind = "title" if i == 0 else "outro" if i == len(lines) - 1 else "stat" if i == 1 else "narration"
        scenes.append(
            {
                "kind": kind,
                "text": line if line.endswith((".", "!", "?")) else line + ".",
                "on_screen": _on_screen(line, nice.upper()),
            }
        )
    return scenes


def _outro(topic: str, nice: str) -> dict[str, Any]:
    return {
        "kind": "outro",
        "text": (
            f"If this gave you a cleaner model of {topic}, subscribe. "
            f"Comment with the part of {nice} you still think we got wrong. "
            f"The next video goes one layer deeper."
        ),
        "on_screen": "SUBSCRIBE",
    }


def _weave_facts(frames: list[str], facts: list[str]) -> list[str]:
    out = []
    fi = 0
    for i, frame in enumerate(frames):
        out.append(frame)
        if fi < len(facts) and i % 2 == 0:
            out.append(f"Here is a piece of the public record. {facts[fi]}")
            fi += 1
    while fi < min(len(facts), 6):
        out.append(facts[fi])
        fi += 1
    return out


def _fit_to_duration(scenes: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
    target_words = max(40, int(target * WORDS_PER_MINUTE / 60))
    texts = [s["text"] for s in scenes]
    total = word_count(" ".join(texts))
    # Grow by repeating a clarifying beat if far too short
    if total < target_words * 0.72 and scenes:
        extra = (
            "Slow down on that last point. If it feels obvious, you are still on the slogan. "
            "Stay with the mechanism until you could explain it to a skeptical friend without a slide."
        )
        scenes.insert(-1, {"kind": "narration", "text": extra, "on_screen": "SLOW DOWN"})
        total = word_count(" ".join(s["text"] for s in scenes))
    # Trim from the middle if wildly long
    while word_count(" ".join(s["text"] for s in scenes)) > target_words * 1.25 and len(scenes) > 4:
        # drop a middle narration scene
        mid = len(scenes) // 2
        if scenes[mid]["kind"] in {"title", "outro"}:
            mid -= 1
        scenes.pop(mid)
    for i, scene in enumerate(scenes):
        scene["id"] = f"sc{i + 1:02d}"
        scene["duration"] = round(estimate_seconds(scene["text"]), 2)
    return scenes


def _tags(topic: str, style: str) -> list[str]:
    words = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", topic) if len(w) > 2]
    base = words[:5] + [style, "explainer", "documentary", "facts", "youtube", "education", "channelforge"]
    seen = []
    for t in base:
        if t not in seen:
            seen.append(t)
    return seen[:14]


def _description(
    nice: str, topic: str, full: str, research: dict[str, Any] | None, tags: list[str]
) -> str:
    hook = " ".join(_split_sentences(full)[:2])
    source_line = ""
    if research and research.get("url"):
        source_line = f"\nResearch starting point: {research['url']}\n"
    hashtags = " ".join(f"#{re.sub(r'[^A-Za-z0-9]', '', t)}" for t in tags[:6] if t)
    return (
        f"{hook}\n\n"
        f"This ChannelForge video is a structured briefing on {nice}. "
        f"It was written, voiced, designed, and assembled in the studio pipeline.\n"
        f"{source_line}\n"
        f"Chapters are auto-marked by scene. Watch once for the hook, again for the mechanism.\n\n"
        f"If you want the next layer, subscribe and name the angle we should film.\n\n"
        f"{hashtags}"
    )


def scenes_from_text(text: str) -> list[dict[str, Any]]:
    return _pack_scenes(_split_sentences(text))


def normalize_script(data: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    scenes = []
    for i, raw in enumerate(data.get("scenes") or []):
        text = (raw.get("text") or "").strip()
        if not text:
            continue
        scenes.append(
            {
                "id": raw.get("id") or f"sc{i + 1:02d}",
                "kind": raw.get("kind") or "narration",
                "text": text,
                "on_screen": (raw.get("on_screen") or _on_screen(text, "SCENE")).strip(),
                "visual_prompt": (raw.get("visual_prompt") or "").strip(),
                "duration": round(float(raw.get("duration") or estimate_seconds(text)), 2),
            }
        )
    if not scenes:
        scenes = [
            {
                "id": "sc01",
                "kind": "title",
                "text": f"Today we look at {project.get('topic')}.",
                "on_screen": _slug_words(project.get("topic") or "VIDEO"),
                "duration": 4.0,
            }
        ]
    full = data.get("full_text") or " ".join(s["text"] for s in scenes)
    title = (data.get("title") or project.get("title") or project.get("topic") or "Untitled").strip()
    return {
        "title": title[:90],
        "hook": data.get("hook") or scenes[0]["text"],
        "description": data.get("description") or _description(title, project.get("topic") or title, full, None, data.get("tags") or []),
        "tags": data.get("tags") or _tags(project.get("topic") or title, project.get("style") or "explainer"),
        "scenes": scenes,
        "full_text": full,
        "engine": data.get("engine") or "manual",
        "word_count": word_count(full),
        "estimated_seconds": round(estimate_seconds(full), 1),
    }


async def write_script(project: dict[str, Any], research: dict[str, Any] | None) -> dict[str, Any]:
    llm = await generate_script_llm(_brief(project, research))
    if llm:
        llm["engine"] = llm.get("engine") or "llm"
        return normalize_script(llm, project)
    local = _local_script(project, research)
    from app.services.llm import last_error

    err = last_error()
    if err:
        local["llm_error"] = err
    return local
