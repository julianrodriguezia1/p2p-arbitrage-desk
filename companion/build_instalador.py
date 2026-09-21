"""Genera la config embebida desde .env y compila el .exe del agente (PyInstaller).

Correr en la PC (Windows), desde la raiz del repo:
    python -m companion.build_instalador
Requiere: pip install pyinstaller
"""
import subprocess
import sys
from pathlib import Path

import config  # carga el .env

REPO = Path(__file__).resolve().parent.parent
KEYS = ["VPS_API_URL", "SYNC_AGENT_TOKEN", "BINANCE_API_KEY",
        "BINANCE_API_SECRET", "BYBIT_API_KEY", "BYBIT_API_SECRET"]


def write_frozen_config() -> None:
    faltan = [k for k in KEYS if not getattr(config, k, "")]
    if faltan:
        sys.exit(f"Faltan estos valores en el .env: {', '.join(faltan)}")
    lines = [f"{k} = {getattr(config, k)!r}" for k in KEYS]
    (REPO / "companion" / "_frozen_config.py").write_text(
        "# GENERADO por build_instalador.py - NO commitear (tiene secrets).\n"
        + "\n".join(lines) + "\n", encoding="utf-8")


def build() -> None:
    write_frozen_config()
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--onefile", "--noconsole",
        "--name", "agente-arbitrador", "--noconfirm",
        "--collect-submodules", "core",
        "--collect-submodules", "cli",
        "--collect-submodules", "companion",
        str(REPO / "companion" / "agent_app.py"),
    ], cwd=str(REPO), check=True)
    print("Listo: dist/agente-arbitrador.exe")


if __name__ == "__main__":
    build()
