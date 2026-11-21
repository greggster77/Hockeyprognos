"""Read-only comparison of three historical Swedish hockey seasons against Neon."""
import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

FIELDS = ('id', 'league', 'date', 'home_id', 'away_id', 'home_name', 'away_name', 'home_goals', 'away_goals', 'status')
PATTERN = re.compile(r'^historik_(SHL|HA)_(\d{4})_(\d{4})_preview\.json$')
YEARS = (2023, 2024, 2025)
LEAGUES = ('SHL', 'HA')


def fixture_key(row):
    return (str(row['league']).upper(), str(row['date'])[:10],
            str(row['home_name']).strip().casefold(),
            str(row['away_name']).strip().casefold())


def main():
    parser = argparse.ArgumentParser(description='Read-only historical comparison against Neon')
    parser.add_argument('--folder', default='.')
    parser.add_argument('--report', default='historik_jamforelse_2023_2026.json')
    args = parser.parse_args()
    folder = Path(args.folder)
    files = [folder / f'historik_{league}_{year}_{year+1}_preview.json'
             for year in YEARS for league in LEAGUES]
    absent = [p.name for p in files if not p.is_file()]
    if absent:
        parser.error('Missing required season files: ' + ', '.join(absent))
    incoming = []
    for path in files:
        match = PATTERN.fullmatch(path.name)
        league, start, end = match.group(1), int(match.group(2)), int(match.group(3))
        rows = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(rows, list) or not rows:
            raise ValueError(f'{path.name}: expected nonempty match list')
        for index, original in enumerate(rows, 1):
            if not isinstance(original, dict):
                raise ValueError(f'{path.name}, record {index}: not an object')
            row = dict(original)
            mid = row.get('id')
            if not isinstance(mid, str) or not mid.startswith(league + ':'):
                raise ValueError(f'{path.name}, record {index}: invalid league-prefixed ID')
            if row.get('league') not in (None, league):
                raise ValueError(f'{path.name}, record {index}: league mismatch')
            row['league'] = league
            if any(field not in row for field in FIELDS):
                raise ValueError(f'{path.name}, record {index}: missing required match field')
            date = row['date']
            if not isinstance(date, str) or not re.match(r'^\d{4}-\d{2}-\d{2}', date):
                raise ValueError(f'{path.name}, record {index}: invalid date')
            if not (f'{start}-07-01' <= date[:10] < f'{end}-07-01'):
                raise ValueError(f'{path.name}, record {index}: date outside requested season: {date}')
            if any(not isinstance(row[k], str) or not row[k].strip() for k in ('home_id', 'away_id', 'home_name', 'away_name')):
                raise ValueError(f'{path.name}, record {index}: invalid team fields')
            if row['status'] != 'FINISHED' or any(type(row[k]) is not int or row[k] < 0 for k in ('home_goals', 'away_goals')):
                raise ValueError(f'{path.name}, record {index}: unverified result')
            row['_source_file'] = path.name
            incoming.append(row)

    if not os.getenv('DATABASE_URL'):
        parser.error('DATABASE_URL not set; refusing SQLite fallback')
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        parser.error('Install psycopg: py -m pip install "psycopg[binary]"')

    # Explicitly read-only transaction; no SQL changes to Neon.
    with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row, connect_timeout=12) as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('SELECT id, league, date, home_id, away_id, home_name, away_name, home_goals, away_goals, status FROM matches')
            existing = cur.fetchall()
        conn.rollback()

    by_id = {str(r['id']): r for r in existing}
    by_fixture = {}
    for row in existing:
        by_fixture.setdefault(fixture_key(row), []).append(row)
    seen_ids = set()
    seen_fixtures = set()
    counts = Counter()
    problems = []
    candidates = []
    for row in incoming:
        mid = row['id']
        fixture = fixture_key(row)
        if mid in seen_ids:
            counts['duplicate_json_ids'] += 1
            problems.append({'type': 'duplicate_json_id', 'id': mid})
            continue
        seen_ids.add(mid)
        if fixture in seen_fixtures:
            counts['duplicate_json_fixtures'] += 1
            problems.append({'type': 'duplicate_json_fixture', 'id': mid})
            continue
        seen_fixtures.add(fixture)
        if mid in by_id:
            old = by_id[mid]
            if fixture_key(old) != fixture:
                counts['id_conflicts'] += 1
                problems.append({'type': 'id_conflict', 'id': mid})
            else:
                counts['already_exists_by_id'] += 1
                if (old['home_goals'], old['away_goals']) != (row['home_goals'], row['away_goals']):
                    counts['existing_score_differences'] += 1
                    problems.append({'type': 'existing_score_difference', 'id': mid})
            continue
        if fixture in by_fixture:
            counts['already_exists_by_fixture'] += 1
            continue
        counts['missing_candidates'] += 1
        candidates.append({k: row[k] for k in FIELDS})

    report = {'mode': 'READ ONLY - NO IMPORT', 'files': [p.name for p in files],
              'database_rows': len(existing), 'historical_rows': len(incoming),
              'counts': dict(counts), 'problems': problems,
              'missing_candidates': candidates,
              'warning': 'Fixture matching by names/date can miss aliases and timezone differences. Candidates are NOT approved for insertion.'}
    destination = Path(args.report)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(f'Existing Neon matches: {len(existing)}; selected history: {len(incoming)}')
    for label, count in sorted(counts.items()):
        print(f'{label}: {count}')
    print(f'Local report: {destination.resolve()}')
    print('READ ONLY: no matches inserted, updated or deleted.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'Comparison stopped: {exc}', file=sys.stderr)
        sys.exit(1)
