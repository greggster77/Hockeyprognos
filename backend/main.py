import os, json, logging, sqlite3, threading
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
from model import predict

ROOT=Path(__file__).resolve().parent.parent
DB=Path(os.getenv('DB_PATH',str(ROOT/'hockey.db')))
LEAGUES={'SHL':'SHL','HA':'HockeyAllsvenskan','NHL':'NHL'}
log=logging.getLogger(__name__)
scheduler=BackgroundScheduler(timezone='UTC')
def db():
    conn=sqlite3.connect(DB);conn.row_factory=sqlite3.Row;return conn
def init():
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS matches (id TEXT PRIMARY KEY,league TEXT NOT NULL,date TEXT NOT NULL,home_id TEXT NOT NULL,away_id TEXT NOT NULL,home_name TEXT NOT NULL,away_name TEXT NOT NULL,home_goals INTEGER,away_goals INTEGER,status TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS predictions (match_id TEXT PRIMARY KEY,created_at TEXT NOT NULL,home_win REAL,draw REAL,away_win REAL,expected_home REAL,expected_away REAL,details TEXT NOT NULL,FOREIGN KEY(match_id) REFERENCES matches(id));
        CREATE TABLE IF NOT EXISTS prediction_results (match_id TEXT PRIMARY KEY,actual TEXT NOT NULL,brier REAL NOT NULL,evaluated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sync_status (league TEXT PRIMARY KEY,updated_at TEXT,error TEXT);''')
def now():return datetime.now(timezone.utc).isoformat()
def store(league, games):
    with db() as c:
        for g in games:
            c.execute('''INSERT INTO matches VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET date=excluded.date,home_name=excluded.home_name,away_name=excluded.away_name,home_goals=excluded.home_goals,away_goals=excluded.away_goals,status=excluded.status,updated_at=excluded.updated_at''', (g['id'],league,g['date'],g['home_id'],g['away_id'],g['home_name'],g['away_name'],g.get('home_goals'),g.get('away_goals'),g['status'],now()))
        c.execute('INSERT INTO sync_status VALUES (?,?,NULL) ON CONFLICT(league) DO UPDATE SET updated_at=excluded.updated_at,error=NULL',(league,now()))
def error(league, message):
    with db() as c:c.execute('INSERT INTO sync_status VALUES (?,?,?) ON CONFLICT(league) DO UPDATE SET error=excluded.error',(league,now(),str(message)[:500]))
def normalize_nhl(game):
    # NHL final score includes OT/SO; use regulation period scoring ONLY.
    gid=str(game['id']);state=game.get('gameState','')
    complete=state in ('FINAL','OFF')
    periods=game.get('periodDescriptor',{}).get('number',0)
    h=game['homeTeam'];a=game['awayTeam']
    home_goals=away_goals=None
    if complete:
        # NHL schedule endpoint doesn't reliably expose per-period goals.
        # Regulation scores are obtained from gamecenter landing endpoint.
        return None
    return dict(id='NHL:'+gid,date=game['startTimeUTC'],home_id='NHL:'+str(h['id']),away_id='NHL:'+str(a['id']),home_name=h.get('placeName',{}).get('default','')+' '+h.get('commonName',{}).get('default',h.get('abbrev','')),away_name=a.get('placeName',{}).get('default','')+' '+a.get('commonName',{}).get('default',a.get('abbrev','')),home_goals=home_goals,away_goals=away_goals,status='SCHEDULED')
def nhl_final(g,landing):
    # sum first 3 periods from scoring summary; shootout/OT excluded.
    scoring=landing.get('summary',{}).get('scoring',[])
    if len(scoring)<3:raise ValueError('Periodresultat saknas i NHL-källan')
    hg=sum(int(p['homeScore']) for p in scoring[:3]);ag=sum(int(p['awayScore']) for p in scoring[:3])
    return dict(id='NHL:'+str(g['id']),date=g['startTimeUTC'],home_id='NHL:'+str(g['homeTeam']['id']),away_id='NHL:'+str(g['awayTeam']['id']),home_name=g['homeTeam'].get('abbrev','Hemma'),away_name=g['awayTeam'].get('abbrev','Borta'),home_goals=hg,away_goals=ag,status='FINISHED')
def fetch_nhl():
    # NHL's public API; no fabricated fixtures.
    start=date.today()-timedelta(days=100)
    end=date.today()+timedelta(days=21)
    games={}
    with httpx.Client(timeout=18,follow_redirects=True) as client:
        d=start
        while d<=end:
            response=client.get(f'https://api-web.nhle.com/v1/schedule/{d.isoformat()}');response.raise_for_status()
            for week in response.json().get('gameWeek',[]):
                for g in week.get('games',[]):games[str(g['id'])]=g
            d+=timedelta(days=7)
        out=[]
        for g in games.values():
            if g.get('gameType')!=2:continue
            if g.get('gameState') in ('FINAL','OFF'):
                try:
                    r=client.get(f"https://api-web.nhle.com/v1/gamecenter/{g['id']}/landing");r.raise_for_status()
                    out.append(nhl_final(g,r.json()))
                except (KeyError,ValueError,httpx.HTTPError) as e:log.warning('Skip incomplete NHL regulation score %s: %s',g['id'],e)
            else:
                row=normalize_nhl(g)
                if row:out.append(row)
    return out
def fetch_swedish(league):
    # Operator supplies a licensed JSON feed; never guess undocumented endpoints.
    url=os.getenv(f'{league}_FEED_URL')
    if not url:raise ValueError('Ingen datakälla är konfigurerad för '+LEAGUES[league])
    headers={}
    token=os.getenv(f'{league}_FEED_TOKEN')
    if token:headers['Authorization']='Bearer '+token
    with httpx.Client(timeout=25) as client:
        r=client.get(url,headers=headers);r.raise_for_status();items=r.json()
    if not isinstance(items,list):raise ValueError('Datakällan måste returnera en JSON-lista')
    out=[]
    for x in items:
        for key in ('id','date','home_id','away_id','home_name','away_name','status'):
            if key not in x:raise ValueError('Saknat fält: '+key)
        if x['status']=='FINISHED' and (x.get('home_goals') is None or x.get('away_goals') is None):raise ValueError('Resultat efter 60 minuter saknas')
        out.append({**x,'id':league+':'+str(x['id']),'home_id':league+':'+str(x['home_id']),'away_id':league+':'+str(x['away_id'])})
    return out
class HistoricalMatch:
    def __init__(self,r):self.home_id=r['home_id'];self.away_id=r['away_id'];self.home_goals=r['home_goals'];self.away_goals=r['away_goals']
def recompute():
    with db() as c:
        for match in c.execute("SELECT * FROM matches WHERE status='SCHEDULED' AND date>? ORDER BY date",(now(),)).fetchall():
            if c.execute('SELECT 1 FROM predictions WHERE match_id=?',(match['id'],)).fetchone():continue
            hist=c.execute("SELECT * FROM matches WHERE league=? AND status='FINISHED' AND date<? ORDER BY date",(match['league'],match['date'])).fetchall()
            try:p=predict([HistoricalMatch(r) for r in hist],match['home_id'],match['away_id'])
            except ValueError:continue
            c.execute('INSERT INTO predictions VALUES (?,?,?,?,?,?,?,?)',(match['id'],now(),p['home_win'],p['draw'],p['away_win'],p['expected_home'],p['expected_away'],json.dumps(p['details'])))
        for m in c.execute("SELECT m.*,p.home_win,p.draw,p.away_win FROM matches m JOIN predictions p ON p.match_id=m.id WHERE m.status='FINISHED' AND m.home_goals IS NOT NULL AND NOT EXISTS (SELECT 1 FROM prediction_results r WHERE r.match_id=m.id)").fetchall():
            actual='1' if m['home_goals']>m['away_goals'] else 'X' if m['home_goals']==m['away_goals'] else '2'
            probs=[m['home_win']/100,m['draw']/100,m['away_win']/100]
            brier=sum((v-(1 if k==actual else 0))**2 for k,v in zip(['1','X','2'],probs))
            c.execute('INSERT INTO prediction_results VALUES (?,?,?,?)',(m['id'],actual,brier,now()))
def sync():
    for league in LEAGUES:
        try:store(league,fetch_nhl() if league=='NHL' else fetch_swedish(league))
        except Exception as e:log.exception('Sync failed %s',league);error(league,e)
    recompute()
@asynccontextmanager
async def lifespan(app):
    init();scheduler.add_job(sync,'interval',hours=3,id='sync',max_instances=1,replace_existing=True);scheduler.start()
    # Keep the web service responsive while NHL history is downloaded.
    threading.Thread(target=sync, name='initial-hockey-sync', daemon=True).start()
    yield;scheduler.shutdown(wait=False)
app=FastAPI(title='Hockeyprognos',lifespan=lifespan)
@app.get('/api/leagues')
def leagues():
    with db() as c:
        states={r['league']:dict(updated_at=r['updated_at'],error=r['error']) for r in c.execute('SELECT * FROM sync_status')}
    return [{'code':k,'name':v,**states.get(k,{'error':'Data har ännu inte hämtats','updated_at':None})} for k,v in LEAGUES.items()]
def serialize(c,m):
    p=c.execute('SELECT * FROM predictions WHERE match_id=?',(m['id'],)).fetchone()
    return {'id':m['id'],'date':m['date'],'league':m['league'],'home':m['home_name'],'away':m['away_name'],'status':m['status'],'score':{'home':m['home_goals'],'away':m['away_goals']},'prediction':None if p is None else {'home_win':p['home_win'],'draw':p['draw'],'away_win':p['away_win'],'expected_home':p['expected_home'],'expected_away':p['expected_away'],'details':json.loads(p['details']),'created_at':p['created_at']}}
@app.get('/api/matches')
def matches(day:date|None=None,league:str|None=None,days:int=Query(1,ge=1,le=14)):
    if league and league not in LEAGUES:raise HTTPException(400,'Okänd liga')
    day=day or date.today()
    with db() as c:
        end=(day+timedelta(days=days)).isoformat()
        rows=c.execute('SELECT * FROM matches WHERE substr(date,1,10)>=? AND substr(date,1,10)<? '+('AND league=? ' if league else '')+'ORDER BY date',((day.isoformat(),end,league) if league else (day.isoformat(),end))).fetchall()
        return [serialize(c,m) for m in rows]
@app.get('/api/matches/{match_id:path}')
def detail(match_id:str):
    with db() as c:
        m=c.execute('SELECT * FROM matches WHERE id=?',(match_id,)).fetchone()
        if not m:raise HTTPException(404,'Matchen finns inte')
        return serialize(c,m)
@app.get('/api/performance')
def performance():
    with db() as c:
        r=c.execute('SELECT COUNT(*) n,AVG(brier) b FROM prediction_results').fetchone()
        return {'evaluated':r['n'],'mean_brier':r['b']}
@app.get('/health')
def health():return {'status':'ok'}
app.mount('/',StaticFiles(directory=str(ROOT/'web'),html=True),name='web')
