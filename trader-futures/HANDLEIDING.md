# trader-futures: handleiding

Een automatische handelaar voor **index futures** via **Interactive Brokers
(IBKR)**. Hij draait op je eigen pc naast IB Gateway, kijkt elke 5 minuten
naar de markt, en handelt alleen als er een volumepiek met een uitbraak is.
Jij hoeft niet mee te kijken: je krijgt een melding op je telefoon bij elk
signaal, elke order en elke uitstap.

Dit is geen beleggingsadvies. Futures werken met hefboom: een verlies kan
groter zijn dan wat er op de rekening staat. Begin altijd met paper trading.

## Wat hij doet

**Markten** (standaard alleen MES; meer in `contracts` in de config):

| code | contract | per indexpunt | handelsvenster (Nederlandse tijd, wintertijd) | sluit uiterlijk |
| --- | --- | --- | --- | --- |
| MES | Micro E-mini S&P 500 | $ 5 | 15:45 - 21:30 | 21:55 |
| MNQ | Micro E-mini Nasdaq-100 | $ 2 | 15:45 - 21:30 | 21:55 |
| MYM | Micro E-mini Dow | $ 0,50 | 15:45 - 21:30 | 21:55 |
| M2K | Micro E-mini Russell 2000 | $ 5 | 15:45 - 21:30 | 21:55 |
| MNK | Micro Nikkei (in dollar, CME) | $ 0,50 (tick 5 punten = $ 2,50) | drie sessies, zie hieronder | per sessie |
| FDXS | Micro-DAX | € 1 | 09:15 - 17:00 | 17:25 |
| FSXE | Micro Euro Stoxx 50 | € 1 | 09:15 - 17:00 | 17:25 |

**MNK handelt in drie sessies.** Het contract loopt op CME bijna de klok rond,
dus hij handelt in drie vensters (Nederlandse tijd):

| sessie | wintertijd | zomertijd | plat om (winter / zomer) |
| --- | --- | --- | --- |
| Tokyo | 01:15 - 07:00 | 02:15 - 08:00 | 07:25 / 08:25 |
| Europa | 09:15 - 15:00 | 09:15 - 15:00 | 15:25 |
| VS | 15:45 - 21:30 | 15:45 - 21:30 | 21:55 |

Elke sessie heeft een eigen VWAP en een eigen volumevergelijking: een bar van
03:00 wordt vergeleken met eerdere bars van 03:00, niet met de drukte bij de
Amerikaanse opening. Tussen de sessies staat hij altijd plat. Wil je minder
sessies, bijvoorbeeld alleen Tokyo en de VS, zet dan in de config
`"contract_overrides": {"MNK": {"sessions": ["tokyo", "us"]}}`. Voor de
Tokyo-sessie moeten je pc en IB Gateway 's nachts aan blijven.

Wil je naast MES ook MNK, zet dan `"contracts": ["MES", "MNK"]`. De daglimiet en
het aantal trades gelden dan samen per Nederlandse kalenderdag. MNK is jonger en
dunner dan MES: reken op meer slippage, vooral buiten de Tokyo-uren. Doe eerst
een backtest op MNK zelf (`--contract MNK`). Die laat per trade de sessie zien,
zodat je ziet welke sessie iets oplevert.

Alle tijden in de meldingen, het journaal en de backtest staan in Nederlandse tijd.

De Amerikaanse tijden volgen New York (09:45 - 15:30, flat om 15:55). In de
weken dat de VS en Europa niet tegelijk de klok verzetten (maart en eind
oktober) liggen ze voor ons een uur eerder. Dat rekent het programma zelf uit.

**Het signaal** (een voltooide 5-minutenbar, alle vijf moeten kloppen):

1. het volume is minstens 2,5 keer zo hoog als normaal voor dat tijdstip (gemiddelde van de laatste 10 handelsdagen);
2. de slotkoers breekt boven het hoogste punt van het afgelopen uur;
3. het is een sterke bar: groen, en sluit in de bovenste 30 % van zijn bereik;
4. de koers staat boven de VWAP (de gemiddelde prijs van de dag, gewogen naar volume);
5. de bar is niet uitzonderlijk groot (maximaal 2,5 x de gemiddelde beweging), om niet de top van een uitschieter te kopen.

**De trade**: een limietorder net boven de slotkoers (loopt de markt weg,
dan geen aankoop, er wordt niet achteraan gejaagd), een stop net onder het
midden van de signaalbar, een koersdoel op 2 x het risico, en altijd plat
voor het slot. Er blijft nooit een positie 's nachts staan. Standaard alleen
long (kopen); short staat uit.

**De grenzen** (allemaal in `trader/config.json`):

- `max_loss_per_trade_eur` (100): het aantal contracten wordt zo gekozen dat het verlies op de stop, inclusief commissie en slippage, hieronder blijft. Past zelfs 1 contract niet, dan geen trade;
- `max_daily_loss_eur` (250): bereikt het dagresultaat dit verlies, dan sluit hij alles en stopt hij voor die dag. Hij opent ook geen trade die bij een stop-out over deze grens zou gaan;
- `max_trades_per_day` (3), `max_contracts` (2), `max_open_positions` (1);
- `cooldown_after_loss_min` (30): na een verlies 30 minuten geen nieuwe trade in dat contract;
- `max_margin_pct` (50): de margin van een trade mag maximaal de helft van je beschikbare ruimte zijn;
- een positie die je zelf met de hand opent, laat hij met rust, maar zolang die er staat opent hij in dat contract niets.

## Future of CFD

Je kiest zelf of hij de future zelf handelt of de bijbehorende **CFD bij
IBKR**. Het signaal komt in beide gevallen uit het echte beursvolume van de
future, alleen de order gaat naar de CFD:

| signaal (future) | order (CFD bij IBKR) | kosten per order |
| --- | --- | --- |
| MES | IBUS500 (S&P 500) | 0,005 %, min. $ 1 |
| MNQ | IBUST100 (Nasdaq-100) | 0,010 %, min. $ 1 |
| MYM | IBUS30 (Dow) | 0,005 %, min. $ 1 |
| MNK | IBJP225 (Nikkei, in yen) | 0,010 %, min. ¥ 40 |
| FDXS | IBDE40 (DAX) | 0,005 %, min. € 1 |
| FSXE | IBEU50 (Euro Stoxx 50) | 0,010 %, min. € 1 |

Aanzetten in `trader\config.json`: `"execute_as": "cfd"` voor alles, of per
markt `"contract_overrides": {"MES": {"execute_as": "cfd"}}`.

Hoe het werkt: het plan (instap, stop, koersdoel) wordt op de future gemaakt
en daarna verschoven met het actuele verschil tussen CFD en future (de
"basis", live opgevraagd bij IBKR), afgerond op de stapgrootte van de CFD.
Is er geen live CFD-koers, dan geen trade.

Verschillen met de future:
- **fijnere positiegrootte**: 1 CFD beweegt 1 dollar (of euro of yen) per indexpunt, tegen $ 5 bij MES. Het maximum staat in `max_cfd_units` (standaard 10);
- **geen negatief saldo**: als particuliere CFD-klant in de EU kun je niet meer verliezen dan je inleg;
- **meer margin**: de hefboom op index-CFD's is in de EU begrensd (1:20 op grote indices);
- **hogere kosten** voor dezelfde blootstelling: in het testvoorbeeld $ 6,90 per trade voor 10 IBUS500, tegen $ 2,48 voor 2 MES. Vergelijk het zelf met de backtest:
  `python trader-futures\futures.py backtest --contract MES --bars trader\mes-5m.csv --execute cfd`

Voor CFD's moet je in de Client Portal ook de handelsrechten voor **CFD's**
aanzetten. Het futures-data-abonnement blijft nodig voor het signaal.

## Eenmalig instellen

1. **IBKR-rekening** met handelsrechten voor **futures**: in de Client
   Portal onder Instellingen > Accountinstellingen > Handelsrechten
   (Futures: Verenigde Staten en/of Duitsland/Eurex).
2. **Marktdata**: een realtime-abonnement voor CME (en CBOT voor MYM) en/of
   Eurex. Zet "marktdata delen met paper account" aan, anders krijgt je
   paper account vertraagde koersen en komt elk signaal te laat.
3. **IB Gateway** installeren (versie "stable") en inloggen op je **paper
   account**. Ga naar Configure > Settings > API > Settings en stel in:
   - ActiveX and Socket Clients: aan;
   - socket port: 4002 (paper; live is 4001);
   - Read-Only API: uit (in observe-modus maakt het programma zelf een alleen-lezen verbinding);
   - Trusted IPs: 127.0.0.1;
   - en zet auto-restart aan, zodat de Gateway de nachtelijke herstart van IBKR overleeft.
4. **Python 3.10 of nieuwer** (python.org), en in een opdrachtvenster:
   `pip install ib_async tzdata`
5. Zet de repository in een map, bijvoorbeeld `C:\Handelen\day-trader-skill`,
   maak daarin een map `trader`, kopieer `trader-futures\config.example.json`
   naar `trader\config.json` en vul je grenzen in.
6. **Meldingen op je telefoon** (optioneel): installeer de gratis app
   *ntfy*, abonneer je op een lange, onraadbare naam (bijvoorbeeld
   `eren-futures-8f3k29xq`) en zet die bij `"ntfy_topic"` in de config.

## Elke keer

Open een opdrachtvenster in `C:\Handelen\day-trader-skill`.

```
python trader-futures\ib_tools.py status
```
Hier moet PAPER staan, met het contract (bijvoorbeeld MESZ6) en positie 0.
Meldt hij dat IBKR een contract niet kent, zoek het dan op in TWS of de IBKR-app.
Gebruikt IBKR een ander symbool, zet dat in de config, bijvoorbeeld
`"contract_overrides": {"MNK": {"symbol": "..."}}`.

**1. Eerst testen op echte koersen (backtest)**
```
python trader-futures\ib_tools.py download --contract MES --days 60 --out trader\mes-5m.csv
python trader-futures\futures.py backtest --contract MES --bars trader\mes-5m.csv --out trader\backtest.csv
```
`trader\backtest.csv` opent direct in Excel (puntkomma's, decimale komma's).
Kijk vooral naar de verliestrades en de grootste daling ("drawdown"), niet
alleen naar het totaal.

**2. Meekijken zonder orders (observe)**
```
python trader-futures\autotrader.py --mode observe
```
Je krijgt elk signaal als melding, maar er gaat geen order uit. Doe dit
minstens een week.

**3. Zelf laten handelen op paper**
```
python trader-futures\autotrader.py --mode paper
```
Hij weigert te starten als de Gateway op een echte rekening is ingelogd
(paper-rekeningen beginnen met DU). Laat het venster openstaan.

**Stoppen**
- `Ctrl+C`: het programma stopt. Openstaande posities houden hun stop en koersdoel bij IBKR.
- Noodstop: maak een leeg bestand `trader\STOP`. Dan sluit hij alles wat hij zelf geopend heeft en stopt. Hij start pas weer als je dat bestand verwijdert.
- Met de hand één contract sluiten: `python trader-futures\ib_tools.py flatten --contract MES`

**Terugkijken**
- `trader\journal.csv`: elke afgesloten trade (Excel);
- `trader\state\autotrader.log`: alles wat hij deed en waarom, ook signalen die geblokkeerd werden.

## Live gaan (echt geld)

Pas na weken paper trading, en alleen als je dat zelf besluit. Dan:

1. log IB Gateway in op je echte rekening (poort 4001);
2. zet in `trader\config.json`: `"paper": false` en
   `"live_confirm": "IK BEGRIJP DAT DIT ECHT GELD IS"`;
3. start met `--mode live`.

Zonder die twee regels, of met een paper-rekening, weigert hij. Claude
verandert deze instellingen nooit voor je.

## Goed om te weten

- **Het contract wisselt elk kwartaal** (maart, juni, september, december).
  Acht dagen voor de vervaldatum stapt hij vanzelf over op het volgende
  contract. De eerste dagen daarna kunnen er minder signalen zijn, omdat de
  volumevergelijking dunne dagen overslaat.
- **Een stop is een plan, geen garantie.** Bij een snelle markt of een
  koerssprong wordt hij slechter uitgevoerd.
- **Een backtest is geen voorspelling.** Hij laat zien wat de regels op
  oude koersen deden, niet wat ze morgen doen.
- **De pc moet aan blijven** met IB Gateway ingelogd, zolang het programma
  moet handelen. Valt de verbinding weg, dan probeert hij opnieuw te
  verbinden en opent hij intussen niets nieuws; je stop en koersdoel staan
  dan al bij IBKR.
