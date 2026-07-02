import debugpy
import os
import sys


def _kill_process_on_port(port):
    my_pid = os.getpid()
    if sys.platform in ("linux", "darwin"):
        import subprocess, signal

        if sys.platform == "linux":
            result = subprocess.run(
                ["fuser", f"{port}/tcp"], capture_output=True, text=True
            )
        else:
            result = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}"], capture_output=True, text=True
            )
        for pid in [int(p) for p in result.stdout.split() if p.strip().isdigit()]:
            if pid != my_pid:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
    elif sys.platform == "win32":
        import subprocess

        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                try:
                    pid = int(line.split()[-1])
                    if pid != my_pid:
                        subprocess.run(
                            ["taskkill", "/PID", str(pid), "/F"], capture_output=True
                        )
                except Exception:
                    pass


_kill_process_on_port(5678)
debugpy.listen(5678)
