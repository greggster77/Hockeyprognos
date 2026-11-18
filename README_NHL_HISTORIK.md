# NHL-historik – 2026/27

Denna version bygger på Hockeyprognos_NHL_20matcher_70procent.zip.

- Ny flik **NHL-historik** med alla importerade avslutade grundseriematcher från aktuell säsong.
- Filter på lag, 50 matcher per sida och paginering.
- Nytt API: `/api/history?league=NHL&limit=50&offset=0`, valfritt `&team=NHL:6`.
- Historik visar resultat efter 60 minuter; gamla matcher utan sparade förhandsprognoser visas tydligt som sådana.
- Befintliga NHL-prognoser, loggor och SHL/HA-kod är orörda.
- Befintlig NHL-import från 1 oktober fyller historiken. På Render utan persistent disk kan databasen nollställas vid omstart och måste synkroniseras på nytt.
- Prognosmodellen använder fortsatt 20 matcher och 70% vikt på senaste fem.

Publicera projektet som vanligt via GitHub/Render. Kontrollera `/api/history?league=NHL&limit=5` efter synkronisering.
