# NHL-prognosmodell – 20 matcher / 70 %

- Använder enbart avslutade NHL-grundseriematcher från aktuell säsong, före respektive matchstart.
- Form baseras på senaste 20 matcher per lag, oavsett spelplats. Senaste fem står för 70 % av formvikten, föregående 15 för 30 %. Om färre matcher finns används tillgängliga matcher.
- Hemma-/bortastatistik från samma 20 matcher blandas med lagets totalform och krymps mot totalform vid litet underlag.
- Elo räknas kronologiskt från säsongsstart och Poisson ger 1X2 efter ordinarie tid.
- NHL-import börjar 1 oktober för aktuell säsong och återanvänder färdiga resultat som redan finns i databasen.
- Prognoser för framtida matcher uppdateras efter synkronisering. Historiska prognoser bevaras.
- NHL-logotyper och webbgränssnitt har inte ändrats. Svenska ligornas API-status är oförändrad.

## Installation

Lägg projektfilerna i GitHub-repot och distribuera till Render. Ingen ny miljövariabel behövs. Vid omstart kan första synkroniseringen ta längre tid eftersom hela pågående säsongen hämtas. På Render Free är `/tmp/hockey.db` inte beständig.

## Tester

`cd backend && python -m unittest -v test_nhl_model`

Fyra enhetstester har körts lokalt. Liveanrop till NHL:s API och faktisk Render-distribution har inte verifierats i denna miljö.
