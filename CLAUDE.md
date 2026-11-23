# Day Trader de Vicente

Fork de Jakeschincariol/day-trader-skill, configurado para usarlo desde Claude Code web (claude.ai/code).

## Cómo hablarle a Vicente
- Responde siempre en español, informal y directo.
- Respuestas cortas: muchas veces lee desde el celular.
- Da las horas en hora de Nueva York y también en hora de Chile (America/Santiago). El mercado de EE.UU. abre 9:30 y cierra 16:00 en Nueva York.

## Su contexto
- Invierte con la app Racional: S&P 500, NVIDIA, Tesla y Solana.
- Racional no tiene API, así que nunca hay órdenes automáticas. trader-broker solo muestra el ticket: Vicente lo ejecuta a mano en Racional. No configures Alpaca ni IBKR salvo que él lo pida.
- Racional permite fracciones de acciones (`"fractional": true`).
- Solana no es una acción: los scripts de este repo no la cubren. Para SOL usa la búsqueda web.
- Sus límites están en `trader/config.json` (presupuesto, pérdida máxima por trade, etc.). Los valores actuales son un punto de partida; si él da otros, actualiza ese archivo.
- `trader/portfolio.json` tiene sus posiciones (sin cantidades por ahora). trader-news lo lee cuando no se le pasan tickers.

## Las skills
Están en `.claude/skills/` (enlaces a las carpetas `trader-*` de la raíz). Si `${CLAUDE_SKILL_DIR}` no está definido, los scripts están en `trader-<nombre>/` dentro de este repo; córrelos desde la raíz del repo.

Prueba rápida de que los datos llegan:
```bash
python3 trader-news/news.py --tickers NVDA TSLA --hours 12
```
Si aparece "403 Forbidden" o "could not reach", falta agregar el dominio en Network access del entorno (Custom):
query1.finance.yahoo.com, query2.finance.yahoo.com, feeds.finance.yahoo.com, www.nasdaqtrader.com, data.sec.gov, www.sec.gov, disclosures-clerk.house.gov.
La SEC necesita la variable `SEC_USER_AGENT` ("Nombre correo") en las variables de entorno del entorno.

## Reglas
- No es asesoría financiera. Un PASS de trader-risk es un chequeo de reglas, no una recomendación.
- Siempre con stop. Nada de opciones, margen, venta en corto ni apalancamiento.
- Si busca ganancias diarias chicas, recuérdale (una vez) que el spread y los costos de Racional pueden comérselas.
