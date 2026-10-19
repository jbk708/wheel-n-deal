import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class LocalProxy:
    """A forward proxy stand-in on loopback: answers absolute-form requests from a table
    and records every URL it was asked for. Nothing leaves the machine."""

    def __init__(self, responses: dict[str, tuple[int, dict[str, str], str]]):
        self.responses = responses
        self.requests: list[str] = []
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                proxy.requests.append(self.path)
                status, headers, body = proxy.responses.get(self.path, (502, {}, "unknown"))
                data = body.encode()
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, args=(0.05,), daemon=True).start()


@pytest.fixture
def local_proxy():
    proxy = LocalProxy({})
    yield proxy
    proxy.server.shutdown()
    proxy.server.server_close()


@pytest.fixture
def dead_proxy_url():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"
