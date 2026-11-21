"""Two-step SHL/HA historical import. No updates/deletes. Requires pg_dump backup."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

YEARS = (2023, 2024, 2025)
LEAGUES = ('SHL', 'HA')
COLUMNS = ('id','league','date','home_id','away_id','home_name','away_name','home_goals','away_goals','status')


def fail(message):
    raise ValueError(message)


def load_files(folder):
    records = []
    names = []
    for year in YEARS:
        for league in LEAGUES:
            name = f'historik_{league}_{year}_{year+1}_preview.json'
            path = folder / name
            if not path.is_file():
                fail(f'Saknar {path}')
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, list) or len(data) != 364:
                fail(f'{name}: förväntade 364 matcher, fick {len(data) if isinstance(data,list) else "fel format"}')
            for i, item in enumerate(data, 1):
                if not isinstance(item, dict):
                    fail(f'{name} rad {i}: inte objekt')
                row = dict(item)
                if not all(k in row for k in COLUMNS if k != 'league'):
                    fail(f'{name} rad {i}: saknade fält')
                if row.get('league') not in (None, league) or not isinstance(row['id'], str) or not row['id'].startswith(league+':'):
                    fail(f'{name} rad {i}: fel liga/ID')
                row['league'] = league
                date = row['date']
                if not isinstance(date,str) or not re.match(r'^\d{4}-\d\d-\d\d',date) or not (f'{year}-07-01' <= date[:10] < f'{year+1}-07-01'):
                    fail(f'{name} rad {i}: datum utanför säsong')
                if row['status'] != 'FINISHED' or any(type(row[k]) is not int or row[k] < 0 for k in ('home_goals','away_goals')):
                    fail(f'{name} rad {i}: resultat ej verifierat')
                if any(not isinstance(row[k],str) or not row[k].strip() for k in ('home_id','away_id','home_name','away_name')):
                    fail(f'{name} rad {i}: ogiltigt lag')
                records.append({k:row[k] for k in COLUMNS})
            names.append(name)
    ids = [r['id'] for r in records]
    if len(set(ids)) != len(ids):
        fail('Dubblett-ID i historikfilerna')
    fixtures = [(r['league'],r['date'][:10],r['home_name'].strip().casefold(),r['away_name'].strip().casefold()) for r in records]
    if len(set(fixtures)) != len(fixtures):
        fail('Dubblettmatch i historikfilerna')
    return records, names


def digest(rows):
    return hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def db_read(cur):
    cur.execute('SELECT id,league,date,home_id,away_id,home_name,away_name,home_goals,away_goals,status FROM matches')
    return [dict(zip(COLUMNS,row)) for row in cur.fetchall()]


def logical(row):
    return (str(row['league']).upper(),str(row['date'])[:10],str(row['home_name']).strip().casefold(),str(row['away_name']).strip().casefold())


def compare(incoming,existing):
    by_id = {str(r['id']):r for r in existing}
    by_fixture = {}
    for row in existing:
        by_fixture.setdefault(logical(row),[]).append(row)
    candidates, conflicts = [], []
    counts = Counter()
    for row in incoming:
        old = by_id.get(row['id'])
        if old is not None:
            counts['already_by_id'] += 1
            if logical(old) != logical(row) or (old['home_goals'],old['away_goals']) != (row['home_goals'],row['away_goals']):
                conflicts.append({'id':row['id'],'reason':'existing_id_differs'})
            continue
        if logical(row) in by_fixture:
            counts['already_by_fixture'] += 1
            old = by_fixture[logical(row)]
            if len(old)!=1 or (old[0]['home_goals'],old[0]['away_goals']) != (row['home_goals'],row['away_goals']):
                conflicts.append({'id':row['id'],'reason':'fixture_conflict'})
            continue
        candidates.append(row)
    return candidates,conflicts,dict(counts)


def full_backup(url, destination):
    pg_dump = shutil.which('pg_dump')
    if not pg_dump:
        fail('pg_dump saknas. Installera PostgreSQL client tools och kontrollera PATH. Ingen import tillåts utan full backup.')
    from psycopg.conninfo import conninfo_to_dict
    d = conninfo_to_dict(url)
    env = os.environ.copy()
    mapping = {'host':'PGHOST','port':'PGPORT','user':'PGUSER','password':'PGPASSWORD','dbname':'PGDATABASE','sslmode':'PGSSLMODE','channel_binding':'PGCHANNELBINDING'}
    for k,v in mapping.items():
        if d.get(k):env[v]=str(d[k])
    if not env.get('PGDATABASE'):
        fail('DATABASE_URL saknar databasnamn')
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Credentials never passed as CLI args, and subprocess output never includes connection URL.
    command = [pg_dump,'--format=custom','--no-owner','--no-acl','--file',str(destination)]
    result = subprocess.run(command,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=240)
    if result.returncode != 0 or not destination.exists() or destination.stat().st_size < 100:
        destination.unlink(missing_ok=True)
        fail('pg_dump misslyckades. Kontrollera PostgreSQL-version/anslutning lokalt. Ingen import gjord.')


def main():
    p=argparse.ArgumentParser(description='Säker SHL/HA-import: prepare (read only) eller apply (explicit godkännande)')
    p.add_argument('action',choices=('prepare','apply'))
    p.add_argument('--folder',default='.')
    p.add_argument('--plan',default='historik_importplan_2023_2026.json')
    p.add_argument('--approve',default='',help='SHA256 från prepare-rapporten, krävs för apply')
    a=p.parse_args()
    if not os.getenv('DATABASE_URL'):
        p.error('DATABASE_URL saknas; ingen SQLite-fallback')
    import psycopg
    incoming,names=load_files(Path(a.folder))
    input_hash=digest(incoming)
    plan_path=Path(a.plan)
    if a.action=='prepare':
        with psycopg.connect(os.environ['DATABASE_URL'],connect_timeout=12) as conn:
            with conn.cursor() as cur:
                cur.execute('SET TRANSACTION READ ONLY')
                existing=db_read(cur)
            conn.rollback()
        candidates,conflicts,counts=compare(incoming,existing)
        plan={'mode':'READ ONLY','created_utc':datetime.now(timezone.utc).isoformat(),'files':names,'input_sha256':input_hash,
              'existing_count':len(existing),'candidate_count':len(candidates),'candidates_sha256':digest(candidates),
              'counts':counts,'conflicts':conflicts,'candidate_ids':[r['id'] for r in candidates]}
        plan_path.write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'Neon: {len(existing)} | Historik: {len(incoming)} | Saknade: {len(candidates)} | Konflikter: {len(conflicts)}')
        print(f'Plan: {plan_path.resolve()}')
        if conflicts:
            print('STOPP: konflikter hittades. Ingen import får göras innan dessa undersökts.')
        else:
            print('Förhandskontroll klar. INGA databasändringar. Granska planen före apply.')
            print(f'Godkännandekod: {input_hash}')
        return
    if not plan_path.is_file():fail('Saknar förhandsgranskad plan. Kör prepare först.')
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    if plan.get('conflicts'):fail('Planen innehåller konflikter. Import stoppad.')
    if not a.approve or a.approve!=plan.get('input_sha256') or input_hash!=plan.get('input_sha256'):
        fail('Godkännandekod eller filhash matchar inte. Kör prepare på nytt.')
    if len(plan.get('candidate_ids',[]))!=plan.get('candidate_count'):
        fail('Ogiltig importplan')
    # Full database backup is mandatory before ANY write. No DB write happens here.
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    backup=Path('neon_backups')/f'hockeyprognos_full_{stamp}.dump'
    print('Skapar FULL PostgreSQL-backup innan import...')
    full_backup(os.environ['DATABASE_URL'],backup)
    print(f'Backup skapad: {backup.resolve()} ({backup.stat().st_size} bytes)')
    with psycopg.connect(os.environ['DATABASE_URL'],connect_timeout=12) as conn:
        try:
            with conn.cursor() as cur:
                # Lock table to prevent concurrent inserts/updates while verifying the snapshot.
                cur.execute('LOCK TABLE matches IN SHARE ROW EXCLUSIVE MODE')
                existing=db_read(cur)
                candidates,conflicts,counts=compare(incoming,existing)
                if conflicts or len(existing)!=plan['existing_count'] or len(candidates)!=plan['candidate_count'] or digest(candidates)!=plan['candidates_sha256']:
                    fail('Neon har ändrats sedan prepare eller konflikter hittades. ROLLBACK. Kör prepare på nytt.')
                placeholders=','.join(['%s']*len(COLUMNS))
                sql=f"INSERT INTO matches ({','.join(COLUMNS)}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING"
                inserted=0
                for row in candidates:
                    cur.execute(sql,tuple(row[k] for k in COLUMNS))
                    if cur.rowcount!=1:
                        fail('INSERT hoppade över match; ROLLBACK')
                    inserted+=1
                if inserted!=len(candidates):fail('Antal INSERT matchar inte; ROLLBACK')
                cur.execute('SELECT COUNT(*) FROM matches')
                total=cur.fetchone()[0]
                if total!=len(existing)+inserted:fail('Efterkontroll misslyckades; ROLLBACK')
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    print(f'IMPORT KLAR: {inserted} nya matcher. Totalt {total}. Ingen UPDATE/DELETE utförd.')
    print(f'Backup: {backup.resolve()}')


if __name__=='__main__':
    try:main()
    except Exception as e:
        print(f'STOPP: {e}',file=sys.stderr)
        sys.exit(1)
