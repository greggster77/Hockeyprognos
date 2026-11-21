"""Read-only historical season preview for Hockeyprognos. Never connects to Neon."""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

from swedish_sources import (
    HEADERS, SHL_CATALOG, SHL_SCHEDULE, find_shl_season,
    pick, parse_shl_schedule, parse_ha_stats,
)

HA_STATS_URL = 'https://hockeyallsvenskan.se/api/all-time-games-stats'


def fetch_shl(client, start_year):
    catalog = client.get(SHL_CATALOG)
    catalog.raise_for_status()
    season = find_shl_season(catalog.json(), start_year + 1)
    info = pick(season, 'seasonInfo', 'season')
    game_type = pick(season, 'gameTypeInfo', 'gameType')
    series = pick(season, 'seriesInfo', 'series')
    params = {
        'seasonUuid': pick(season, 'seasonUuid') or pick(info, 'uuid'),
        'gameTypeUuid': pick(season, 'gameTypeUuid') or pick(game_type, 'uuid'),
        'seriesUuid': pick(season, 'seriesUuid') or pick(series, 'uuid'),
    }
    if not all(params.values()):
        raise ValueError('SHL: season identifiers are missing')
    response = client.get(SHL_SCHEDULE, params=params)
    response.raise_for_status()
    return parse_shl_schedule(response.json())


def ha_request(client, start_year, page, page_size, attempts=3):
    payload = dict(
        league='HA', phase='HA', team_side='all', team='all',
        against_team='all', all_results='all', game_status='all',
        decided_in='all', categories='all', page=page,
        page_size=page_size, season=str(start_year),
    )
    for attempt in range(1, attempts + 1):
        try:
            response = client.post(
                HA_STATS_URL, json=payload,
                headers={**HEADERS, 'Accept': 'application/json'},
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or not isinstance(result.get('results'), list):
                raise ValueError(f'HA page {page}: invalid response structure')
            return result
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            if attempt == attempts:
                raise
            print(f'HA page {page}: network error ({type(exc).__name__}), retry {attempt}/{attempts - 1}', flush=True)
            time.sleep(attempt)


def fetch_ha(client, start_year, page_size=20):
    first = ha_request(client, start_year, 1, page_size)
    count = first.get('count')
    total_pages = first.get('total_pages')
    if not isinstance(count, int) or count < 1 or not isinstance(total_pages, int) or total_pages < 1:
        raise ValueError('HA: missing count or total_pages in response')
    if total_pages != (count + page_size - 1) // page_size:
        raise ValueError(f'HA: inconsistent pagination metadata: count={count}, pages={total_pages}')
    if total_pages > 100:
        raise ValueError('HA: unexpected page count; aborting')
    print(f'HA API reports {count} matches across {total_pages} pages.', flush=True)
    raw = []
    for page in range(1, total_pages + 1):
        data = first if page == 1 else ha_request(client, start_year, page, page_size)
        if data.get('count') != count or data.get('total_pages') != total_pages:
            raise ValueError(f'HA page {page}: total changed during download; aborting')
        if data.get('page') != page:
            raise ValueError(f'HA page {page}: wrong page returned ({data.get("page")})')
        matches = data['results']
        if not matches:
            raise ValueError(f'HA page {page}: empty page; aborting')
        raw.extend(matches)
        print(f'Page {page}/{total_pages}: {len(matches)} records, {len(raw)}/{count} downloaded', flush=True)
    if len(raw) != count:
        raise ValueError(f'HA: expected {count} records, received {len(raw)}; aborting')
    # Parse as one payload to detect duplicate IDs across pages.
    # The source parser omits matches whose regulation score cannot be verified.
    rows = parse_ha_stats({'results': raw})
    if len(rows) != count:
        print(f'WARNING: {count - len(rows)} source records omitted by the parser (e.g. unverified 60-min score).', flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description='Read-only preview of historical hockey seasons')
    parser.add_argument('--league', choices=['SHL', 'HA'], required=True)
    parser.add_argument('--season', type=int, required=True, help='Start year: 2024 = 2024/25')
    parser.add_argument('--save', action='store_true', help='Save JSON locally; never writes to Neon')
    args = parser.parse_args()
    if not 2000 <= args.season <= 2025:
        parser.error('Choose season start year between 2000 and 2025')
    try:
        timeout = httpx.Timeout(connect=15, read=60, write=20, pool=15)
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=HEADERS) as client:
            rows = fetch_shl(client, args.season) if args.league == 'SHL' else fetch_ha(client, args.season)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f'Import preview failed: {exc}', file=sys.stderr)
        return 1
    # Reject API responses from a neighboring season before saving any JSON.
    # SHL/HA regular seasons run in autumn/spring; generous July boundaries.
    earliest = f'{args.season}-07-01'
    latest = f'{args.season + 1}-07-01'
    outside = [row for row in rows if not (earliest <= str(row.get('date', ''))[:10] < latest)]
    if outside:
        example = outside[0]
        print(f'ERROR: {len(outside)} matches outside requested season '
              f'{args.season}/{args.season + 1}; first: '
              f'{example.get("date")} ({example.get("id")}). No JSON saved.', file=sys.stderr)
        return 3
    ids = [row['id'] for row in rows]
    if len(ids) != len(set(ids)):
        print('WARNING: duplicate match IDs; preview rejected.', file=sys.stderr)
        return 2
    status = Counter(row['status'] for row in rows)
    print(f'{args.league} {args.season}/{str(args.season + 1)[-2:]}')
    print(f'Total parsed: {len(rows)}; verified finished: {status["FINISHED"]}; scheduled: {status["SCHEDULED"]}')
    print('READ ONLY: no Neon connection, no database changes, no comparison with existing matches.')
    if args.save:
        path = Path(f'historik_{args.league}_{args.season}_{args.season + 1}_preview.json')
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Local JSON saved: {path.resolve()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
