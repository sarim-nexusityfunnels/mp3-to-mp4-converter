"""
MP3 to MP4 Converter — Memory Optimized for 512MB
"""

import os, uuid, time, logging, tempfile, glob, base64, shutil, threading
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONVERTER_URL = "https://mp3-to-youtube-automator-113913926974.us-west1.run.app/"
TIMEOUT_MS = 300_000
jobs = {}

@app.route("/", methods=["GET"])
def home():
    return '''<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>MP3 to MP4</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#0a0a0f;color:#e0e0e0;min-height:100vh;display:flex;align-items:center;justify-content:center}.c{max-width:500px;width:90%;text-align:center}h1{font-size:28px;margin-bottom:8px;color:#fff}.s{color:#666;font-size:14px;margin-bottom:32px}.dz{border:2px dashed #333;border-radius:16px;padding:48px 24px;cursor:pointer;transition:all .2s;background:#0f0f18}.dz:hover{border-color:#a78bfa;background:#13131f}.dt{font-size:16px;color:#888}.dt span{color:#a78bfa;text-decoration:underline}#fi{display:none}.fn{margin-top:16px;padding:10px 16px;background:#1a1a2e;border-radius:8px;font-size:13px;color:#a78bfa;display:none}.btn{margin-top:20px;padding:14px;background:#a78bfa;color:#000;border:none;border-radius:10px;font-size:16px;font-weight:700;cursor:pointer;display:none;width:100%}.btn:disabled{background:#333;color:#666;cursor:not-allowed}.st{margin-top:20px;padding:16px;border-radius:10px;font-size:14px;display:none}.st.l{display:block;background:#1a1a0e;border:1px solid #fbbf2433;color:#d4a017}.st.ok{display:block;background:#0e1a0e;border:1px solid #4ade8033;color:#4ade80}.st.er{display:block;background:#1a0e0e;border:1px solid #f8717133;color:#f87171}.dl{display:inline-block;margin-top:12px;padding:12px 24px;background:#4ade80;color:#000;border-radius:8px;text-decoration:none;font-weight:700}.sp{display:inline-block;width:18px;height:18px;border:2px solid #fbbf2444;border-top-color:#fbbf24;border-radius:50%;animation:spin .8s linear infinite;vertical-align:middle;margin-right:8px}@keyframes spin{to{transform:rotate(360deg)}}.lg{margin-top:12px;font-size:11px;color:#555;font-family:monospace}.n{margin-top:24px;font-size:11px;color:#444}</style></head><body><div class="c"><h1>MP3 to MP4</h1><p class="s">Upload an MP3 and get a music video with AI-generated art</p><div class="dz" id="dz" onclick="document.getElementById('fi').click()"><input type="file" id="fi" accept=".mp3,.m4a,audio/*"><p class="dt">Drag & drop your MP3 here<br>or <span>browse files</span></p></div><div class="fn" id="fn"></div><button class="btn" id="btn" onclick="go()">Convert to MP4</button><div class="st" id="st"></div><div class="lg" id="lg"></div><p class="n">Conversion takes 2-4 minutes</p></div><script>let F=null;const Z=id=>document.getElementById(id);['dragenter','dragover'].forEach(e=>Z('dz').addEventListener(e,v=>{v.preventDefault();Z('dz').style.borderColor='#a78bfa'}));['dragleave','drop'].forEach(e=>Z('dz').addEventListener(e,v=>{v.preventDefault();Z('dz').style.borderColor='#333'}));Z('dz').addEventListener('drop',v=>{if(v.dataTransfer.files.length)hf(v.dataTransfer.files[0])});Z('fi').addEventListener('change',v=>{if(v.target.files.length)hf(v.target.files[0])});function hf(f){F=f;Z('fn').textContent=f.name+' ('+(f.size/1048576).toFixed(1)+' MB)';Z('fn').style.display='block';Z('btn').style.display='block';Z('st').className='st';Z('st').style.display='none'}async function go(){if(!F)return;Z('btn').disabled=true;Z('btn').textContent='Converting...';Z('st').className='st l';Z('st').innerHTML='<span class="sp"></span> Uploading...';try{const fd=new FormData;fd.append('file',F);const r=await fetch('/convert',{method:'POST',body:fd});const d=await r.json();if(!r.ok||!d.job_id)throw new Error(d.error||'Failed');Z('st').innerHTML='<span class="sp"></span> Converting... 2-4 min';Z('lg').textContent='Job: '+d.job_id;const n=F.name.replace(/\\.[^.]+$/,'.mp4');let t=0;while(true){await new Promise(r=>setTimeout(r,5e3));t+=5;Z('lg').textContent='Checking... '+t+'s';const s=await(await fetch('/status/'+d.job_id)).json();if(s.status==='done'){Z('st').className='st ok';Z('st').innerHTML='Done!<br><a class="dl" href="/download/'+d.job_id+'" download="'+n+'">Download '+n+'</a>';break}if(s.status==='error')throw new Error(s.error||'Failed')}}catch(e){Z('st').className='st er';Z('st').textContent='Error: '+e.message}Z('btn').disabled=false;Z('btn').textContent='Convert to MP4'}</script></body></html>'''

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/convert", methods=["POST"])
def convert():
    jid = str(uuid.uuid4())[:8]
    logger.info(f"[{jid}] New request")
    try:
        if "file" in request.files:
            f = request.files["file"]
            name = f.filename or "input.mp3"
            tmp = tempfile.mkdtemp(prefix=f"j{jid}_")
            path = os.path.join(tmp, name)
            f.save(path)
        elif request.is_json and request.json.get("mp3_url"):
            import requests as req
            url = request.json["mp3_url"]
            r = req.get(url, timeout=120); r.raise_for_status()
            name = url.split("/")[-1].split("?")[0] or "input.mp3"
            tmp = tempfile.mkdtemp(prefix=f"j{jid}_")
            path = os.path.join(tmp, name)
            with open(path, "wb") as o: o.write(r.content)
        else:
            return jsonify({"error": "No file"}), 400
        jobs[jid] = {"status": "processing", "mp4_path": None, "error": None, "mp4_name": os.path.splitext(name)[0]+".mp4", "tmp": tmp}
        threading.Thread(target=run_job, args=(jid, path, tmp), daemon=True).start()
        return jsonify({"job_id": jid, "status": "processing"}), 202
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/status/<jid>")
def status(jid):
    j = jobs.get(jid)
    return jsonify({"error": "Not found"}) if not j else jsonify({"status": j["status"], "error": j.get("error")})

@app.route("/download/<jid>")
def download(jid):
    j = jobs.get(jid)
    if not j: return jsonify({"error": "Not found"}), 404
    if j["status"] != "done": return jsonify({"error": "Not ready"}), 400
    return send_file(j["mp4_path"], mimetype="video/mp4", as_attachment=True, download_name=j["mp4_name"])

def run_job(jid, mp3, tmp):
    try:
        mp4 = automate(jid, mp3, tmp)
        if mp4 and os.path.exists(mp4):
            logger.info(f"[{jid}] Done! {os.path.getsize(mp4)}b")
            jobs[jid]["status"] = "done"; jobs[jid]["mp4_path"] = mp4
        else:
            jobs[jid]["status"] = "error"; jobs[jid]["error"] = "No MP4 produced"
    except Exception as e:
        logger.exception(f"[{jid}] Fail")
        jobs[jid]["status"] = "error"; jobs[jid]["error"] = str(e)

def automate(jid, mp3, tmp):
    from playwright.sync_api import sync_playwright
    logger.info(f"[{jid}] Browser start...")
    dl_dir = os.path.join(tmp, "dl"); os.makedirs(dl_dir, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage",
            "--disable-gpu","--single-process","--no-zygote",
            "--disable-extensions","--disable-background-networking",
            "--disable-default-apps","--disable-sync","--disable-translate",
            "--disable-software-rasterizer","--disable-features=site-per-process",
            "--js-flags=--max-old-space-size=200","--renderer-process-limit=1",
            "--disable-accelerated-2d-canvas","--disable-canvas-aa",
            "--disable-2d-canvas-clip-aa","--disable-gl-drawing-for-tests",
            "--disable-composited-antialiasing","--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding","--disable-hang-monitor",
            "--disable-ipc-flooding-protection","--disable-component-update",
            "--disable-domain-reliability","--disable-features=AudioServiceOutOfProcess,TranslateUI",
            "--memory-pressure-off",
        ])
        ctx = browser.new_context(accept_downloads=True, viewport={"width":1280,"height":720})
        page = ctx.new_page()
        try:
            logger.info(f"[{jid}] Opening site...")
            page.goto(CONVERTER_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(2000)
            logger.info(f"[{jid}] Loaded")
            fi = page.query_selector('input[type="file"]')
            if fi: fi.set_input_files(mp3)
            else:
                with page.expect_file_chooser(timeout=10000) as fc: page.get_by_text("Select MP3 File").click()
                fc.value.set_files(mp3)
            logger.info(f"[{jid}] Uploaded")
            page.wait_for_timeout(1500)
            page.get_by_text("Start Magic").click()
            logger.info(f"[{jid}] Started, polling...")
            end = time.time() + TIMEOUT_MS/1000; btn = None
            while time.time() < end:
                for s in ['button:has-text("Download Video")','a:has-text("Download Video")','button:has-text("Download")','a:has-text("Download")']:
                    btn = page.query_selector(s)
                    if btn: break
                if btn: logger.info(f"[{jid}] Download ready!"); break
                page.wait_for_timeout(3000)
            if not btn:
                page.screenshot(path=os.path.join(tmp,"timeout.png"))
                raise TimeoutError("Download button not found")
            page.wait_for_timeout(2000); mp4 = None
            try:
                with page.expect_download(timeout=60000) as di: btn.click()
                d = di.value; mp4 = os.path.join(dl_dir, d.suggested_filename or "out.mp4"); d.save_as(mp4)
                logger.info(f"[{jid}] Got: {mp4}")
            except Exception as e1:
                logger.warning(f"[{jid}] Direct fail: {e1}")
                try:
                    a = page.query_selector('a[download]') or page.query_selector('a:has-text("Download")')
                    if a:
                        href = a.get_attribute("href")
                        if href and href.startswith(("blob:","data:")):
                            b64 = page.evaluate("async u=>{try{const r=await fetch(u),b=await r.blob();return await new Promise(v=>{const x=new FileReader;x.onloadend=()=>v(x.result.split(',')[1]);x.readAsDataURL(b)})}catch(e){return null}}",href)
                            if b64: mp4 = os.path.join(dl_dir,"out.mp4"); open(mp4,"wb").write(base64.b64decode(b64)); logger.info(f"[{jid}] Blob ok")
                        elif href and href.startswith("http"):
                            import requests as req; r = req.get(href,timeout=120); mp4 = os.path.join(dl_dir,"out.mp4"); open(mp4,"wb").write(r.content)
                except Exception as e2: logger.error(f"[{jid}] Blob fail: {e2}")
            if not mp4 or not os.path.exists(mp4):
                fs = glob.glob(os.path.join(dl_dir,"*"))
                if fs: mp4 = fs[0]
            return mp4
        except Exception as e:
            try: page.screenshot(path=os.path.join(tmp,"err.png"))
            except: pass
            raise
        finally: browser.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
