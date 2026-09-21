"""Instalador + agente autocontenido (entrypoint del .exe de PyInstaller).

Doble proposito segun desde donde corre:
- Fuera de la carpeta de instalacion -> se instala (copia + autoarranque) y lanza la copia.
- Desde la carpeta de instalacion -> corre el loop del agente.
La config (6 valores) va embebida en companion._frozen_config (generada en build).
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

APP_NAME = "ArbitradorAgente"
EXE_NAME = "agente-arbitrador.exe"


def frozen_config() -> SimpleNamespace:
    """Config embebida (las 6 claves). Vacias si no se genero (ej. en tests)."""
    try:
        from companion import _frozen_config as fc
    except Exception:
        fc = None
    g = lambda k: getattr(fc, k, "") if fc else ""
    return SimpleNamespace(
        VPS_API_URL=g("VPS_API_URL"),
        SYNC_AGENT_TOKEN=g("SYNC_AGENT_TOKEN"),
        BINANCE_API_KEY=g("BINANCE_API_KEY"),
        BINANCE_API_SECRET=g("BINANCE_API_SECRET"),
        BYBIT_API_KEY=g("BYBIT_API_KEY"),
        BYBIT_API_SECRET=g("BYBIT_API_SECRET"),
    )


def install_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA", str(Path.home()))
    return Path(base) / APP_NAME


def startup_vbs_path() -> Path:
    appdata = os.environ.get("APPDATA", str(Path.home()))
    return (Path(appdata) / "Microsoft" / "Windows" / "Start Menu"
            / "Programs" / "Startup" / f"{APP_NAME}.vbs")


def is_running_installed(argv0: str, inst_dir: Path) -> bool:
    try:
        return Path(argv0).resolve().parent == inst_dir.resolve()
    except Exception:
        return False


def vbs_contents(exe_path: Path) -> str:
    return (
        'Set sh = CreateObject("WScript.Shell")\n'
        f'sh.Run """{exe_path}""", 0, False\n'
    )


def install(src_exe: Path, inst_dir: Path, startup_path: Path,
            launch=subprocess.Popen) -> Path:
    inst_dir.mkdir(parents=True, exist_ok=True)
    dst_exe = inst_dir / EXE_NAME
    shutil.copy2(src_exe, dst_exe)
    startup_path.parent.mkdir(parents=True, exist_ok=True)
    startup_path.write_text(vbs_contents(dst_exe), encoding="ascii")
    launch([str(dst_exe)])
    return dst_exe


def main() -> None:
    exe = Path(sys.argv[0])
    inst = install_dir()
    if is_running_installed(str(exe), inst):
        from companion import agent
        agent.loop(frozen_config())
    else:
        install(exe, inst, startup_vbs_path())


if __name__ == "__main__":
    main()
