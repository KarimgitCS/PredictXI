function formatKickoffTime(isoString) {
  return new Date(isoString).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function formatMatchDate(isoString) {
  return new Date(isoString).toLocaleDateString(undefined, {
    weekday: "long", month: "long", day: "numeric",
  });
}

function ordinal(n) {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

// Position is live, not a fixed label — it's computed from match_features
// as of right now (each team's actual current standing), so it updates on
// its own as results come in; no separate "refresh position" logic needed.
function teamRow(name, crestUrl, colorHex, position) {
  const crest = crestUrl
    ? `<img class="team-crest" src="${crestUrl}" alt="" onerror="this.style.visibility='hidden'" />`
    : `<span class="team-crest team-crest-placeholder"></span>`;
  const positionLabel = position != null ? ` <span class="team-position">(${ordinal(position)})</span>` : "";
  return `
    <div class="team-row">
      ${crest}
      <span class="team-color-dot" style="background:${colorHex}"></span>
      <span class="team-name">${name}${positionLabel}</span>
    </div>`;
}

function fixtureCard(fixture, prediction) {
  const li = document.createElement("li");
  li.className = "fixture-card";
  const colors = resolveMatchColors(fixture.home_team, fixture.away_team);

  const matchup = `
    <div class="fixture-matchup">
      ${teamRow(fixture.home_team, fixture.home_crest_url, colors.home.hex, prediction?.home_position)}
      <span class="vs">vs</span>
      ${teamRow(fixture.away_team, fixture.away_crest_url, colors.away.hex, prediction?.away_position)}
    </div>
    <p class="fixture-kickoff">${formatKickoffTime(fixture.kickoff_at)}</p>`;

  if (!prediction) {
    li.innerHTML = `${matchup}<p class="status-text">Prediction unavailable.</p>`;
    return li;
  }

  const pct = (p) => Math.round(p * 100);

  const hasForm = prediction.home_form_ppg != null && prediction.away_form_ppg != null;
  const statsLine = hasForm
    ? `<div class="match-stats">
        <span>Form (last 5): ${prediction.home_form_ppg.toFixed(1)} vs ${prediction.away_form_ppg.toFixed(1)} pts/game</span>
      </div>`
    : "";

  li.innerHTML = `
    ${matchup}
    <p class="likely-score">Most likely score: <strong>${fixture.home_team} ${prediction.predicted_home_goals}–${prediction.predicted_away_goals} ${fixture.away_team}</strong></p>
    ${statsLine}
    <div class="prob-values">
      <span>${pct(prediction.prob_home)}%</span>
      <span>Draw ${pct(prediction.prob_draw)}%</span>
      <span>${pct(prediction.prob_away)}%</span>
    </div>
    <div class="prob-bar" role="img"
         aria-label="Predicted: ${pct(prediction.prob_home)}% ${fixture.home_team} win, ${pct(prediction.prob_draw)}% draw, ${pct(prediction.prob_away)}% ${fixture.away_team} win">
      <span style="width:${prediction.prob_home * 100}%; background:${colors.home.hex}"></span>
      <span class="draw" style="width:${prediction.prob_draw * 100}%"></span>
      <span style="width:${prediction.prob_away * 100}%; background:${colors.away.hex}"></span>
    </div>`;
  return li;
}

// Two-level grouping: matchweek (matchday), then calendar date within it —
// a Premier League "matchweek" typically spans several days (Fri-Mon), so
// both groupings are meaningful at once, not redundant.
function groupFixtures(fixtures) {
  const byMatchday = new Map();
  for (const fixture of fixtures) {
    const matchday = fixture.matchday ?? 0;
    if (!byMatchday.has(matchday)) byMatchday.set(matchday, new Map());
    const byDate = byMatchday.get(matchday);
    const dateKey = new Date(fixture.kickoff_at).toDateString();
    if (!byDate.has(dateKey)) byDate.set(dateKey, []);
    byDate.get(dateKey).push(fixture);
  }
  return byMatchday;
}

function renderFixtureGroups(fixtures, predictionsById) {
  const container = document.getElementById("fixtures-groups");
  container.innerHTML = "";

  const grouped = groupFixtures(fixtures);
  const matchdays = [...grouped.keys()].sort((a, b) => a - b);

  for (const matchday of matchdays) {
    const section = document.createElement("div");
    section.className = "matchweek-group";

    const heading = document.createElement("h3");
    heading.className = "matchweek-heading";
    heading.textContent = matchday ? `Matchweek ${matchday}` : "Matchweek";
    section.appendChild(heading);

    const byDate = grouped.get(matchday);
    const dateKeys = [...byDate.keys()].sort((a, b) => new Date(a) - new Date(b));

    for (const dateKey of dateKeys) {
      const dayFixtures = byDate.get(dateKey);

      const dateHeading = document.createElement("h4");
      dateHeading.className = "date-heading";
      dateHeading.textContent = formatMatchDate(dayFixtures[0].kickoff_at);
      section.appendChild(dateHeading);

      const ul = document.createElement("ul");
      ul.className = "fixtures-list";
      for (const fixture of dayFixtures) {
        ul.appendChild(fixtureCard(fixture, predictionsById.get(fixture.fixture_id)));
      }
      section.appendChild(ul);
    }

    container.appendChild(section);
  }
}

async function loadFixtures() {
  const statusEl = document.getElementById("fixtures-status");

  try {
    const fixtures = await fetch(`${API_BASE}/matches`).then((r) => r.json());

    // One /predict call per fixture, in parallel — each call also logs a
    // row in `predictions`, which is exactly why /matches defaults to only
    // the next 10 rather than the whole season.
    const predictions = await Promise.all(
      fixtures.map((f) =>
        fetch(`${API_BASE}/predict?fixture_id=${f.fixture_id}`)
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null)
      )
    );
    const predictionsById = new Map(fixtures.map((f, i) => [f.fixture_id, predictions[i]]));

    renderFixtureGroups(fixtures, predictionsById);
    statusEl.hidden = true;
  } catch (err) {
    statusEl.textContent = "Couldn't reach the API — is the server running?";
  }
}

loadFixtures();
