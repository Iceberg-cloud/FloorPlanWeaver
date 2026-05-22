"""
FloorPlanWeaver 启动脚本
自动启动后端和前端，并在浏览器中打开界面。
关闭浏览器中的标签页后自动关闭前后端服务。
"""

import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
SHUTDOWN_FLAG = ROOT / ".shutdown_flag"

BACKEND_PORT = 8000
FRONTEND_PORT = 3001

# Prefer Anaconda env, fall back to system python
PREFERRED_PYTHON = r"E:\ananconda\envs\Agent\python.exe"


def log(msg: str) -> None:
    text = f"[FloorPlanWeaver] {msg}"
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(enc, errors="replace").decode(enc), flush=True)


def free_port(port: int) -> None:
    """Release a TCP port on Windows by terminating its listener process."""
    if sys.platform != "win32":
        return
    result = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    pids: set[int] = set()
    for line in result.stdout.splitlines():
        if f":{port}" not in line or "LISTENING" not in line:
            continue
        parts = line.split()
        if parts and parts[-1].isdigit():
            pids.add(int(parts[-1]))
    for proc_id in pids:
        kill = subprocess.run(
            ["taskkill", "/F", "/PID", str(proc_id)],
            capture_output=True,
            text=True,
        )
        if kill.returncode == 0:
            log(f"已释放端口 {port} (PID {proc_id})")


def find_python() -> str:
    if os.path.isfile(PREFERRED_PYTHON):
        return PREFERRED_PYTHON
    return sys.executable


def find_npm() -> str:
    if sys.platform == "win32":
        return "npm.cmd"
    return "npm"


def wait_for_health(url: str, timeout: int = 30) -> bool:
    import urllib.request
    import urllib.error
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(url, timeout=3)
            if resp.status == 200:
                return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(0.5)
    return False


def stream_output(proc: subprocess.Popen, label: str) -> None:
    """Read subprocess stdout and print it with a label prefix."""
    try:
        if proc.stdout:
            for line in iter(proc.stdout.readline, b""):
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    print(f"  [{label}] {text}", flush=True)
    except Exception:
        pass


def main() -> None:
    log("=" * 50)
    log("  FloorPlanWeaver 启动中...")
    log("=" * 50)

    # Clean up old shutdown flag
    if SHUTDOWN_FLAG.exists():
        SHUTDOWN_FLAG.unlink(missing_ok=True)

    backend_proc = None
    frontend_proc = None
    python_exe = find_python()
    npm_cmd = find_npm()

    log(f"Python: {python_exe}")
    log(f"npm:    {npm_cmd}")
    log(f"后端端口: {BACKEND_PORT}")
    log(f"前端端口: {FRONTEND_PORT}")

    free_port(BACKEND_PORT)
    free_port(FRONTEND_PORT)

    try:
        # ═══════════════════════════════════
        # 1. Start Backend
        # ═══════════════════════════════════
        env = os.environ.copy()
        env["FLOORPLAN_SHUTDOWN_FILE"] = str(SHUTDOWN_FLAG)

        backend_cmd = [
            python_exe, "-m", "uvicorn",
            "app.main:app",
            "--host", "0.0.0.0",
            "--port", str(BACKEND_PORT),
            "--reload",
        ]
        log(f"启动后端 ...")
        log(f"  命令: {' '.join(backend_cmd)}")
        backend_proc = subprocess.Popen(
            backend_cmd,
            cwd=str(BACKEND_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        # Stream backend output in background
        backend_thread = threading.Thread(
            target=stream_output, args=(backend_proc, "后端"), daemon=True
        )
        backend_thread.start()

        # Wait for backend health
        log(f"  等待后端就绪 (http://localhost:{BACKEND_PORT}/api/v1/health) ...")
        if not wait_for_health(f"http://localhost:{BACKEND_PORT}/api/v1/health", timeout=30):
            log("ERROR: 后端启动超时！")
            log("  请检查：")
            log(f"    1. {python_exe} 是否安装了 uvicorn, fastapi 等依赖")
            log(f"    2. {BACKEND_DIR}/app/main.py 是否存在")
            if backend_proc:
                backend_proc.terminate()
            sys.exit(1)
        log("后端已就绪 [OK]")

        # ═══════════════════════════════════
        # 2. Start Frontend
        # ═══════════════════════════════════
        # Install deps if needed
        node_modules = FRONTEND_DIR / "node_modules"
        if not node_modules.exists():
            log("安装前端依赖 (npm install) ...")
            install_result = subprocess.run(
                [npm_cmd, "install"],
                cwd=str(FRONTEND_DIR),
                capture_output=True,
                text=True,
            )
            if install_result.returncode != 0:
                log(f"ERROR: npm install 失败：{install_result.stderr}")
                backend_proc.terminate()
                sys.exit(1)
            log("前端依赖安装完成 [OK]")

        # Start frontend dev server
        frontend_cmd = [npm_cmd, "run", "dev"]
        env_fe = os.environ.copy()
        # PORT env is respected by next dev (but -p in package.json takes precedence)
        env_fe["PORT"] = str(FRONTEND_PORT)
        log(f"启动前端 ...")
        log(f"  命令: {' '.join(frontend_cmd)} (cwd: {FRONTEND_DIR})")
        frontend_proc = subprocess.Popen(
            frontend_cmd,
            cwd=str(FRONTEND_DIR),
            env=env_fe,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        # Stream frontend output in background
        frontend_thread = threading.Thread(
            target=stream_output, args=(frontend_proc, "前端"), daemon=True
        )
        frontend_thread.start()

        # Wait for frontend
        log(f"  等待前端就绪 (http://localhost:{FRONTEND_PORT}) ...")
        if not wait_for_health(f"http://localhost:{FRONTEND_PORT}", timeout=40):
            log("WARNING: 前端启动超时，但仍在尝试打开浏览器...")
            log("  如果浏览器无法访问，请检查 node_modules 是否完整。")
        else:
            log("前端已就绪 [OK]")

        # ═══════════════════════════════════
        # 3. Open Browser
        # ═══════════════════════════════════
        url = f"http://localhost:{FRONTEND_PORT}"
        log(f"打开浏览器: {url}")
        webbrowser.open(url)

        # ═══════════════════════════════════
        # 4. Monitor & Wait
        # ═══════════════════════════════════
        log("-" * 50)
        log("服务正在运行。")
        log("  · 在界面中点击「关闭服务」按钮")
        log("  · 或按 Ctrl+C 停止")
        log("-" * 50)

        # Monitor shutdown flag from web UI
        shutdown_monitor = threading.Thread(
            target=_monitor_shutdown, args=(SHUTDOWN_FLAG,), daemon=True
        )
        shutdown_monitor.start()

        # Also monitor process liveness
        try:
            while not SHUTDOWN_FLAG.exists():
                # Check if processes are still alive
                if backend_proc and backend_proc.poll() is not None:
                    log("ERROR: 后端进程意外退出！")
                    break
                if frontend_proc and frontend_proc.poll() is not None:
                    log("WARNING: 前端进程意外退出！")
                    break
                time.sleep(1)

            if SHUTDOWN_FLAG.exists():
                log("检测到关闭信号（来自界面按钮）。")
        except KeyboardInterrupt:
            log("检测到 Ctrl+C。")

    finally:
        log("=" * 50)
        log("正在关闭服务 ...")

        if frontend_proc:
            log("  关闭前端 ...")
            frontend_proc.terminate()
            try:
                frontend_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                frontend_proc.kill()
                log("  前端已强制终止。")
            else:
                log("  前端已关闭 [OK]")

        if backend_proc:
            log("  关闭后端 ...")
            backend_proc.terminate()
            try:
                backend_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend_proc.kill()
                log("  后端已强制终止。")
            else:
                log("  后端已关闭 [OK]")

        if SHUTDOWN_FLAG.exists():
            SHUTDOWN_FLAG.unlink(missing_ok=True)

        log("FloorPlanWeaver 已完全退出。")
        log("=" * 50)


def _monitor_shutdown(flag_path: Path) -> None:
    while True:
        if flag_path.exists():
            return
        time.sleep(1)


if __name__ == "__main__":
    main()
