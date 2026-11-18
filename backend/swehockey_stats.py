"""Parse public Swehockey season tables without inventing missing data.

The caller fetches SOURCES and passes the response HTML to parse_*.
"""
from html.parser import HTMLParser
import re
import unicodedata

BASE = 'https://stats.swehockey.se'
SOURCES = {
    'standings': BASE + '/ScheduleAndResults/Overview/20961',
    'scorers': BASE + '/Players/Statistics/ScoringLeaders/20961',
    'goalies': BASE + '/Players/Statistics/LeadingGoaliesSVS/20961',
}

class Tables(HTMLParser):
    """Collect tables, including nested tables, without merging unrelated rows."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.stack = []
        self.cell = None
        self.cell_tag = None

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.stack.append({'rows': [], 'row': None})
        elif self.stack and tag == 'tr':
            self.stack[-1]['row'] = []
        elif self.stack and self.stack[-1]['row'] is not None and tag in ('td', 'th'):
            self.cell = []
            self.cell_tag = tag
        elif self.cell is not None and tag == 'br':
            self.cell.append(' ')

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None and self.stack:
            row = self.stack[-1]['row']
            if row is not None:
                row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
            self.cell_tag = None
        elif tag == 'tr' and self.stack:
            table = self.stack[-1]
            if table['row']:
                table['rows'].append(table['row'])
            table['row'] = None
        elif tag == 'table' and self.stack:
            table = self.stack.pop()
            if table['rows']:
                self.tables.append(table['rows'])

def _norm(s):
    s = unicodedata.normalize('NFKD', str(s).lower())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9%]', '', s)

def _number(s):
    s = str(s or '').replace('\u00a0', '').replace(' ', '').replace(',', '.').replace('%', '').replace('−', '-').strip()
    return float(s) if re.fullmatch(r'-?\d+(?:\.\d+)?', s) else None

def inspect_tables(html):
    """Safe diagnostic: no page contents or user data are logged."""
    parser = Tables()
    parser.feed(html)
    return {'html_bytes': len(html.encode('utf-8')), 'table_count': len(parser.tables),
            'table_headers': [t[0][:14] for t in parser.tables[:12] if t]}

def _parse_table(html, required, aliases, numeric):
    parser = Tables()
    parser.feed(html)
    for table in parser.tables:
        for h, header in enumerate(table[:8]):
            keys = [_norm(v) for v in header]
            mapping = {}
            for field, options in aliases.items():
                mapping[field] = next((keys.index(_norm(option)) for option in options if _norm(option) in keys), None)
            if any(mapping.get(k) is None for k in required):
                continue
            rows = []
            for row in table[h + 1:]:
                if len(row) <= max(mapping[k] for k in required):
                    continue
                item = {k: row[i] if i is not None and i < len(row) else '' for k, i in mapping.items()}
                for k in numeric:
                    item[k] = _number(item[k])
                if any(item[k] is None for k in numeric if k in required):
                    continue
                if not item.get(required[0]):
                    continue
                rows.append(item)
            if rows:
                return rows
    return []

def parse_standings(html):
    aliases = {
        'rank': ['RK', 'Rk', 'Rank', 'Pl', 'Plac'],
        'team': ['Team', 'Lag'], 'played': ['GP', 'Sp', 'M', 'Matcher'],
        'wins': ['W', 'V'], 'draws': ['T', 'O'], 'losses': ['L', 'F'],
        'goal_diff': ['GD', 'MS', 'Målskillnad'], 'points': ['TP', 'P', 'Pts', 'Poäng'],
    }
    return _parse_table(html, ['team', 'played', 'points'], aliases,
                        ['rank', 'played', 'wins', 'draws', 'losses', 'goal_diff', 'points'])[:14]

def parse_scorers(html):
    aliases = {
        'rank': ['Rk', 'Rank', 'RK'], 'name': ['Name', 'Namn', 'Player', 'Spelare'],
        'team': ['Team', 'Lag'], 'position': ['Pos'], 'played': ['GP', 'Sp'],
        'goals': ['G', 'M'], 'assists': ['A'], 'points': ['TP', 'P', 'Pts', 'Poäng'],
    }
    return _parse_table(html, ['name', 'team', 'points'], aliases,
                        ['rank', 'played', 'goals', 'assists', 'points'])[:30]

def parse_goalies(html):
    aliases = {
        'rank': ['Rk', 'Rank', 'RK'], 'number': ['No', 'Nr'],
        'name': ['Name', 'Namn', 'Player'], 'team': ['Team', 'Lag'],
        'played': ['GPI', 'GP', 'Sp'], 'shots': ['SOG', 'Shots'],
        'against': ['GA'], 'gaa': ['GAA'], 'save_pct': ['SVS%', 'SV%', 'Save%', 'R%'],
    }
    rows = _parse_table(html, ['name', 'team', 'save_pct'], aliases,
                        ['rank', 'played', 'shots', 'against', 'gaa', 'save_pct'])
    return [r for r in rows if r['save_pct'] is not None and 0 <= r['save_pct'] <= 100][:45]
