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

def weighted_form(matches, team_id, limit=20, recent=5, recent_share=0.70):
    """Latest 20 team games; latest five get 70% of the total weight.

    Returns weighted GF/GA overall and split home/away; small samples are
    shrunk toward overall form rather than trusted independently.
    """
    selected = [m for m in matches if m.home_id == team_id or m.away_id == team_id][-limit:]
    if not selected:
        raise ValueError("Laget saknar historiska matcher denna säsong")
    n_recent = min(recent, len(selected))
    older = len(selected) - n_recent
    if older:
        weights = [(1 - recent_share) / older] * older + [recent_share / n_recent] * n_recent
    else:
        weights = [1 / n_recent] * n_recent
    records = []
    for m, w in zip(selected, weights):
        is_home = m.home_id == team_id
        gf = m.home_goals if is_home else m.away_goals
        ga = m.away_goals if is_home else m.home_goals
        records.append((gf, ga, is_home, w))
    def avg(rows, idx):
        total = sum(row[3] for row in rows)
        return sum(row[idx] * row[3] for row in rows) / total if total else None
    return {"played": len(records), "gf": avg(records, 0), "ga": avg(records, 1),
            "home": [r for r in records if r[2]], "away": [r for r in records if not r[2]],
            "avg": avg}


def dixon_coles_factor(home_goals, away_goals, home_rate, away_rate, rho=-0.08):
    """Low-score correlation adjustment; only applied to the experimental model.

    Negative rho increases 0-0 and 1-1 relative to independent Poisson.
    The parameter is a hypothesis to validate with walk-forward backtesting.
    """
    if home_goals == 0 and away_goals == 0:
        return 1 - home_rate * away_rate * rho
    if home_goals == 0 and away_goals == 1:
        return 1 + home_rate * rho
    if home_goals == 1 and away_goals == 0:
        return 1 + away_rate * rho
    if home_goals == 1 and away_goals == 1:
        return 1 - rho
    return 1.0


def predict(history, home_id, away_id, league="NHL", variant="current"):
    if variant not in ("current", "experimental"):
        raise ValueError("Okänd modellvariant")
    # history contains ONLY completed matches before the prediction date,
    # sorted chronologically, within the current NHL season.
    if len(history) < 20:
        raise ValueError("För få matcher i säsongen (minst 20 krävs).")
    ratings = defaultdict(lambda: 1500.0)
    for m in history:
        if m.home_goals is None or m.away_goals is None:
            continue
        ratings[m.home_id], ratings[m.away_id] = update_elo(
            ratings[m.home_id], ratings[m.away_id], m.home_goals, m.away_goals)
    window = 10 if league == "SHL" else 20
    hf = weighted_form(history, home_id, limit=window)
    af = weighted_form(history, away_id, limit=window)
    if hf["played"] < 3 or af["played"] < 3:
        raise ValueError("För få matcher för något av lagen (minst 3).")
    league_home = sum(m.home_goals for m in history) / len(history)
    league_away = sum(m.away_goals for m in history) / len(history)
    if league_home <= 0 or league_away <= 0:
        raise ValueError("Ogiltigt ligasnitt")

    # Blend venue-specific form with overall weighted form, using sample-size
    # shrinkage. Venue form counts only games within each team's last 20.
    def venue_mean(form, venue, index):
        rows = form[venue]
        venue_avg = form["avg"](rows, index)
        if venue_avg is None:
            return form["gf" if index == 0 else "ga"]
        venue_strength = len(rows) / (len(rows) + 5)
        return venue_strength * venue_avg + (1 - venue_strength) * form["gf" if index == 0 else "ga"]

    hgf, hga = venue_mean(hf, "home", 0), venue_mean(hf, "home", 1)
    agf, aga = venue_mean(af, "away", 0), venue_mean(af, "away", 1)
    # Shrink observed scoring ratios toward league mean to avoid extreme values.
    h_attack = (hgf + 5 * league_home) / (6 * league_home)
    h_def = (hga + 5 * league_away) / (6 * league_away)
    a_attack = (agf + 5 * league_away) / (6 * league_away)
    a_def = (aga + 5 * league_home) / (6 * league_home)
    elo_factor = max(.75, min(1.25, 10 ** ((ratings[home_id] - ratings[away_id]) / 1600)))
    xh = max(.15, min(4.5, league_home * h_attack * a_def * elo_factor))
    xa = max(.15, min(4.5, league_away * a_attack * h_def / elo_factor))
    matrix = [
        (i, j, poisson(i, xh) * poisson(j, xa) *
         (dixon_coles_factor(i, j, xh, xa) if variant == "experimental" else 1.0))
        for i in range(9) for j in range(9)
    ]
    ph = sum(p for i, j, p in matrix if i > j)
    pd = sum(p for i, j, p in matrix if i == j)
    pa = sum(p for i, j, p in matrix if i < j)
    h, d, a = normalize_percent(ph, pd, pa)
    mass = sum(p for _, _, p in matrix)
    top = sorted(matrix, key=lambda v: v[2], reverse=True)[:5]
    return dict(home_win=h, draw=d, away_win=a, expected_home=round(xh, 2), expected_away=round(xa, 2), details={
        "top_scores": [{"score": f"{i}–{j}", "probability": round(p / mass * 100, 2)} for i, j, p in top],
        "home_elo": round(ratings[home_id]), "away_elo": round(ratings[away_id]),
        "home_form": {"played": hf["played"], "scored": round(hf["gf"] * hf["played"], 1), "conceded": round(hf["ga"] * hf["played"], 1)},
        "away_form": {"played": af["played"], "scored": round(af["gf"] * af["played"], 1), "conceded": round(af["ga"] * af["played"], 1)},
        "league_home_avg": round(league_home, 2), "league_away_avg": round(league_away, 2),
        "model_version": (("shl-dc-experimental-v1" if league == "SHL" else "nhl-dc-experimental-v1") if variant == "experimental" else ("shl-2026-10games-70pct-v1" if league == "SHL" else "nhl-2026-20games-70pct-v1")), "recent_matches": 5,
        "window_matches": window, "recent_weight_pct": 70,
        "home_venue_games": len(hf["home"]), "away_venue_games": len(af["away"]),
    })
