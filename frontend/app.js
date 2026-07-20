// Point this at wherever the API is running.
const API_BASE = "http://localhost:8000";

const styles = getComputedStyle(document.documentElement);
const color = (name) => styles.getPropertyValue(name).trim();

function formatKickoff(isoString) {
  return new Date(isoString).toLocaleString(undefined, {
    weekday: "short", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit",
  });
}

function fixtureCard(fixture, prediction) {
  const li = document.createElement("li");
  li.className = "fixture-card";

  if (!prediction) {
    li.innerHTML = `
      <div class="fixture-teams"><span>${fixture.home_team} vs ${fixture.away_team}</span></div>
      <p class="fixture-kickoff">${formatKickoff(fixture.kickoff_at)}</p>
      <p class="status-text">Prediction unavailable.</p>`;
    return li;
  }

  const pct = (p) => Math.round(p * 100);
  li.innerHTML = `
    <div class="fixture-teams">
      <span>${fixture.home_team} vs ${fixture.away_team}</span>
    </div>
    <p class="fixture-kickoff">${formatKickoff(fixture.kickoff_at)}</p>
    <div class="prob-values">
      <span>H ${pct(prediction.prob_home)}%</span>
      <span>D ${pct(prediction.prob_draw)}%</span>
      <span>A ${pct(prediction.prob_away)}%</span>
    </div>
    <div class="prob-bar" role="img"
         aria-label="Predicted: ${pct(prediction.prob_home)}% home win, ${pct(prediction.prob_draw)}% draw, ${pct(prediction.prob_away)}% away win">
      <span class="home" style="width:${prediction.prob_home * 100}%"></span>
      <span class="draw" style="width:${prediction.prob_draw * 100}%"></span>
      <span class="away" style="width:${prediction.prob_away * 100}%"></span>
    </div>`;
  return li;
}

async function loadFixtures() {
  const statusEl = document.getElementById("fixtures-status");
  const listEl = document.getElementById("fixtures-list");

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

    listEl.innerHTML = "";
    fixtures.forEach((f, i) => listEl.appendChild(fixtureCard(f, predictions[i])));
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
