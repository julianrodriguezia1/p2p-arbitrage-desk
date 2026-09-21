"""Una captura que el bot no supo leer no se puede perder.

El 2026-09-08 el usuario mandó una captura de KuCoin, el lector falló y la
imagen se descartó: no quedó en disco ni en el log, así que hubo que pedírsela
de nuevo. Ahora se guarda antes de contestar, para poder reintentarla.
"""
from pathlib import Path

from bot.captura import guardar_fallida


class TestGuardarFallida:
    def test_escribe_la_imagen_y_devuelve_la_ruta(self, tmp_path):
        p = guardar_fallida(b"\x89PNG_lo_que_sea", "image/png", carpeta=tmp_path)
        assert p.exists()
        assert p.read_bytes() == b"\x89PNG_lo_que_sea"

    def test_el_nombre_lleva_la_fecha_para_encontrarla(self, tmp_path):
        p = guardar_fallida(b"x", "image/jpeg", carpeta=tmp_path)
        assert p.suffix == ".jpg"
        assert p.name.startswith("captura-")

    def test_dos_capturas_seguidas_no_se_pisan(self, tmp_path):
        a = guardar_fallida(b"uno", "image/png", carpeta=tmp_path)
        b = guardar_fallida(b"dos", "image/png", carpeta=tmp_path)
        assert a != b
        assert a.read_bytes() == b"uno" and b.read_bytes() == b"dos"

    def test_crea_la_carpeta_si_no_existe(self, tmp_path):
        destino = tmp_path / "nueva" / "capturas"
        p = guardar_fallida(b"x", "image/png", carpeta=destino)
        assert p.exists()

    def test_si_no_puede_guardar_no_rompe(self, tmp_path, monkeypatch):
        """Guardar es un extra: nunca puede tumbar la respuesta al usuario."""
        def explota(*a, **k):
            raise OSError("disco lleno")
        monkeypatch.setattr(Path, "write_bytes", explota)
        assert guardar_fallida(b"x", "image/png", carpeta=tmp_path) is None
