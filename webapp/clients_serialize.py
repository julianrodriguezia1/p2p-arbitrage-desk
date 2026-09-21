"""Adaptador entre Client (DB) y el dict JSON (camelCase) que consume el HTML."""
from core.clients_db import Client

# Mapeo snake_case (DB) -> camelCase (HTML).
_FIELD_MAP = {
    "id": "id", "name": "name", "alias": "alias", "doc_number": "docNumber",
    "contact": "contact", "notes": "notes", "source": "source", "status": "status",
    "last_contacted_at": "lastContactedAt", "bank_holder": "bankHolder",
    "bank_name": "bankName", "cbu_cvu": "cbuCvu", "bank_alias": "bankAlias",
    "created_at": "createdAt", "updated_at": "updatedAt",
}
_INVERSE = {v: k for k, v in _FIELD_MAP.items()}


def client_to_dashboard(c: Client) -> dict:
    return {camel: getattr(c, snake) for snake, camel in _FIELD_MAP.items()}


def dashboard_to_client(d: dict) -> Client:
    snake = {_INVERSE[k]: v for k, v in d.items() if k in _INVERSE}
    if not str(snake.get("name") or "").strip():
        raise ValueError("El cliente necesita un nombre.")
    snake.pop("id", None)  # id lo asigna la DB
    snake.pop("created_at", None)
    snake.pop("updated_at", None)
    return Client(id=None, **snake)
