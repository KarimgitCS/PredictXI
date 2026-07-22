// Point this at wherever the API is running.
const API_BASE = "http://localhost:8000";

const styles = getComputedStyle(document.documentElement);
const color = (name) => styles.getPropertyValue(name).trim();

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
    statusEl.textContent = "Couldn't reach the API — is it running at " + API_BASE + "?";
  }
}

function renderCalibrationTable(data) {
  const rows = [];
  for (const [model, byClass] of Object.entries(data)) {
    for (const [cls, bins] of Object.entries(byClass)) {
      for (const bin of bins) {
        rows.push({ model, cls, ...bin });
      }
    }
  }
  const label = { H: "Home", D: "Draw", A: "Away" };
  const table = document.createElement("table");
  table.innerHTML = `
    <thead><tr>
      <th>Model</th><th>Outcome</th><th>Predicted bin</th>
      <th>Predicted mean</th><th>Observed frequency</th><th>Count</th>
    </tr></thead>
    <tbody>${rows.map((r) => `
      <tr>
        <td>${r.model}</td>
        <td>${label[r.cls]}</td>
        <td>${r.bin_range[0]}–${r.bin_range[1]}</td>
        <td>${r.predicted_mean.toFixed(3)}</td>
        <td>${r.observed_frequency.toFixed(3)}</td>
        <td>${r.count}</td>
      </tr>`).join("")}
    </tbody>`;
  document.getElementById("calibration-table-wrap").appendChild(table);
}

function pooledPoints(byClass) {
  // Pools all three outcome classes' bins into one series per model —
  // simpler to read as one calibration curve per model rather than six
  // separate lines (2 models x 3 classes) on one small chart.
  const points = [];
  for (const bins of Object.values(byClass)) {
    for (const bin of bins) {
      points.push({ x: bin.predicted_mean, y: bin.observed_frequency });
    }
  }
  return points.sort((a, b) => a.x - b.x);
}

async function loadCalibration() {
  const statusEl = document.getElementById("calibration-status");
  try {
    const data = await fetch(`${API_BASE}/calibration`).then((r) => r.json());
    statusEl.hidden = true;

    new Chart(document.getElementById("calibration-chart"), {
      type: "line",
      data: {
        datasets: [
          {
            // showLine: false — points are pooled across three different
            // outcome classes (H/D/A), sorted only by predicted probability.
            // Connecting them with a line implies a continuous relationship
            // between what are really three separate curves, which produced
            // a misleading zigzag/spike where a low-frequency bin from one
            // class sat near a high-frequency bin from another. Scatter is
            // the honest representation of pooled data; a real trend is
            // still visible as a diagonal cluster of dots.
            label: "Logistic regression",
            data: pooledPoints(data.logreg),
            showLine: false,
            backgroundColor: color("--logreg-color"),
            pointRadius: 4,
            pointBackgroundColor: color("--logreg-color"),
            pointBorderColor: color("--surface-1"),
            pointBorderWidth: 2,
          },
          {
            label: "XGBoost",
            data: pooledPoints(data.xgboost),
            showLine: false,
            backgroundColor: color("--xgboost-color"),
            pointRadius: 4,
            pointBackgroundColor: color("--xgboost-color"),
            pointBorderColor: color("--surface-1"),
            pointBorderWidth: 2,
          },
          {
            label: "Perfect calibration",
            data: [{ x: 0, y: 0 }, { x: 1, y: 1 }],
            borderColor: color("--text-muted"),
            borderWidth: 1.5,
            borderDash: [4, 4],
            pointRadius: 0,
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: {
            type: "linear",
            min: 0, max: 1,
            title: { display: true, text: "Predicted probability", color: color("--text-secondary") },
            grid: { color: color("--gridline") },
            ticks: { color: color("--text-muted") },
          },
          y: {
            min: 0, max: 1,
            title: { display: true, text: "Actual outcome frequency", color: color("--text-secondary") },
            grid: { color: color("--gridline") },
            ticks: { color: color("--text-muted") },
          },
        },
        plugins: {
          legend: { labels: { color: color("--text-secondary") } },
          tooltip: {
            callbacks: {
              label: (ctx) =>
                `${ctx.dataset.label}: predicted ${ctx.parsed.x.toFixed(2)}, observed ${ctx.parsed.y.toFixed(2)}`,
            },
          },
        },
      },
    });

    renderCalibrationTable(data);
  } catch (err) {
    statusEl.textContent = "Couldn't reach the API — is it running at " + API_BASE + "?";
  }
}

loadFixtures();
loadCalibration();
