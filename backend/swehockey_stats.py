"""Read public Swehockey SHL 2026/27 tables; no predictions or starter assertions."""
from html.parser import HTMLParser
import re

BASE = 'https://stats.swehockey.se'
SOURCES = {
    'standings': BASE + '/ScheduleAndResults/Overview/20961',
    'scorers': BASE + '/Players/Statistics/ScoringLeaders/20961',
    'goalies': BASE + '/Players/Statistics/LeadingGoaliesSVS/20961',
}

class Tables(HTMLParser):
    def __init__(self):
        super().__init__(); self.tables=[]; self.table=None; self.row=None; self.cell=None; self.depth=0
    def handle_starttag(self,tag,attrs):
        if tag=='table':
            self.depth+=1
            if self.depth==1:self.table=[]
        elif self.depth==1 and tag=='tr':self.row=[]
        elif self.row is not None and tag in ('td','th'):self.cell=[]
        elif self.cell is not None and tag=='br':self.cell.append(' ')
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()));self.cell=None
        elif tag=='tr' and self.row is not None:
            if self.row:self.table.append(self.row)
            self.row=None
        elif tag=='table' and self.depth:
            self.depth-=1
            if self.depth==0 and self.table:self.tables.append(self.table);self.table=None

def _number(s):
    s=s.replace(',','.').replace('%','').strip()
    return float(s) if re.fullmatch(r'-?\d+(?:\.\d+)?',s) else None

def _parse_table(html, required, aliases, numeric):
    p=Tables();p.feed(html)
    for table in p.tables:
        for h, header in enumerate(table):
            keys=[re.sub(r'[^a-z0-9%]','',v.lower()) for v in header]
            mapping={}
            for field,options in aliases.items():
                mapping[field]=next((keys.index(re.sub(r'[^a-z0-9%]','',x.lower())) for x in options if re.sub(r'[^a-z0-9%]','',x.lower()) in keys),None)
            if any(mapping.get(k) is None for k in required):continue
            rows=[]
            for row in table[h+1:]:
                if len(row)<=max(mapping[k] for k in required):continue
                item={k:(row[i] if i is not None and i<len(row) else '') for k,i in mapping.items()}
                for k in numeric:item[k]=_number(item[k])
                if any(item[k] is None for k in numeric if k in required):continue
                if not item.get(required[0]):continue
                rows.append(item)
            if rows:return rows
    return []

def parse_standings(html):
    aliases={'rank':['RK','Rk','Rank'],'team':['Team','Lag'],'played':['GP','Sp'],'wins':['W','V'],'draws':['T','O'],'losses':['L','F'],'goal_diff':['GD','MS'],'points':['TP','P','Pts']}
    rows=_parse_table(html,['team','played','points'],aliases,['rank','played','wins','draws','losses','goal_diff','points'])
    return [r for r in rows if r['played'] is not None and r['points'] is not None][:14]

def parse_scorers(html):
    aliases={'rank':['Rk','Rank'],'name':['Name','Namn'],'team':['Team','Lag'],'position':['Pos'],'played':['GP','Sp'],'goals':['G','M'],'assists':['A'],'points':['TP','P','Pts']}
    rows=_parse_table(html,['name','team','points'],aliases,['rank','played','goals','assists','points'])
    return [r for r in rows if r['points'] is not None][:30]

def parse_goalies(html):
    aliases={'rank':['Rk','Rank'],'number':['No','Nr'],'name':['Name','Namn'],'team':['Team','Lag'],'played':['GPI','GP'],'shots':['SOG'],'against':['GA'],'gaa':['GAA'],'save_pct':['SVS%','SV%','Save%']}
    rows=_parse_table(html,['name','team','save_pct'],aliases,['rank','played','shots','against','gaa','save_pct'])
    return [r for r in rows if r['save_pct'] is not None and 0<=r['save_pct']<=100][:45]


def inspect_tables(html):
    """Return diagnostic information about HTML tables."""
    parser = Tables()
    parser.feed(html)

    return {
        "table_count": len(parser.tables),
        "tables": [
            {
                "rows": len(table),
                "headers": table[0] if table else [],
                "sample": table[:3]
            }
            for table in parser.tables
        ]
    }
