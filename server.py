#!/usr/bin/env python3
import argparse
import json
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


MAX_MESSAGES = 200


class ChatState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.messages = []
        self.next_id = 1

    def get_messages_after(self, last_id: int):
        with self.lock:
            return [m for m in self.messages if m["id"] > last_id]

    def add_message(self, author: str, text: str):
        now_ms = int(time.time() * 1000)
        with self.condition:
            msg = {
                "id": self.next_id,
                "author": author,
                "text": text,
                "timestamp": now_ms,
            }
            self.next_id += 1
            self.messages.append(msg)
            if len(self.messages) > MAX_MESSAGES:
                self.messages = self.messages[-MAX_MESSAGES:]
            self.condition.notify_all()
            return msg

    def wait_for_new_messages(self, last_id: int, timeout: float = 25.0):
        with self.condition:
            if any(m["id"] > last_id for m in self.messages):
                return [m for m in self.messages if m["id"] > last_id]
            self.condition.wait(timeout=timeout)
            return [m for m in self.messages if m["id"] > last_id]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chat en vivo sin dependencias")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host del servidor. 0.0.0.0 acepta conexiones externas.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Puerto HTTP.",
    )
    parser.add_argument(
        "--dir",
        default=".",
        help="Carpeta donde vive index.html.",
    )
    return parser.parse_args()


def build_handler(static_dir: Path, state: ChatState):
    class ChatHandler(BaseHTTPRequestHandler):
        def _send_json(self, payload, status=HTTPStatus.OK):
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return None
            if length <= 0:
                return None
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return None

        def _serve_index(self):
            index_path = static_dir / "index.html"
            if not index_path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "No existe index.html")
                return
            body = index_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path

            if path in ("/", "/index.html"):
                self._serve_index()
                return

            if path == "/health":
                self._send_json({"ok": True})
                return

            if path == "/messages":
                after = 0
                if parsed.query:
                    pairs = [p for p in parsed.query.split("&") if p]
                    for pair in pairs:
                        if pair.startswith("after="):
                            value = pair.split("=", 1)[1]
                            try:
                                after = max(0, int(value))
                            except ValueError:
                                after = 0
                self._send_json({"messages": state.get_messages_after(after)})
                return

            if path == "/events":
                after = 0
                if parsed.query:
                    pairs = [p for p in parsed.query.split("&") if p]
                    for pair in pairs:
                        if pair.startswith("after="):
                            value = pair.split("=", 1)[1]
                            try:
                                after = max(0, int(value))
                            except ValueError:
                                after = 0

                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()

                try:
                    while True:
                        new_messages = state.wait_for_new_messages(after, timeout=20.0)
                        payload = json.dumps({"messages": new_messages}, ensure_ascii=True)
                        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        if new_messages:
                            after = new_messages[-1]["id"]
                except (BrokenPipeError, ConnectionResetError):
                    return

            self.send_error(HTTPStatus.NOT_FOUND, "Ruta no encontrada")

        def do_POST(self):
            parsed = urlparse(self.path)
            if parsed.path != "/send":
                self.send_error(HTTPStatus.NOT_FOUND, "Ruta no encontrada")
                return

            data = self._read_json_body()
            if not isinstance(data, dict):
                self._send_json({"error": "JSON invalido"}, status=HTTPStatus.BAD_REQUEST)
                return

            author = str(data.get("author", "Anonimo")).strip()
            text = str(data.get("text", "")).strip()

            if not author:
                author = "Anonimo"

            if not text:
                self._send_json(
                    {"error": "El mensaje no puede estar vacio"},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            if len(author) > 30:
                author = author[:30]
            if len(text) > 500:
                text = text[:500]

            msg = state.add_message(author=author, text=text)
            self._send_json({"ok": True, "message": msg}, status=HTTPStatus.CREATED)

        def log_message(self, fmt, *args):
            return

    return ChatHandler


def main() -> None:
    args = parse_args()
    static_dir = Path(args.dir).resolve()
    if not static_dir.is_dir():
        raise SystemExit(f"La carpeta no existe: {static_dir}")

    state = ChatState()
    state.add_message("Sistema", "Bienvenido al chat en vivo")

    handler_cls = build_handler(static_dir=static_dir, state=state)
    server = ThreadingHTTPServer((args.host, args.port), handler_cls)

    print("Chat en vivo iniciado")
    print(f"Carpeta: {static_dir}")
    print(f"URL local: http://127.0.0.1:{args.port}")
    print(f"URL LAN:   http://{args.host}:{args.port}")
    print("Presiona Ctrl+C para detener")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nApagando servidor...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
