"""Teacher UI for local and hosted testing; secrets stay on the server."""
import argparse
import io
import json
import os
import subprocess
import sys
import threading
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
CATALOG = {
    "python": {"label": "Python", "subject": "파이썬", "topics": ["변수", "조건문", "반복문", "함수", "리스트", "딕셔너리", "문자열"]},
    "pythonlib": {"label": "Python 라이브러리", "subject": "파이썬 라이브러리", "topics": ["numpy", "pandas"]},
}
LEVELS = ("쉬움", "보통", "어려움")


def origin_allowed(origin, host):
    if not origin:
        return True
    parsed = urlsplit(origin)
    return (parsed.scheme in ("http", "https") and parsed.netloc.lower() == host.lower()
            and not parsed.username and parsed.path in ("", "/")
            and not parsed.query and not parsed.fragment)


def validate_selection(data):
    if not isinstance(data, dict):
        raise ValueError("선택 내용을 확인하세요.")
    category, topic, counts = data.get("category"), data.get("topic"), data.get("counts")
    if not isinstance(category, str) or category not in CATALOG:
        raise ValueError("대분류를 선택하세요.")
    if topic not in CATALOG[category]["topics"]:
        raise ValueError("대분류에 맞는 소분류를 선택하세요.")
    if not isinstance(counts, dict) or set(counts) != set(LEVELS):
        raise ValueError("난이도별 문항 수를 선택하세요.")
    if any(type(n) is not int or not 0 <= n <= 10 for n in counts.values()) or not 1 <= sum(counts.values()) <= 10:
        raise ValueError("총 문항 수는 1~10개로 선택하세요.")
    generate_csv = data.get("generate_csv", topic == "pandas")
    if type(generate_csv) is not bool:
        raise ValueError("CSV 생성 여부를 선택하세요.")
    if category != "pythonlib" and generate_csv:
        raise ValueError("CSV 생성은 Python 라이브러리에서 선택하세요.")
    return category, topic, counts


def generation_command(data, output, demo=False):
    category, topic, counts = validate_selection(data)
    generate_csv = data.get("generate_csv", topic == "pandas")
    command = [sys.executable, "-B", str(ROOT / "main.py"), "--subject", CATALOG[category]["subject"],
               "--topic", topic, "--difficulty-counts", ",".join(f"{level}:{counts[level]}" for level in LEVELS if counts[level]),
               "--type", "data" if generate_csv else "general", "--output", str(output)]
    if category == "pythonlib" and not generate_csv:
        command.extend(["--constraints", "문제당 20분 이내. 외부 CSV 파일을 사용하지 않고 필요한 입력 데이터를 문제에 직접 제공."])
    if demo:
        command.append("--demo")
    return command


class JobStore:
    def __init__(self, demo=False, output_root=None):
        self.demo = demo
        self.output_root = Path(output_root or os.getenv("OUTPUT_DIR") or ROOT / "outputs")
        self.jobs = {}
        self.lock = threading.RLock()

    def create(self, selection):
        validate_selection(selection)
        selection = dict(selection, generate_csv=selection.get("generate_csv", selection["topic"] == "pandas"))
        with self.lock:
            if any(job["status"] == "running" for job in self.jobs.values()):
                raise RuntimeError("다른 문제를 생성하고 있습니다. 완료 후 다시 시도하세요.")
            identifier = uuid.uuid4().hex
            job = {"id": identifier, "status": "running", "message": "생성을 준비하고 있습니다.",
                   "selection": selection, "questions": [], "errors": [], "review": None,
                   "output": str(self.output_root / f"web_{identifier}"), "run": None}
            self.jobs[identifier] = job
        threading.Thread(target=self.run, args=(identifier,), daemon=True).start()
        return identifier

    def refresh(self, job):
        output = Path(job["output"])
        runs = sorted(output.glob("*/run_summary.json"))
        folders = sorted(output.glob("*/problem_*/instructor/problem.json"))
        questions = []
        for path in folders:
            try:
                question = json.loads(path.read_text(encoding="utf-8"))
                folder = path.parent.parent
                run = folder.parent
                question["number"] = int(folder.name.split("_")[-1])
                question["validation"] = json.loads((path.parent / "validation.json").read_text(encoding="utf-8"))
                csv_path = folder / "student" / "data.csv"
                question["csv_file"] = str(csv_path.relative_to(run)) if csv_path.exists() else None
                questions.append(question)
                job["run"] = str(run)
            except (OSError, ValueError, KeyError):
                continue  # A file may still be being written; retry on the next update.
        job["questions"] = questions
        if runs:
            try:
                summary = json.loads(runs[-1].read_text(encoding="utf-8"))
                job["errors"] = summary.get("errors", [])
                job["run"] = str(runs[-1].parent)
            except (OSError, ValueError):
                pass
        if job["run"] and (Path(job["run"]) / "review_all.ipynb").exists():
            job["review"] = "review_all.ipynb"

    def run(self, identifier):
        job = self.jobs[identifier]
        try:
            command = generation_command(job["selection"], Path(job["output"]), self.demo)
            with subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, encoding="utf-8", bufsize=1) as process:
                for line in process.stdout:
                    with self.lock:
                        # Only expose known progress messages, never raw SDK errors or environment data.
                        if line.startswith("["):
                            job["message"] = line.strip()
                        self.refresh(job)
                code = process.wait()
            with self.lock:
                self.refresh(job)
                job["status"] = "completed" if code == 0 else "partial" if job["questions"] else "failed"
                job["message"] = ("문제 생성이 완료되었습니다." if code == 0 else
                                  "일부 문항 생성에 실패했습니다." if job["questions"] else
                                  "문제 생성에 실패했습니다. API 키·모델·결제 상태를 확인하세요.")
        except Exception as exc:
            with self.lock:
                job["status"] = "failed"
                job["message"] = f"문제 생성 실행에 실패했습니다 ({type(exc).__name__})."

    def snapshot(self, identifier):
        with self.lock:
            job = self.jobs.get(identifier)
            if job is None:
                return None
            return json.loads(json.dumps({key: value for key, value in job.items() if key not in ("output", "run")}))

    def download(self, identifier, filename):
        with self.lock:
            job = self.jobs.get(identifier)
            if not job or not job["run"]:
                raise FileNotFoundError
            run = Path(job["run"]).resolve()
            target = (run / filename).resolve()
            if not target.is_relative_to(run) or target.suffix not in (".csv", ".ipynb") or not target.is_file():
                raise FileNotFoundError
            return target

    def archive(self, identifier):
        with self.lock:
            job = self.jobs.get(identifier)
            if not job or not job["run"] or job["status"] == "running":
                raise FileNotFoundError
            run = Path(job["run"])
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(run.rglob("*")):
                    if path.is_file() and not path.is_symlink():
                        archive.write(path, path.relative_to(run))
            return buffer.getvalue()


def handler(store):
    class Handler(BaseHTTPRequestHandler):
        def send_data(self, code, body, content_type="application/json; charset=utf-8", filename=None):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlsplit(self.path)
            path = parsed.path
            if path == "/api/health":
                return self.send_data(200, {"status": "ok"})
            if path in ("/", "/app.js", "/style.css"):
                name = "index.html" if path == "/" else path[1:]
                kind = {"index.html": "text/html", "app.js": "text/javascript", "style.css": "text/css"}[name]
                return self.send_data(200, (ROOT / "web" / name).read_bytes(), kind + "; charset=utf-8")
            if path == "/api/catalog":
                return self.send_data(200, {"categories": CATALOG, "levels": LEVELS,
                    "demo": store.demo, "ready": store.demo or bool(os.getenv("OPENAI_API_KEY"))})
            parts = path.strip("/").split("/")
            if len(parts) in (3, 4) and parts[:2] == ["api", "jobs"]:
                identifier = parts[2]
                if len(parts) == 3:
                    snapshot = store.snapshot(identifier)
                    return self.send_data(200 if snapshot else 404, snapshot or {"error": "생성 기록을 찾을 수 없습니다."})
                try:
                    if parts[3] == "download":
                        target = store.download(identifier, parse_qs(parsed.query).get("file", [""])[0])
                        return self.send_data(200, target.read_bytes(), "application/octet-stream", target.name)
                    if parts[3] == "archive":
                        return self.send_data(200, store.archive(identifier), "application/zip", "questions.zip")
                except (OSError, ValueError):
                    pass
            return self.send_data(404, {"error": "파일 또는 생성 기록을 찾을 수 없습니다."})

        def do_POST(self):
            if self.path != "/api/jobs":
                return self.send_data(404, {"error": "없는 요청입니다."})
            origin = self.headers.get("Origin")
            if not origin_allowed(origin, self.headers.get("Host", "")):
                return self.send_data(403, {"error": "현재 화면에서 다시 요청하세요."})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 4096:
                    raise ValueError("요청 크기를 확인하세요.")
                data = json.loads(self.rfile.read(size))
                validate_selection(data)
                if not store.demo and not os.getenv("OPENAI_API_KEY"):
                    return self.send_data(400, {"error": "서버 환경변수 또는 .env에 OPENAI_API_KEY를 설정하고 서버를 다시 실행하세요."})
                identifier = store.create(data)
                return self.send_data(202, {"id": identifier})
            except (ValueError, TypeError):
                return self.send_data(400, {"error": "분류와 난이도별 개수를 확인하세요. 총 1~10문항입니다."})
            except RuntimeError as exc:
                return self.send_data(409, {"error": str(exc)})

        def log_message(self, format, *args):
            pass
    return Handler


def server_options(argv=None):
    parser = argparse.ArgumentParser(description="강사용 문제 생성 웹 화면")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=os.getenv("PORT", "8000"))
    parser.add_argument("--demo", action="store_true", help="API 없이 고정 예제로 화면 테스트")
    return parser.parse_args(argv)


def main():
    load_dotenv(ROOT / ".env")
    args = server_options()
    server = ThreadingHTTPServer((args.host, args.port), handler(JobStore(args.demo)))
    print(f"문제 생성 서버: http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
