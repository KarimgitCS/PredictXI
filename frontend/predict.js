// Point this at wherever the API is running.
const API_BASE = "http://localhost:8000";

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

// Purely client-side — nothing here is sent anywhere or saved. The one
// network call this makes (/predict) is the same endpoint the fixture list
// already uses to show the model's own prediction for comparison; it isn't
// storing the user's personal pick.
function selectChoice(fixture, card, btn) {
  card.querySelectorAll(".predict-choice-btn").forEach((b) => b.classList.remove("selected"));
  btn.classList.add("selected");
  const choice = btn.dataset.choice;

  const label = { H: fixture.home_team, D: "a draw", A: fixture.away_team }[choice];
  const suffix = choice === "D" ? "" : " to win";
  const resultEl = card.querySelector(".predict-result");
  resultEl.hidden = false;
  resultEl.innerHTML =
    `<strong>Your prediction:</strong> ${label}${suffix}. Not saved anywhere — just for fun. ` +
    `<span class="model-compare">Checking what the model thinks…</span>`;

  fetch(`${API_BASE}/predict?fixture_id=${fixture.fixture_id}`)
    .then((r) => (r.ok ? r.json() : null))
    .then((prediction) => {
      const compareEl = resultEl.querySelector(".model-compare");
      if (!compareEl || !prediction) return;
      const modelPct = {
        H: prediction.prob_home, D: prediction.prob_draw, A: prediction.prob_away,
      }[choice];
      compareEl.textContent = `The model gives that outcome a ${Math.round(modelPct * 100)}% chance.`;
    })
    .catch(() => {
      const compareEl = resultEl.querySelector(".model-compare");
      if (compareEl) compareEl.textContent = "";
    });
}

function predictFixtureCard(fixture) {
  const colors = resolveMatchColors(fixture.home_team, fixture.away_team);
  const drawColor = getComputedStyle(document.documentElement).getPropertyValue("--baseline").trim();

  const card = document.createElement("li");
  card.className = "fixture-card predict-fixture-card";
  card.innerHTML = `
    <div class="fixture-matchup">
      <div class="team-row">
        ${teamCrest(fixture.home_crest_url)}
        <span class="team-color-dot" style="background:${colors.home.hex}"></span>
        <span class="team-name">${fixture.home_team}</span>
      </div>
      <span class="vs">vs</span>
      <div class="team-row">
        ${teamCrest(fixture.away_crest_url)}
        <span class="team-color-dot" style="background:${colors.away.hex}"></span>
        <span class="team-name">${fixture.away_team}</span>
      </div>
    </div>
    <p class="fixture-kickoff">${formatKickoff(fixture.kickoff_at)}</p>
    <div class="predict-choice-row">
      <button class="predict-choice-btn" data-choice="H" style="--chosen-color:${colors.home.hex}">
        ${crestOrPlaceholder(fixture.home_crest_url)}
        <span>${fixture.home_team}</span>
      </button>
      <button class="predict-choice-btn" data-choice="D" style="--chosen-color:${drawColor}">
        <span class="draw-icon">DRAW</span>
        <span>Draw</span>
      </button>
      <button class="predict-choice-btn" data-choice="A" style="--chosen-color:${colors.away.hex}">
        ${crestOrPlaceholder(fixture.away_crest_url)}
        <span>${fixture.away_team}</span>
      </button>
    </div>
    <div class="predict-result" hidden></div>`;

  card.querySelectorAll(".predict-choice-btn").forEach((btn) => {
    btn.addEventListener("click", () => selectChoice(fixture, card, btn));
  });

  return card;
}

async function init() {
  const statusEl = document.getElementById("predict-status");
  const listEl = document.getElementById("predict-fixtures");

  try {
    const fixtures = await fetch(`${API_BASE}/matches`).then((r) => r.json());
    if (fixtures.length === 0) {
      statusEl.textContent = "No upcoming fixtures found.";
      return;
    }

    const ul = document.createElement("ul");
    ul.className = "fixtures-list";
    fixtures.forEach((fixture) => ul.appendChild(predictFixtureCard(fixture)));
    listEl.appendChild(ul);

    statusEl.hidden = true;
  } catch (err) {
    statusEl.textContent = "Couldn't reach the API — is it running at " + API_BASE + "?";
  }
}

init();
