# Free, quota-limited regulation-time 1X2 comparison.
import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
import httpx

LOG = logging.getLogger(__name__)
SPORTS = {'SHL':'icehockey_sweden_hockey_league','HA':'icehockey_sweden_allsvenskan','NHL':'icehockey_nhl'}
API = 'https://api.the-odds-api.com/v4/sports/{sport}/odds'


def setup(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS odds_snapshots (
        event_id TEXT NOT NULL, league TEXT NOT NULL, commence_time TEXT NOT NULL,
        home_name TEXT NOT NULL, away_name TEXT NOT NULL, fetched_at TEXT NOT NULL,
        bookmakers INTEGER NOT NULL, market_probs TEXT NOT NULL, mean_odds TEXT NOT NULL,
        PRIMARY KEY(event_id, fetched_at));
        CREATE INDEX IF NOT EXISTS idx_odds_league_start ON odds_snapshots(league, commence_time);
        CREATE TABLE IF NOT EXISTS odds_quota (
        month TEXT PRIMARY KEY, used INTEGER NOT NULL DEFAULT 0, remaining INTEGER);
        CREATE TABLE IF NOT EXISTS odds_sync (
        league TEXT PRIMARY KEY, attempted_at TEXT, error TEXT, saved INTEGER NOT NULL DEFAULT 0);
    ''')


def canonical(name):
    name = unicodedata.normalize('NFKD', str(name or '')).casefold()
    name = ''.join(ch for ch in name if not unicodedata.combining(ch))
    name = re.sub(r'[^a-z0-9]+', ' ', name).strip()
    for suffix in (' hockey club', ' hockey', ' hc', ' if', ' aik', ' bk'):
        if name.endswith(suffix): name = name[:-len(suffix)].strip()
    return name


def parse_event(event):
    home, away = event.get('home_team',''), event.get('away_team','')
    samples=[]
    for book in event.get('bookmakers',[]):
        for market in book.get('markets',[]):
            if market.get('key') != 'h2h': continue
            outcomes=market.get('outcomes',[])
            if len(outcomes) != 3: continue  # 2-way includes OT/shootout: NEVER use
            prices={}
            for outcome in outcomes:
                name=outcome.get('name','')
                key=('1' if canonical(name)==canonical(home) else
                     '2' if canonical(name)==canonical(away) else
                     'X' if canonical(name) in ('draw','tie') else None)
                try: price=float(outcome.get('price',0))
                except (ValueError,TypeError): continue
                if key and price > 1.0: prices[key]=price
            if len(prices)!=3: continue
            implied={k:1.0/prices[k] for k in ('1','X','2')}
            total=sum(implied.values())
            if not 0.95 <= total <= 1.35: continue
            samples.append((prices,{k:implied[k]/total for k in implied}))
            break
    if not samples: return None
    return {'bookmakers':len(samples),
            'market_probs':{k:round(100*sum(p[k] for _,p in samples)/len(samples),2) for k in ('1','X','2')},
            'mean_odds':{k:round(sum(p[k] for p,_ in samples)/len(samples),3) for k in ('1','X','2')}}


def month_now(): return datetime.now(timezone.utc).strftime('%Y-%m')


def fetch_league(c, league):
    key=os.getenv('ODDS_API_KEY','').strip()
    if not key: return {'status':'not_configured','saved':0}
    month=month_now()
    quota=c.execute('SELECT used,remaining FROM odds_quota WHERE month=?',(month,)).fetchone()
    used=int(quota['used']) if quota else 0
    remaining=quota['remaining'] if quota else None
    # Hard local cap; reserve capacity in case provider charges more than expected.
    if used >= 400 or (remaining is not None and remaining < 20):
        return {'status':'quota_guard','saved':0,'used':used,'remaining':remaining}
    timestamp=datetime.now(timezone.utc).isoformat()
    try:
        with httpx.Client(timeout=15,follow_redirects=True) as client:
            response=client.get(API.format(sport=SPORTS[league]),params={
                'apiKey':key,'regions':'eu','markets':'h2h','oddsFormat':'decimal'})
        # On an error, do not burn credits on retries.
        header_used=response.headers.get('x-requests-used')
        header_remaining=response.headers.get('x-requests-remaining')
        if header_used is not None:
            new_used=int(header_used)
        else: new_used=used+1
        new_remaining=int(header_remaining) if header_remaining is not None else remaining
        c.execute('INSERT INTO odds_quota(month,used,remaining) VALUES(?,?,?) ON CONFLICT(month) DO UPDATE SET used=excluded.used,remaining=excluded.remaining',(month,max(used,new_used),new_remaining))
        response.raise_for_status()
        events=response.json()
        if not isinstance(events,list): raise ValueError('Unexpected API payload')
        saved=0
        for event in events:
            result=parse_event(event)
            if not result: continue
            try:
                start=datetime.fromisoformat(event['commence_time'].replace('Z','+00:00'))
            except (ValueError,KeyError,AttributeError): continue
            if start <= datetime.now(timezone.utc): continue
            c.execute('''INSERT INTO odds_snapshots VALUES(?,?,?,?,?,?,?,?,?)''',(
                str(event['id']),league,event['commence_time'],event['home_team'],event['away_team'],
                timestamp,result['bookmakers'],json.dumps(result['market_probs']),json.dumps(result['mean_odds'])))
            saved+=1
        c.execute('''INSERT INTO odds_sync VALUES(?,?,?,?) ON CONFLICT(league) DO UPDATE SET attempted_at=excluded.attempted_at,error=excluded.error,saved=excluded.saved''',(league,timestamp,None,saved))
        return {'status':'ok','saved':saved,'used':new_used,'remaining':new_remaining}
    except (httpx.HTTPError,ValueError,KeyError,TypeError) as exc:
        LOG.warning('Odds fetch %s: %s',league,exc)
        c.execute('''INSERT INTO odds_sync VALUES(?,?,?,?) ON CONFLICT(league) DO UPDATE SET attempted_at=excluded.attempted_at,error=excluded.error,saved=excluded.saved''',(league,timestamp,str(exc)[:250],0))
        return {'status':'error','saved':0}


def for_match(c, league, home, away, match_date):
    try: target=datetime.fromisoformat(match_date.replace('Z','+00:00'))
    except (AttributeError,ValueError): return None
    rows=c.execute('''SELECT * FROM odds_snapshots WHERE league=? AND commence_time>=? AND commence_time<=? ORDER BY fetched_at DESC LIMIT 120''',(
        league,(target.replace(tzinfo=timezone.utc)).isoformat()[:10]+'T00:00:00',
        (target.replace(tzinfo=timezone.utc)).isoformat()[:10]+'T23:59:59Z')).fetchall()
    # Match by both team names and kickoff within 3h, never by team alone.
    for row in rows:
        if canonical(row['home_name'])!=canonical(home) or canonical(row['away_name'])!=canonical(away): continue
        try: start=datetime.fromisoformat(row['commence_time'].replace('Z','+00:00'))
        except ValueError: continue
        if abs((start-target).total_seconds()) > 3*3600: continue
        if datetime.fromisoformat(row['fetched_at'].replace('Z','+00:00')) >= target: continue
        return {'probabilities':json.loads(row['market_probs']),'mean_odds':json.loads(row['mean_odds']),
                'bookmakers':row['bookmakers'],'fetched_at':row['fetched_at'],
                'market':'1X2 efter 60 minuter (tre utfall)','source':'The Odds API · EU'}
    return None
