const root = document.getElementById("root");
const state = {
  league: "ALL",
  date: new Date().toLocaleDateString("sv-SE", {
    timeZone: "Europe/Stockholm",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }),
  leagues: [],
  matches: [],
  error: "",
  detail: null,
  loading: true,
  light: localStorage.getItem("theme") === "light",
  days: 7,
  view: "matches",
  analysisLeague: "SHL",
  history: [],
  historyTeams: [],
  historyTeam: "",
  historyTotal: 0,
  historyOffset: 0,
  historyLimit: 50,
  formData: {},
  formExpanded: {},
  formLoading: false,
  formError: "",
  goalies: null,
  goalieError: "",
  goalieLoading: false,
  shlStats: null,
  shlStatsError: "",
  shlStatsLoading: false,
  shlStatsTab: "standings",
  h2h: null,
  h2hError: "",
};
state.date = state.date.split("-").join("-");
const esc = (x) =>
  String(x ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const pct = (p) =>
  p === undefined || p === null
    ? "–"
    : Number(p).toFixed(2).replace(".", ",") + " %";
const formatDate = (d) =>
  new Date(d).toLocaleString("sv-SE", {
    timeZone: "Europe/Stockholm",
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
async function get(path) {
  const r = await fetch(path);
  if (!r.ok) throw Error("Serverfel " + r.status);
  return r.json();
}
// Officiella NHL-klubbmärken från NHL:s publika bildserver.
const NHL_CODES = {
  "Anaheim Ducks": "ANA",
  "Boston Bruins": "BOS",
  "Buffalo Sabres": "BUF",
  "Calgary Flames": "CGY",
  "Carolina Hurricanes": "CAR",
  "Chicago Blackhawks": "CHI",
  "Colorado Avalanche": "COL",
  "Columbus Blue Jackets": "CBJ",
  "Dallas Stars": "DAL",
  "Detroit Red Wings": "DET",
  "Edmonton Oilers": "EDM",
  "Florida Panthers": "FLA",
  "Los Angeles Kings": "LAK",
  "Minnesota Wild": "MIN",
  "Montréal Canadiens": "MTL",
  "Montreal Canadiens": "MTL",
  "Nashville Predators": "NSH",
  "New Jersey Devils": "NJD",
  "New York Islanders": "NYI",
  "New York Rangers": "NYR",
  "Ottawa Senators": "OTT",
  "Philadelphia Flyers": "PHI",
  "Pittsburgh Penguins": "PIT",
  "San Jose Sharks": "SJS",
  "Seattle Kraken": "SEA",
  "St. Louis Blues": "STL",
  "Tampa Bay Lightning": "TBL",
  "Toronto Maple Leafs": "TOR",
  "Utah Mammoth": "UTA",
  "Utah Hockey Club": "UTA",
  "Vancouver Canucks": "VAN",
  "Vegas Golden Knights": "VGK",
  "Washington Capitals": "WSH",
  "Winnipeg Jets": "WPG",
};
// Svensk klubbidentifiering 2026/27. Commons-loggor laddas endast när en fil
// tydligt matchar klubbnamn och är märkt som logotyp/emblem.
const SWEDISH_CLUBS = {
  SHL: {
    "IF Björklöven": ["IF Björklöven", "Björklöven"],
    Björklöven: ["IF Björklöven", "Björklöven"],
    "Brynäs IF": ["Brynäs IF", "Brynäs"],
    Brynäs: ["Brynäs IF", "Brynäs"],
    "Djurgårdens IF": ["Djurgårdens IF", "Djurgården"],
    "Djurgården Hockey": ["Djurgårdens IF", "Djurgården"],
    Djurgården: ["Djurgårdens IF", "Djurgården"],
    "Frölunda HC": ["Frölunda HC", "Frölunda"],
    Frölunda: ["Frölunda HC", "Frölunda"],
    "Färjestad BK": ["Färjestad BK", "Färjestad"],
    Färjestad: ["Färjestad BK", "Färjestad"],
    HV71: ["HV71", "HV71"],
    "Linköping HC": ["Linköping HC", "Linköping"],
    Linköping: ["Linköping HC", "Linköping"],
    "Luleå Hockey": ["Luleå HF", "Luleå"],
    "Luleå HF": ["Luleå HF", "Luleå"],
    Luleå: ["Luleå HF", "Luleå"],
    "Malmö Redhawks": ["Malmö Redhawks", "Malmö"],
    Malmö: ["Malmö Redhawks", "Malmö"],
    "Rögle BK": ["Rögle BK", "Rögle"],
    Rögle: ["Rögle BK", "Rögle"],
    "Skellefteå AIK": ["Skellefteå AIK", "Skellefteå"],
    Skellefteå: ["Skellefteå AIK", "Skellefteå"],
    "Timrå IK": ["Timrå IK", "Timrå"],
    Timrå: ["Timrå IK", "Timrå"],
    "Växjö Lakers": ["Växjö Lakers", "Växjö"],
    Växjö: ["Växjö Lakers", "Växjö"],
    "Örebro HK": ["Örebro HK", "Örebro"],
    "Örebro Hockey": ["Örebro HK", "Örebro"],
    Örebro: ["Örebro HK", "Örebro"],
  },
  HA: {
    AIK: ["AIK Ishockey", "AIK"],
    "AIK Hockey": ["AIK Ishockey", "AIK"],
    "Almtuna IS": ["Almtuna IS", "Almtuna"],
    Almtuna: ["Almtuna IS", "Almtuna"],
    "BIK Karlskoga": ["BIK Karlskoga", "Karlskoga"],
    Karlskoga: ["BIK Karlskoga", "Karlskoga"],
    "IK Oskarshamn": ["IK Oskarshamn", "Oskarshamn"],
    Oskarshamn: ["IK Oskarshamn", "Oskarshamn"],
    "Kalmar HC": ["Kalmar HC", "Kalmar"],
    Kalmar: ["Kalmar HC", "Kalmar"],
    "Leksands IF": ["Leksands IF", "Leksand"],
    Leksand: ["Leksands IF", "Leksand"],
    "MoDo Hockey": ["MoDo Hockey", "MoDo"],
    MoDo: ["MoDo Hockey", "MoDo"],
    "Modo Hockey": ["MoDo Hockey", "MoDo"],
    "Mora IK": ["Mora IK", "Mora"],
    Mora: ["Mora IK", "Mora"],
    "Nybro Vikings IF": ["Nybro Vikings", "Nybro"],
    "Nybro Vikings": ["Nybro Vikings", "Nybro"],
    Nybro: ["Nybro Vikings", "Nybro"],
    "Södertälje SK": ["Södertälje SK", "Södertälje"],
    Södertälje: ["Södertälje SK", "Södertälje"],
    "Vimmerby HC": ["Vimmerby HC", "Vimmerby"],
    Vimmerby: ["Vimmerby HC", "Vimmerby"],
    "Visby/Roma HK": ["Visby Roma", "Visby"],
    "Visby Roma": ["Visby Roma", "Visby"],
    "Visby/Roma": ["Visby Roma", "Visby"],
    "Västerås IK": ["Västerås IK", "Västerås"],
    Västerås: ["Västerås IK", "Västerås"],
    "Östersunds IK": ["Östersunds IK", "Östersund"],
    Östersund: ["Östersunds IK", "Östersund"],
  },
};
// Matchdatans kortnamn kopplas till samma namn som SHL:s loggregister.

const SHL_CANONICAL = {
  Brynäs: "Brynäs IF",
  Djurgården: "Djurgårdens IF",
  "Djurgården Hockey": "Djurgårdens IF",
  "Djurgården Herr": "Djurgårdens IF",

  Färjestad: "Färjestad BK",
  "Färjestad Herr": "Färjestad BK",

  Frölunda: "Frölunda HC",
  Linköping: "Linköping HC",

  Luleå: "Luleå Hockey",
  "Luleå HF": "Luleå Hockey",

  Malmö: "Malmö Redhawks",
  Redhawks: "Malmö Redhawks",

  Örebro: "Örebro Hockey",
  "Örebro HK": "Örebro Hockey",

  Rögle: "Rögle BK",
  Skellefteå: "Skellefteå AIK",
  Timrå: "Timrå IK",
  Växjö: "Växjö Lakers",

  Björklöven: "Björklöven",
  "IF Björklöven": "Björklöven",
  "Björklöven Herr": "Björklöven",
};

const HA_CANONICAL = {
  LIF: "Leksands IF",
  VIS: "Visby/Roma HK",
  AIK: "AIK",
  SSK: "Södertälje SK",
  KHC: "Kalmar HC",
  AIS: "Almtuna IS",
  MORA: "Mora IK",
  MODO: "MoDo Hockey",
  BIK: "BIK Karlskoga",
  IKO: "IK Oskarshamn",
  NYB: "Nybro Vikings IF",
  VIK: "Västerås IK",
  VHC: "Vimmerby HC",
  OIK: "Östersunds IK",
};
function displayTeamName(name, league) {
  if (league === "SHL") return SHL_CANONICAL[name] || name;
  if (league === "HA") return HA_CANONICAL[String(name).toUpperCase()] || name;
  return name;
}
// SHL:s officiella lagregister ger klubbmärken direkt, utan Wikimedia-sökning.
// 2026/27 grundserie: ssgtUuid från SHL:s layout-info.
const SHL_SSGT_UUID = "qa98unlbd6";
const logoMemo = new Map();
const swedishLogoDirectories = new Map();
const logoKey = (league, name) => league + ":" + name;
function normalizedLogoText(v) {
  return String(v ?? "")
    .toLocaleLowerCase("sv")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]/g, "");
}
async function loadSwedishLogoDirectory(league) {
  if (!swedishLogoDirectories.has(league)) {
    const endpoint = league === "HA" ? "/api/ha/logos" : "/api/shl/logos";
    const promise = (async () => {
      const r = await fetch(endpoint, { signal: AbortSignal.timeout(12000) });
      if (!r.ok) throw Error(league + " lagregister HTTP " + r.status);
      const data = await r.json();
      const teams = Array.isArray(data) ? data : data.teams || [];
      return teams.map((t) => ({
        name: t.name || t.displayName || t.fullName || t.names?.long || "",
        fullName: t.fullName || "",
        code: t.code || "",
        icon: t.icon || t.logo || "",
      }));
    })().catch((err) => {
      console.warn(league + "-loggor kunde inte hämtas:", err);
      swedishLogoDirectories.delete(league);
      return [];
    });
    swedishLogoDirectories.set(league, promise);
  }
  return swedishLogoDirectories.get(league);
}
async function resolveSwedishLogo(league, name) {
  if (league !== "SHL" && league !== "HA") return null;
  const canonical = displayTeamName(name, league);
  const key = logoKey(league, canonical);
  if (logoMemo.has(key)) return logoMemo.get(key);
  const sites = await loadSwedishLogoDirectory(league);
  const targets = [
    canonical,
    name,
    ...(SWEDISH_CLUBS[league]?.[name] || []),
    ...(SWEDISH_CLUBS[league]?.[canonical] || []),
  ].map(normalizedLogoText);
  const site = sites.find((s) =>
    [s.name, s.fullName, s.code].some((n) =>
      targets.includes(normalizedLogoText(n)),
    ),
  );
  let url = site?.icon || "";
  if (url.startsWith("//")) url = "https:" + url;
  else if (url.startsWith("/"))
    url =
      (league === "HA"
        ? "https://hockeyallsvenskan.se"
        : "https://www.shl.se") + url;
  if (!/^https:\/\//i.test(url)) url = "";
  if (league === "HA" && site?.code && url) {
    // The official image is the backup if the server-side proxy is blocked.
    const official = url;
    url = "/api/ha/logo/" + encodeURIComponent(site.code);
    // Only same-origin fallback metadata; do not trust arbitrary HTML attributes.
    logoMemo.set(key + ":official", official);
  }
  if (url) logoMemo.set(key, url);
  return url || null;
}

function hydrateSwedishLogos() {
  document.querySelectorAll("[data-swedish-logo]").forEach(async (el) => {
    const league = el.dataset.league;
    const name = el.dataset.team;

    const url = await resolveSwedishLogo(league, name);

    if (!url || !el.isConnected) return;

    const img = document.createElement("img");
    img.className = "team-logo";
    img.alt = name + " klubbmärke";
    img.loading = "lazy";
    img.decoding = "async";

    img.onerror = () => {
      const official = logoMemo.get(
        logoKey(league, displayTeamName(name, league)) + ":official",
      );
      if (
        league === "HA" &&
        official &&
        img.src !== official &&
        !img.dataset.triedOfficial
      ) {
        img.dataset.triedOfficial = "1";
        img.src = official;
        return;
      }
      if (img.isConnected) img.replaceWith(el);
    };

    img.src = url;
    el.replaceWith(img);
  });
}

function teamMark(name, league) {
  const code = league === "NHL" ? NHL_CODES[name] : null;
  if (!code) {
    const swedish = league === "SHL" || league === "HA";
    return `<span class="team-initial" ${swedish ? `data-swedish-logo="1" data-league="${esc(league)}" data-team="${esc(name)}"` : ""} aria-hidden="true">${esc(name).slice(0, 2).toUpperCase()}</span>`;
  }
  return `<img class="team-logo" src="https://assets.nhle.com/logos/nhl/svg/${code}_light.svg" alt="${esc(name)} klubbmärke" loading="lazy" decoding="async" onerror="this.style.display='none';this.nextElementSibling.style.display='grid'"><span class="team-initial" style="display:none" aria-hidden="true">${esc(code)}</span>`;
}
function notice() {
  return '<section class="panel notice">ℹ️ Prognoser är statistiska uppskattningar, inte garantier. 1X2 avser resultatet efter 60 minuter – utan förlängning och straffar.</section>';
}

// 1X2-förslag från den aktuella liveprognosen; ingen separat tränad AI aktiveras här.
function suggestedOutcome(m) {
  const p = m.prediction;
  if (
    !p ||
    [p.home_win, p.draw, p.away_win].some((v) => !Number.isFinite(Number(v)))
  )
    return null;
  const entries = [
    ["1", Number(p.home_win)],
    ["X", Number(p.draw)],
    ["2", Number(p.away_win)],
  ];
  const total = entries.reduce((s, e) => s + e[1], 0);
  if (total <= 0) return null;
  entries.forEach((e) => (e[1] /= total));
  entries.sort((a, b) => b[1] - a[1]);
  const [pick, prob] = entries[0];
  const second = entries[1][1];
  return { pick, prob, margin: prob - second };
}
function trendBadge(m, field) {
  const v = m.trend?.[field];
  if (v === undefined || v === null || !Number.isFinite(Number(v)))
    return `<small class="muted" title="Kräver två sparade förhandsprognoser">Trend: –</small>`;
  const pp = Number(v) * 100;
  const symbol = pp > 0.5 ? "↗" : pp < -0.5 ? "↘" : "→";
  const color = pp > 0.5 ? "#22c55e" : pp < -0.5 ? "#ef4444" : "#94a3b8";
  return `<small style="color:${color}" title="Förändring sedan föregående sparade prognos">${symbol} ${pp > 0 ? "+" : ""}${pp.toFixed(1).replace(".", ",")} pp</small>`;
}
function restInfo(m) {
  if (!m.rest) return "";
  const part = (side, name) => {
    const r = m.rest[side];
    if (!r || r.days_since_last === null)
      return `${esc(name)}: vilodata saknas`;
    return `${esc(name)}: ${r.days_since_last.toFixed(1).replace(".", ",")} dagar sedan senaste match · ${r.games_last_7_days} matcher/7 dagar`;
  };
  return `<p class="muted" style="margin-top:8px;font-size:.83rem">🕒 ${part("home", m.home)}<br>🕒 ${part("away", m.away)}</p>`;
}
function suggestionPanel(m) {
  const s = suggestedOutcome(m);
  if (!s)
    return `<div class="pick-panel"><strong>🎯 Modellens 1X2-förslag</strong><p class="muted">Väntar på tillräcklig statistik för ett förslag.</p></div>`;
  const names = { 1: "Hemmaseger", X: "Oavgjort", 2: "Bortaseger" };
  // Initial display threshold, NOT trained or calibrated. A pick remains visible for analysis.
  const marginPP = s.margin * 100;
  const verdict =
    marginPP < 5
      ? "Avstå – jämn match"
      : marginPP < 12
        ? "Jämn match – försiktighet"
        : "Tydligare modellförslag";
  const verified = m.status === "FINISHED" && m.actual_outcome;
  const result = verified
    ? `<p class="muted">Utfall efter 60 min: <strong>${esc(m.actual_outcome)}</strong> · <strong>${s.pick === m.actual_outcome ? "✓ Rätt" : "✕ Fel"}</strong></p>`
    : "";
  return `<div class="pick-panel"><div class="pick-head"><strong>🎯 Modellens 1X2-förslag</strong><span class="pick-choice">${esc(s.pick)} · ${names[s.pick]}</span></div><p><strong>${verdict}</strong></p><p class="muted">Sannolikhet: ${(s.prob * 100).toFixed(1).replace(".", ",")} % · Skillnad till tvåan: ${marginPP.toFixed(1).replace(".", ",")} procentenheter</p>${restInfo(m)}<p class="muted">🥅 Startmålvakter: ej bekräftade i tillgänglig datakälla. Målvaktsstatistik finns under SHL Statistik.</p>${result}<p class="muted pick-note">Gränserna 5/12 pp är preliminära och ska backtestas. Förslaget kommer från nuvarande modell, inte AI-kandidaten.</p></div>`;
}

function card(m) {
  const p = m.prediction;
  const finished = m.status === "FINISHED";
  const live = m.status === "LIVE";
  const pending =
    m.status === "PENDING" ||
    (m.status === "SCHEDULED" && new Date(m.date).getTime() <= Date.now());
  const status = finished
    ? `SLUT · 60 min: ${esc(m.score.home)}–${esc(m.score.away)}`
    : live
      ? "PÅGÅR · resultat inväntas"
      : pending
        ? "STARTAD · resultat inväntas"
        : "Kommande";
  const outcome =
    finished && m.actual_outcome && m.predicted_outcome
      ? `<p class="muted" style="margin-top:10px">Prognos före match: ${esc(m.predicted_outcome)} · Utfall efter 60 min: ${esc(m.actual_outcome)} · <strong>${m.predicted_outcome === m.actual_outcome ? "✓ Rätt" : "✕ Fel"}</strong></p>`
      : "";
  const probabilities = p
    ? `<div class="percent"><div><small>1 · Hemma</small><b>${pct(p.home_win)}</b>${trendBadge(m, "home_win")}</div><div><small>X · Oavgjort</small><b>${pct(p.draw)}</b>${trendBadge(m, "draw")}</div><div><small>2 · Borta</small><b>${pct(p.away_win)}</b>${trendBadge(m, "away_win")}</div></div>`
    : `<p class="muted">${finished ? "Ingen arkiverad prognos före matchstart." : pending || live ? "Resultatet kontrolleras mot NHL:s officiella uppgifter." : "Ingen prognos tillgänglig: otillräcklig verifierad matchhistorik."}</p>`;
  return `<article class="panel match" data-id="${esc(m.id)}"><div class="topline"><span>${esc(m.league)} · ${esc(formatDate(m.date))}</span><span>${status}</span></div><div class="teams"><div class="team-side">${teamMark(m.home, m.league)}<span>${esc(displayTeamName(m.home, m.league))}</span></div><span class="vs">${finished ? `${esc(m.score.home)}–${esc(m.score.away)}` : "VS"}</span><div class="team-side">${teamMark(m.away, m.league)}<span>${esc(displayTeamName(m.away, m.league))}</span></div></div>${finished ? '<p class="muted" style="margin-bottom:8px">Arkiverad prognos före matchstart</p>' : ""}${probabilities}${suggestionPanel(m)}${outcome}</article>`;
}

// Resultat efter 60 minuter: V / O / F utifrån valt lags perspektiv.
function teamFormResult(m, team) {
  const home =
    typeof m.perspective_home === "boolean"
      ? m.perspective_home
      : m.home === team;
  const gf = Number(home ? m.score?.home : m.score?.away),
    ga = Number(home ? m.score?.away : m.score?.home);
  return gf > ga ? "V" : gf < ga ? "F" : "O";
}
function formDate(d) {
  return new Date(d).toLocaleDateString("sv-SE", {
    timeZone: "Europe/Stockholm",
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  });
}
function teamFormCard(team, league = "NHL") {
  const matches = state.formData[team] || [];
  const expanded = !!state.formExpanded[team];
  const maxGames = league === "SHL" ? 10 : league === "HA" ? 100 : 20;
  const shown = expanded ? matches.slice(0, maxGames) : matches.slice(0, 5);
  return `<section class="panel form-panel"><div class="form-heading"><div class="form-team">${teamMark(team, league)}<strong>Senast ${esc(team)}</strong></div><div class="form-dots">${matches
    .slice(0, 5)
    .map(
      (m) =>
        `<span class="form-dot form-${teamFormResult(m, team)}" title="${esc(formDate(m.date))}">${teamFormResult(m, team)}</span>`,
    )
    .join("")}</div></div>${
    state.formLoading
      ? '<p class="muted">Hämtar senaste matcher…</p>'
      : !matches.length
        ? '<p class="muted">Ingen historik hittades för laget.</p>'
        : `<div class="form-list">${shown
            .map((m) => {
              const home =
                typeof m.perspective_home === "boolean"
                  ? m.perspective_home
                  : m.home === team;
              const opponent = home ? m.away : m.home;
              const gf = home ? m.score.home : m.score.away;
              const ga = home ? m.score.away : m.score.home;
              return `<div class="form-match"><div class="form-location">${home ? "H" : "B"}</div><div class="form-result form-${teamFormResult(m, team)}">${teamFormResult(m, team)}</div><div class="form-scores"><span>${esc(m.home)} <b>${esc(m.score.home)}</b></span><span>${esc(m.away)} <b>${esc(m.score.away)}</b></span></div><div class="form-match-date">${esc(formDate(m.date))}<small>60 min</small></div></div>`;
            })
            .join(
              "",
            )}</div>${matches.length > 5 ? `<button class="form-more" data-form-team="${esc(team)}">${expanded ? "Visa färre matcher" : "Visa alla " + Math.min(matches.length, maxGames) + " matcher"} <span>${expanded ? "⌃" : "⌄"}</span></button>` : ""}`
  }</section>`;
}
async function loadTeamForms(m) {
  if (m.league !== "NHL" && m.league !== "SHL" && m.league !== "HA") return;
  state.formLoading = true;
  state.formData = {};
  state.formError = "";
  render();
  try {
    if (m.league === "HA") {
      const data = await get(
        "/api/match-form/" + encodeURIComponent(m.id) + "?limit=100",
      );
      if (state.detail?.id !== m.id) return;
      state.formData[m.home] = data.home?.matches || [];
      state.formData[m.away] = data.away?.matches || [];
      return;
    }
    const listing = await get(
      "/api/history?league=" + encodeURIComponent(m.league) + "&limit=1",
    );
    const teams = listing.teams || [];
    const selected = [m.home, m.away];
    const pairs = selected.map((name) => ({
      name,
      id: teams.find((t) => t.name === name)?.id,
    }));
    const result = await Promise.all(
      pairs.map(async (t) =>
        t.id
          ? get(
              "/api/history?league=" +
                encodeURIComponent(m.league) +
                "&limit=" +
                (m.league === "SHL" ? 10 : 20) +
                "&team=" +
                encodeURIComponent(t.id),
            )
          : null,
      ),
    );
    if (state.detail?.id !== m.id) return;
    pairs.forEach((t, i) => {
      state.formData[t.name] = result[i]?.matches || [];
    });
  } catch (e) {
    if (state.detail?.id === m.id) state.formError = e.message;
  } finally {
    if (state.detail?.id === m.id) {
      state.formLoading = false;
      render();
    }
  }
}
async function loadGoalies(m) {
  if (m.league !== "SHL") return;
  state.goalieLoading = true;
  state.goalies = null;
  state.goalieError = "";
  render();
  try {
    const data = await get("/api/shl/goalkeepers");
    if (state.detail?.id !== m.id) return;
    state.goalies = data;
  } catch (e) {
    if (state.detail?.id === m.id) state.goalieError = e.message;
  } finally {
    if (state.detail?.id === m.id) {
      state.goalieLoading = false;
      render();
    }
  }
}
function goaliePanel() {
  const rows = state.goalies?.goalkeepers || [];
  const link =
    state.goalies?.source ||
    "https://www.shl.se/game-stats/goalkeepers/summary";
  return `<section class="panel"><h3>🥅 SHL · Målvaktsstatistik</h3>
    <p class="muted">Officiell säsongsstatistik. Startande målvakter är ännu inte verifierade och påverkar inte prognosen.</p>
    ${
      state.goalieLoading
        ? '<p class="muted">Hämtar målvaktsstatistik…</p>'
        : state.goalieError
          ? `<p class="muted">Kunde inte hämta statistik: ${esc(state.goalieError)}</p>`
          : rows.length
            ? `<div class="metric"><span>Målvakt</span><strong>SVS% · GAA</strong></div>${rows
                .slice(0, 12)
                .map(
                  (g) =>
                    `<div class="metric"><span>${esc(g.name)}${g.team ? ` · ${esc(g.team)}` : ""}</span><strong>${esc(g.save_pct)} % · ${esc(g.gaa)}</strong></div>`,
                )
                .join("")}`
            : '<p class="muted">Ingen verifierbar statistik kunde läsas automatiskt just nu.</p>'
    }
    <p><a href="${esc(link)}" target="_blank" rel="noopener noreferrer">Visa officiell målvaktsstatistik hos SHL ↗</a></p>
  </section>`;
}
function showDetail(m) {
  state.detail = m;
  state.formExpanded = {};
  state.formData = {};
  state.formError = "";
  state.goalies = null;
  state.goalieError = "";
  state.h2h = null;
  state.h2hError = "";
  render();
  loadTeamForms(m);
  get("/api/h2h/" + encodeURIComponent(m.id) + "?limit=10")
    .then((data) => {
      if (state.detail?.id === m.id) {
        state.h2h = data;
        render();
      }
    })
    .catch((e) => {
      if (state.detail?.id === m.id) {
        state.h2hError = e.message;
        render();
      }
    });
}
function bindFormButtons() {
  document.querySelectorAll("[data-form-team]").forEach(
    (b) =>
      (b.onclick = () => {
        const team = b.dataset.formTeam;
        state.formExpanded[team] = !state.formExpanded[team];
        render();
      }),
  );
}
async function loadShlStatistics() {
  state.shlStatsLoading = true;
  state.shlStatsError = "";
  render();
  try {
    state.shlStats = await get("/api/shl/statistics");
  } catch (e) {
    state.shlStatsError = e.message;
  } finally {
    state.shlStatsLoading = false;
    if (state.view === "shl-stats") render();
  }
}

function shlStatisticsView() {
  const data = state.shlStats || {};
  const tab = state.shlStatsTab;
  const fmt = (n, digits = 0) =>
    n == null ? "–" : Number(n).toFixed(digits).replace(".", ",");
  const cols = {
    standings: [
      ["rank", "#"],
      ["team", "Lag"],
      ["played", "M"],
      ["wins", "V"],
      ["draws", "O"],
      ["losses", "F"],
      ["goal_diff", "MS"],
      ["points", "P"],
    ],
    scorers: [
      ["rank", "#"],
      ["name", "Spelare"],
      ["team", "Lag"],
      ["played", "M"],
      ["goals", "Mål"],
      ["assists", "Ass"],
      ["points", "Poäng"],
    ],
    goalies: [
      ["rank", "#"],
      ["name", "Målvakt"],
      ["team", "Lag"],
      ["played", "Matcher"],
      ["shots", "Skott"],
      ["gaa", "GAA"],
      ["save_pct", "Räddn. %"],
    ],
  };
  const fields = cols[tab];
  const rows = data[tab] || [];
  const numeric = new Set(["gaa", "save_pct"]);
  const table = rows.length
    ? `<div class="swehockey-table-wrap"><table class="swehockey-table"><thead><tr>${fields.map(([, label]) => `<th>${label}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${fields.map(([k]) => `<td>${esc(typeof r[k] === "number" ? fmt(r[k], numeric.has(k) ? 2 : 0) : r[k] || "–")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
    : `<div class="swehockey-empty">Ingen verifierad statistik kunde läsas för den här kategorin. Kontrollera källan nedan.</div>`;
  const source = {
    standings: "https://stats.swehockey.se/ScheduleAndResults/Overview/20961",
    scorers:
      "https://stats.swehockey.se/Players/Statistics/ScoringLeaders/20961",
    goalies:
      "https://stats.swehockey.se/Players/Statistics/LeadingGoaliesSVS/20961",
  }[tab];
  root.innerHTML = `<div class="header"><div><div class="eyebrow">SWEHOCKEY · SHL 2026/27</div><h1 class="title">📊 SHL Statistik</h1><div class="muted">Officiell säsongsstatistik · Svenska Ishockeyförbundet</div></div><button class="theme" id="theme">${state.light ? "🌙 Mörkt" : "☀️ Ljust"}</button></div><div class="filters"><button class="chip" id="stats-back">← Matcher</button>${[
    ["standings", "Tabell"],
    ["scorers", "Poängliga"],
    ["goalies", "Målvakter"],
  ]
    .map(
      ([id, label]) =>
        `<button class="chip ${tab === id ? "active" : ""}" data-stats-tab="${id}">${label}</button>`,
    )
    .join(
      "",
    )}<button class="chip" id="stats-refresh">↻ Uppdatera</button></div><section class="panel swehockey-panel"><div class="swehockey-head"><div><h3>${{ standings: "🏆 SHL-tabellen", scorers: "🏒 Poängligan", goalies: "🥅 Målvaktsligan" }[tab]}</h3><p class="muted">Säsongen 2026/27 · ${rows.length} poster</p></div><span class="swehockey-tag">Officiell statistik</span></div>${state.shlStatsLoading ? '<p class="muted">Hämtar Swehockey-statistik…</p>' : state.shlStatsError ? `<p class="muted">Kunde inte hämta statistik: ${esc(state.shlStatsError)}</p>` : table}<p class="muted" style="margin-top:14px">${tab === "goalies" ? "Säsongsstatistik – inte bekräftade startmålvakter. " : ""}Källa: <a href="${source}" target="_blank" rel="noopener noreferrer">Swehockey ↗</a></p></section><section class="panel notice">ℹ️ Statistiken visas separat och påverkar ännu inte prognosmodellens 1X2-beräkningar.</section>`;
  document.getElementById("theme").onclick = () => {
    state.light = !state.light;
    localStorage.setItem("theme", state.light ? "light" : "dark");
    render();
  };
  document.getElementById("stats-back").onclick = () => {
    state.view = "matches";
    render();
  };
  document.getElementById("stats-refresh").onclick = loadShlStatistics;
  document.querySelectorAll("[data-stats-tab]").forEach(
    (el) =>
      (el.onclick = () => {
        state.shlStatsTab = el.dataset.statsTab;
        render();
      }),
  );
}

function h2hPanel() {
  const h = state.h2h;
  if (!h)
    return `<section class="panel"><h3>🤝 Inbördes möten (H2H)</h3><p class="muted">${state.h2hError ? "Kunde inte läsa historiken: " + esc(state.h2hError) : "Hämtar tidigare möten…"}</p></section>`;
  const games = h.meetings || [];
  return `<section class="panel"><h3>🤝 Inbördes möten · senaste ${h.total}</h3>
    <p class="muted">Historiska 60-minutersresultat · ingen påverkan på liveprognosen ännu</p>
    <div class="metric"><span>${esc(h.home)} / Oavgjort / ${esc(h.away)}</span><strong>${h.home_wins} / ${h.draws} / ${h.away_wins}</strong></div>
    ${games.length ? games.map((g) => `<div class="metric"><span>${esc(g.home)} – ${esc(g.away)}<small class="accuracy-sub">${esc(formDate(g.date))}</small></span><strong>${g.home_goals}–${g.away_goals}</strong></div>`).join("") : '<p class="muted">Inga tidigare inbördes möten finns i databasen.</p>'}
    </section>`;
}

function render() {
  document.documentElement.classList.toggle("light", state.light);
  if (state.view === "shl-stats" && !state.detail) {
    shlStatisticsView();
    return;
  }
  if (state.detail) {
    const m = state.detail,
      p = m.prediction,
      d = p?.details;
    root.innerHTML = `<button class="back" id="back">← Till matcher</button><div class="eyebrow">${esc(m.league)} · ${esc(formatDate(m.date))}</div><h1 class="title">${esc(displayTeamName(m.home, m.league))} – ${esc(displayTeamName(m.away, m.league))}</h1>${card(m)}${m.league === "NHL" || m.league === "SHL" ? `<h2 class="form-section-title">Lagform · senaste ${m.league === "SHL" ? "10" : "20"} matcher</h2>${state.formError ? `<p class="muted">${esc(state.formError)}</p>` : ""}${teamFormCard(m.home, m.league)}${teamFormCard(m.away, m.league)}` : ""}${m.league === "HA" ? `<h2 class="form-section-title">Senaste spelade matcher</h2><p class="muted">Resultat och form efter 60 minuter · V / O / F</p>${state.formError ? `<p class="muted">Kunde inte läsa historiken: ${esc(state.formError)}</p>` : ""}${teamFormCard(m.home, m.league)}${teamFormCard(m.away, m.league)}` : ""}${h2hPanel()}${p ? `<section class="panel"><h3>Matchanalys</h3><div class="metric"><span>Förväntade mål hemma</span><strong>${p.expected_home}</strong></div><div class="metric"><span>Förväntade mål borta</span><strong>${p.expected_away}</strong></div><div class="metric"><span>Elo hemma / borta</span><strong>${d.home_elo} / ${d.away_elo}</strong></div><div class="metric"><span>Hemmaform (mål för/emot)</span><strong>${d.home_form.scored} / ${d.home_form.conceded} (${d.home_form.played} matcher)</strong></div><div class="metric"><span>Bortaform (mål för/emot)</span><strong>${d.away_form.scored} / ${d.away_form.conceded} (${d.away_form.played} matcher)</strong></div><h3>Troligaste resultat efter 60 min</h3>${d.top_scores.map((s) => `<div class="metric"><span>${esc(s.score)}</span><strong>${pct(s.probability)}</strong></div>`).join("")}</section>` : ""}${notice()}`;
    hydrateSwedishLogos();
    document.getElementById("back").onclick = () => {
      state.detail = null;
      render();
    };
    bindFormButtons();
    return;
  }
  if (state.view === "analysis") {
    root.innerHTML = `<div class="header"><div><div class="eyebrow">STATISTIK · HOCKEY</div><h1 class="title">🧪 Modellanalys</h1><div class="muted">Backtest och prognosernas träffsäkerhet</div></div><button class="theme" id="theme">${state.light ? "🌙 Mörkt" : "☀️ Ljust"}</button></div><div class="filters"><button class="chip" id="analysis-back">← Matcher</button><button class="chip ${state.analysisLeague === "SHL" ? "active" : ""}" data-analysis-league="SHL">SHL</button><button class="chip ${state.analysisLeague === "NHL" ? "active" : ""}" data-analysis-league="NHL">NHL</button><button class="chip ${state.analysisLeague === "HA" ? "active" : ""}" data-analysis-league="HA">HA</button></div><section class="panel"><h3>🧪 Modelltest · ${esc(state.analysisLeague)}</h3><p class="muted">Jämför nuvarande modell med experimentell målmodell på tidigare matcher. Testet ändrar inte liveprognoserna.</p><button class="chip" id="run-backtest">Kör backtest</button><div id="backtest-result" class="muted" style="margin-top:12px"></div></section><section class="panel"><h3>🧠 AI-träning · ${esc(state.analysisLeague)}</h3><p class="muted">Träna en experimentell kandidat på historiska matcher. Liveprognoserna ändras inte. Kräver en administratörsnyckel som du ställer in i Render.</p><div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center"><input id="ai-admin-token" type="password" placeholder="Administratörsnyckel" autocomplete="off" style="min-width:190px;padding:10px;border-radius:8px"/><button class="chip" id="run-ai-training">Starta AI-träning</button><button class="chip" id="refresh-ai-status">Uppdatera status</button></div><div id="ai-training-status" class="muted" style="margin-top:12px">Läser träningsstatus…</div></section><section class="panel accuracy-panel"><h3>🎯 Modellens träffsäkerhet · ${esc(state.analysisLeague)}</h3><div id="perf">Hämtar utvärderade prognoser…</div></section>`;
    document.getElementById("theme").onclick = () => {
      state.light = !state.light;
      localStorage.setItem("theme", state.light ? "light" : "dark");
      render();
    };
    document.getElementById("analysis-back").onclick = () => {
      state.view = "matches";
      render();
    };
    document.querySelectorAll("[data-analysis-league]").forEach(
      (el) =>
        (el.onclick = () => {
          state.analysisLeague = el.dataset.analysisLeague;
          render();
        }),
    );
    const aiStatus = document.getElementById("ai-training-status");
    const refreshAI = async () => {
      const league = state.analysisLeague;
      try {
        const d = await get(
          "/api/ai/training?league=" + encodeURIComponent(league),
        );
        if (!aiStatus.isConnected || state.analysisLeague !== league) return;
        const statusNames = {
          awaiting_first_weekly_training: "Inväntar första träning",
          training_in_progress: "Träning pågår",
          insufficient_data: "För få historiska matcher",
          evaluated: "Träning och utvärdering genomförd",
        };
        const fmt = (x) => (x == null ? "–" : Number(x).toFixed(3));

        aiStatus.innerHTML =
          `<p><strong>${esc(statusNames[d.status] || d.status || "Okänd status")}</strong></p>` +
          (d.trained_at
            ? `<p>🕒 Senaste AI-träning: ${esc(formatDate(d.trained_at))}</p>`
            : `<p class="muted">Ingen träningstid registrerad ännu.</p>`) +
          (d.available_samples != null
            ? `<p>Matcher tillgängliga: ${esc(d.available_samples)} (minst ${esc(d.minimum_samples)})</p>`
            : "") +
          (d.training_matches != null
            ? `<p>Träningsmatcher: ${esc(d.training_matches)} · Testmatcher: ${esc(d.validation_matches)}</p>`
            : "") +
          (d.baseline && d.candidate
            ? `<div class="metric">
       <span>Träffsäkerhet: nuvarande / AI</span>
       <strong>${fmt(d.baseline.accuracy_pct)}% / ${fmt(d.candidate.accuracy_pct)}%</strong>
     </div>
     <div class="metric">
       <span>Brier score: nuvarande / AI</span>
       <strong>${fmt(d.baseline.mean_brier)} / ${fmt(d.candidate.mean_brier)}</strong>
     </div>
     <div class="metric">
       <span>Log loss: nuvarande / AI</span>
       <strong>${fmt(d.baseline.mean_log_loss)} / ${fmt(d.candidate.mean_log_loss)}</strong>
     </div>`
            : "") +
          (d.diagnostics
            ? (() => {
                const q = d.diagnostics;
                const percent = (v) =>
                  v == null ? "–" : Number(v).toFixed(1) + "%";
                const rows = Object.entries(q.match_types || {})
                  .map(
                    ([k, v]) =>
                      `<div class="metric"><span>${esc({ hemmafavorit: "Hemmafavorit", bortafavorit: "Bortafavorit", oavgjort_favorit: "Oavgjort som favorit", jämn_match: "Jämna matcher", tydlig_favorit: "Tydlig favorit" }[k] || k)} (${v.matches})</span><strong>${percent(v.baseline_accuracy_pct)} / ${percent(v.ai_accuracy_pct)}</strong></div>`,
                  )
                  .join("");
                const outcomeRows = Object.entries(q.outcomes || {})
                  .map(
                    ([k, v]) =>
                      `<div class="metric"><span>${esc(k)}: ${v.actual} verkliga · ${v.predicted} AI-tips</span><strong>Precision ${percent(v.precision_pct)} · Recall ${percent(v.recall_pct)}</strong></div>`,
                  )
                  .join("");
                const confidenceRows = Object.entries(q.confidence_bins || {})
                  .filter(([_, v]) => v.matches)
                  .map(
                    ([k, v]) =>
                      `<div class="metric"><span>${esc(k.replaceAll("_", "–"))}: ${v.matches} matcher · snittprognos ${percent(v.average_confidence_pct)}</span><strong>${percent(v.accuracy_pct)} rätt</strong></div>`,
                  )
                  .join("");
                const mistakes = (q.recent_ai_misses || [])
                  .map(
                    (v) =>
                      `<div class="metric"><span>${esc(v.date)} · AI ${esc(v.ai_pick)} (${percent(v.ai_confidence_pct)})</span><strong>Utfall ${esc(v.actual)}</strong></div>`,
                  )
                  .join("");
                return `<details style="margin-top:16px" open><summary><strong>🔍 Varför missar AI:n? · Testanalys</strong></summary><p class="muted">${esc(q.note || "")}</p><div class="metric"><span>AI rättade fel från grundmodellen</span><strong>${q.ai_corrected_baseline_errors}</strong></div><div class="metric"><span>AI skapade nya fel</span><strong>${q.ai_introduced_errors}</strong></div><h4>Träff per matchtyp</h4><p class="muted">Nuvarande / AI. Jämn match = mindre än 10 procentenheter mellan två högsta utfall.</p>${rows}<h4>1X2 · precision och recall</h4>${outcomeRows}<h4>Kalibrering per säkerhetsnivå</h4>${confidenceRows}<h4>Senaste AI-missarna</h4>${mistakes || "<p>Inga registrerade missar.</p>"}</details>`;
              })()
            : "") +
          (d.insights?.recommendations?.length
            ? `<details style="margin-top:16px" open><summary><strong>🧠 AI:ns förbättringsförslag · ${esc(league)}</strong></summary><p class="muted">Hypoteser från testperioden – inga ändringar aktiveras automatiskt.</p>${d.insights.recommendations.map((r) => `<div style="padding:12px 0;border-bottom:1px solid var(--border, #334155)"><strong>${esc(r.title)}</strong><p class="muted">${esc(r.evidence)}</p><p><strong>Nästa test:</strong> ${esc(r.next_test)}</p></div>`).join("")}</details>`
            : "") +
          `<p class="muted">Liveprognoser: oförändrade. ${esc(d.warning || "")}</p>`;

        if (d.status === "training_in_progress") {
          setTimeout(() => {
            if (aiStatus.isConnected && state.analysisLeague === league) {
              refreshAI();
            }
          }, 15000);
        }
      } catch (e) {
        if (aiStatus.isConnected)
          aiStatus.textContent = "Kunde inte läsa AI-status: " + e.message;
      }
    };
    document.getElementById("refresh-ai-status").onclick = refreshAI;
    document.getElementById("run-ai-training").onclick = async () => {
      const button = document.getElementById("run-ai-training");
      const key = document.getElementById("ai-admin-token").value;
      if (!key) {
        aiStatus.textContent = "Ange administratörsnyckeln från Render.";
        return;
      }
      button.disabled = true;
      aiStatus.textContent = "Startar AI-träning…";
      try {
        const res = await fetch(
          "/api/ai/training/run?league=" +
            encodeURIComponent(state.analysisLeague),
          { method: "POST", headers: { "X-Training-Token": key } },
        );
        const d = await res.json();
        if (!res.ok) throw new Error(d.detail || `HTTP ${res.status}`);
        aiStatus.textContent =
          d.status === "already_running"
            ? "Träning pågår redan. Uppdatera status om en stund."
            : "AI-träning startad. Uppdatera status om en stund.";
        document.getElementById("ai-admin-token").value = "";
      } catch (e) {
        aiStatus.textContent = "Kunde inte starta: " + e.message;
      } finally {
        button.disabled = false;
      }
    };
    refreshAI();
    document.getElementById("run-backtest").onclick = async () => {
      const output = document.getElementById("backtest-result");
      const button = document.getElementById("run-backtest");
      const league = state.analysisLeague;
      button.disabled = true;
      output.textContent = "Testar tidigare matcher i " + league + "…";
      try {
        const data = await get(
          "/api/backtest?league=" + encodeURIComponent(league) + "&limit=120",
        );
        const fmt = (x, digits = 3) =>
          x == null ? "–" : Number(x).toFixed(digits);
        const a = data.models.current,
          b = data.models.experimental,
          h = data.models.h2h;
        output.innerHTML = `<p>${esc(data.method)}</p><div class="accuracy-stats"><div><strong>${a.evaluated}</strong><span>Jämförda matcher</span></div><div><strong>${fmt(a.accuracy_pct, 1)}%</strong><span>Nuvarande träff</span></div><div><strong>${fmt(b.accuracy_pct, 1)}%</strong><span>Experiment träff</span></div><div><strong>${fmt(h?.accuracy_pct, 1)}%</strong><span>H2H träff</span></div></div><div class="metric"><span>Brier · nuvarande / experiment</span><strong>${fmt(a.mean_brier)} / ${fmt(b.mean_brier)}</strong></div><div class="metric"><span>Log loss · nuvarande / experiment / H2H</span><strong>${fmt(a.mean_log_loss)} / ${fmt(b.mean_log_loss)} / ${fmt(h?.mean_log_loss)}</strong></div><div class="metric"><span>Brier · H2H</span><strong>${fmt(h?.mean_brier)}</strong></div><p class="muted">${esc(data.warning)}</p>`;
      } catch (e) {
        output.textContent = "Kunde inte köra modelltest: " + e.message;
      } finally {
        button.disabled = false;
      }
    };
    get("/api/performance?league=" + encodeURIComponent(state.analysisLeague))
      .then((p) => {
        const el = document.getElementById("perf");
        if (!el || p.league !== state.analysisLeague) return;
        const games = p.recent || [];
        el.innerHTML = `<p class="muted">${esc(p.method)}</p><div class="accuracy-stats"><div><strong>${p.evaluated}</strong><span>Utvärderade</span></div><div><strong>${p.accuracy_pct === null ? "–" : pct(p.accuracy_pct)}</strong><span>Rätt favorit (1/X/2)</span></div><div><strong>${p.mean_brier === null ? "–" : Number(p.mean_brier).toFixed(3)}</strong><span>Brier-poäng</span></div></div>${
          !p.evaluated
            ? '<p class="muted">Inga sparade förhandsprognoser har ännu hunnit avslutas och utvärderas. Statistik byggs upp automatiskt.</p>'
            : `<h4>Träffsäkerhet per prognosstyrka</h4><div class="accuracy-bins">${p.calibration
                .filter((b) => b.games)
                .map(
                  (b) =>
                    `<div class="metric"><span>${esc(b.range)} % favorit · ${b.games} matcher</span><strong>${pct(b.hit_rate_pct)} rätt</strong></div>`,
                )
                .join(
                  "",
                )}</div><h4>Senaste utvärderade matcher</h4>${games.map((g) => `<div class="metric"><span>${g.correct ? "✓" : "✕"} ${esc(g.home)} – ${esc(g.away)} (${g.score.home}–${g.score.away})<small class="accuracy-sub"> Tips ${esc(g.predicted_outcome)} · Utfall ${esc(g.actual_outcome)}</small></span><strong>${g.correct ? "Rätt" : "Fel"}</strong></div>`).join("")}`
        }<p class="muted">${p.pending_forecasts} sparade prognoser väntar på resultat.</p>${p.storage_warning ? `<p class="accuracy-warning">⚠️ ${esc(p.storage_warning)}</p>` : ""}`;
      })
      .catch(() => {
        const el = document.getElementById("perf");
        if (el) el.textContent = "Träffsäkerheten kunde inte hämtas.";
      });
    return;
  }
  if (state.view === "history") {
    root.innerHTML = `<div class="header"><div><div class="eyebrow">NHL · ${esc(state.historySeason || "2026/27")}</div><h1 class="title">🏒 Matchhistorik</h1><div class="muted">Verifierade resultat efter 60 minuter</div></div><button class="theme" id="theme">${state.light ? "🌙 Mörkt" : "☀️ Ljust"}</button></div><div class="filters"><button class="chip" id="to-matches">Kommande matcher</button><button class="chip active">NHL-historik</button></div><div class="controls"><select class="date" id="history-team"><option value="">Alla NHL-lag</option>${state.historyTeams.map((t) => `<option value="${esc(t.id)}" ${t.id === state.historyTeam ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select><button class="chip" id="history-refresh">↻</button></div>${state.error ? `<section class="panel warning">⚠️ ${esc(state.error)}</section>` : ""}${state.loading ? '<section class="panel empty">Hämtar historik…</section>' : `<p class="muted">${state.historyTotal} färdigspelade matcher · visar ${state.history.length ? state.historyOffset + 1 : 0}–${state.historyOffset + state.history.length}</p>${state.history.length ? state.history.map(card).join("") : '<section class="panel empty">Ingen importerad NHL-historik hittades.</section>'}<div class="controls history-pager"><button class="chip" id="history-prev" ${state.historyOffset === 0 ? "disabled" : ""}>← Föregående</button><button class="chip" id="history-next" ${state.historyOffset + state.history.length >= state.historyTotal ? "disabled" : ""}>Nästa →</button></div>`}${notice()}`;
    hydrateSwedishLogos();
    document.getElementById("theme").onclick = () => {
      state.light = !state.light;
      localStorage.setItem("theme", state.light ? "light" : "dark");
      render();
    };
    document.getElementById("to-matches").onclick = () => {
      state.view = "matches";
      load();
    };
    document.getElementById("history-team").onchange = (e) => {
      state.historyTeam = e.target.value;
      state.historyOffset = 0;
      loadHistory();
    };
    document.getElementById("history-refresh").onclick = loadHistory;
    document.getElementById("history-prev")?.addEventListener("click", () => {
      state.historyOffset = Math.max(
        0,
        state.historyOffset - state.historyLimit,
      );
      loadHistory();
    });
    document.getElementById("history-next")?.addEventListener("click", () => {
      state.historyOffset += state.historyLimit;
      loadHistory();
    });
    document.querySelectorAll("[data-id]").forEach(
      (el) =>
        (el.onclick = async () => {
          try {
            showDetail(
              await get("/api/matches/" + encodeURIComponent(el.dataset.id)),
            );
          } catch (e) {
            state.error = e.message;
            render();
          }
        }),
    );
    return;
  }
  root.innerHTML = `<div class="header"><div><div class="eyebrow">STATISTIK · HOCKEY</div><h1 class="title">🏒 Hockeyprognos</h1><div class="muted">1X2 efter 60 minuter</div></div><button class="theme" id="theme">${state.light ? "🌙 Mörkt" : "☀️ Ljust"}</button></div><div class="filters">${[
    ["ALL", "Alla"],
    ["SHL", "SHL"],
    ["HA", "HockeyAllsvenskan"],
    ["NHL", "NHL"],
  ]
    .map(
      ([id, label]) =>
        `<button class="chip ${state.league === id ? "active" : ""}" data-league="${id}">${label}</button>`,
    )
    .join(
      "",
    )}<button class="chip" id="open-stats">📊 SHL Statistik</button><button class="chip" id="open-analysis">🧪 Modellanalys</button></div><div class="controls"><input class="date" type="date" id="date" value="${state.date}"><button class="chip" id="refresh">↻</button></div>${state.error ? `<section class="panel warning">⚠️ ${esc(state.error)}</section>` : ""}${state.loading ? '<section class="panel empty">Hämtar matcher…</section>' : state.matches.length ? state.matches.map(card).join("") : '<section class="panel empty"><strong>Inga verifierade matcher hittades</strong><p class="muted">Välj ett annat datum eller kontrollera datakällornas status.</p></section>'}${state.leagues
    .filter(
      (l) => l.error && (state.league === "ALL" || l.league === state.league),
    )
    .map(
      (l) =>
        `<section class="panel warning">⚠️ ${esc(l.name)}: ${esc(l.error)}</section>`,
    )
    .join("")}${notice()}`;
  hydrateSwedishLogos();
  document.getElementById("theme").onclick = () => {
    state.light = !state.light;
    localStorage.setItem("theme", state.light ? "light" : "dark");
    render();
  };
  document.querySelectorAll("[data-league]").forEach(
    (el) =>
      (el.onclick = () => {
        state.league = el.dataset.league;
        load();
      }),
  );
  document.getElementById("date").onchange = (e) => {
    state.date = e.target.value;
    load();
  };
  document.getElementById("refresh").onclick = () => load(true);
  document.getElementById("open-stats").onclick = () => {
    state.view = "shl-stats";
    render();
    if (!state.shlStats) loadShlStatistics();
  };
  document.getElementById("open-analysis").onclick = () => {
    state.view = "analysis";
    render();
  };
  document.querySelectorAll("[data-id]").forEach(
    (el) =>
      (el.onclick = async () => {
        try {
          showDetail(
            await get("/api/matches/" + encodeURIComponent(el.dataset.id)),
          );
        } catch (e) {
          state.error = e.message;
          render();
        }
      }),
  );
}
async function loadHistory() {
  state.loading = true;
  state.error = "";
  render();
  try {
    const data = await get(
      "/api/history?league=NHL&limit=" +
        state.historyLimit +
        "&offset=" +
        state.historyOffset +
        (state.historyTeam
          ? "&team=" + encodeURIComponent(state.historyTeam)
          : ""),
    );
    state.history = data.matches;
    state.historyTotal = data.total;
    state.historyTeams = data.teams;
    state.historySeason = data.season;
  } catch (e) {
    state.error = "Historiken kunde inte hämtas: " + e.message;
    state.history = [];
  }
  state.loading = false;
  render();
}
// Fast league switching: stale-while-revalidate with a small, bounded session cache.
// Never persist sensitive data; these endpoints contain only public match information.
const MATCH_CACHE_TTL = 5 * 60 * 1000;
const MATCH_CACHE_STALE = 48 * 60 * 60 * 1000;
const MATCH_CACHE_MAX = 12;
const matchCache = new Map();
const pendingMatches = new Map();
let loadGeneration = 0;
let leagueData = null;
let leaguePromise = null;

function matchKey(day, days, league) {
  return `${day}|${days}|${league}`;
}
function readMatchCache(key) {
  let entry = matchCache.get(key);
  if (!entry) {
    try {
      const stored = localStorage.getItem("hp3913:" + key);
      if (stored) entry = JSON.parse(stored);
    } catch (_) {
      /* private mode or storage disabled */
    }
  }
  if (
    !entry ||
    !Array.isArray(entry.data) ||
    Date.now() - entry.time > MATCH_CACHE_STALE
  )
    return null;
  matchCache.delete(key);
  matchCache.set(key, entry);
  return entry;
}
function saveMatchCache(key, data) {
  const entry = { time: Date.now(), data };
  matchCache.delete(key);
  matchCache.set(key, entry);
  while (matchCache.size > MATCH_CACHE_MAX) {
    const oldest = matchCache.keys().next().value;
    matchCache.delete(oldest);
    try {
      localStorage.removeItem("hp3913:" + oldest);
    } catch (_) {}
  }
  try {
    localStorage.setItem("hp3913:" + key, JSON.stringify(entry));
  } catch (_) {}
}
function getLeaguesOnce() {
  if (leagueData) return Promise.resolve(leagueData);
  if (!leaguePromise) {
    leaguePromise = get("/api/leagues")
      .then((data) => {
        leagueData = data;
        return data;
      })
      .finally(() => {
        leaguePromise = null;
      });
  }
  return leaguePromise;
}
function fetchMatches(key, day, days, league) {
  if (!pendingMatches.has(key)) {
    const path =
      "/api/matches?day=" +
      day +
      "&days=" +
      days +
      (league === "ALL" ? "" : "&league=" + encodeURIComponent(league));
    const promise = get(path)
      .then((data) => {
        saveMatchCache(key, data);
        return data;
      })
      .finally(() => pendingMatches.delete(key));
    pendingMatches.set(key, promise);
  }
  return pendingMatches.get(key);
}
async function load(force = false) {
  // onclick passes a MouseEvent, not a boolean; only explicit true forces refresh.
  force = force === true;
  const generation = ++loadGeneration;
  const { date: day, days, league } = state;
  const key = matchKey(day, days, league);
  const cached = !force && readMatchCache(key);
  state.error = "";
  if (cached) {
    state.matches = cached.data;
    state.loading = false;
  } else {
    state.matches = [];
    state.loading = true;
  }
  render();
  // Fetch league metadata only once per page session, not on every tab switch.
  getLeaguesOnce()
    .then((data) => {
      state.leagues = data;
      if (generation === loadGeneration) render();
    })
    .catch(() => {
      /* match list can still be shown without league metadata */
    });
  // Never treat live or imminent fixtures as five-minute-fresh.
  const hasLive =
    cached &&
    cached.data.some(
      (m) =>
        m.status === "LIVE" ||
        (m.status === "SCHEDULED" && new Date(m.date).getTime() <= Date.now()),
    );
  if (cached && !hasLive && Date.now() - cached.time < MATCH_CACHE_TTL) return;
  try {
    const matches = await fetchMatches(key, day, days, league);
    if (generation !== loadGeneration || state.view !== "matches") return;
    state.matches = matches;
    state.loading = false;
    render();
  } catch (e) {
    if (generation !== loadGeneration) return;
    state.loading = false;
    if (!cached) {
      state.error =
        "Kunde inte hämta matchdata. Kontrollera internetanslutningen och servern. " +
        e.message;
    } else {
      state.error =
        "Visar tidigare hämtade matcher. Uppdateringen misslyckades: " +
        e.message;
    }
    render();
  }
}

load();
if ("serviceWorker" in navigator)
  navigator.serviceWorker.register("/sw.js").catch(() => {});

// Refresh recent NHL results while the page is open; never overwrite manual date selection.
setInterval(() => {
  if (state.view !== "matches" || state.loading) return;
  if (
    state.matches.some(
      (m) =>
        m.league === "NHL" &&
        (m.status === "LIVE" ||
          m.status === "PENDING" ||
          (m.status === "SCHEDULED" &&
            new Date(m.date).getTime() <= Date.now())),
    )
  ) {
    load(true);
  }
}, 60 * 1000);
