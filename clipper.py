# clipper.py — v2 with face tracking + animated captions
# pip install yt-dlp openai-whisper anthropic opencv-python Pillow numpy

import os
import json
import subprocess
import cv2
import numpy as np
import whisper
import yt_dlp
import anthropic
from PIL import Image, ImageDraw, ImageFont

# ── config ─────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "YOUR_API_KEY_HERE")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "clips")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")
FONT_PATH = os.environ.get("FONT_PATH", None)
FONT_SIZE = int(os.environ.get("FONT_SIZE", "52"))
# ───────────────────────────────────────────────────────────

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ── step 1: download ────────────────────────────────────────
def download_video(url):
    print("[1/6] downloading video...")
    output_path = os.path.join(OUTPUT_DIR, "source.mp4")
    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
        "outtmpl": output_path,
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    print(f"    saved → {output_path}")
    return output_path


# ── step 2: transcribe with word timestamps ─────────────────
def transcribe_video(video_path):
    print("[2/6] transcribing with whisper (word-level)...")
    model = whisper.load_model(WHISPER_MODEL)
    result = model.transcribe(video_path, word_timestamps=True)

    words = []
    for seg in result["segments"]:
        if "words" in seg:
            for w in seg["words"]:
                words.append({
                    "word": w["word"].strip(),
                    "start": w["start"],
                    "end": w["end"]
                })

    segments = result["segments"]
    print(f"    {len(words)} words transcribed across {len(segments)} segments")
    return segments, words


# ── step 3: find viral moments ──────────────────────────────
def find_viral_moments(segments):
    print("[3/6] finding viral moments with claude...")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    transcript_text = "\n".join([
        f"[{s['start']:.1f}s - {s['end']:.1f}s]: {s['text'].strip()}"
        for s in segments
    ])

    prompt = f"""you're a viral clip editor. analyze this transcript and find the 3 best moments to clip.
look for: funny reactions, insane moments, shocking statements, peak energy, anything that makes someone stop scrolling.
each clip should be 30-90 seconds long. don't overlap clips.

return ONLY a valid JSON array, nothing else:
[
  {{"start": 12.0, "end": 55.0, "reason": "why"}},
  {{"start": 102.0, "end": 165.0, "reason": "why"}},
  {{"start": 210.0, "end": 275.0, "reason": "why"}}
]

transcript:
{transcript_text}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    moments = json.loads(raw)
    for i, m in enumerate(moments):
        print(f"    clip {i+1}: {m['start']}s → {m['end']}s | {m['reason']}")
    return moments


# ── step 4: face-tracked vertical reframe ──────────────────
def get_face_crop_positions(video_path, start, end):
    print("    detecting faces for smart reframe...")

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    start_frame = int(start * fps)
    end_frame = int(end * fps)

    crop_width = int(height * 9 / 16)
    center_x_positions = []
    last_known_center = width // 2

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    frame_idx = start_frame

    while frame_idx <= end_frame:
        ret, frame = cap.read()
        if not ret:
            break

        if (frame_idx - start_frame) % 6 == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
            )
            if len(faces) > 0:
                largest = max(faces, key=lambda f: f[2] * f[3])
                x, y, w, h = largest
                face_center_x = x + w // 2
                last_known_center = np.clip(
                    face_center_x,
                    crop_width // 2,
                    width - crop_width // 2
                )

        center_x_positions.append(last_known_center)
        frame_idx += 1

    cap.release()

    if len(center_x_positions) > 15:
        kernel = np.ones(15) / 15
        center_x_positions = np.convolve(center_x_positions, kernel, mode="same").tolist()

    return center_x_positions, fps, width, height, crop_width


def reframe_with_face_tracking(input_path, output_path, start, end):
    positions, fps, width, height, crop_width = get_face_crop_positions(
        input_path, start, end
    )

    raw_cut = output_path.replace(".mp4", "_raw_cut.mp4")
    subprocess.run([
        "ffmpeg", "-i", input_path,
        "-ss", str(start), "-to", str(end),
        "-c:v", "libx264", "-c:a", "aac",
        "-y", raw_cut
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("    applying face-tracked crop...")

    cap = cv2.VideoCapture(raw_cut)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(
        output_path.replace(".mp4", "_noaudio.mp4"),
        fourcc, fps,
        (crop_width, height)
    )

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        pos_idx = min(frame_idx, len(positions) - 1)
        cx = int(positions[pos_idx])
        x1 = max(0, cx - crop_width // 2)
        x2 = x1 + crop_width
        if x2 > width:
            x2 = width
            x1 = x2 - crop_width

        cropped = frame[:, x1:x2]
        out.write(cropped)
        frame_idx += 1

    cap.release()
    out.release()

    subprocess.run([
        "ffmpeg",
        "-i", output_path.replace(".mp4", "_noaudio.mp4"),
        "-i", raw_cut,
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0", "-map", "1:a:0",
        "-shortest",
        "-y", output_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    os.remove(raw_cut)
    os.remove(output_path.replace(".mp4", "_noaudio.mp4"))
    return output_path


# ── step 5: animated word-by-word captions ─────────────────
def draw_caption_frame(frame_rgb, word, frame_width, frame_height):
    img = Image.fromarray(frame_rgb)
    draw = ImageDraw.Draw(img)

    font_paths_to_try = [
        FONT_PATH,
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]

    font = None
    for fp in font_paths_to_try:
        if fp and os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, FONT_SIZE)
                break
            except Exception:
                continue

    if font is None:
        font = ImageFont.load_default()

    text = word.upper()
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    x = (frame_width - text_w) // 2
    y = frame_height - text_h - 80

    outline_range = 3
    for dx in range(-outline_range, outline_range + 1):
        for dy in range(-outline_range, outline_range + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 255))

    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))

    return np.array(img)


def add_animated_captions(input_path, output_path, words, clip_start):
    print("    adding animated word-by-word captions...")

    cap = cv2.VideoCapture(input_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    temp_video = output_path.replace(".mp4", "_captioned_noaudio.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(temp_video, fourcc, fps, (width, height))

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        current_time = clip_start + (frame_idx / fps)

        active_word = None
        for w in words:
            if w["start"] <= current_time <= w["end"]:
                active_word = w["word"]
                break

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if active_word:
            frame_rgb = draw_caption_frame(frame_rgb, active_word, width, height)
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

        out.write(frame_bgr)
        frame_idx += 1

    cap.release()
    out.release()

    subprocess.run([
        "ffmpeg",
        "-i", temp_video,
        "-i", input_path,
        "-c:v", "copy", "-c:a", "aac",
        "-map", "0:v:0", "-map", "1:a:0",
        "-shortest", "-y", output_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    os.remove(temp_video)
    return output_path


# ── step 6: full clip pipeline ──────────────────────────────
def process_clip(source_path, words, moment, index):
    print(f"\n processing clip {index + 1} ({moment['start']}s → {moment['end']}s)...")

    start = moment["start"]
    end = moment["end"]

    tracked_path = os.path.join(OUTPUT_DIR, f"clip_{index + 1}_tracked.mp4")
    reframe_with_face_tracking(source_path, tracked_path, start, end)

    clip_words = [w for w in words if w["start"] >= start and w["end"] <= end]

    final_path = os.path.join(OUTPUT_DIR, f"clip_{index + 1}_final.mp4")
    add_animated_captions(tracked_path, final_path, clip_words, start)

    os.remove(tracked_path)
    print(f"    done → {final_path}")
    return final_path


# ── main ────────────────────────────────────────────────────
def run(url):
    print(f"\n clipper v2 | {url}\n")

    source = download_video(url)
    segments, words = transcribe_video(source)
    moments = find_viral_moments(segments)

    print(f"\n[4-6/6] processing {len(moments)} clips...\n")
    finals = []
    for i, moment in enumerate(moments):
        clip = process_clip(source, words, moment, i)
        finals.append(clip)

    print("\n all done.")
    print(f" output clips:")
    for f in finals:
        print(f"   → {f}")
    print()
    return finals


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "PASTE_LINK_HERE"
    run(url)
