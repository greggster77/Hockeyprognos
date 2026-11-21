"""Separata officiella slutresultat och 60-minutersresultat.

Skriver aldrig till databasen. Saknade uppgifter representeras med None.
"""
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class MatchResult:
    home_goals: int | None
    away_goals: int | None
    final_home_goals: int | None
    final_away_goals: int | None
    decided_in: str | None

    def as_dict(self):
        return asdict(self)


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 and str(value).strip() == str(n) else None


def _get(obj, *keys):
    if not isinstance(obj, dict):
        return None
    for key in keys:
        if obj.get(key) is not None:
            return obj[key]
    return None


def extract_result(game, regulation=None):
    """Hämta säkra resultat från källans råobjekt.

    regulation: verifierad tuple från period 1-3 eller explicit regulationScore.
    Inga slutsatser dras från slutresultat om OT/SO-status saknas.
    """
    home = _get(game, 'homeTeam', 'home_team', 'homeTeamInfo')
    away = _get(game, 'awayTeam', 'away_team', 'awayTeamInfo')
    final = _get(game, 'GameResult', 'gameResult')
    if isinstance(final, dict):
        fh = _number(_get(final, 'Home', 'home', 'homeScore'))
        fa = _number(_get(final, 'Away', 'away', 'awayScore'))
    else:
        fh = _number(_get(home, 'score', 'goals'))
        fa = _number(_get(away, 'score', 'goals'))
    raw = str(_get(game, 'decided_in', 'decidedIn', 'decision') or '').strip().lower()
    if game.get('shootout') is True or game.get('hasShootout') is True or raw in ('so', 'shootout', 'penalties'):
        decided = 'SO'
    elif game.get('overtime') is True or game.get('hasOvertime') is True or raw in ('ot', 'overtime', 'extra-time'):
        decided = 'OT'
    elif raw in ('ft', 'regulation', 'regular', '60', '60min') or game.get('regulationOnly') is True or game.get('decidedInRegulation') is True:
        decided = 'REG'
    else:
        decided = None
    if regulation is None:
        rg = _get(game, 'regulationScore', 'regulation_score')
        if isinstance(rg, dict):
            a = _number(_get(rg, 'home', 'homeScore', 'homeGoals'))
            b = _number(_get(rg, 'away', 'awayScore', 'awayGoals'))
            if a is not None and b is not None:
                regulation = (a, b)
    if regulation is None and decided == 'REG' and fh is not None and fa is not None:
        regulation = (fh, fa)
    rh, ra = regulation if regulation is not None else (None, None)
    if decided in ('OT', 'SO') and rh is not None and ra is not None and rh != ra:
        raise ValueError('OT/SO-match måste vara oavgjord efter 60 minuter')
    if None not in (rh, ra, fh, fa):
        if fh < rh or fa < ra:
            raise ValueError('Slutresultat får inte ha färre mål än efter 60 minuter')
    return MatchResult(rh, ra, fh, fa, decided)
