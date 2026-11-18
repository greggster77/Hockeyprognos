# Svenska ligor – testversion

Detta paket bygger på användarens Hockeyprognos-main(1).zip.

## Vad som ändrats
- `backend/swedish_sources.py` är ny och `backend/main.py` anropar den.
- SHL försöker nu hämta grundseriens spelschema direkt från SHL:s publika webb-API, utan `SHL_FEED_URL`.
- HockeyAllsvenskan kan importeras från en JSON-feed via `HA_FEED_URL`, inklusive fält enligt HA:s dokumenterade spelschema. **Ingen verifierad direktadress för HA är ännu implementerad.**
- Resultat efter förlängning/straffar måste innehålla periodresultat 1–3; annars utelämnas matchen för att undvika fel 1X2.
- NHL:s import är oförändrad.

## Viktigt innan publicering
SHL:s faktiska JSON-svar kunde inte nås från testmiljön, så den inbyggda SHL-adaptern är **inte liveverifierad**. Den kan behöva justeras efter ett riktigt API-svar. För att inte störa befintlig produktion, testa gärna som en separat Render-tjänst/branch.

## Test
`python -m unittest discover -s tests -v`

## Kontroll efter driftsättning
1. Öppna `/api/leagues` och läs `error` för SHL och HA.
2. Öppna `/api/matches?league=SHL&days=7`.
3. Om SHL fortfarande har ett fel, spara den exakta texten från `/api/leagues` och Render-loggarna.
4. HA kräver fortsatt en verifierad JSON-feed, konfigurerad med `HA_FEED_URL`.

Datakällor: https://www.shl.se/api/sports-v2/game-schedule ; https://fastrhockey.sportsdataverse.org/reference/ha_schedule.html
