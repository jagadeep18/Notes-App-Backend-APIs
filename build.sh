#!/usr/bin/env bash
# build.sh — Render build script
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt --no-cache-dir

# Run database migrations
alembic upgrade head
