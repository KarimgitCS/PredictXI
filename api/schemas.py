"""Pydantic response models for the API."""

from datetime import datetime

from pydantic import BaseModel


class FixtureOut(BaseModel):
    fixture_id: int
    season: str
    matchday: int | None
    kickoff_at: datetime
    home_team: str
    away_team: str
    home_crest_url: str | None
    away_crest_url: str | None
    status: str


class StandingOut(BaseModel):
    team: str
    crest_url: str | None
    position: int
    played: int
    points: int
    wins: int
    draws: int
    losses: int
    goal_diff: int


class PredictionOut(BaseModel):
    fixture_id: int
    home_team: str
    away_team: str
    prob_home: float
    prob_draw: float
    prob_away: float
    predicted_outcome: str
    predicted_home_goals: int
    predicted_away_goals: int
    home_position: int | None
    away_position: int | None
    home_form_ppg: float | None
    away_form_ppg: float | None
    model_name: str
