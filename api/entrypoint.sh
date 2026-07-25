#!/bin/sh
# Model artifacts are gitignored (see ml/artifacts/.gitkeep comment) and the
# `models.artifact_path` row is only valid on the machine that trained it —
# so a freshly built container has no usable model yet. Train against the
# already-loaded hosted Postgres data (fast: ~3k rows, no ETL involved) and
# register+activate it before serving, rather than shipping binary model
# files in the image or depending on a path from whatever host trained them.
set -e

python ml/model_registry.py

exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
