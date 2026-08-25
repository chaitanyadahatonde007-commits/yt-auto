from __future__ import annotations

from typing import Any

CAST = (
    {
        "id": "golu",
        "name": "Golu",
        "role": "overconfident dost",
        "look": (
            "A consistent 3D cartoon Indian young man named Golu, round face, messy black hair, "
            "bright yellow hoodie, big expressive eyes, always a little too sure of himself"
        ),
    },
    {
        "id": "pihu",
        "name": "Pihu",
        "role": "sharp roast queen",
        "look": (
            "A consistent 3D cartoon Indian young woman named Pihu, sharp jaw, short wavy hair, "
            "magenta jacket, unimpressed smirk, the one who actually knows the twist"
        ),
    },
)


def pick_character(index: int) -> dict[str, Any]:
    return CAST[index % len(CAST)]


def acting_prompt(scene: dict[str, Any], project: dict[str, Any], index: int = 0) -> str:
    name = (scene.get("character") or "").strip()
    member = next((c for c in CAST if c["name"].lower() == name.lower()), None)
    if not member:
        member = pick_character(index)
    line = (scene.get("text") or scene.get("on_screen") or project.get("topic") or "")[:180]
    topic = project.get("topic") or "this story"
    return (
        f"{member['look']}, acting out this beat: {line}. "
        f"Story is about {topic}. Full body in frame, cinematic comedy lighting, "
        f"exaggerated expression, no text, no letters, no watermark, no logo."
    )


def cast_note() -> str:
    return (
        "Two cartoon hosts act every line. Golu is loud and usually wrong first. "
        "Pihu roasts him and drops the twist. Alternate speakers. Mark each scene with character Golu or Pihu."
    )
