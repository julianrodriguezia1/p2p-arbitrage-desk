import pytest

from core.clients_db import Client
from webapp.clients_serialize import client_to_dashboard, dashboard_to_client


def test_client_to_dashboard():
    c = Client(id=3, name="Juan", alias="jj", doc_number="20-1-3",
               contact="tg:@jj", cbu_cvu="000", bank_alias="juan.mp",
               status="activo", last_contacted_at="2026-06-24")
    d = client_to_dashboard(c)
    assert d["id"] == 3
    assert d["name"] == "Juan"
    assert d["docNumber"] == "20-1-3"
    assert d["cbuCvu"] == "000"
    assert d["bankAlias"] == "juan.mp"
    assert d["lastContactedAt"] == "2026-06-24"
    assert d["status"] == "activo"


def test_dashboard_to_client_roundtrip():
    d = {"name": "Ana", "docNumber": "27-9", "contact": "+54911",
         "cbuCvu": "123", "bankAlias": "ana.lemon", "status": "contactado",
         "campoDesconocido": "x"}
    c = dashboard_to_client(d)
    assert c.name == "Ana"
    assert c.doc_number == "27-9"
    assert c.cbu_cvu == "123"
    assert c.bank_alias == "ana.lemon"
    assert c.status == "contactado"
    assert c.id is None


def test_dashboard_to_client_sin_name_falla():
    with pytest.raises((KeyError, ValueError)):
        dashboard_to_client({"alias": "x"})
