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

# Only what the API actually reads at runtime — not db/, etl/, data/.
# reports/: GET /calibration serves reports/calibration_data.json.
# frontend/: served as static files at "/" (see api/main.py).
COPY ml/ ml/
COPY api/ api/
COPY reports/ reports/
COPY frontend/ frontend/

ENV PYTHONPATH=/app

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
