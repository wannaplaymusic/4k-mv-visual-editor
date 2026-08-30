import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-web-security --disable-gpu --disable-gpu-rasterization"

import sys
import json
import shutil
import datetime

from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtCore import QEventLoop, QTimer, QUrl

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_VISUALS_DIR = os.path.join(WORKSPACE_DIR, "custom_visuals")
ABNORMAL_BACKUP_DIR = os.path.join(CUSTOM_VISUALS_DIR, "abnormal_backup")
REVERIFY_REPORT_FILE = os.path.join(WORKSPACE_DIR, "reverify_report.json")


class DiagnosticPage(QWebEnginePage):
    """Custom page to intercept JavaScript console errors and exceptions."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.js_errors = []

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        msg_lower = message.lower()
        ignored_patterns = [
            "failed to fetch", "audiocontext", "cors", "[mock]", "[loadingwatchdog]",
            "opentype", ".ttf", ".otf", "width or height of 0", "[preloadguard]",
            "net::err", "mime type"
        ]
        if any(p in msg_lower for p in ignored_patterns):
            return

        # Intercept error levels
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel or "uncaught" in msg_lower:
            self.js_errors.append({
                "level": level.name,
                "line": line_number,
                "source": source_id,
                "message": message
            })


def make_reverify_html(code: str, custom_css: str = "", custom_html: str = "") -> str:
    is_module = "import " in code or "export " in code
    script_tag = f'<script type="module">\n{code}\n</script>' if is_module else f'<script>\n{code}\n</script>'
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ margin: 0; overflow: hidden; background: #000; }}
    canvas {{ display: block !important; width: 100vw !important; height: 100vh !important; }}
    {custom_css}
  </style>
  <script>
    window.onerror = function(msg, url, line) {{
      console.error("WindowError Line " + line + ": " + msg);
      return true;
    }};
    window.addEventListener('unhandledrejection', function(event) {{
      const reason = event.reason ? (event.reason.message || String(event.reason)) : "";
      console.error("Promise Rejected: " + reason);
    }});
  </script>
  <script src="custom_visuals/libs/p5.min.js"></script>
  <script src="custom_visuals/libs/p5.sound.min.js"></script>
  <script src="custom_visuals/libs/p5.func.min.js"></script>
  <script src="custom_visuals/libs/gsap.min.js"></script>
  <script src="custom_visuals/libs/p5.flex.min.js"></script>
  <script src="custom_visuals/libs/rampensau.js"></script>
  <script src="custom_visuals/libs/chroma.min.js"></script>
  {custom_html}
</head>
<body>
  {script_tag}
</body>
</html>"""


def wait_for_load(web_view, timeout_ms=3000):
    """Blocks execution locally until loadFinished fires or times out."""
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)

    loaded_success = False

    def on_load_finished(ok):
        nonlocal loaded_success
        loaded_success = ok
        if loop.isRunning():
            loop.quit()

    def on_timeout():
        if loop.isRunning():
            loop.quit()

    web_view.loadFinished.connect(on_load_finished)
    timer.timeout.connect(on_timeout)

    timer.start(timeout_ms)
    loop.exec()

    # Disconnect signals to avoid memory leaks across iterations
    try:
        web_view.loadFinished.disconnect(on_load_finished)
    except Exception:
        pass

    return loaded_success


def main():
    app = QApplication(sys.argv)

    if not os.path.exists(CUSTOM_VISUALS_DIR):
        print(f"❌ Target dir {CUSTOM_VISUALS_DIR} does not exist!")
        return

    os.makedirs(ABNORMAL_BACKUP_DIR, exist_ok=True)
    os.makedirs(os.path.join(ABNORMAL_BACKUP_DIR, "thumbnails"), exist_ok=True)

    json_files = [f for f in os.listdir(CUSTOM_VISUALS_DIR) if f.endswith(".json") and f != "modules_index.json"]
    json_files.sort()

    total_files = len(json_files)
    print(f"🚀 Re-Verifying {total_files} active modules in custom_visuals...")

    passed_count = 0
    failed_count = 0
    report_details = []

    web_view = QWebEngineView()
    web_view.resize(1280, 720)
    settings = web_view.settings()
    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
    settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)

    temp_html_path = os.path.join(WORKSPACE_DIR, "_temp_reverify.html")

    for idx, fname in enumerate(json_files):
        file_path = os.path.join(CUSTOM_VISUALS_DIR, fname)
        name = fname[:-5]
        page = DiagnosticPage(web_view)
        web_view.setPage(page)

        is_valid = True
        error_reasons = []

        # 1. Parse JSON structure
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            is_valid = False
            error_reasons.append(f"JSON Parse Error: {str(e)}")
            data = None

        # 2. Render HTML in WebEngine
        if is_valid and data:
            if "html" in data and data["html"].strip():
                html_content = data["html"]
            elif "content" in data and data["content"].strip():
                html_content = data["content"]
            elif "code" in data and data["code"].strip():
                html_content = make_reverify_html(data.get("code", ""), data.get("custom_css", ""), data.get("custom_html", ""))
            else:
                html_content = ""

            if not html_content.strip():
                is_valid = False
                error_reasons.append("Empty or missing code/HTML content")
            else:
                with open(temp_html_path, "w", encoding="utf-8") as tf:
                    tf.write(html_content)

                web_view.setUrl(QUrl.fromLocalFile(temp_html_path))
                loaded_ok = wait_for_load(web_view, timeout_ms=2500)

                if not loaded_ok:
                    is_valid = False
                    error_reasons.append("Page failed to load or timed out")

                critical_js_errors = [
                    err for err in page.js_errors
                    if "ErrorMessage" in err["level"] or "uncaught" in err["message"].lower()
                ]
                if critical_js_errors:
                    is_valid = False
                    error_reasons.extend([e["message"] for e in critical_js_errors])

        # 3. Process outcome
        if is_valid:
            passed_count += 1
            report_details.append({
                "file": fname,
                "status": "PASSED"
            })
        else:
            failed_count += 1
            report_details.append({
                "file": fname,
                "status": "QUARANTINED",
                "errors": error_reasons
            })
            # Move problematic file and thumbnail to backup
            dest_path = os.path.join(ABNORMAL_BACKUP_DIR, fname)
            try:
                if os.path.exists(file_path):
                    shutil.move(file_path, dest_path)
            except Exception:
                pass

            src_thumb = os.path.join(CUSTOM_VISUALS_DIR, "thumbnails", f"{name}.jpg")
            dest_thumb = os.path.join(ABNORMAL_BACKUP_DIR, "thumbnails", f"{name}.jpg")
            if os.path.exists(src_thumb):
                try:
                    shutil.move(src_thumb, dest_thumb)
                except Exception:
                    pass

        page.deleteLater()

        if (idx + 1) % 50 == 0 or (idx + 1) == total_files:
            print(f"[{idx+1}/{total_files}] Verified: Passed: {passed_count}, Quarantined: {failed_count}")

    if os.path.exists(temp_html_path):
        try:
            os.remove(temp_html_path)
        except Exception:
            pass

    # 4. Save reverification report
    final_report = {
        "timestamp": datetime.datetime.now().isoformat(),
        "total_checked": total_files,
        "passed": passed_count,
        "quarantined": failed_count,
        "results": report_details
    }

    with open(REVERIFY_REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_report, f, indent=2, ensure_ascii=False)

    print(f"🎉 Re-Verification Complete! Report written to {REVERIFY_REPORT_FILE}")


if __name__ == "__main__":
    main()
