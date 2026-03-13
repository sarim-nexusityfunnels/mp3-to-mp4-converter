"""
MP3 to MP4 Converter Service
Uses background threading so Render's health checks don't kill long conversions.
"""

import os
import uuid
import time
import logging
import tempfile
import glob
import base64
import shutil
import threading
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONVERTER_URL = "https://mp3-to-youtube-automator-113913926974.us-west1.run.app/"
TIMEOUT_MS = 300_000

# Store jobs in memory
jobs = {}


@app.route("/", methods=["GET"])
def home():
    return '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MP3 to MP4 Converter</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0a0a0f;color:#e0e0e0;min-height:100vh;display:flex;align-items:center;justify-content:center}
  .container{max-width:500px;width:90%;text-align:center}
  h1{font-size:28px;margin-bottom:8px;color:#fff}
  .sub{color:#666;font-size:14px;margin-bottom:32px}
  .dropzone{border:2px dashed #333;border-radius:16px;padding:48px 24px;cursor:pointer;transition:all .2s;background:#0f0f18}
  .dropzone:hover,.dropzone.dragover{border-color:#a78bfa;background:#13131f}
  .dropzone-text{font-size:16px;color:#888}
  .dropzone-text span{color:#a78bfa;text-decoration:underline;cursor:pointer}
  #fileInput{display:none}
  .file-name{margin-top:16px;padding:10px 16px;background:#1a1a2e;border-radius:8px;font-size:13px;color:#a78bfa;display:none}
  .btn{margin-top:20px;padding:14px 32px;background:#a78bfa;color:#000;border:none;border-radius:10px;font-size:16px;font-weight:700;cursor:pointer;display:none;transition:all .2s;width:100%}
  .btn:hover{background:#c4b5fd}
  .btn:disabled{background:#333;color:#666;cursor:not-allowed}
  .status{margin-top:20px;padding:16px;border-radius:10px;font-size:14px;display:none}
  .status.loading{display:block;background:#1a1a0e;border:1px solid #fbbf2433;color:#d4a017}
  .status.success{display:block;background:#0e1a0e;border:1px solid #4ade8033;color:#4ade80}
  .status.error{display:block;background:#1a0e0e;border:1px solid #f8717133;color:#f87171}
  .download-link{display:inline-block;margin-top:12px;padding:12px 24px;background:#4ade80;color:#000;border-radius:8px;text-decoration:none;font-weight:700;font-size:14px}
  .download-link:hover{background:#6ee7a0}
  .spinner{display:inline-block;width:18px;height:18px;border:2px solid #fbbf2444;border-top-color:#fbbf24;border-radius:50%;animation:spin .8s linear infinite;vertical-align:middle;margin-right:8px}
  @keyframes spin{to{transform:rotate(360deg)}}
  .note{margin-top:24px;font-size:11px;color:#444}
  .log{margin-top:12px;font-size:11px;color:#555;font-family:monospace}
</style>
</head>
<body>
<div class="container">
  <h1>MP3 to MP4</h1>
  <p class="sub">Upload an MP3 and get a music video with AI-generated art</p>
  <div class="dropzone" id="dropzone" onclick="document.getElementById('fileInput').click()">
    <input type="file" id="fileInput" accept=".mp3,audio/mpeg">
    <p class="dropzone-text">Drag & drop your MP3 here<br>or <span>browse files</span></p>
  </div>
  <div class="file-name" id="fileName"></div>
  <button class="btn" id="convertBtn" onclick="startConvert()">Convert to MP4</button>
  <div class="status" id="status"></div>
  <div class="log" id="logArea"></div>
  <p class="note">Conversion typically takes 2-4 minutes depending on audio length</p>
</div>
<script>
const dz=document.getElementById('dropzone'),fi=document.getElementById('fileInput'),fn=document.getElementById('fileName'),cb=document.getElementById('convertBtn'),st=document.getElementById('status'),lg=document.getElementById('logArea');
let sf=null;
['dragenter','dragover'].forEach(e=>dz.addEventListener(e,ev=>{ev.preventDefault();dz.classList.add('dragover')}));
['dragleave','drop'].forEach(e=>dz.addEventListener(e,ev=>{ev.preventDefault();dz.classList.remove('dragover')}));
dz.addEventListener('drop',ev=>{if(ev.dataTransfer.files.length)hf(ev.dataTransfer.files[0])});
fi.addEventListener('change',ev=>{if(ev.target.files.length)hf(ev.target.files[0])});
function hf(f){if(!f.name.toLowerCase().endsWith('.mp3')){alert('Please select an MP3 file');return}sf=f;fn.textContent=f.name+' ('+(f.size/1024/1024).toFixed(1)+' MB)';fn.style.display='block';cb.style.display='block';st.className='status';st.style.display='none';lg.textContent=''}
function al(m){lg.textContent=new Date().toLocaleTimeString()+' - '+m}
async function startConvert(){
  if(!sf)return;cb.disabled=true;cb.textContent='Converting...';
  st.className='status loading';st.innerHTML='<span class="spinner"></span> Uploading MP3...';
  try{
    const fd=new FormData();fd.append('file',sf);
    al('Uploading...');
    const r=await fetch('/convert',{method:'POST',body:fd});
    const d=await r.json();
    if(!r.ok||!d.job_id)throw new Error(d.error||'Failed to start');
    al('Job started: '+d.job_id);
    st.innerHTML='<span class="spinner"></span> Converting... please wait 2-4 minutes';
    const n=sf.name.replace('.mp3','.mp4');
    let elapsed=0;
    while(true){
      await new Promise(r=>setTimeout(r,5000));elapsed+=5;
      al('Checking status... ('+elapsed+'s)');
      const sr=await fetch('/status/'+d.job_id);
      const sd=await sr.json();
      if(sd.status==='done'){
        st.className='status success';
        st.innerHTML='Done! Your video is ready.<br><a class="download-link" href="/download/'+d.job_id+'" download="'+n+'">Download '+n+'</a>';
        al('Complete!');break;
      }else if(sd.status==='error'){throw new Error(sd.error||'Conversion failed')}
    }
  }catch(e){st.className='status error';st.textContent='Error: '+e.message;al('Failed: '+e.message)}
  cb.disabled=false;cb.textContent='Convert to MP4';
}
</script>
</body></html>'''


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/convert", methods=["POST"])
def convert():
    job_id = str(uuid.uuid4())[:8]
    logger.info(f"[{job_id}] New conversion request")
    try:
        if "file" in request.files:
            mp3_file = request.files["file"]
            mp3_filename = mp3_file.filename or "input.mp3"
            tmp_dir = tempfile.mkdtemp(prefix=f"job_{job_id}_")
            mp3_path = os.path.join(tmp_dir, mp3_filename)
            mp3_file.save(mp3_path)
            logger.info(f"[{job_id}] Got MP3: {mp3_filename}")
        elif request.is_json and request.json.get("mp3_url"):
            import requests as req
            mp3_url = request.json["mp3_url"]
            resp = req.get(mp3_url, timeout=120)
            resp.raise_for_status()
            mp3_filename = mp3_url.split("/")[-1].split("?")[0] or "input.mp3"
            if not mp3_filename.endswith(".mp3"):
                mp3_filename += ".mp3"
            tmp_dir = tempfile.mkdtemp(prefix=f"job_{job_id}_")
            mp3_path = os.path.join(tmp_dir, mp3_filename)
            with open(mp3_path, "wb") as f:
                f.write(resp.content)
        else:
            return jsonify({"error": "No MP3 provided."}), 400

        mp4_name = os.path.splitext(mp3_filename)[0] + ".mp4"
        jobs[job_id] = {"status": "processing", "mp4_path": None, "error": None, "mp4_name": mp4_name, "tmp_dir": tmp_dir}
        
        thread = threading.Thread(target=run_job, args=(job_id, mp3_path, tmp_dir))
        thread.daemon = True
        thread.start()

        return jsonify({"job_id": job_id, "status": "processing"}), 202
    except Exception as e:
        logger.exception(f"[{job_id}] Error")
        return jsonify({"error": str(e)}), 500


@app.route("/status/<job_id>", methods=["GET"])
def get_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"status": job["status"], "error": job.get("error")})


@app.route("/download/<job_id>", methods=["GET"])
def download(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] != "done":
        return jsonify({"error": "Not ready", "status": job["status"]}), 400
    return send_file(job["mp4_path"], mimetype="video/mp4", as_attachment=True, download_name=job["mp4_name"])


def run_job(job_id, mp3_path, tmp_dir):
    try:
        mp4_path = run_browser(job_id, mp3_path, tmp_dir)
        if mp4_path and os.path.exists(mp4_path):
            logger.info(f"[{job_id}] Done! MP4: {os.path.getsize(mp4_path)} bytes")
            jobs[job_id]["status"] = "done"
            jobs[job_id]["mp4_path"] = mp4_path
        else:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = "No MP4 generated"
    except Exception as e:
        logger.exception(f"[{job_id}] Error")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)


def run_browser(job_id, mp3_path, tmp_dir):
    from playwright.sync_api import sync_playwright
    logger.info(f"[{job_id}] Starting browser...")
    dl_dir = os.path.join(tmp_dir, "downloads")
    os.makedirs(dl_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage","--disable-gpu","--single-process"])
        ctx = browser.new_context(accept_downloads=True, viewport={"width":1280,"height":720})
        page = ctx.new_page()
        try:
            logger.info(f"[{job_id}] Opening website...")
            page.goto(CONVERTER_URL, wait_until="networkidle", timeout=60_000)
            page.wait_for_timeout(3000)
            logger.info(f"[{job_id}] Page loaded")

            fi = page.query_selector('input[type="file"]')
            if fi:
                fi.set_input_files(mp3_path)
            else:
                with page.expect_file_chooser(timeout=10_000) as fc:
                    page.get_by_text("Select MP3 File").click()
                fc.value.set_files(mp3_path)
            logger.info(f"[{job_id}] MP3 uploaded")
            page.wait_for_timeout(1500)

            page.get_by_text("Start Magic").click()
            logger.info(f"[{job_id}] Started, polling...")

            deadline = time.time() + (TIMEOUT_MS / 1000)
            dl_btn = None
            while time.time() < deadline:
                for sel in ['button:has-text("Download Video")','a:has-text("Download Video")','button:has-text("Download")','a:has-text("Download")']:
                    dl_btn = page.query_selector(sel)
                    if dl_btn:
                        break
                if dl_btn:
                    logger.info(f"[{job_id}] Download button found!")
                    break
                page.wait_for_timeout(3000)

            if not dl_btn:
                page.screenshot(path=os.path.join(tmp_dir, "timeout.png"))
                raise TimeoutError("Download button never appeared")

            page.wait_for_timeout(2000)
            mp4 = None

            try:
                with page.expect_download(timeout=60_000) as di:
                    dl_btn.click()
                d = di.value
                mp4 = os.path.join(dl_dir, d.suggested_filename or "output.mp4")
                d.save_as(mp4)
                logger.info(f"[{job_id}] Downloaded: {mp4}")
            except Exception as e1:
                logger.warning(f"[{job_id}] Direct dl failed: {e1}")
                try:
                    link = page.query_selector('a[download]') or page.query_selector('a:has-text("Download")')
                    if link:
                        href = link.get_attribute("href")
                        if href and (href.startswith("blob:") or href.startswith("data:")):
                            b64 = page.evaluate("async(u)=>{try{const r=await fetch(u);const b=await r.blob();return await new Promise(v=>{const x=new FileReader();x.onloadend=()=>v(x.result.split(',')[1]);x.readAsDataURL(b)})}catch(e){return null}}", href)
                            if b64:
                                mp4 = os.path.join(dl_dir, "output.mp4")
                                with open(mp4, "wb") as f:
                                    f.write(base64.b64decode(b64))
                                logger.info(f"[{job_id}] Downloaded via blob")
                        elif href and href.startswith("http"):
                            import requests as req
                            r = req.get(href, timeout=120)
                            mp4 = os.path.join(dl_dir, "output.mp4")
                            with open(mp4, "wb") as f:
                                f.write(r.content)
                except Exception as e2:
                    logger.error(f"[{job_id}] Blob fail: {e2}")

            if not mp4 or not os.path.exists(mp4):
                files = glob.glob(os.path.join(dl_dir, "*"))
                if files:
                    mp4 = files[0]
            return mp4
        except Exception as e:
            try:
                page.screenshot(path=os.path.join(tmp_dir, "error.png"))
            except:
                pass
            raise e
        finally:
            browser.close()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
