"""Stop an owned worker and wait until its model memory can be reclaimed."""
import os
import subprocess


def stop_owned_worker(process, *, graceful=True):
    if process is None:
        return
    if process.poll() is None:
        if graceful and process.stdin:
            process.stdin.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        if process.poll() is None:
            # Windows venv python.exe may be a launcher with a real Python child.
            # Terminating just the launcher can leave the GPU model alive.
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                )
            else:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
    for stream in (process.stdin, process.stdout):
        if stream and not stream.closed:
            stream.close()
