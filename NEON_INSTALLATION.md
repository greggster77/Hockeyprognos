# Hockeyprognos 3.1 – Neon PostgreSQL

## Vad är ändrat?
- `backend/storage.py` väljer Neon PostgreSQL när `DATABASE_URL` finns, annars befintlig SQLite (`DB_PATH`).
- Alla befintliga tabeller skapas automatiskt i Neon vid FastAPI-start.
- Matchhistorik, SHL-statistikens snapshots, prognosarkiv och modellutvärderingar lagras i samma databas.
- `/api/storage/status` testar faktisk databasåtkomst och visar antal matcher/snapshots.
- Befintlig 1/X/2-modell och H2H-testmodell är oförändrade.

## Installera på Render
1. Behåll `DATABASE_URL` i Render > Environment (PostgreSQL URI från Neon). Behåll `DB_PATH` under övergången.
2. Ersätt projektfilerna och kör `git add .`, `git commit -m "Connect Hockeyprognos to Neon PostgreSQL"`, `git push`.
3. Vänta på Render `Live`. Om deploy misslyckas, läs Deploy logs. Databaskopplingsfel gör att servern inte startar; det är avsiktligt för att undvika tyst dataförlust.
4. Öppna `https://hockeyprognos.onrender.com/api/storage/status`. Förväntat `engine: neon-postgresql`, `status: ok`.
5. Öppna `/api/shl/statistics` och kontrollera `storage_persistent: true`. Nya data sparas vid schemalagd uppdatering.

## Viktigt om tidigare data
Det sker **ingen automatisk kopiering** från gammal SQLite till Neon. Render Free kan ha haft en temporär SQLite-fil; data i den följer inte automatiskt med. För en säker historikmigrering behövs en faktisk kopia av den gamla `.db`-filen och en separat migrering innan man påstår att äldre prognoser finns kvar. Byt inte tillbaka till SQLite efter att Neon tagits i drift utan att planera synkronisering.

## Lokal utveckling
Utan `DATABASE_URL` används SQLite. För att testa Neon lokalt, sätt `DATABASE_URL` som en hemlig miljövariabel (inte i Git) och kör Python-backenden. Projektet har inget npm-buildskript; Docker-bygget och Python-tester är relevanta kontroller.

## Säkerhet
Lägg aldrig `DATABASE_URL`, `.env`, `.env.local` eller lösenord i Git. Status-endpointen visar inga hemligheter.
