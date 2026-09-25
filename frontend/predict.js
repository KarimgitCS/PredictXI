// Saved in this browser only (localStorage) — never sent to or stored on
// any server. The one network call this page makes per fixture (/predict,
// for the most-likely-score line) and one per season of saved picks (/results,
// to check the outcomes) don't carry the user's personal choice at all.
const STORAGE_KEY = "predictxi_predictions";

function loadSavedPredictions() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
  } catch {
    return [];
  }
}

function savePrediction(record) {
  const all = loadSavedPredictions();
  const index = all.findIndex((p) => p.fixture_id === record.fixture_id);
  if (index >= 0) all[index] = record;
  else all.push(record);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
}

function formatKickoff(isoString) {
  return new Date(isoString).toLocaleString(undefined, {
    weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

function crestOrPlaceholder(url) {
  return url
    ? `<img class="crest-lg" src="${url}" alt="" onerror="this.style.visibility='hidden'" />`
    : `<span class="draw-icon"></span>`;
}

function teamCrest(url) {
  return url
    ? `<img class="team-crest" src="${url}" alt="" onerror="this.style.visibility='hidden'" />`
    : `<span class="team-crest team-crest-placeholder"></span>`;
}

function ordinal(n) {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

function positionLabel(position) {
  return position != null ? ` <span class="team-position">(${ordinal(position)})</span>` : "";
}

function pickLabel(pred) {
  if (pred.choice === "H") return pred.home_team;
  if (pred.choice === "A") return pred.away_team;
  return "a draw";
}

function selectChoice(fixture, card, btn) {
  card.querySelectorAll(".predict-choice-btn").forEach((b) => b.classList.remove("selected"));
  btn.classList.add("selected");

  savePrediction({
    fixture_id: fixture.fixture_id,
    season: fixture.season,
    home_team: fixture.home_team,
    away_team: fixture.away_team,
    matchday: fixture.matchday,
    kickoff_at: fixture.kickoff_at,
    choice: btn.dataset.choice,
  });

  renderMyPredictions();
  if (!resultsBySeason.has(fixture.season)) refreshResults();
}

function predictFixtureCard(fixture, prediction, savedChoice) {
  const colors = resolveMatchColors(fixture.home_team, fixture.away_team);
  const drawColor = getComputedStyle(document.documentElement).getPropertyValue("--baseline").trim();

  const card = document.createElement("li");
  card.className = "fixture-card predict-fixture-card";

  const scoreLine = prediction
    ? `<p class="likely-score">Most likely score: <strong>${fixture.home_team} ${prediction.predicted_home_goals}–${prediction.predicted_away_goals} ${fixture.away_team}</strong></p>`
    : "";

  const selected = (choice) => (savedChoice === choice ? " selected" : "");

  card.innerHTML = `
    <div class="fixture-matchup">
      <div class="team-row">
        ${teamCrest(fixture.home_crest_url)}
        <span class="team-color-dot" style="background:${colors.home.hex}"></span>
        <span class="team-name">${fixture.home_team}${positionLabel(prediction?.home_position)}</span>
      </div>
      <span class="vs">vs</span>
      <div class="team-row">
        ${teamCrest(fixture.away_crest_url)}
        <span class="team-color-dot" style="background:${colors.away.hex}"></span>
        <span class="team-name">${fixture.away_team}${positionLabel(prediction?.away_position)}</span>
      </div>
    </div>
    <p class="fixture-kickoff">${formatKickoff(fixture.kickoff_at)}</p>
    ${scoreLine}
    <div class="predict-choice-row">
      <button class="predict-choice-btn${selected("H")}" data-choice="H" style="--chosen-color:${colors.home.hex}">
        ${crestOrPlaceholder(fixture.home_crest_url)}
        <span>${fixture.home_team}</span>
      </button>
      <button class="predict-choice-btn${selected("D")}" data-choice="D" style="--chosen-color:${drawColor}">
        <span class="draw-icon">DRAW</span>
        <span>Draw</span>
      </button>
      <button class="predict-choice-btn${selected("A")}" data-choice="A" style="--chosen-color:${colors.away.hex}">
        ${crestOrPlaceholder(fixture.away_crest_url)}
        <span>${fixture.away_team}</span>
      </button>
    </div>`;

  card.querySelectorAll(".predict-choice-btn").forEach((btn) => {
    btn.addEventListener("click", () => selectChoice(fixture, card, btn));
  });

  return card;
}

// Played results per season, fetched in one call per season (GET /results)
// and matched to saved picks locally by "home|away" — a season's picks
// would otherwise be one /result request each. A season missing from this
// map means "not loaded yet, or the fetch failed", not "nothing played".
const resultsBySeason = new Map();
const resultsFailedFor = new Set();

// Which matchweek groups the user has expanded. Kept outside the DOM so an
// expanded week stays open when the list re-renders (picking a new
// prediction, or the periodic results refresh).
const openWeeks = new Set();

const RESULTS_REFRESH_MS = 5 * 60 * 1000;

async function refreshResults() {
  const seasons = [...new Set(loadSavedPredictions().map((p) => p.season))];
  await Promise.all(
    seasons.map(async (season) => {
      try {
        const rows = await fetch(`${API_BASE}/results?season=${encodeURIComponent(season)}`)
          .then((r) => (r.ok ? r.json() : Promise.reject()));
        resultsBySeason.set(
          season,
          new Map(rows.map((row) => [`${row.home_team}|${row.away_team}`, row]))
        );
        resultsFailedFor.delete(season);
      } catch {
        resultsFailedFor.add(season);
      }
    })
  );
  renderMyPredictions();
}

// { state: "checking" | "failed" | "pending" | "played", row? }
function outcomeFor(pred) {
  const results = resultsBySeason.get(pred.season);
  if (!results) return { state: resultsFailedFor.has(pred.season) ? "failed" : "checking" };
  const row = results.get(`${pred.home_team}|${pred.away_team}`);
  return row ? { state: "played", row } : { state: "pending" };
}

function myPredictionCard(pred, outcome) {
  const li = document.createElement("li");
  li.className = "fixture-card my-prediction-card";

  let outcomeHtml;
  if (outcome.state === "played") {
    const { row } = outcome;
    const correct = row.result === pred.choice;
    outcomeHtml =
      `<p class="my-prediction-outcome">Final score: <strong>${pred.home_team} ${row.home_goals}–${row.away_goals} ${pred.away_team}</strong> — ` +
      (correct
        ? `<span class="pick-correct">You called it</span>`
        : `<span class="pick-incorrect">Not this time</span>`) +
      `</p>`;
  } else {
    const text = {
      checking: "Checking result…",
      failed: "Couldn't check the result.",
      pending: "Pending — not played yet.",
    }[outcome.state];
    outcomeHtml = `<p class="my-prediction-outcome status-text">${text}</p>`;
  }

  li.innerHTML = `
    <div class="fixture-matchup">
      <span class="team-name">${pred.home_team}</span>
      <span class="vs">vs</span>
      <span class="team-name">${pred.away_team}</span>
    </div>
    <p class="fixture-kickoff">${formatKickoff(pred.kickoff_at)}</p>
    <p class="my-prediction-pick">Your pick: <strong>${pickLabel(pred)}</strong>${pred.choice !== "D" ? " to win" : ""}</p>
    ${outcomeHtml}`;
  return li;
}

// Right–wrong record for the week (e.g. 5–4), shown on the collapsed row so
// it's visible without opening the week. Picks still awaiting a result are
// counted separately, not as wrong.
function weekSummary(entries) {
  const total = entries.length;
  const known = entries.every((e) => e.outcome.state === "played" || e.outcome.state === "pending");
  if (!known) return `<span class="week-count">${total} pick${total === 1 ? "" : "s"}</span>`;

  const played = entries.filter((e) => e.outcome.state === "played");
  const right = played.filter((e) => e.outcome.row.result === e.pred.choice).length;
  const wrong = played.length - right;
  const pending = total - played.length;

  return `
    <span class="week-record" title="${right} right, ${wrong} wrong">
      <span class="pick-correct">${right}</span>–<span class="pick-incorrect">${wrong}</span>
    </span>
    <span class="week-count">${pending > 0 ? `${pending} pending` : `${total} played`}</span>`;
}

function weekGroup(weekKey, entries) {
  const details = document.createElement("details");
  details.className = "week-group";
  details.open = openWeeks.has(weekKey);
  details.addEventListener("toggle", () => {
    if (details.open) openWeeks.add(weekKey);
    else openWeeks.delete(weekKey);
  });

  const title = weekKey === "none" ? "Other" : `Matchweek ${weekKey}`;
  details.innerHTML = `
    <summary>
      <span class="week-title">${title}</span>
      <span class="week-meta">${weekSummary(entries)}</span>
    </summary>`;

  const ul = document.createElement("ul");
  ul.className = "fixtures-list";
  [...entries]
    .sort((a, b) => new Date(a.pred.kickoff_at) - new Date(b.pred.kickoff_at))
    .forEach(({ pred, outcome }) => ul.appendChild(myPredictionCard(pred, outcome)));
  details.appendChild(ul);
  return details;
}

function renderMyPredictions() {
  const statusEl = document.getElementById("my-predictions-status");
  const listEl = document.getElementById("my-predictions-list");
  const saved = loadSavedPredictions();

  listEl.innerHTML = "";
  if (saved.length === 0) {
    statusEl.hidden = false;
    return;
  }
  statusEl.hidden = true;

  const byWeek = new Map();
  for (const pred of saved) {
    const key = pred.matchday != null ? String(pred.matchday) : "none";
    if (!byWeek.has(key)) byWeek.set(key, []);
    byWeek.get(key).push({ pred, outcome: outcomeFor(pred) });
  }

  // Newest matchweek first; picks with no matchweek recorded go last.
  const weekKeys = [...byWeek.keys()].sort((a, b) => {
    if (a === "none") return 1;
    if (b === "none") return -1;
    return Number(b) - Number(a);
  });
  weekKeys.forEach((key) => listEl.appendChild(weekGroup(key, byWeek.get(key))));
}

async function init() {
  const statusEl = document.getElementById("predict-status");
  const listEl = document.getElementById("predict-fixtures");

  // Saved picks don't depend on there being upcoming fixtures (or on the
  // fixture list loading at all), so they render and refresh independently.
  renderMyPredictions();
  refreshResults();
  setInterval(refreshResults, RESULTS_REFRESH_MS);

  try {
    const fixtures = await fetch(`${API_BASE}/matches`).then((r) => r.json());
    if (fixtures.length === 0) {
      statusEl.textContent = "No upcoming fixtures found.";
      return;
    }

    // Fetched once up front (not on click) so the most-likely-score line is
    // visible immediately for every match, same as the fixtures page.
    const predictions = await Promise.all(
      fixtures.map((f) =>
        fetch(`${API_BASE}/predict?fixture_id=${f.fixture_id}`)
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null)
      )
    );

    const saved = loadSavedPredictions();
    const savedByFixtureId = new Map(saved.map((p) => [p.fixture_id, p.choice]));

    const ul = document.createElement("ul");
    ul.className = "fixtures-list";
    fixtures.forEach((fixture, i) => {
      ul.appendChild(predictFixtureCard(fixture, predictions[i], savedByFixtureId.get(fixture.fixture_id)));
    });
    listEl.appendChild(ul);

    statusEl.hidden = true;
  } catch (err) {
    statusEl.textContent = "Couldn't reach the API — is the server running?";
  }
}

init();
