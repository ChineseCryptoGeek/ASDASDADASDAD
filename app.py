import os
import uuid
import threading
from flask import Flask, request, jsonify, send_file, render_template_string
from clipper import run

app = Flask(__name__)

# track job status
jobs = {}

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>clipper</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #0a0a0a;
      color: #fff;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .container {
      width: 100%;
      max-width: 560px;
      padding: 40px 24px;
    }
    h1 {
      font-size: 28px;
      font-weight: 700;
      margin-bottom: 8px;
      letter-spacing: -0.5px;
    }
    p.sub {
      color: #666;
      font-size: 14px;
      margin-bottom: 32px;
    }
    .input-row {
      display: flex;
      gap: 10px;
    }
    input {
      flex: 1;
      background: #161616;
      border: 1px solid #2a2a2a;
      border-radius: 10px;
      color: #fff;
      font-size: 15px;
      padding: 14px 16px;
      outline: none;
      transition: border-color 0.2s;
    }
    input:focus { border-color: #555; }
    input::placeholder { color: #444; }
    button {
      background: #fff;
      color: #000;
      border: none;
      border-radius: 10px;
      font-size: 15px;
      font-weight: 600;
      padding: 14px 24px;
      cursor: pointer;
      white-space: nowrap;
      transition: opacity 0.2s;
    }
    button:hover { opacity: 0.85; }
    button:disabled { opacity: 0.4; cursor: not-allowed; }
    .status {
      margin-top: 24px;
      padding: 16px;
      background: #161616;
      border: 1px solid #2a2a2a;
      border-radius: 10px;
      font-size: 14px;
      color: #aaa;
      display: none;
    }
    .status.visible { display: block; }
    .status.done { border-color: #2a5a2a; color: #6fcf6f; }
    .status.error { border-color: #5a2a2a; color: #cf6f6f; }
    .clips-list {
      margin-top: 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .clip-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 14px;
      background: #1a1a1a;
      border-radius: 8px;
      font-size: 13px;
    }
    .clip-item a {
      color: #7eb8f7;
      text-decoration: none;
      font-weight: 500;
    }
    .clip-item a:hover { text-decoration: underline; }
    .dot {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #555;
      margin-right: 10px;
      animation: pulse 1.2s ease-in-out infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.3; }
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>clipper</h1>
    <p class="sub">paste a link. get viral clips. powered by whisper + claude.</p>

    <div class="input-row">
      <input id="url" type="text" placeholder="youtube, twitch, tiktok, twitter..." />
      <button id="btn" onclick="startClip()">clip it</button>
    </div>

    <div class="status" id="status"></div>
  </div>

  <script>
    let pollInterval = null;

    async function startClip() {
      const url = document.getElementById('url').value.trim();
      if (!url) return;

      const btn = document.getElementById('btn');
      const statusEl = document.getElementById('status');

      btn.disabled = true;
      statusEl.className = 'status visible';
      statusEl.innerHTML = '<span class="dot"></span>starting...';

      const res = await fetch('/clip', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
      });

      const data = await res.json();
      if (data.error) {
        statusEl.className = 'status visible error';
        statusEl.textContent = 'error: ' + data.error;
        btn.disabled = false;
        return;
      }

      const jobId = data.job_id;
      statusEl.innerHTML = '<span class="dot"></span>downloading + transcribing...';

      pollInterval = setInterval(async () => {
        const r = await fetch('/status/' + jobId);
        const s = await r.json();

        if (s.status === 'processing') {
          statusEl.innerHTML = '<span class="dot"></span>' + (s.message || 'processing...');
        } else if (s.status === 'done') {
          clearInterval(pollInterval);
          btn.disabled = false;
          statusEl.className = 'status visible done';
          let html = '✓ done — ' + s.clips.length + ' clips ready<div class="clips-list">';
          s.clips.forEach((c, i) => {
            html += `<div class="clip-item"><span>clip ${i+1}</span><a href="/download/${jobId}/${i}" download>download</a></div>`;
          });
          html += '</div>';
          statusEl.innerHTML = html;
        } else if (s.status === 'error') {
          clearInterval(pollInterval);
          btn.disabled = false;
          statusEl.className = 'status visible error';
          statusEl.textContent = 'failed: ' + s.message;
        }
      }, 3000);
    }

    document.getElementById('url').addEventListener('keydown', e => {
      if (e.key === 'Enter') startClip();
    });
  </script>
</body>
</html>
"""


def run_job(job_id, url):
    try:
        jobs[job_id] = {"status": "processing", "message": "downloading video..."}
        clips = run(url)
        jobs[job_id] = {"status": "done", "clips": clips}
    except Exception as e:
        jobs[job_id] = {"status": "error", "message": str(e)}


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/clip", methods=["POST"])
def clip():
    data = request.json
    url = data.get("url")
    if not url:
        return jsonify({"error": "no url provided"}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing", "message": "starting..."}

    thread = threading.Thread(target=run_job, args=(job_id, url))
    thread.daemon = True
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"status": "error", "message": "job not found"}), 404
    return jsonify(job)


@app.route("/download/<job_id>/<int:clip_index>")
def download(job_id, clip_index):
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return "not ready", 404
    clips = job.get("clips", [])
    if clip_index >= len(clips):
        return "clip not found", 404
    clip_path = clips[clip_index]
    return send_file(clip_path, as_attachment=True, download_name=f"clip_{clip_index + 1}.mp4")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
