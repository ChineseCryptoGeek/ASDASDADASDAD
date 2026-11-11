# clipper

paste a video link. get viral clips. automatically.

downloads → transcribes → finds best moments → face-tracks → adds animated captions → exports.

---

## what it does

- **downloads** from youtube, twitch, tiktok, twitter via yt-dlp
- **transcribes** with openai whisper (word-level timestamps)
- **finds viral moments** using claude api — reads the transcript and picks the 3 best clips
- **vertical reframe** with face tracking — opencv follows the subject, not a dumb center crop
- **animated captions** — word-by-word tiktok style, big white text, black outline

---

## deploy to railway (no install needed)

1. fork this repo
2. go to [railway.app](https://railway.app) → new project → deploy from github repo
3. select your fork
4. add environment variable: `ANTHROPIC_API_KEY` = your key from [console.anthropic.com](https://console.anthropic.com)
5. railway builds the docker image and gives you a live URL

that's it. paste the URL into your browser, drop in a link, clips come out.

---

## run locally with docker

```bash
git clone https://github.com/BasedOffAssets/ASDADAD
cd ASDADAD

# run it
ANTHROPIC_API_KEY=your_key docker-compose up
```

open `http://localhost:5000` → paste link → download clips from `/clips/`

---

## run locally with python

```bash
pip install -r requirements.txt

# also need ffmpeg:
# mac:   brew install ffmpeg
# linux: sudo apt install ffmpeg
# win:   https://ffmpeg.org/download.html

export ANTHROPIC_API_KEY=your_key
python app.py
```

---

## env vars

| var | default | description |
|-----|---------|-------------|
| `ANTHROPIC_API_KEY` | required | get from console.anthropic.com |
| `WHISPER_MODEL` | `base` | `base` = fast, `small`/`medium` = more accurate |
| `OUTPUT_DIR` | `clips` | where clips are saved |

---

## stack

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — video downloading
- [openai-whisper](https://github.com/openai/whisper) — transcription
- [anthropic](https://docs.anthropic.com) — virality detection
- [opencv](https://opencv.org) — face tracking
- [ffmpeg](https://ffmpeg.org) — video processing
- [flask](https://flask.palletsprojects.com) — web server
