"""Best-effort public SHL goalkeeper summary, no lineup/start assertions."""
import re
from html.parser import HTMLParser

SOURCE = "https://www.shl.se/game-stats/goalkeepers/summary?count=100"

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.cell_depth = 0
        self.cell = []
        self.row = []
        self.rows = []
    def handle_starttag(self, tag, attrs):
        if tag == "table": self.in_table = True
        elif self.in_table and tag == "tr": self.in_row = True; self.row = []
        elif self.in_row and tag in ("td", "th"):
            self.cell_depth += 1
            if self.cell_depth == 1: self.cell = []
    def handle_data(self, data):
        if self.cell_depth: self.cell.append(data)
    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell_depth:
            self.cell_depth -= 1
            if not self.cell_depth: self.row.append(" ".join(" ".join(self.cell).split()))
        elif tag == "tr" and self.in_row:
            if self.row: self.rows.append(self.row)
            self.in_row = False
        elif tag == "table": self.in_table = False

def parse_goalkeepers(html):
    parser = TableParser()
    parser.feed(html)
    rows = parser.rows
    header = next((r for r in rows if "SVS%" in r and "GAA" in r), None)
    if not header: return []
    columns = {name: header.index(name) for name in ("Spelare", "SVS%", "GAA") if name in header}
    if len(columns) != 3: return []
    team_col = next((header.index(k) for k in ("LAG", "Lag") if k in header), None)
    result = []
    for r in rows[rows.index(header)+1:]:
        if len(r) <= max(columns.values()): continue
        name = r[columns["Spelare"]].strip()
        save = r[columns["SVS%"]].strip().replace(",", ".")
        gaa = r[columns["GAA"]].strip().replace(",", ".")
        if not name or not re.fullmatch(r"\d{1,3}(?:\.\d+)?", save) or not re.fullmatch(r"\d{1,2}(?:\.\d+)?", gaa): continue
        if not 0 <= float(save) <= 100: continue
        result.append({"name": name, "team": r[team_col] if team_col is not None and team_col < len(r) else "", "save_pct": save, "gaa": gaa})
    return result
