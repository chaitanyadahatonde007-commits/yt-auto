# ChannelForge

A local YouTube automation studio. Give it a topic and it will:

1. Research a briefing (Wikipedia when reachable, plus your notes)
2. Write a spoken script and scene cards
3. Record a voiceover
4. Design cinematic frames and three thumbnails
5. Render a captioned MP4
6. Upload to your YouTube channel (optional)

No cloud account is required to write, voice, design, or render. Neural voices and smarter writing light up if you add keys.

## Quick start

```bash
chmod +x start.sh
./start.sh
```

Open [http://localhost:8000](http://localhost:8000).

Requirements: Python 3.11+, Node.js (for the offline voice engine). FFmpeg is pulled in automatically via `imageio-ffmpeg`.

## How a cut is made

| Stage | What happens |
| --- | --- |
| Research | Wikipedia summary + your notes |
| Script | Local showrunner, or OpenAI / Anthropic / Gemini if a key is saved |
| Voice | Edge neural TTS when the network allows, OpenAI TTS if keyed, otherwise a local studio voice |
| Visuals | Motion-ready posters from cinematic plates + type |
| Thumbnails | Three 1280×720 posters — pick one |
| Render | Ken Burns picture, captions, voice, low score, H.264 |
| Publish | Official YouTube Data API upload + thumbnail |

Use **Auto-cut** from the floor, or step through the studio.

Formats:

- **Long** — 16:9, 2–8 minutes
- **Short** — 9:16 YouTube Short

## Better scripts (optional)

In **Settings**, paste one of:

- OpenAI API key (`gpt-4o-mini` by default)
- Anthropic API key
- Gemini API key

The writer stays honest: it will not invent statistics. Without a key it still produces a structured host-read from the briefing.

## Connect YouTube

1. Create a Google Cloud project
2. Enable **YouTube Data API v3**
3. Create an OAuth client (Web application)
4. Add the redirect URI:

   `https://YOUR_STUDIO_URL/api/youtube/callback`

5. Paste client ID, client secret, and the same public base URL into **Settings**
6. Open **Channel → Connect YouTube**

Uploads default to **private**. Change privacy per video before publish.

If you skip OAuth, download the MP4 from the Render step and upload it yourself.

## Project layout

```
app/            FastAPI app + studio UI
app/services/   script, TTS, visuals, compositor, YouTube
assets/         fonts, brand, cinematic plates
data/           local database, renders, OAuth token (gitignored)
```

Each project lives in `data/projects/<id>/` with `voice.wav`, `scenes/`, thumbnails, and `final.mp4`.

## Voices

- `local:*` — always available
- `edge:*` — Microsoft neural voices when `speech.platform.bing.com` is reachable
- `openai:*` — when an OpenAI key is saved

## Safety

This tool creates original narration and graphics from a topic you provide. You are responsible for the claims you publish, copyright on any extra assets you add, and your channel’s compliance with YouTube policies.
