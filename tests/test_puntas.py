"""Puntas del libro por venue, el mejor cruce y el vigilante de avisos propios.

El 2026-09-11 el usuario publicó una venta y el libro se corrió sin que se
diera cuenta: siguió vendiendo al precio viejo. El motor de acá contesta dos
preguntas: "¿a cuánto se publica en cada venue?" y "¿mi aviso sigue siendo la
punta o me pasaron?".

Convención de `p2p_scanner.Ad.side` (la misma de core/verificado_hoy):
  "BUY"  = avisos de gente que te VENDE  → vos comprás (te_venden)
  "SELL" = avisos de gente que te COMPRA → vos vendés  (te_compran)
"""
import pytest

from core.puntas import (
    Cruce,
    estado_aviso,
    mejor_cruce,
    precio_propio,
    punta_de_libro,
    puntas_de,
    ranking_cruces,
)


class FakeAd:
    """Mínimo para el motor: precio, stock y reputación."""

    def __init__(self, price, available=1000.0, orders=50, finish_rate=0.95,
                 min_amount=1000.0, max_amount=1_000_000.0, merchant="x"):
        self.price = price
        self.available = available
        self.orders = orders
        self.finish_rate = finish_rate
        self.min_amount = min_amount
        self.max_amount = max_amount
        self.merchant = merchant


def libro(venue="binancep2p", te_venden=(1594.0, 1595.0, 1596.0),
          te_compran=(1589.5, 1589.0, 1588.0)):
    return {
        "te_venden": [FakeAd(p) for p in te_venden],
        "te_compran": [FakeAd(p) for p in te_compran],
    }


class TestPuntaDeLibro:
    def test_para_vender_publicando_te_ponés_en_el_aviso_mas_barato(self):
        ads = [FakeAd(1596.0), FakeAd(1594.0), FakeAd(1595.0)]
        assert punta_de_libro(ads, mas_caro=False) == 1594.0

    def test_para_comprar_publicando_te_ponés_en_el_que_mas_paga(self):
        ads = [FakeAd(1588.0), FakeAd(1589.5), FakeAd(1589.0)]
        assert punta_de_libro(ads, mas_caro=True) == 1589.5

    def test_un_anzuelo_sin_stock_no_es_punta(self):
        """Dos monedas a un precio irreal no mueven el precio publicado."""
        ads = [FakeAd(1580.0, available=2.0), FakeAd(1594.0, available=500.0),
               FakeAd(1595.0, available=500.0)]
        assert punta_de_libro(ads, mas_caro=False) == 1594.0

    def test_libro_vacio_no_inventa_precio(self):
        assert punta_de_libro([], mas_caro=False) is None


class TestPuntasDe:
    def test_devuelve_una_fila_por_venue(self):
        out = puntas_de({"binancep2p": libro(), "kucoinp2p": libro(
            te_venden=(1601.5,), te_compran=(1584.15,))})
        assert {p.venue for p in out} == {"binancep2p", "kucoinp2p"}

    def test_la_fila_trae_los_dos_lados_publicando(self):
        p = puntas_de({"binancep2p": libro()})[0]
        assert p.comprar_publicando == 1589.5
        assert p.vender_publicando == 1594.0

    def test_el_ancho_es_el_negocio_de_publicar_las_dos_puntas(self):
        p = puntas_de({"binancep2p": libro()})[0]
        # (1594 − 1589,5) / 1594 × 100
        assert p.ancho_pct == pytest.approx(0.2823, abs=1e-3)

    def test_mi_propio_aviso_no_es_la_punta_del_libro(self):
        # 2026-09-13: MiApodoP2P compraba a 1.594,05 y era el primero del libro.
        # Contado como punta, el vigilante se comparaba contra sí mismo y decía
        # "sos la punta" aunque el resto pagara menos: nunca sonaba.
        lib = {"te_venden": [FakeAd(1599.0)],
               "te_compran": [FakeAd(1594.05, merchant="MiApodoP2P"), FakeAd(1592.0)]}
        p = puntas_de({"binancep2p": lib}, excluir=("miapodop2p",))[0]
        assert p.comprar_publicando == 1592.0
        assert p.stock_compra == 1000.0

    def test_lee_el_precio_de_mi_aviso_del_libro(self):
        # 2026-09-13: el casillero decía 1.597 (el rival) y el aviso real estaba
        # en 1.599. El precio propio sale del libro, no de lo que se tipeó.
        ads = [FakeAd(1597.0, merchant="Parabailarlabamba"), FakeAd(1599.0, merchant="MiApodoP2P")]
        assert precio_propio(ads, ("miapodop2p",), mas_caro=False) == 1599.0

    def test_con_dos_avisos_propios_vale_el_mejor(self):
        ads = [FakeAd(1588.2, merchant="Mi Apodo KuCoin"), FakeAd(1590.0, merchant="Mi Apodo KuCoin")]
        assert precio_propio(ads, ("Mi Apodo KuCoin",), mas_caro=True) == 1590.0

    def test_si_mi_aviso_no_esta_no_inventa_precio(self):
        assert precio_propio([FakeAd(1595.5, merchant="josecripto")], ("MiApodoP2P",), mas_caro=True) is None

    def test_sin_excluir_el_libro_queda_como_viene(self):
        lib = {"te_venden": [FakeAd(1599.0)],
               "te_compran": [FakeAd(1594.05, merchant="MiApodoP2P"), FakeAd(1592.0)]}
        assert puntas_de({"binancep2p": lib})[0].comprar_publicando == 1594.05

    def test_un_venue_con_un_lado_caido_no_rompe(self):
        p = puntas_de({"okexp2p": {"te_venden": [], "te_compran": [FakeAd(1589.0)]}})[0]
        assert p.vender_publicando is None
        assert p.comprar_publicando == 1589.0
        assert p.ancho_pct is None


MAKER = {"binancep2p": 0.20, "kucoinp2p": 0.0, "bybitp2p": 0.0}
RED = {"binancep2p": 0.01, "kucoinp2p": 0.40, "bybitp2p": 0.20}


class TestMejorCruce:
    def test_elige_comprar_barato_y_vender_caro_entre_venues(self):
        """Con los precios del 2026-09-12, comprar publicando en Binance y
        vender publicando en Bybit (9,30 ARS/USDT) le gana a quedarse dentro
        de cualquiera de los dos (−1,87 en Binance, 9,00 en Bybit)."""
        ps = puntas_de({
            "binancep2p": libro(te_venden=(1594.0,), te_compran=(1589.5,)),
            "bybitp2p": libro(te_venden=(1602.0,), te_compran=(1593.0,)),
        })
        c = mejor_cruce(ps, maker_pct=MAKER, fee_red_usdt=RED, tanda_usdt=1000)
        assert (c.comprar_en, c.vender_en) == ("binancep2p", "bybitp2p")
        assert c.cross_venue is True
        assert c.neto_ars_por_usdt == pytest.approx(9.305, abs=1e-2)

    def test_un_libro_sin_stock_no_entra_aunque_tenga_el_mejor_precio(self):
        """Lo que dijo el usuario el 2026-09-12: en KuCoin se mueve poco, así
        que un precio divino sin nadie del otro lado no es una jugada."""
        ps = puntas_de({
            "binancep2p": libro(te_venden=(1594.0,), te_compran=(1589.5,)),
            "kucoinp2p": {"te_venden": [FakeAd(1601.5, available=10.0)],
                          "te_compran": [FakeAd(1584.15, available=10.0)]},
        })
        c = mejor_cruce(ps, maker_pct=MAKER, fee_red_usdt=RED, tanda_usdt=1000,
                        stock_min_usdt=100.0)
        assert "kucoinp2p" not in (c.comprar_en, c.vender_en)

    def test_descuenta_los_makers_de_las_dos_patas(self):
        """KuCoin→Binance: (1594 − 1584,15) menos 0,2% de maker de Binance
        menos 0,40 USDT de red repartidos en la tanda de 1.000."""
        ps = puntas_de({
            "binancep2p": libro(te_venden=(1594.0,), te_compran=(1589.5,)),
            # KuCoin sólo con el lado de compra: la venta es en Binance.
            "kucoinp2p": {"te_venden": [], "te_compran": [FakeAd(1584.15)]},
        })
        c = mejor_cruce(ps, maker_pct=MAKER, fee_red_usdt=RED, tanda_usdt=1000)
        assert (c.comprar_en, c.vender_en) == ("kucoinp2p", "binancep2p")
        # 9,85 − 3,188 − 0,6376 = 6,0244 ARS por USDT
        assert c.neto_ars_por_usdt == pytest.approx(6.0244, abs=1e-3)

    def test_el_fee_de_red_se_reparte_en_la_tanda_no_por_operacion(self):
        """La corrección del 2026-09-12: el 0,40 se paga UNA vez por
        transferencia, no en cada venta de 50 USD."""
        ps = puntas_de({
            "binancep2p": libro(te_venden=(1594.0,), te_compran=(1589.5,)),
            # KuCoin sólo con el lado de compra: la venta es en Binance.
            "kucoinp2p": {"te_venden": [], "te_compran": [FakeAd(1584.15)]},
        })
        chica = mejor_cruce(ps, maker_pct=MAKER, fee_red_usdt=RED, tanda_usdt=50)
        grande = mejor_cruce(ps, maker_pct=MAKER, fee_red_usdt=RED, tanda_usdt=1000)
        assert grande.neto_ars_por_usdt > chica.neto_ars_por_usdt
        assert chica.neto_ars_por_usdt < 0  # con tanda de 50 la red se lo come

    def test_dentro_del_mismo_venue_no_paga_red(self):
        ps = puntas_de({"bybitp2p": libro(te_venden=(1602.0,), te_compran=(1593.0,))})
        c = mejor_cruce(ps, maker_pct=MAKER, fee_red_usdt=RED, tanda_usdt=50)
        assert c.cross_venue is False
        assert c.neto_ars_por_usdt == pytest.approx(9.0, abs=1e-6)

    def test_sin_venues_devuelve_nada(self):
        assert mejor_cruce([], maker_pct=MAKER, fee_red_usdt=RED, tanda_usdt=1000) is None

    def test_un_venue_sin_precio_no_entra_al_ranking(self):
        ps = puntas_de({"okexp2p": {"te_venden": [], "te_compran": []}})
        assert mejor_cruce(ps, maker_pct=MAKER, fee_red_usdt=RED, tanda_usdt=1000) is None


class TestEstadoAviso:
    def test_vendiendo_al_precio_de_la_punta_seguis_primero(self):
        e = estado_aviso(mi_precio=1594.0, lado="venta", punta=1594.0)
        assert e.estado == "punta"

    def test_vendiendo_muy_abajo_del_libro_estas_regalando(self):
        """El caso que le costó plata el 12/09: publicó a 1.594, el libro se fue
        a 1.596 y el tablero decía "sos la punta" — cierto, pero regalando 2 ARS
        por USDT. Un aviso que no avisa de esto no sirve."""
        e = estado_aviso(mi_precio=1594.0, lado="venta", punta=1596.0)
        assert e.estado == "regalando"
        assert e.diferencia_ars == pytest.approx(2.0)
        assert e.sugerido == 1596.0

    def test_comprando_muy_arriba_del_libro_tambien_estas_regalando(self):
        e = estado_aviso(mi_precio=1592.0, lado="compra", punta=1589.0)
        assert e.estado == "regalando"
        assert e.diferencia_ars == pytest.approx(3.0)
        assert e.sugerido == 1589.0

    def test_una_diferencia_dentro_de_la_tolerancia_no_molesta(self):
        """Sin esto sonaría por un centavo, cada 30 segundos."""
        e = estado_aviso(mi_precio=1594.0, lado="venta", punta=1594.5, tolerancia=1.0)
        assert e.estado == "punta"

    def test_la_tolerancia_no_tapa_un_movimiento_de_verdad(self):
        e = estado_aviso(mi_precio=1594.0, lado="venta", punta=1596.0, tolerancia=1.0)
        assert e.estado == "regalando"

    def test_vendiendo_mas_caro_que_la_punta_te_pasaron(self):
        e = estado_aviso(mi_precio=1596.0, lado="venta", punta=1594.0)
        assert e.estado == "pasado"
        assert e.diferencia_ars == pytest.approx(2.0)
        assert e.sugerido == 1594.0

    def test_comprando_mas_barato_que_la_punta_te_pasaron(self):
        e = estado_aviso(mi_precio=1587.0, lado="compra", punta=1589.5)
        assert e.estado == "pasado"
        assert e.diferencia_ars == pytest.approx(2.5)
        assert e.sugerido == 1589.5

    def test_comprando_al_tope_del_libro_seguis_primero(self):
        e = estado_aviso(mi_precio=1589.5, lado="compra", punta=1589.5)
        assert e.estado == "punta"

    def test_sin_punta_no_inventa_veredicto(self):
        e = estado_aviso(mi_precio=1594.0, lado="venta", punta=None)
        assert e.estado == "sin_dato"
        assert e.diferencia_ars is None

    def test_sin_precio_propio_no_hay_nada_que_vigilar(self):
        e = estado_aviso(mi_precio=0, lado="venta", punta=1594.0)
        assert e.estado == "sin_dato"

    def test_lado_invalido_avisa(self):
        with pytest.raises(ValueError):
            estado_aviso(mi_precio=1594.0, lado="loquesea", punta=1594.0)


class TestPrioridadBinance:
    """Mientras se persiga el Verificado, una ruta que no toca Binance no suma
    ninguna operación: el ranking la muestra, pero nunca primero."""

    def _tres(self):
        return puntas_de({
            "binancep2p": libro(te_venden=(1594.0,), te_compran=(1589.5,)),
            "kucoinp2p": libro(te_venden=(1599.0,), te_compran=(1585.15,)),
            "bybitp2p": libro(te_venden=(1600.0,), te_compran=(1593.55,)),
        })

    def test_el_cruce_sabe_cuantas_patas_pisan_binance(self):
        cs = {(c.comprar_en, c.vender_en): c for c in ranking_cruces(
            self._tres(), maker_pct=MAKER, fee_red_usdt=RED, tanda_usdt=1000)}
        assert cs[("binancep2p", "binancep2p")].patas_binance == 2
        assert cs[("kucoinp2p", "binancep2p")].patas_binance == 1
        assert cs[("kucoinp2p", "bybitp2p")].patas_binance == 0

    def test_priorizando_binance_el_primero_toca_binance(self):
        r = ranking_cruces(self._tres(), maker_pct=MAKER, fee_red_usdt=RED,
                           tanda_usdt=1000, priorizar="binancep2p")
        assert r[0].patas_binance >= 1
        # y el que no toca Binance sigue estando, más abajo
        assert any(c.patas_binance == 0 for c in r)

    def test_sin_priorizar_gana_el_que_mas_deja_aunque_no_sume(self):
        r = ranking_cruces(self._tres(), maker_pct=MAKER, fee_red_usdt=RED,
                           tanda_usdt=1000)
        assert r[0].patas_binance == 0   # KuCoin → Bybit deja más, pero no suma

    def test_dentro_del_grupo_que_toca_binance_manda_la_plata(self):
        r = ranking_cruces(self._tres(), maker_pct=MAKER, fee_red_usdt=RED,
                           tanda_usdt=1000, priorizar="binancep2p")
        con_binance = [c for c in r if c.patas_binance >= 1]
        assert con_binance == sorted(con_binance,
                                     key=lambda c: c.neto_ars_por_usdt, reverse=True)
