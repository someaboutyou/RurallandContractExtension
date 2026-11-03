"""Silent production launcher (double-click entry, no console window ever).

Runs under the bundled windowless interpreter:
    runtime\\windows\\python\\pythonw.exe scripts\\start-production-silent.pyw
Dev machines usually also work by plain double-click (.pyw file association).

It reuses the full start-production.ps1 flow (install/init/env checks, PG,
Redis, GeoServer, backend) via powershell with CREATE_NO_WINDOW, so nothing
flashes on screen. Startup output is captured to runtime\\logs\\startup-silent.log
(-Silent transcript); runtime logs stay in runtime\\logs\\backend.log etc.
Stop everything with scripts\\stop-all.cmd as usual.
"""
import ctypes
import subprocess
import sys
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000

script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
ps_script = script_dir / "start-production.ps1"

if not ps_script.exists():
    ctypes.windll.user32.MessageBoxW(
        0,
        "start-production.ps1 not found:\n" + str(ps_script),
        "Silent startup failed",
        0x10,  # MB_ICONERROR
    )
    sys.exit(1)

subprocess.Popen(
    [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-File",
        str(ps_script),
        "-Silent",
    ],
    cwd=str(project_root),
    creationflags=CREATE_NO_WINDOW,
    close_fds=True,
)
