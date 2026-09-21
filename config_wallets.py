"""Declaración de billeteras (vías de pago ARS) para el control de topes.
Alias→canónica junta las etiquetas sucias del campo `bank` de trades.db.
Los topes arrancan vacíos (None): completá `in`/`out` cuando los investigues.
Consumido por webapp/server.py (/api/wallets) y bot/commands.py."""

WALLET_ALIASES: dict[str, list[str]] = {
    "MercadoPago":  ["MercadoPagoNew", "Mercadopago", "Mercado Pago"],
    "Lemon Cash":   ["Lemon", "LemonCash", "Lemon Cash"],
    "Ualá":         ["UalaNew", "UalaNewest", "Uala"],
    "NaranjaX":     ["NaranjaX"],
    "Banco":        ["BankArgentina", "Transferencia Pesos ARG"],
    "Satoshitango": ["Satoshitango"],
    "Cocos":        ["Cocos"],
    "Sin clasificar": ["", "Binance Spot"],
}

# Topes mensuales de acreditación (in) y débito (out) en ARS. None = sin tope
# definido todavía. Completar a mano cuando se investiguen los reales.
WALLET_LIMITS: dict[str, dict] = {
    "MercadoPago":  {"in": None, "out": None},
    "Lemon Cash":   {"in": None, "out": None},
    "Ualá":         {"in": None, "out": None},
    "NaranjaX":     {"in": None, "out": None},
    "Banco":        {"in": None, "out": None},
    "Satoshitango": {"in": None, "out": None},
    "Cocos":        {"in": None, "out": None},
}
