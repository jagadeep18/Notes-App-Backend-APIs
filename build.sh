#!/usr/bin/env bash
# build.sh — Render build script
# Render runs this during every deploy

set -o errexit  # exit on error

pip install --upgrade pip
pip install -r requirements.txt

# Run database migrations
alembic upgrade head
