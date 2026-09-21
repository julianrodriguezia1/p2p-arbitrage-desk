"""Tests for cli/push_movement.py"""
from cli.push_movement import push


class _FakeResp:
    def __init__(self, status, text):
        self.status_code = status
        self.text = text


class _FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        return _FakeResp(201, '{"ok":1}')


def test_push_postea_al_endpoint_movement():
    sess = _FakeSession()
    status, text = push({"order_id": "x", "side": "COMPRA"}, "http://vps:8002", session=sess)
    assert status == 201
    url, body = sess.calls[0]
    assert url == "http://vps:8002/api/movement"
    assert body == {"order_id": "x", "side": "COMPRA"}


def test_push_normaliza_barra_final_de_url():
    sess = _FakeSession()
    push({"order_id": "y"}, "http://vps:8002/", session=sess)
    assert sess.calls[0][0] == "http://vps:8002/api/movement"


from cli.push_movement import assign_client, create_client, get_client, list_clients


class _FakeCRMResp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeCRMSession:
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(("GET", url, None))
        return self._resp

    def post(self, url, json=None, timeout=None):
        self.calls.append(("POST", url, json))
        return self._resp

    def put(self, url, json=None, timeout=None):
        self.calls.append(("PUT", url, json))
        return self._resp


def test_list_clients_pega_al_endpoint():
    sess = _FakeCRMSession(_FakeCRMResp(payload=[{"id": 4, "name": "Daniel"}]))
    out = list_clients("http://vps:8002", session=sess)
    assert out == [{"id": 4, "name": "Daniel"}]
    assert sess.calls[0][:2] == ("GET", "http://vps:8002/api/clients")


def test_list_clients_saca_la_barra_de_mas():
    sess = _FakeCRMSession(_FakeCRMResp(payload=[]))
    list_clients("http://vps:8002/", session=sess)
    assert sess.calls[0][1] == "http://vps:8002/api/clients"


def test_get_client_trae_cliente_y_movimientos():
    payload = {"client": {"id": 4, "name": "Daniel"}, "movements": [{"opId": "x"}]}
    sess = _FakeCRMSession(_FakeCRMResp(payload=payload))
    out = get_client(4, "http://vps:8002", session=sess)
    assert out["movements"] == [{"opId": "x"}]
    assert sess.calls[0][:2] == ("GET", "http://vps:8002/api/clients/4")


def test_create_client_manda_nombre_y_estado_activo():
    sess = _FakeCRMSession(_FakeCRMResp(status=201, payload={"id": 9, "name": "Martín"}))
    out = create_client("Martín", "http://vps:8002", session=sess)
    assert out["id"] == 9
    metodo, url, body = sess.calls[0]
    assert (metodo, url) == ("POST", "http://vps:8002/api/clients")
    assert body == {"name": "Martín", "status": "activo"}


def test_assign_client_devuelve_status_y_texto():
    sess = _FakeCRMSession(_FakeCRMResp(status=200, payload={"updated": True},
                                        text='{"updated":true}'))
    status, text = assign_client("man-daniel-20260812", 4, "http://vps:8002", session=sess)
    assert status == 200
    assert "updated" in text
    metodo, url, body = sess.calls[0]
    assert metodo == "PUT"
    assert url == "http://vps:8002/api/movements/man-daniel-20260812/client"
    assert body == {"client_id": 4}
