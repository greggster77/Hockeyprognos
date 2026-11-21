"""Läsbefintliga historikfiler. Ingen databasanslutning och inga skrivningar."""
import json
import sys
from collections import Counter
from pathlib import Path


def check(path):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(data, list):
        raise ValueError(f'{path}: förväntade en lista')
    c = Counter()
    ids = set()
    for row in data:
        ident = row.get('id')
        if not ident or ident in ids:
            raise ValueError(f'{path}: saknat/dubblerat ID {ident}')
        ids.add(ident)
        h, a = row.get('home_goals'), row.get('away_goals')
        if type(h) is not int or type(a) is not int or min(h, a) < 0:
            raise ValueError(f'{path}: ogiltigt 60-minutersresultat {ident}')
        c['1' if h > a else '2' if h < a else 'X'] += 1
        if row.get('final_home_goals') is None or row.get('final_away_goals') is None:
            c['saknar_verifierat_slutresultat'] += 1
    print(f'{Path(path).name}: {len(data)} matcher, 1={c["1"]}, X={c["X"]}, 2={c["2"]}, slutresultat saknas={c["saknar_verifierat_slutresultat"]}')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit('Användning: py kontrollera_historik.py historik_*.json')
    for file in sys.argv[1:]:
        check(file)
