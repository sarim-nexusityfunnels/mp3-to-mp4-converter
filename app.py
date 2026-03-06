"""
MP3 to MP4 Converter Service
Automates the AI Music Video Generator website using Playwright.
Deploy on Render.com, call from Make.com.
"""

import os
import uuid
import time
import logging
import tempfile
import glob
import base64
import shutil
from flask import Flask, request, jsonify, send_file
from playwright.sync_api import sync_playwright

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONVERTER_URL = "https://mp3-to-youtube-automator-113913926974.us-west1.run.app/"
TIMEOUT_MS = 300_000  # 5 min max wait


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "service": "MP3 to MP4 Converter",
        "status": "running",
        "usage": "POST /convert with 'file' (multipart) or 'mp3_url' (JSON)"
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/convert", methods=["POST"])
def convert():
    """
    Convert MP3 to MP4.
    
    Option A: multipart/form-data with field 'file' 
    Option B: JSON with 'mp3_url'
    
    Returns: MP4 file download
    """
    job_id = str(uuid.uuid4())[:8]
    logger.info(f"[{job_id}] New conversion request")

    tmp_dir = tempfile.mkdtemp(prefix=f"job_{job_id}_")

    try:
        # --- Get the MP3 ---
        if "file" in request.files:
            mp3_file = request.files["file"]
            mp3_filename = mp3_file.filename or "input.mp3"
            mp3_path = os.path.join(tmp_dir, mp3_filename)
            mp3_file.save(mp3_path)
            logger.info(f"[{job_id}] Got MP3 upload: {mp3_filename}")

        elif request.is_json and request.json.get("mp3_url"):
            import requests as req
            mp3_url = request.json["mp3_url"]
            logger.info(f"[{job_id}] Downloading MP3 from: {mp3_url}")
            resp = req.get(mp3_url, timeout=120)
            resp.raise_for_status()
            mp3_filename = mp3_url.split("/")[-1].split("?")[0] or "input.mp3"
            if not mp3_filename.endswith(".mp3"):
                mp3_filename += ".mp3"
            mp3_path = os.path.join(tmp_dir, mp3_filename)
            with open(mp3_path, "wb") as f:
                f.write(resp.content)
            logger.info(f"[{job_id}] Downloaded: {len(resp.content)} bytes")

        else:
            return jsonify({
                "error": "No MP3 provided. Send 'file' in form-data or 'mp3_url' in JSON."
            }), 400

        # --- Run Playwright automation ---
        mp4_path = run_browser_conversion(job_id, mp3_path, tmp_dir)

        if mp4_path and os.path.exists(mp4_path):
            size = os.path.getsize(mp4_path)
            logger.info(f"[{job_id}] Done! MP4: {size} bytes")
            mp4_name = os.path.splitext(os.path.basename(mp3_path))[0] + ".mp4"
            return send_file(
                mp4_path,
                mimetype="video/mp4",
                as_attachment=True,
                download_name=mp4_name
            )
        else:
            return jsonify({"error": "Conversion failed. No MP4 generated."}), 500

    except Exception as e:
        logger.exception(f"[{job_id}] Error")
        return jsonify({"error": str(e)}), 500

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def run_browser_conversion(job_id: str, mp3_path: str, tmp_dir: str):
    """
    Use Playwright to:
    1. Open the converter website
    2. Upload MP3
    3. Click "Start Magic"
    4. Wait for "Download Video" 
    5. Download the MP4
    """
    logger.info(f"[{job_id}] Starting browser automation...")

    download_dir = os.path.join(tmp_dir, "downloads")
    os.makedirs(download_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process",
            ]
        )

        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()

        try:
            # 1. Go to the website
            logger.info(f"[{job_id}] Opening website...")
            page.goto(CONVERTER_URL, wait_until="networkidle", timeout=60_000)
            page.wait_for_timeout(3000)
            logger.info(f"[{job_id}] Page loaded")

            # 2. Upload MP3
            file_input = page.query_selector('input[type="file"]')
            if file_input:
                logger.info(f"[{job_id}] Found file input directly")
                file_input.set_input_files(mp3_path)
            else:
                logger.info(f"[{job_id}] Using file chooser dialog...")
                with page.expect_file_chooser(timeout=10_000) as fc_info:
                    page.get_by_text("Select MP3 File").click()
                file_chooser = fc_info.value
                file_chooser.set_files(mp3_path)

            logger.info(f"[{job_id}] MP3 uploaded")
            page.wait_for_timeout(1500)

            # 3. Click "Start Magic"
            logger.info(f"[{job_id}] Clicking Start Magic...")
            start_btn = page.get_by_text("Start Magic")
            start_btn.click()
            logger.info(f"[{job_id}] Conversion started, waiting...")

            # 4. Wait for completion — "Download Video" button appears
            # Use a polling approach since the selector syntax varies
            logger.info(f"[{job_id}] Polling for Download Video button...")
            deadline = time.time() + (TIMEOUT_MS / 1000)
            download_ready = False

            while time.time() < deadline:
                # Check for the download button
                dl_btn = page.query_selector('button:has-text("Download Video")')
                if not dl_btn:
                    dl_btn = page.query_selector('a:has-text("Download Video")')
                if not dl_btn:
                    dl_btn = page.query_selector('text="Download Video"')
                if not dl_btn:
                    # Also check for "Done" or "Ready" text
                    done_text = page.query_selector('text="Done"')
                    ready_text = page.query_selector('text="Ready to download"')
                    if done_text or ready_text:
                        dl_btn = page.query_selector('button:has-text("Download")')
                        if not dl_btn:
                            dl_btn = page.query_selector('a:has-text("Download")')

                if dl_btn:
                    download_ready = True
                    logger.info(f"[{job_id}] Download button found!")
                    break

                page.wait_for_timeout(3000)  # Check every 3 seconds

            if not download_ready:
                # Take debug screenshot
                page.screenshot(path=os.path.join(tmp_dir, "timeout_screenshot.png"))
                raise TimeoutError("Conversion timed out - Download button never appeared")

            page.wait_for_timeout(2000)

            # 5. Download the MP4
            mp4_path = None

            # Method 1: Playwright download handler
            try:
                logger.info(f"[{job_id}] Attempting download via click...")
                with page.expect_download(timeout=60_000) as dl_info:
                    dl_btn.click()
                download = dl_info.value
                mp4_path = os.path.join(download_dir, download.suggested_filename or "output.mp4")
                download.save_as(mp4_path)
                logger.info(f"[{job_id}] Downloaded via browser: {mp4_path}")
            except Exception as e1:
                logger.warning(f"[{job_id}] Direct download failed: {e1}")

                # Method 2: Extract blob/data URL from the download link
                try:
                    link = page.query_selector('a[download]')
                    if not link:
                        link = page.query_selector('a:has-text("Download")')
                    if link:
                        href = link.get_attribute("href")
                        logger.info(f"[{job_id}] Found link href: {str(href)[:80]}...")

                        if href and (href.startswith("blob:") or href.startswith("data:")):
                            mp4_b64 = page.evaluate("""
                                async (url) => {
                                    try {
                                        const r = await fetch(url);
                                        const blob = await r.blob();
                                        return await new Promise((resolve) => {
                                            const reader = new FileReader();
                                            reader.onloadend = () => resolve(reader.result.split(',')[1]);
                                            reader.readAsDataURL(blob);
                                        });
                                    } catch(e) {
                                        return null;
                                    }
                                }
                            """, href)
                            if mp4_b64:
                                mp4_path = os.path.join(download_dir, "output.mp4")
                                with open(mp4_path, "wb") as f:
                                    f.write(base64.b64decode(mp4_b64))
                                logger.info(f"[{job_id}] Downloaded via blob extraction")

                        elif href and href.startswith("http"):
                            import requests as req
                            resp = req.get(href, timeout=120)
                            mp4_path = os.path.join(download_dir, "output.mp4")
                            with open(mp4_path, "wb") as f:
                                f.write(resp.content)
                            logger.info(f"[{job_id}] Downloaded via HTTP URL")
                except Exception as e2:
                    logger.error(f"[{job_id}] Blob extraction failed: {e2}")

                # Method 3: Try clicking the button again with JS
                if not mp4_path or not os.path.exists(mp4_path):
                    try:
                        logger.info(f"[{job_id}] Trying JS click method...")
                        page.evaluate("""
                            () => {
                                const btns = [...document.querySelectorAll('button, a')];
                                const dlBtn = btns.find(b => b.textContent.includes('Download'));
                                if (dlBtn) dlBtn.click();
                            }
                        """)
                        page.wait_for_timeout(5000)
                        # Check download dir
                        files = glob.glob(os.path.join(download_dir, "*"))
                        if files:
                            mp4_path = files[0]
                            logger.info(f"[{job_id}] Found file after JS click: {mp4_path}")
                    except Exception as e3:
                        logger.error(f"[{job_id}] JS click also failed: {e3}")

            return mp4_path

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
