// Real team identity colors, bucketed into four simple, maximally-distinct
// colors (red/blue/black/white) rather than a unique hue per team — some
// clubs' actual third colors (yellow, orange, claret) get folded into their
// closest bucket. When both teams in a match land in the same bucket, the
// away team is rotated to the next color in COLOR_ORDER so the two sides are
// never visually identical — deterministic, not random, so the same match
// always resolves to the same pair of colors.

const TEAM_COLORS = {
  "Arsenal": "red",
  "Aston Villa": "red",
  "Birmingham City": "blue",
  "Blackburn Rovers": "blue",
  "Blackpool": "black",
  "Bolton Wanderers": "white",
  "Bournemouth": "red",
  "Brentford": "red",
  "Brighton & Hove Albion": "blue",
  "Burnley": "blue",
  "Cardiff City": "blue",
  "Chelsea": "blue",
  "Coventry City": "blue",
  "Crystal Palace": "red",
  "Everton": "blue",
  "Fulham": "white",
  "Huddersfield Town": "blue",
  "Hull City": "black",
  "Ipswich Town": "blue",
  "Leeds United": "white",
  "Leicester City": "blue",
  "Liverpool": "red",
  "Manchester City": "blue",
  "Manchester United": "red",
  "Middlesbrough": "red",
  "Newcastle United": "black",
  "Norwich City": "white",
  "Nottingham Forest": "red",
  "Queens Park Rangers": "blue",
  "Reading": "blue",
  "Sheffield United": "red",
  "Southampton": "red",
  "Stoke City": "red",
  "Sunderland": "red",
  "Swansea City": "white",
  "Tottenham Hotspur": "white",
  "Watford": "black",
  "West Bromwich Albion": "blue",
  "West Ham United": "red",
  "Wigan Athletic": "blue",
  "Wolverhampton Wanderers": "black",
};

const COLOR_HEX = {
  red: "#D32F2F",
  blue: "#1D4ED8",
  black: "#18181B",
  white: "#FFFFFF",
};

const COLOR_ORDER = ["red", "blue", "black", "white"];
const DEFAULT_COLOR_KEY = "blue";

function teamColorKey(teamName) {
  return TEAM_COLORS[teamName] || DEFAULT_COLOR_KEY;
}

// Returns { home: {key, hex}, away: {key, hex} } — away is rotated to a
// different bucket if it would otherwise match home exactly.
function resolveMatchColors(homeTeam, awayTeam) {
  const homeKey = teamColorKey(homeTeam);
  let awayKey = teamColorKey(awayTeam);
  if (awayKey === homeKey) {
    const nextIndex = (COLOR_ORDER.indexOf(homeKey) + 1) % COLOR_ORDER.length;
    awayKey = COLOR_ORDER[nextIndex];
  }
  return {
    home: { key: homeKey, hex: COLOR_HEX[homeKey] },
    away: { key: awayKey, hex: COLOR_HEX[awayKey] },
  };
}
