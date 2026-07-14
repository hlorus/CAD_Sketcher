"""TCP JSON bridge for CAD Sketcher MCP (default port 9877)."""

from __future__ import annotations

import json
import logging
import socket
import threading
import traceback
from typing import Optional

import bpy

from .handlers import dispatch

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9877

_server_instance: Optional["CadSketcherMCPServer"] = None


class CadSketcherMCPServer:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = int(port)
        self.running = False
        self.socket: Optional[socket.socket] = None
        self.server_thread: Optional[threading.Thread] = None
        self.last_error: str = ""

    def start(self):
        if self.running:
            return
        if bpy.app.background:
            raise RuntimeError(
                "CAD Sketcher MCP cannot start in background mode (blender -b). "
                "Run Blender with a GUI."
            )
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.socket.listen(1)
        self.socket.settimeout(1.0)
        self.running = True
        self.last_error = ""
        self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
        self.server_thread.start()
        logger.info("CAD Sketcher MCP listening on %s:%s", self.host, self.port)

    def stop(self):
        self.running = False
        sock = self.socket
        self.socket = None
        if sock:
            try:
                sock.close()
            except OSError:
                pass
        thread = self.server_thread
        self.server_thread = None
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        logger.info("CAD Sketcher MCP stopped")

    def _server_loop(self):
        while self.running and self.socket:
            try:
                client, address = self.socket.accept()
                logger.debug("MCP client connected: %s", address)
                client_thread = threading.Thread(
                    target=self._handle_client, args=(client,), daemon=True
                )
                client_thread.start()
            except socket.timeout:
                continue
            except OSError:
                if self.running:
                    logger.exception("MCP accept failed")
                break
            except Exception:
                if self.running:
                    logger.exception("MCP server loop error")
                break

    def _handle_client(self, client: socket.socket):
        buffer = b""
        try:
            client.settimeout(180.0)
            while self.running:
                try:
                    data = client.recv(8192)
                    if not data:
                        break
                    buffer += data
                    try:
                        command = json.loads(buffer.decode("utf-8"))
                        buffer = b""
                    except json.JSONDecodeError:
                        continue

                    done = threading.Event()
                    response_holder = {}

                    def execute_wrapper():
                        try:
                            response_holder["response"] = dispatch(command)
                        except Exception as e:
                            response_holder["response"] = {
                                "status": "error",
                                "message": str(e),
                            }
                            logger.exception("MCP dispatch failed")
                        finally:
                            done.set()
                        return None

                    bpy.app.timers.register(execute_wrapper, first_interval=0.0)
                    if not done.wait(timeout=180.0):
                        response_holder["response"] = {
                            "status": "error",
                            "message": "Timed out waiting for Blender main thread",
                        }
                    payload = json.dumps(
                        response_holder.get(
                            "response",
                            {"status": "error", "message": "No response"},
                        )
                    )
                    client.sendall(payload.encode("utf-8"))
                except socket.timeout:
                    break
                except OSError:
                    break
                except Exception:
                    logger.exception("MCP client handler error")
                    try:
                        err = {
                            "status": "error",
                            "message": traceback.format_exc(),
                        }
                        client.sendall(json.dumps(err).encode("utf-8"))
                    except OSError:
                        pass
                    break
        finally:
            try:
                client.close()
            except OSError:
                pass


def get_server() -> Optional[CadSketcherMCPServer]:
    return _server_instance


def is_running() -> bool:
    return bool(_server_instance and _server_instance.running)


def start_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> CadSketcherMCPServer:
    global _server_instance
    if _server_instance and _server_instance.running:
        if _server_instance.port == int(port) and _server_instance.host == host:
            return _server_instance
        _server_instance.stop()
    server = CadSketcherMCPServer(host=host, port=port)
    server.start()
    _server_instance = server
    return server


def stop_server():
    global _server_instance
    if _server_instance:
        _server_instance.stop()
        _server_instance = None
