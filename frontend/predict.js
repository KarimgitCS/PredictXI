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

function ordinal(n) {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

// Position is live, not a fixed label — computed from match_features as of
// right now, so it updates on its own as results come in.
function positionLabel(position) {
  return position != null ? ` <span class="team-position">(${ordinal(position)})</span>` : "";
}

// Purely visual — just marks which button you clicked. Nothing is sent
// anywhere or saved; there's no message, popup, or network call on click.
function selectChoice(card, btn) {
  card.querySelectorAll(".predict-choice-btn").forEach((b) => b.classList.remove("selected"));
  btn.classList.add("selected");
}

function predictFixtureCard(fixture, prediction) {
  const colors = resolveMatchColors(fixture.home_team, fixture.away_team);
  const drawColor = getComputedStyle(document.documentElement).getPropertyValue("--baseline").trim();

  const card = document.createElement("li");
  card.className = "fixture-card predict-fixture-card";

  const scoreLine = prediction
    ? `<p class="likely-score">Most likely score: <strong>${fixture.home_team} ${prediction.predicted_home_goals}–${prediction.predicted_away_goals} ${fixture.away_team}</strong></p>`
    : "";

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
    </div>`;

  card.querySelectorAll(".predict-choice-btn").forEach((btn) => {
    btn.addEventListener("click", () => selectChoice(card, btn));
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

    // Fetched once up front (not on click) so the most-likely-score line is
    // visible immediately for every match, same as the fixtures page.
    const predictions = await Promise.all(
      fixtures.map((f) =>
        fetch(`${API_BASE}/predict?fixture_id=${f.fixture_id}`)
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null)
      )
    );

    const ul = document.createElement("ul");
    ul.className = "fixtures-list";
    fixtures.forEach((fixture, i) => ul.appendChild(predictFixtureCard(fixture, predictions[i])));
    listEl.appendChild(ul);

    statusEl.hidden = true;
  } catch (err) {
    statusEl.textContent = "Couldn't reach the API — is it running at " + API_BASE + "?";
  }
}

init();
