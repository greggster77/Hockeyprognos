const root=document.getElementById('root');const state={league:'ALL',date:new Date().toLocaleDateString('sv-SE',{timeZone:'Europe/Stockholm',year:'numeric',month:'2-digit',day:'2-digit'}),leagues:[],matches:[],error:'',detail:null,loading:true,light:localStorage.getItem('theme')==='light',days:7};
state.date=state.date.split('-').join('-');
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct=p=>p===undefined||p===null?'–':Number(p).toFixed(2).replace('.',',')+' %';
const formatDate=d=>new Date(d).toLocaleString('sv-SE',{timeZone:'Europe/Stockholm',weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
async function get(path){const r=await fetch(path);if(!r.ok)throw Error('Serverfel '+r.status);return r.json()}
// Officiella NHL-klubbmärken från NHL:s publika bildserver.
const NHL_CODES={
'Anaheim Ducks':'ANA','Boston Bruins':'BOS','Buffalo Sabres':'BUF','Calgary Flames':'CGY',
'Carolina Hurricanes':'CAR','Chicago Blackhawks':'CHI','Colorado Avalanche':'COL',
'Columbus Blue Jackets':'CBJ','Dallas Stars':'DAL','Detroit Red Wings':'DET',
'Edmonton Oilers':'EDM','Florida Panthers':'FLA','Los Angeles Kings':'LAK',
'Minnesota Wild':'MIN','Montréal Canadiens':'MTL','Montreal Canadiens':'MTL',
'Nashville Predators':'NSH','New Jersey Devils':'NJD','New York Islanders':'NYI',
'New York Rangers':'NYR','Ottawa Senators':'OTT','Philadelphia Flyers':'PHI',
'Pittsburgh Penguins':'PIT','San Jose Sharks':'SJS','Seattle Kraken':'SEA',
'St. Louis Blues':'STL','Tampa Bay Lightning':'TBL','Toronto Maple Leafs':'TOR',
'Utah Mammoth':'UTA','Utah Hockey Club':'UTA','Vancouver Canucks':'VAN',
'Vegas Golden Knights':'VGK','Washington Capitals':'WSH','Winnipeg Jets':'WPG'};
// Svensk klubbidentifiering 2026/27. Commons-loggor laddas endast när en fil
// tydligt matchar klubbnamn och är märkt som logotyp/emblem.
const SWEDISH_CLUBS={
 SHL:{
 'IF Björklöven':['IF Björklöven','Björklöven'], 'Björklöven':['IF Björklöven','Björklöven'],
 'Brynäs IF':['Brynäs IF','Brynäs'], 'Brynäs':['Brynäs IF','Brynäs'],
 'Djurgårdens IF':['Djurgårdens IF','Djurgården'], 'Djurgården Hockey':['Djurgårdens IF','Djurgården'], 'Djurgården':['Djurgårdens IF','Djurgården'],
 'Frölunda HC':['Frölunda HC','Frölunda'], 'Frölunda':['Frölunda HC','Frölunda'],
 'Färjestad BK':['Färjestad BK','Färjestad'], 'Färjestad':['Färjestad BK','Färjestad'],
 'HV71':['HV71','HV71'], 'Linköping HC':['Linköping HC','Linköping'], 'Linköping':['Linköping HC','Linköping'],
 'Luleå Hockey':['Luleå HF','Luleå'], 'Luleå HF':['Luleå HF','Luleå'], 'Luleå':['Luleå HF','Luleå'],
 'Malmö Redhawks':['Malmö Redhawks','Malmö'], 'Malmö':['Malmö Redhawks','Malmö'],
 'Rögle BK':['Rögle BK','Rögle'], 'Rögle':['Rögle BK','Rögle'],
 'Skellefteå AIK':['Skellefteå AIK','Skellefteå'], 'Skellefteå':['Skellefteå AIK','Skellefteå'],
 'Timrå IK':['Timrå IK','Timrå'], 'Timrå':['Timrå IK','Timrå'],
 'Växjö Lakers':['Växjö Lakers','Växjö'], 'Växjö':['Växjö Lakers','Växjö'],
 'Örebro HK':['Örebro HK','Örebro'], 'Örebro Hockey':['Örebro HK','Örebro'], 'Örebro':['Örebro HK','Örebro']},
 HA:{
 'AIK':['AIK Ishockey','AIK'], 'AIK Hockey':['AIK Ishockey','AIK'],
 'Almtuna IS':['Almtuna IS','Almtuna'], 'Almtuna':['Almtuna IS','Almtuna'],
 'BIK Karlskoga':['BIK Karlskoga','Karlskoga'], 'Karlskoga':['BIK Karlskoga','Karlskoga'],
 'IK Oskarshamn':['IK Oskarshamn','Oskarshamn'], 'Oskarshamn':['IK Oskarshamn','Oskarshamn'],
 'Kalmar HC':['Kalmar HC','Kalmar'], 'Kalmar':['Kalmar HC','Kalmar'],
 'Leksands IF':['Leksands IF','Leksand'], 'Leksand':['Leksands IF','Leksand'],
 'MoDo Hockey':['MoDo Hockey','MoDo'], 'MoDo':['MoDo Hockey','MoDo'], 'Modo Hockey':['MoDo Hockey','MoDo'],
 'Mora IK':['Mora IK','Mora'], 'Mora':['Mora IK','Mora'],
 'Nybro Vikings IF':['Nybro Vikings','Nybro'], 'Nybro Vikings':['Nybro Vikings','Nybro'], 'Nybro':['Nybro Vikings','Nybro'],
 'Södertälje SK':['Södertälje SK','Södertälje'], 'Södertälje':['Södertälje SK','Södertälje'],
 'Vimmerby HC':['Vimmerby HC','Vimmerby'], 'Vimmerby':['Vimmerby HC','Vimmerby'],
 'Visby/Roma HK':['Visby Roma','Visby'], 'Visby Roma':['Visby Roma','Visby'], 'Visby/Roma':['Visby Roma','Visby'],
 'Västerås IK':['Västerås IK','Västerås'], 'Västerås':['Västerås IK','Västerås'],
 'Östersunds IK':['Östersunds IK','Östersund'], 'Östersund':['Östersunds IK','Östersund']}
};
const logoMemo=new Map();
const logoKey=(league,name)=>league+':'+name;
function normalizedLogoText(v){return String(v).toLocaleLowerCase('sv').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]/g,'')}
async function resolveSwedishLogo(league,name){
 const aliases=SWEDISH_CLUBS[league]?.[name];if(!aliases)return null;
 const key=logoKey(league,aliases[0]);if(logoMemo.has(key))return logoMemo.get(key);
 const cached=sessionStorage.getItem('hockey-logo:'+key);if(cached){logoMemo.set(key,cached==='none'?null:cached);return logoMemo.get(key)}
 // MediaWiki Commons tillåter CORS via origin=*. Ingen API-nyckel behövs.
 const query=new URLSearchParams({action:'query',format:'json',origin:'*',generator:'search',gsrnamespace:'6',gsrlimit:'15',gsrsearch:aliases[0]+' logo',prop:'imageinfo',iiprop:'url',iiurlwidth:'160'});
 try{
  const res=await fetch('https://commons.wikimedia.org/w/api.php?'+query,{signal:AbortSignal.timeout(7000)});
  if(!res.ok)throw Error('Commons '+res.status);
  const json=await res.json();const pages=Object.values(json.query?.pages||{});
  const needles=aliases.map(normalizedLogoText).filter(x=>x.length>=4);
  const options=pages.filter(p=>{const t=normalizedLogoText(p.title);return needles.some(n=>t.includes(n))&&/(logo|logotyp|emblem|crest|vapen)/i.test(p.title)&&/\.(svg|png|webp|jpg|jpeg)$/i.test(p.title)});
  options.sort((a,b)=>Number(/\.svg$/i.test(b.title))-Number(/\.svg$/i.test(a.title)));
  const url=options[0]?.imageinfo?.[0]?.thumburl||options[0]?.imageinfo?.[0]?.url||null;
  logoMemo.set(key,url);sessionStorage.setItem('hockey-logo:'+key,url||'none');return url;
 }catch(e){return null}
}
function hydrateSwedishLogos(){
 document.querySelectorAll('[data-swedish-logo]').forEach(async el=>{
  const league=el.dataset.league,name=el.dataset.team;
  const url=await resolveSwedishLogo(league,name);
  if(!url||!el.isConnected)return;
  const img=document.createElement('img');img.className='team-logo';img.alt=name+' klubbmärke';img.loading='lazy';img.decoding='async';img.src=url;
  img.onerror=()=>{img.remove();el.style.display='grid'};
  img.onload=()=>{if(el.isConnected){el.style.display='none';el.parentNode.insertBefore(img,el)}};
 });
}
function teamMark(name,league){
  const code=league==='NHL'?NHL_CODES[name]:null;
  if(!code){const swedish=Boolean(SWEDISH_CLUBS[league]?.[name]);return `<span class="team-initial" ${swedish?`data-swedish-logo="1" data-league="${esc(league)}" data-team="${esc(name)}"`:''} aria-hidden="true">${esc(name).slice(0,2).toUpperCase()}</span>`;}
  return `<img class="team-logo" src="https://assets.nhle.com/logos/nhl/svg/${code}_light.svg" alt="${esc(name)} klubbmärke" loading="lazy" decoding="async" onerror="this.style.display='none';this.nextElementSibling.style.display='grid'"><span class="team-initial" style="display:none" aria-hidden="true">${esc(code)}</span>`;
}
function notice(){return '<section class="panel notice">ℹ️ Prognoser är statistiska uppskattningar, inte garantier. 1X2 avser resultatet efter 60 minuter – utan förlängning och straffar.</section>'}
function card(m){const p=m.prediction;return `<article class="panel match" data-id="${esc(m.id)}"><div class="topline"><span>${esc(m.league)} · ${esc(formatDate(m.date))}</span><span>${m.status==='FINISHED'?'60 min: '+m.score.home+'–'+m.score.away:'Kommande'}</span></div><div class="teams"><div class="team-side">${teamMark(m.home,m.league)}<span>${esc(m.home)}</span></div><span class="vs">VS</span><div class="team-side">${teamMark(m.away,m.league)}<span>${esc(m.away)}</span></div></div>${p?`<div class="percent"><div><small>1 · Hemma</small><b>${pct(p.home_win)}</b></div><div><small>X · Oavgjort</small><b>${pct(p.draw)}</b></div><div><small>2 · Borta</small><b>${pct(p.away_win)}</b></div></div>`:'<p class="muted">Ingen prognos tillgänglig: otillräcklig verifierad matchhistorik.</p>'}</article>`}
function render(){document.documentElement.classList.toggle('light',state.light);if(state.detail){const m=state.detail,p=m.prediction,d=p?.details;root.innerHTML=`<button class="back" id="back">← Till matcher</button><div class="eyebrow">${esc(m.league)} · ${esc(formatDate(m.date))}</div><h1 class="title">${esc(m.home)} – ${esc(m.away)}</h1>${card(m)}${p?`<section class="panel"><h3>Matchanalys</h3><div class="metric"><span>Förväntade mål hemma</span><strong>${p.expected_home}</strong></div><div class="metric"><span>Förväntade mål borta</span><strong>${p.expected_away}</strong></div><div class="metric"><span>Elo hemma / borta</span><strong>${d.home_elo} / ${d.away_elo}</strong></div><div class="metric"><span>Hemmaform (mål för/emot)</span><strong>${d.home_form.scored} / ${d.home_form.conceded} (${d.home_form.played} matcher)</strong></div><div class="metric"><span>Bortaform (mål för/emot)</span><strong>${d.away_form.scored} / ${d.away_form.conceded} (${d.away_form.played} matcher)</strong></div><h3>Troligaste resultat efter 60 min</h3>${d.top_scores.map(s=>`<div class="metric"><span>${esc(s.score)}</span><strong>${pct(s.probability)}</strong></div>`).join('')}</section>`:''}${notice()}`;hydrateSwedishLogos();document.getElementById('back').onclick=()=>{state.detail=null;render()};return}
root.innerHTML=`<div class="header"><div><div class="eyebrow">STATISTIK · HOCKEY</div><h1 class="title">🏒 Hockeyprognos</h1><div class="muted">1X2 efter 60 minuter</div></div><button class="theme" id="theme">${state.light?'🌙 Mörkt':'☀️ Ljust'}</button></div><div class="filters">${[['ALL','Alla'],['SHL','SHL'],['HA','HockeyAllsvenskan'],['NHL','NHL']].map(([id,label])=>`<button class="chip ${state.league===id?'active':''}" data-league="${id}">${label}</button>`).join('')}</div><div class="controls"><input class="date" type="date" id="date" value="${state.date}"><button class="chip" id="refresh">↻</button></div>${state.error?`<section class="panel warning">⚠️ ${esc(state.error)}</section>`:''}${state.loading?'<section class="panel empty">Hämtar matcher…</section>':state.matches.length?state.matches.map(card).join(''):'<section class="panel empty"><strong>Inga verifierade matcher hittades</strong><p class="muted">Välj ett annat datum eller kontrollera datakällornas status.</p></section>'}${state.leagues.filter(l=>l.error).map(l=>`<section class="panel warning">⚠️ ${esc(l.name)}: ${esc(l.error)}</section>`).join('')}${notice()}<section class="panel"><strong>Modellens träffsäkerhet</strong><p class="muted" id="perf">Hämtar historik…</p></section>`;
hydrateSwedishLogos();document.getElementById('theme').onclick=()=>{state.light=!state.light;localStorage.setItem('theme',state.light?'light':'dark');render()};document.querySelectorAll('[data-league]').forEach(el=>el.onclick=()=>{state.league=el.dataset.league;load()});document.getElementById('date').onchange=e=>{state.date=e.target.value;load()};document.getElementById('refresh').onclick=load;document.querySelectorAll('[data-id]').forEach(el=>el.onclick=async()=>{try{state.detail=await get('/api/matches/'+encodeURIComponent(el.dataset.id));render()}catch(e){state.error=e.message;render()}});get('/api/performance').then(p=>{const el=document.getElementById('perf');if(el)el.textContent=p.evaluated?`${p.evaluated} utvärderade prognoser · Brier: ${Number(p.mean_brier).toFixed(3)}`:'Inga avslutade prognoser har ännu utvärderats.'}).catch(()=>{});
}
async function load(){state.loading=true;state.error='';render();try{const [matches,leagues]=await Promise.all([get('/api/matches?day='+state.date+'&days='+state.days+(state.league==='ALL'?'':'&league='+state.league)),get('/api/leagues')]);state.matches=matches;state.leagues=leagues}catch(e){state.error='Kunde inte hämta riktig matchdata. Kontrollera internetanslutningen och servern. '+e.message;state.matches=[]}state.loading=false;render()}
load();if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
