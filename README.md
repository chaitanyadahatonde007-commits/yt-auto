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

You need [Python 3.11+](https://www.python.org/downloads/) and [Node.js](https://nodejs.org/). On Windows, tick **Add python.exe to PATH** when installing Python. After installing either one, close the terminal and open a new one.

Then open [http://localhost:8000](http://localhost:8000). Leave the terminal running.

### VS Code

1. **File → Open Folder** and choose this `yt-auto` folder
2. Install the recommended **Python** extension if VS Code asks
3. Open the terminal (**Ctrl+`**) and run:

```bat
py -3 run.py
```

Or press **F5** / **Run → Start Debugging** and choose **Run ChannelForge**.

### Command Prompt

```bat
cd C:\Users\hp\OneDrive\ドキュメント\GitHub\yt-auto
start.bat
```

You can also type `py -3 run.py` in that folder. Do **not** type `./start.sh` in CMD.

### Mac / Linux / Git Bash

```bash
python3 run.py
```

## How a cut is made

| Stage | What happens |
| --- | --- |
| Research | Wikipedia summary + your notes |
| Script | Local showrunner, or OpenAI / Anthropic / Gemini if a key is saved |
| Voice | Edge neural TTS when the network allows, OpenAI TTS if keyed, otherwise a local studio voice |
| Visuals | WaveSpeed stills + motion, Pexels stock video, keep the strongest clip |
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
- Groq API key from [console.groq.com](https://console.groq.com/keys) (`gsk_…`). Used to write the script fast, plan scene picture prompts, and optionally speak with PlayAI voices. Groq cannot generate images.
- Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) (`AIza…` or `AQ.…`). Paste it in **Settings**. That key is used to:
  1. Write the spoken script and scene list
  2. Plan a unique picture for each line
  3. Generate those scene stills
  4. Paint a thumbnail photograph

  It is **not** used for voice, FFmpeg render, or YouTube upload. The key stays in local `data/settings.json` and is never committed.

- Pexels API key from [pexels.com/api](https://www.pexels.com/api/). Paste it in **Settings**. Used for real stock video per scene (and backup stills). The key stays in local `data/settings.json` and is never committed.
- Pixabay API key from [pixabay.com/api/docs](https://pixabay.com/api/docs/). Photos and videos. Same local-only storage.
- NewsAPI key from [newsapi.org](https://newsapi.org/). Live headlines for Autopilot and extra facts in research. Same local-only storage.

The writer stays honest: it will not invent statistics. Without a key it still produces a structured host-read from the briefing.

## Autopilot

Open **Autopilot** in the studio.

1. Turn **Start autopilot** on
2. Leave `py -3 run.py` running
3. ChannelForge reads YouTube / Google Trends / Reddit / Wikipedia, picks a famous topic, generates the video, and either schedules it on YouTube (9am / 1pm / 7pm IST) or only renders it

**Make one now** does a single unattended cut immediately.

The PC must stay on and the studio window must stay open for the schedule to fire.

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
