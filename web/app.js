const root=document.getElementById('root');const state={league:'ALL',date:new Date().toLocaleDateString('sv-SE',{timeZone:'Europe/Stockholm',year:'numeric',month:'2-digit',day:'2-digit'}),leagues:[],matches:[],error:'',detail:null,loading:true,light:localStorage.getItem('theme')==='light',days:7,view:"matches",history:[],historyTeams:[],historyTeam:"",historyTotal:0,historyOffset:0,historyLimit:50,formData:{},formExpanded:{},formLoading:false};
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
// SHL:s officiella lagregister ger klubbmärken direkt, utan Wikimedia-sökning.
// 2026/27 grundserie: ssgtUuid från SHL:s layout-info.
const SHL_SSGT_UUID='qa98unlbd6';
const logoMemo=new Map();
let shlLogoDirectoryPromise=null;
const logoKey=(league,name)=>league+':'+name;
function normalizedLogoText(v){return String(v??'').toLocaleLowerCase('sv').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]/g,'')}
async function loadSHLLogoDirectory(){
 if(!shlLogoDirectoryPromise){
  shlLogoDirectoryPromise=(async()=>{
   const r=await fetch('https://www.shl.se/api/sports-v2/all-sites/'+SHL_SSGT_UUID,{signal:AbortSignal.timeout(10000)});
   if(!r.ok)throw Error('SHL lagregister HTTP '+r.status);
   const data=await r.json();
   const sites=Array.isArray(data)?data:(data.sites||data.siteList||data.teams||data.teamList||[]);
   if(!Array.isArray(sites)||!sites.length)throw Error('SHL lagregister saknar laglista');
   return sites.map(s=>({
    name:s.name||s.displayName||s.names?.long||s.names?.short||'',
    icon:s.icon||s.publicUrl||s.public_url||s.logo||'',
    id:s.instanceId||s.instance_id||s.id||s.ownerInstanceId||''
   }));
  })().catch(err=>{console.warn('SHL-loggor kunde inte hämtas:',err);shlLogoDirectoryPromise=null;return []});
 }
 return shlLogoDirectoryPromise;
}
async function resolveSwedishLogo(league,name){
 const aliases=SWEDISH_CLUBS[league]?.[name];if(!aliases)return null;
 const key=logoKey(league,aliases[0]);
 if(logoMemo.has(key))return logoMemo.get(key);
 if(league!=='SHL')return null; // HA lämnas oförändrat tills dess källa fungerar.
 const sites=await loadSHLLogoDirectory();
 const names=[name,...aliases].map(normalizedLogoText);
 const site=sites.find(s=>names.includes(normalizedLogoText(s.name)))||sites.find(s=>names.some(n=>n.length>=5&&normalizedLogoText(s.name).includes(n)));
 let url=site?.icon||'';
 if(!url&&site?.id)url='https://sportality.cdn.s8y.se/team-logos/'+encodeURIComponent(site.id)+'.svg';
 if(url&&url.startsWith('//'))url='https:'+url;
 if(url&&url.startsWith('/'))url='https://www.shl.se'+url;
 if(url&&!/^https:\/\//i.test(url))url='';
 if(url)logoMemo.set(key,url);
 return url||null;
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

// Resultat efter 60 minuter: V / O / F utifrån valt lags perspektiv.
function teamFormResult(m,team){const home=m.home===team;const gf=Number(home?m.score?.home:m.score?.away),ga=Number(home?m.score?.away:m.score?.home);return gf>ga?'V':gf<ga?'F':'O'}
function formDate(d){return new Date(d).toLocaleDateString('sv-SE',{timeZone:'Europe/Stockholm',day:'2-digit',month:'2-digit',year:'2-digit'})}
function teamFormCard(team){const matches=state.formData[team]||[];const expanded=!!state.formExpanded[team];const shown=expanded?matches.slice(0,20):matches.slice(0,5);return `<section class="panel form-panel"><div class="form-heading"><div class="form-team">${teamMark(team,'NHL')}<strong>Senast ${esc(team)}</strong></div><div class="form-dots">${matches.slice(0,5).map(m=>`<span class="form-dot form-${teamFormResult(m,team)}" title="${esc(formDate(m.date))}">${teamFormResult(m,team)}</span>`).join('')}</div></div>${state.formLoading?'<p class="muted">Hämtar senaste matcher…</p>':!matches.length?'<p class="muted">Ingen historik hittades för laget.</p>':`<div class="form-list">${shown.map(m=>{const home=m.home===team;const opponent=home?m.away:m.home;const gf=home?m.score.home:m.score.away;const ga=home?m.score.away:m.score.home;return `<div class="form-match"><div class="form-location">${home?'H':'B'}</div><div class="form-result form-${teamFormResult(m,team)}">${teamFormResult(m,team)}</div><div class="form-scores"><span>${esc(m.home)} <b>${esc(m.score.home)}</b></span><span>${esc(m.away)} <b>${esc(m.score.away)}</b></span></div><div class="form-match-date">${esc(formDate(m.date))}<small>60 min</small></div></div>`}).join('')}</div>${matches.length>5?`<button class="form-more" data-form-team="${esc(team)}">${expanded?'Visa färre matcher':'Visa alla '+Math.min(matches.length,20)+' matcher'} <span>${expanded?'⌃':'⌄'}</span></button>`:''}`}</section>`}
async function loadTeamForms(m){if(m.league!=='NHL')return;state.formLoading=true;state.formData={};render();try{const listing=await get('/api/history?league=NHL&limit=1');const teams=listing.teams||[];const selected=[m.home,m.away];const pairs=selected.map(name=>({name,id:teams.find(t=>t.name===name)?.id}));const result=await Promise.all(pairs.map(async t=>t.id?get('/api/history?league=NHL&limit=20&team='+encodeURIComponent(t.id)):null));if(state.detail?.id!==m.id)return;pairs.forEach((t,i)=>{state.formData[t.name]=result[i]?.matches||[]})}catch(e){if(state.detail?.id===m.id)state.formError=e.message}finally{if(state.detail?.id===m.id){state.formLoading=false;render()}}}
function showDetail(m){state.detail=m;state.formExpanded={};state.formData={};state.formError='';render();loadTeamForms(m)}
function bindFormButtons(){document.querySelectorAll('[data-form-team]').forEach(b=>b.onclick=()=>{const team=b.dataset.formTeam;state.formExpanded[team]=!state.formExpanded[team];render()})}
function render(){document.documentElement.classList.toggle('light',state.light);if(state.detail){const m=state.detail,p=m.prediction,d=p?.details;root.innerHTML=`<button class="back" id="back">← Till matcher</button><div class="eyebrow">${esc(m.league)} · ${esc(formatDate(m.date))}</div><h1 class="title">${esc(m.home)} – ${esc(m.away)}</h1>${card(m)}${m.league==='NHL'?`<h2 class="form-section-title">Lagform · senaste matcher</h2>${state.formError?`<p class="muted">${esc(state.formError)}</p>`:''}${teamFormCard(m.home)}${teamFormCard(m.away)}`:''}${p?`<section class="panel"><h3>Matchanalys</h3><div class="metric"><span>Förväntade mål hemma</span><strong>${p.expected_home}</strong></div><div class="metric"><span>Förväntade mål borta</span><strong>${p.expected_away}</strong></div><div class="metric"><span>Elo hemma / borta</span><strong>${d.home_elo} / ${d.away_elo}</strong></div><div class="metric"><span>Hemmaform (mål för/emot)</span><strong>${d.home_form.scored} / ${d.home_form.conceded} (${d.home_form.played} matcher)</strong></div><div class="metric"><span>Bortaform (mål för/emot)</span><strong>${d.away_form.scored} / ${d.away_form.conceded} (${d.away_form.played} matcher)</strong></div><h3>Troligaste resultat efter 60 min</h3>${d.top_scores.map(s=>`<div class="metric"><span>${esc(s.score)}</span><strong>${pct(s.probability)}</strong></div>`).join('')}</section>`:''}${notice()}`;hydrateSwedishLogos();document.getElementById('back').onclick=()=>{state.detail=null;render()};bindFormButtons();return}
if(state.view==='history'){
root.innerHTML=`<div class="header"><div><div class="eyebrow">NHL · ${esc(state.historySeason||'2026/27')}</div><h1 class="title">🏒 Matchhistorik</h1><div class="muted">Verifierade resultat efter 60 minuter</div></div><button class="theme" id="theme">${state.light?'🌙 Mörkt':'☀️ Ljust'}</button></div><div class="filters"><button class="chip" id="to-matches">Kommande matcher</button><button class="chip active">NHL-historik</button></div><div class="controls"><select class="date" id="history-team"><option value="">Alla NHL-lag</option>${state.historyTeams.map(t=>`<option value="${esc(t.id)}" ${t.id===state.historyTeam?'selected':''}>${esc(t.name)}</option>`).join('')}</select><button class="chip" id="history-refresh">↻</button></div>${state.error?`<section class="panel warning">⚠️ ${esc(state.error)}</section>`:''}${state.loading?'<section class="panel empty">Hämtar historik…</section>':`<p class="muted">${state.historyTotal} färdigspelade matcher · visar ${state.history.length?state.historyOffset+1:0}–${state.historyOffset+state.history.length}</p>${state.history.length?state.history.map(card).join(''):'<section class="panel empty">Ingen importerad NHL-historik hittades.</section>'}<div class="controls history-pager"><button class="chip" id="history-prev" ${state.historyOffset===0?'disabled':''}>← Föregående</button><button class="chip" id="history-next" ${state.historyOffset+state.history.length>=state.historyTotal?'disabled':''}>Nästa →</button></div>`}${notice()}`;
hydrateSwedishLogos();document.getElementById('theme').onclick=()=>{state.light=!state.light;localStorage.setItem('theme',state.light?'light':'dark');render()};document.getElementById('to-matches').onclick=()=>{state.view='matches';load()};document.getElementById('history-team').onchange=e=>{state.historyTeam=e.target.value;state.historyOffset=0;loadHistory()};document.getElementById('history-refresh').onclick=loadHistory;document.getElementById('history-prev')?.addEventListener('click',()=>{state.historyOffset=Math.max(0,state.historyOffset-state.historyLimit);loadHistory()});document.getElementById('history-next')?.addEventListener('click',()=>{state.historyOffset+=state.historyLimit;loadHistory()});document.querySelectorAll('[data-id]').forEach(el=>el.onclick=async()=>{try{showDetail(await get('/api/matches/'+encodeURIComponent(el.dataset.id)))}catch(e){state.error=e.message;render()}});return;
}
root.innerHTML=`<div class="header"><div><div class="eyebrow">STATISTIK · HOCKEY</div><h1 class="title">🏒 Hockeyprognos</h1><div class="muted">1X2 efter 60 minuter</div></div><button class="theme" id="theme">${state.light?'🌙 Mörkt':'☀️ Ljust'}</button></div><div class="filters">${[['ALL','Alla'],['SHL','SHL'],['HA','HockeyAllsvenskan'],['NHL','NHL']].map(([id,label])=>`<button class="chip ${state.league===id?'active':''}" data-league="${id}">${label}</button>`).join('')}</div><div class="controls"><input class="date" type="date" id="date" value="${state.date}"><button class="chip" id="refresh">↻</button></div>${state.error?`<section class="panel warning">⚠️ ${esc(state.error)}</section>`:''}${state.loading?'<section class="panel empty">Hämtar matcher…</section>':state.matches.length?state.matches.map(card).join(''):'<section class="panel empty"><strong>Inga verifierade matcher hittades</strong><p class="muted">Välj ett annat datum eller kontrollera datakällornas status.</p></section>'}${state.leagues.filter(l=>l.error&&(state.league==='ALL'||l.league===state.league)).map(l=>`<section class="panel warning">⚠️ ${esc(l.name)}: ${esc(l.error)}</section>`).join('')}${notice()}<section class="panel accuracy-panel"><h3>🎯 Modellens träffsäkerhet · ${state.league==='ALL'?'NHL (endast NHL-statistik)':state.league==='HA'?'HockeyAllsvenskan':state.league}</h3><div id="perf">Hämtar utvärderade prognoser…</div></section>`;
hydrateSwedishLogos();document.getElementById('theme').onclick=()=>{state.light=!state.light;localStorage.setItem('theme',state.light?'light':'dark');render()};document.querySelectorAll('[data-league]').forEach(el=>el.onclick=()=>{state.league=el.dataset.league;load()});document.getElementById('date').onchange=e=>{state.date=e.target.value;load()};document.getElementById('refresh').onclick=load;document.querySelectorAll('[data-id]').forEach(el=>el.onclick=async()=>{try{showDetail(await get('/api/matches/'+encodeURIComponent(el.dataset.id)))}catch(e){state.error=e.message;render()}});get('/api/performance?league='+encodeURIComponent(state.league==='ALL'?'NHL':state.league)).then(p=>{const el=document.getElementById('perf');if(!el||p.league!==(state.league==='ALL'?'NHL':state.league))return;const games=p.recent||[];el.innerHTML=`<p class="muted">${esc(p.method)}</p><div class="accuracy-stats"><div><strong>${p.evaluated}</strong><span>Utvärderade</span></div><div><strong>${p.accuracy_pct===null?'–':pct(p.accuracy_pct)}</strong><span>Rätt favorit (1/X/2)</span></div><div><strong>${p.mean_brier===null?'–':Number(p.mean_brier).toFixed(3)}</strong><span>Brier-poäng</span></div></div>${!p.evaluated?'<p class="muted">Inga sparade förhandsprognoser har ännu hunnit avslutas och utvärderas. Statistik byggs upp automatiskt.</p>':`<h4>Träffsäkerhet per prognosstyrka</h4><div class="accuracy-bins">${p.calibration.filter(b=>b.games).map(b=>`<div class="metric"><span>${esc(b.range)} % favorit · ${b.games} matcher</span><strong>${pct(b.hit_rate_pct)} rätt</strong></div>`).join('')}</div><h4>Senaste utvärderade matcher</h4>${games.map(g=>`<div class="metric"><span>${g.correct?'✓':'✕'} ${esc(g.home)} – ${esc(g.away)} (${g.score.home}–${g.score.away})<small class="accuracy-sub"> Tips ${esc(g.predicted_outcome)} · Utfall ${esc(g.actual_outcome)}</small></span><strong>${g.correct?'Rätt':'Fel'}</strong></div>`).join('')}`}<p class="muted">${p.pending_forecasts} sparade prognoser väntar på resultat.</p>${p.storage_warning?`<p class="accuracy-warning">⚠️ ${esc(p.storage_warning)}</p>`:''}`}).catch(()=>{const el=document.getElementById('perf');if(el)el.textContent='Träffsäkerheten kunde inte hämtas.'});
}
async function loadHistory(){state.loading=true;state.error="";render();try{const data=await get("/api/history?league=NHL&limit="+state.historyLimit+"&offset="+state.historyOffset+(state.historyTeam?"&team="+encodeURIComponent(state.historyTeam):""));state.history=data.matches;state.historyTotal=data.total;state.historyTeams=data.teams;state.historySeason=data.season}catch(e){state.error="Historiken kunde inte hämtas: "+e.message;state.history=[]}state.loading=false;render()}
async function load(){state.loading=true;state.error='';render();try{const [matches,leagues]=await Promise.all([get('/api/matches?day='+state.date+'&days='+state.days+(state.league==='ALL'?'':'&league='+state.league)),get('/api/leagues')]);state.matches=matches;state.leagues=leagues}catch(e){state.error='Kunde inte hämta riktig matchdata. Kontrollera internetanslutningen och servern. '+e.message;state.matches=[]}state.loading=false;render()}
load();if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
