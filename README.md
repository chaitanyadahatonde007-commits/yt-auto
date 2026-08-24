# yt-auto

Python helper for the **official YouTube Data API v3**: search, video stats, channel stats, and (optional) OAuth for uploads.

This repo **cannot mint Google API keys for you**. Keys are issued only inside *your* Google Cloud project. There is no public “key generator.” Anyone offering a shared YouTube key is almost certainly violating Google’s terms and will get the key revoked.

---

## What the YouTube APIs actually are

YouTube is not one API. Google splits it:

| Product | What it does | Auth |
| --- | --- | --- |
| **YouTube Data API v3** | Search, videos, channels, playlists, comments, **uploads** | API key (public read) or OAuth (private / write) |
| **YouTube Analytics API** | Owner reports (views, revenue, traffic sources) | OAuth + channel ownership |
| **YouTube Reporting API** | Bulk CSV reports for large channels | OAuth |
| **YouTube Live Streaming API** | Live broadcasts / streams | OAuth |
| **YouTube iframe Player API** | Embed / control the player in a browser | No Cloud key (JS) |

**yt-auto uses Data API v3.**

### API key vs OAuth

| You want | Use |
| --- | --- |
| Search, public video/channel metadata, public comments | **API key** (`AIza…`) |
| Upload, edit your videos, manage playlists, post as you | **OAuth 2.0** client ID + secret |
| Your Analytics / revenue | Analytics API + OAuth |

Default free quota: **10,000 units / day / project**. Examples:

- `search.list` = **100** units (so ~100 searches/day)
- `videos.list` / `channels.list` = **1** unit
- `videos.insert` (upload) = **1,600** units

---

## How to get an API key (you must do this in a browser)

1. Sign in at [Google Cloud Console](https://console.cloud.google.com/) (any Google account; **no credit card** required for Data API).
2. Project picker → **New Project** → name it e.g. `yt-auto` → Create. Select it.
3. **APIs & Services → Library** → search **YouTube Data API v3** → **Enable**.
4. **APIs & Services → Credentials → Create credentials → API key**.
5. Copy the key. Restrict it: Application restriction (IP for servers, HTTP referrer for web) + API restriction = YouTube Data API v3 only.
6. In this repo:

```bash
cp .env.example .env
# put YOUTUBE_API_KEY=AIza... in .env
```

Test (costs 100 units):

```bash
curl "https://www.googleapis.com/youtube/v3/search?part=snippet&q=test&type=video&maxResults=1&key=YOUR_KEY"
```

A JSON `items` array means the key works. `accessNotConfigured` means the API is not enabled.

### OAuth (uploads / acting as your channel)

1. Same project, **Credentials → Create credentials → OAuth client ID**.
2. Configure the **OAuth consent screen** (External is fine for testing; add yourself as a test user).
3. Application type: **Desktop app**. Download JSON.
4. Set `GOOGLE_OAUTH_CLIENT_SECRETS=/absolute/path/to/client_secret.json` in `.env`.
5. First run opens a browser; token is stored in `.oauth-token.json` (gitignored).

Never commit `.env`, API keys, or `client_secret*.json`.

---

## Install and run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```bash
python -m yt_auto.cli search "python asyncio" -n 3
python -m yt_auto.cli video dQw4w9WgXcQ
python -m yt_auto.cli channel @GoogleDevelopers
```

---

## What this project will not do

- Create or scrape Google API keys
- Buy views, fake engagement, or mass-spam comments (YouTube ToS)
- Bypass quota or use unofficial “unlimited” keys

Use the official API, stay inside quota, and keep keys private.

## References

- [YouTube Data API overview](https://developers.google.com/youtube/v3)
- [Quota calculator](https://developers.google.com/youtube/v3/determine_quota_cost)
- [Auth guide](https://developers.google.com/youtube/v3/guides/authentication)
- [Cloud Console](https://console.cloud.google.com/)
