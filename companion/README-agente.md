# Agente de sync on-demand — autoarranque

El agente corre en tu PC y, cuando apretás "Actualizar transferencias" en el
dashboard, trae tus operaciones de Binance/Bybit y las sube. Necesita estar
corriendo para que el botón funcione.

## Instalar (una vez por máquina)

```powershell
powershell -ExecutionPolicy Bypass -File companion\instalar_agente.ps1
```

Queda arrancando solo, sin ventana, cada vez que iniciás sesión en Windows.

## Apagarlo

```powershell
powershell -ExecutionPolicy Bypass -File companion\desinstalar_agente.ps1
```

Requiere el `.env` del repo con `VPS_API_URL`, `SYNC_AGENT_TOKEN` y las API keys
read-only de Binance/Bybit (ya configurados).
