from math import exp, factorial
from collections import defaultdict

def poisson(k: int, lam: float) -> float:
    if k < 0 or lam < 0: raise ValueError('Invalid Poisson inputs')
    return exp(-lam) * lam**k / factorial(k)

def update_elo(home: float, away: float, hg: int, ag: int, k: float=24, advantage: float=65):
    expected=1/(1+10**((away-home-advantage)/400))
    actual=1 if hg>ag else 0.5 if hg==ag else 0
    change=k*(actual-expected)
    return home+change, away-change

def normalize_percent(a: float,b: float,c: float):
    vals=[a,b,c]; total=sum(vals)
    if total<=0: raise ValueError('No probability mass')
    raw=[v/total*100 for v in vals]
    floors=[int(v*100) for v in raw]
    missing=10000-sum(floors)
    for i in sorted(range(3),key=lambda i:raw[i]*100-floors[i],reverse=True)[:missing]: floors[i]+=1
    return [v/100 for v in floors]

def predict(history, home_id, away_id):
    # history: completed competition matches sorted by kickoff, no synthetic fallback
    if len(history)<20: raise ValueError('För få historiska matcher för en tillförlitlig prognos (minst 20 krävs).')
    ratings=defaultdict(lambda:1500.0)
    home_stats=defaultdict(list); away_stats=defaultdict(list)
    for m in history:
        if m.home_goals is None or m.away_goals is None: continue
        home_stats[m.home_id].append((m.home_goals,m.away_goals))
        away_stats[m.away_id].append((m.away_goals,m.home_goals))
        ratings[m.home_id],ratings[m.away_id]=update_elo(ratings[m.home_id],ratings[m.away_id],m.home_goals,m.away_goals)
    hs=home_stats[home_id][-10:]; aw=away_stats[away_id][-10:]
    if len(hs)<3 or len(aw)<3: raise ValueError('För lite hemma-/bortahistorik för lagen (minst 3 matcher vardera).')
    league_home=sum(m.home_goals for m in history)/len(history)
    league_away=sum(m.away_goals for m in history)/len(history)
    if league_home<=0 or league_away<=0: raise ValueError('Ogiltigt ligasnitt.')
    avg=lambda arr,i:sum(x[i] for x in arr)/len(arr)
    # shrink towards league averages; Elo relative factor, capped to avoid extremes
    h_attack=(avg(hs,0)+5*league_home)/ (6*league_home)
    h_def=(avg(hs,1)+5*league_away)/ (6*league_away)
    a_attack=(avg(aw,0)+5*league_away)/ (6*league_away)
    a_def=(avg(aw,1)+5*league_home)/ (6*league_home)
    elo_factor=max(.75,min(1.25,10**((ratings[home_id]-ratings[away_id])/1600)))
    xh=max(.15,min(4.5,league_home*h_attack*a_def*elo_factor))
    xa=max(.15,min(4.5,league_away*a_attack*h_def/elo_factor))
    matrix=[(i,j,poisson(i,xh)*poisson(j,xa)) for i in range(9) for j in range(9)]
    ph=sum(p for i,j,p in matrix if i>j); pd=sum(p for i,j,p in matrix if i==j); pa=sum(p for i,j,p in matrix if i<j)
    h,d,a=normalize_percent(ph,pd,pa)
    top=sorted(matrix,key=lambda v:v[2],reverse=True)[:5]
    return dict(home_win=h,draw=d,away_win=a,expected_home=round(xh,2),expected_away=round(xa,2),details={
      'top_scores':[{'score':f'{i}–{j}','probability':round(p/sum(x[2] for x in matrix)*100,2)} for i,j,p in top],
      'home_elo':round(ratings[home_id]),'away_elo':round(ratings[away_id]),
      'home_form':{'played':len(hs),'scored':sum(x[0] for x in hs),'conceded':sum(x[1] for x in hs)},
      'away_form':{'played':len(aw),'scored':sum(x[0] for x in aw),'conceded':sum(x[1] for x in aw)},
      'league_home_avg':round(league_home,2),'league_away_avg':round(league_away,2)})
