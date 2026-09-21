from pathlib import Path

from companion import agent_app


def test_frozen_config_tiene_los_6_campos():
    c = agent_app.frozen_config()
    for k in ("VPS_API_URL", "SYNC_AGENT_TOKEN", "BINANCE_API_KEY",
              "BINANCE_API_SECRET", "BYBIT_API_KEY", "BYBIT_API_SECRET"):
        assert hasattr(c, k)


def test_is_running_installed(tmp_path):
    inst = tmp_path / "inst"
    inst.mkdir()
    exe_in = inst / agent_app.EXE_NAME
    exe_in.write_bytes(b"x")
    assert agent_app.is_running_installed(str(exe_in), inst) is True

    other = tmp_path / "downloads" / agent_app.EXE_NAME
    other.parent.mkdir()
    other.write_bytes(b"x")
    assert agent_app.is_running_installed(str(other), inst) is False


def test_vbs_contents_lanza_oculto():
    v = agent_app.vbs_contents(Path("C:/x/agente-arbitrador.exe"))
    assert "agente-arbitrador.exe" in v
    assert ", 0, False" in v  # ventana oculta, no espera


def test_install_copia_exe_crea_vbs_y_lanza(tmp_path):
    src = tmp_path / agent_app.EXE_NAME
    src.write_bytes(b"FAKEEXE")
    inst = tmp_path / "inst"
    startup = tmp_path / "startup" / "ArbitradorAgente.vbs"
    lanzados = []

    dst = agent_app.install(src, inst, startup, launch=lambda args: lanzados.append(args))

    assert dst.parent == inst
    assert dst.read_bytes() == b"FAKEEXE"
    assert startup.exists()
    assert str(dst) in startup.read_text()
    assert lanzados == [[str(dst)]]
