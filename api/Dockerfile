# A stable Python version deliberately, not this repo's local dev version —
# see requirements.txt history for the string of 3.14-specific workarounds
# (pandas segfault, psycopg2 wheel, xgboost/libomp) that a fresh, well-
# supported version sidesteps entirely.
FROM python:3.12-slim

WORKDIR /app

# libgomp1 is the Linux equivalent of the libomp fix needed locally on
# macOS — xgboost's compiled library needs an OpenMP runtime present.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only what the API actually reads at runtime — not db/ or data/.
# etl/: the API re-runs etl/fetch_live_data.py on a timer (see api/main.py).
# reports/: GET /calibration serves reports/calibration_data.json.
# frontend/: served as static files at "/" (see api/main.py).
COPY ml/ ml/
COPY etl/ etl/
COPY api/ api/
COPY reports/ reports/
COPY frontend/ frontend/
RUN chmod +x api/entrypoint.sh

ENV PYTHONPATH=/app

# Trains a fresh model against the hosted DB before serving — see
# entrypoint.sh for why. $PORT lets platforms like Render assign their own
# port; docker-compose leaves it unset and gets the 8000 default.
ENTRYPOINT ["api/entrypoint.sh"]
