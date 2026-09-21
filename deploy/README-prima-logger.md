# Logger de la prima cripto/ARS en el VPS

Registra cada 15 min las dos puntas de BTC/ETH/USDT contra pesos, su fx
implícito y la prima contra el USDT del mismo momento, más cuántos avisos y
cuánta profundidad la sostienen. Sólo lee precios públicos: no opera ni publica.

Responde lo que quedó pendiente en `docs/investigacion-prima-btc-alts-ars.md`:
si el +1,2% del BTC es estable, y a qué hora y qué día se abre.

Corre en el VPS y no en GitHub Actions por lo mismo que el spread logger: allá
throttlean las corridas. El P2P **público** de Binance sí responde desde el VPS
(lo que da 451 es la API privada de órdenes).

## Instalar

```bash
ssh root@TU_VPS_IP
cd /opt/arbitrador && git pull
cp deploy/prima-logger.service deploy/prima-logger.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now prima-logger.timer
```

## Verificar

```bash
systemctl list-timers prima-logger.timer      # próxima corrida
systemctl start prima-logger.service          # forzar una muestra ya
journalctl -u prima-logger.service -n 20      # qué dijo
wc -l /opt/arbitrador/data/prima_log.csv      # filas acumuladas (3 por ronda)
```

A 15 min por muestra y 3 activos: ~288 filas/día, ~2.000 en la semana.

## Leer el resultado

```bash
cd /opt/arbitrador && .venv/bin/python -m cli.prima_report --csv data/prima_log.csv
```

O traer el CSV a la PC: `scp root@TU_VPS_IP:/opt/arbitrador/data/prima_log.csv data/`

## Parar

```bash
systemctl disable --now prima-logger.timer
```
