#!/usr/bin/env python3
"""
Studio desktop app: a local page in your browser.

    python3 studio/app.py            (or double-click Studio.command / Studio.bat)

Type a title → Claude writes the story → review and edit it → Make video →
watch and download the MP4, thumbnail and description. Everything runs on
this computer; scripts are written through your own Claude Code login.
"""
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import catalog  # noqa: E402

CONF_DIR = os.path.join(os.path.expanduser("~"), ".studio")
CONF = os.path.join(CONF_DIR, "settings.json")
STORIES = os.path.join(HERE, "stories")
PORT = int(os.environ.get("STUDIO_PORT", "8765"))

PRESETS = {
    "preview": {"fps": 12, "scale": 0.5, "samples": 16},
    "final": {"fps": 24, "scale": 1.0, "samples": 48},
}


def load_settings():
    s = {"blender": "", "models": os.path.join(CONF_DIR, "models"), "output": os.path.join(HERE, "output"),
         "engine": "BLENDER_EEVEE_NEXT", "model": ""}
    try:
        s.update(json.load(open(CONF)))
    except (OSError, ValueError):
        pass
    return s


def save_settings(s):
    os.makedirs(CONF_DIR, exist_ok=True)
    json.dump(s, open(CONF, "w"), indent=1)


class Job:
    """One background job at a time (writing or rendering), with a log."""

    def __init__(self):
        self.lock = threading.Lock()
        self.kind, self.story, self.log, self.running, self.error = None, None, [], False, None

    def start(self, kind, story, fn):
        with self.lock:
            if self.running:
                return False
            self.kind, self.story, self.log, self.running, self.error = kind, story, [], True, None

        def run():
            try:
                fn(self)
            except BaseException as e:  # report anything to the page
                self.error = str(e)
                self.log.append("ERROR: " + str(e))
            finally:
                self.running = False

        threading.Thread(target=run, daemon=True).start()
        return True

    def stream(self, cmd):
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in p.stdout:
            line = line.rstrip()
            if line:
                self.log.append(line)
                del self.log[:-400]
        if p.wait() != 0:
            raise RuntimeError(f"{os.path.basename(cmd[1])} failed")


JOB = Job()


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40] or "story"


def list_stories(settings):
    out = []
    if not os.path.isdir(STORIES):
        return out
    for d in sorted(os.listdir(STORIES)):
        p = os.path.join(STORIES, d, "story.json")
        if not os.path.exists(p):
            continue
        try:
            s = json.load(open(p, encoding="utf-8"))
        except ValueError:
            continue
        vid = os.path.join(settings["output"], d, d + ".mp4")
        out.append({"id": d, "title": s.get("title", d), "title_en": s.get("title_en", ""),
                    "scenes": len(s.get("scenes", [])), "video": os.path.exists(vid),
                    "updated": os.path.getmtime(p)})
    return sorted(out, key=lambda x: -x["updated"])


def next_id(title):
    n = 1 + max([int(d[:3]) for d in os.listdir(STORIES) if d[:3].isdigit()] or [0])
    return f"{n:03d}-{slug(title)}"


def description(story):
    lines = [story.get("title", ""), "", story.get("title_en", ""), "",
             "#hindistory #horrorstory #animation #shorts"]
    return "\n".join(lines)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u = urlparse(self.path)
        st = load_settings()
        if u.path == "/":
            return self.send(200, PAGE, "text/html; charset=utf-8")
        if u.path == "/api/state":
            return self.send(200, {"settings": st, "stories": list_stories(st),
                                   "job": {"kind": JOB.kind, "story": JOB.story, "running": JOB.running,
                                           "error": JOB.error, "log": JOB.log[-60:]},
                                   "checks": checks(st)})
        m = re.match(r"^/api/story/([\w\-]+)$", u.path)
        if m:
            p = os.path.join(STORIES, m.group(1), "story.json")
            if not os.path.exists(p):
                return self.send(404, {"error": "no such story"})
            s = json.load(open(p, encoding="utf-8"))
            return self.send(200, {"story": s, "description": description(s)})
        m = re.match(r"^/out/([\w\-]+)/([\w\-.]+)$", u.path)
        if m:
            p = os.path.join(st["output"], m.group(1), m.group(2))
            if not os.path.isfile(p):
                return self.send(404, "not found", "text/plain")
            data = open(p, "rb").read()
            return self.send(200, data, mimetypes.guess_type(p)[0] or "application/octet-stream")
        return self.send(404, "not found", "text/plain")

    def do_POST(self):
        u = urlparse(self.path)
        st = load_settings()
        if u.path == "/api/settings":
            st.update({k: v for k, v in self.body().items() if k in st})
            save_settings(st)
            return self.send(200, {"ok": True})
        if u.path == "/api/write":
            b = self.body()
            title = b.get("title", "").strip()
            if not title:
                return self.send(400, {"error": "type a title first"})
            sid = next_id(b.get("title_en") or title)

            def work(job):
                out = os.path.join(STORIES, sid, "story.json")
                cmd = [sys.executable, os.path.join(HERE, "writer.py"), title, "--out", out,
                       "--genre", b.get("genre", "horror"), "--length", str(b.get("length", 45)),
                       "--notes", b.get("notes", "")]
                if st.get("model"):
                    cmd += ["--model", st["model"]]
                job.log.append("Claude is writing the story…")
                job.stream(cmd)

            ok = JOB.start("write", sid, work)
            return self.send(200 if ok else 409, {"id": sid} if ok else {"error": "a job is already running"})
        m = re.match(r"^/api/story/([\w\-]+)$", u.path)
        if m:
            p = os.path.join(STORIES, m.group(1), "story.json")
            s = self.body().get("story")
            cast = json.load(open(os.path.join(HERE, "cast", "default.json"), encoding="utf-8"))
            errs = catalog.validate(s, cast)
            if errs:
                return self.send(400, {"error": "\n".join(errs)})
            json.dump(s, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            return self.send(200, {"ok": True})
        m = re.match(r"^/api/make/([\w\-]+)$", u.path)
        if m:
            sid = m.group(1)
            q = PRESETS.get(self.body().get("quality", "preview"), PRESETS["preview"])
            if not st["blender"] or not os.path.exists(st["blender"]):
                return self.send(400, {"error": "Set the Blender path in Settings first (run setup_studio.py)."})

            def work(job):
                env_models = st["models"]
                os.environ["STUDIO_VOICES"] = env_models
                job.stream([sys.executable, "-u", os.path.join(HERE, "make_short.py"),
                            os.path.join(STORIES, sid, "story.json"), "--blender", st["blender"],
                            "--out", os.path.join(st["output"], sid), "--engine", st["engine"],
                            "--fps", str(q["fps"]), "--scale", str(q["scale"]), "--samples", str(q["samples"])])

            ok = JOB.start("make", sid, work)
            return self.send(200 if ok else 409, {"ok": ok} if ok else {"error": "a job is already running"})
        return self.send(404, {"error": "unknown"})


def checks(st):
    import shutil
    return {
        "blender": bool(st["blender"]) and os.path.exists(st["blender"]),
        "voices": os.path.exists(os.path.join(st["models"], "kokoro-v1.0.onnx")),
        "claude": shutil.which("claude") is not None,
        "ffmpeg": shutil.which("ffmpeg") is not None,
    }


PAGE = ""


def main():
    global PAGE
    PAGE = open(os.path.join(HERE, "ui.html"), encoding="utf-8").read()
    os.makedirs(STORIES, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}/"
    print("Studio is running at", url, "(close this window to stop)")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
