async function loadStandings() {
  const statusEl = document.getElementById("standings-status");
  const wrapEl = document.getElementById("standings-table-wrap");

  try {
    const standings = await fetch(`${API_BASE}/standings`).then((r) => r.json());
    if (standings.length === 0) {
      statusEl.textContent = "No standings data yet.";
      return;
    }

    const table = document.createElement("table");
    table.className = "standings-table";
    table.innerHTML = `
      <thead><tr>
        <th>#</th><th>Team</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GD</th><th>Pts</th>
      </tr></thead>
      <tbody>${standings.map((row) => {
        const crest = row.crest_url
          ? `<img class="team-crest" src="${row.crest_url}" alt="" onerror="this.style.visibility='hidden'" />`
          : `<span class="team-crest team-crest-placeholder"></span>`;
        return `
        <tr>
          <td>${row.position}</td>
          <td class="standings-team">${crest}<span>${row.team}</span></td>
          <td>${row.played}</td>
          <td>${row.wins}</td>
          <td>${row.draws}</td>
          <td>${row.losses}</td>
          <td>${row.goal_diff}</td>
          <td><strong>${row.points}</strong></td>
        </tr>`;
      }).join("")}</tbody>`;

    wrapEl.appendChild(table);
    statusEl.hidden = true;
  } catch (err) {
    statusEl.textContent = "Couldn't reach the API — is the server running?";
  }
}

loadStandings();
