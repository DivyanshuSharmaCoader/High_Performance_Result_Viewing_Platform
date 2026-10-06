#!/usr/bin/env bash
# Creates the three ScoreCode database roles (see docs/06 §2 and docs/07).
#   scorecode_migrator  owns the schema; runs Alembic. Never used by the running app.
#   scorecode_app       runtime role for API and workers: NOBYPASSRLS, DML only, subject to RLS.
#   scorecode_platform  platform console role: BYPASSRLS, used only by the platform module.
# Runs once, on first container start, as the postgres superuser.
set -euo pipefail

: "${SCORECODE_MIGRATOR_PASSWORD:?missing}"
: "${SCORECODE_APP_PASSWORD:?missing}"
: "${SCORECODE_PLATFORM_PASSWORD:?missing}"
DB="${SCORECODE_DB:-scorecode}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v migrator_pw="$SCORECODE_MIGRATOR_PASSWORD" \
  -v app_pw="$SCORECODE_APP_PASSWORD" \
  -v platform_pw="$SCORECODE_PLATFORM_PASSWORD" \
  -v db="$DB" <<'SQL'
CREATE ROLE scorecode_migrator LOGIN PASSWORD :'migrator_pw' NOSUPERUSER NOBYPASSRLS CREATEDB;
CREATE ROLE scorecode_app      LOGIN PASSWORD :'app_pw'      NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
CREATE ROLE scorecode_platform LOGIN PASSWORD :'platform_pw' NOSUPERUSER BYPASSRLS   NOCREATEDB NOCREATEROLE;

-- Runtime safety nets (docs/07 §7).
ALTER ROLE scorecode_app      SET statement_timeout = '15s';
ALTER ROLE scorecode_app      SET idle_in_transaction_session_timeout = '60s';
ALTER ROLE scorecode_platform SET statement_timeout = '30s';

CREATE DATABASE :"db" OWNER scorecode_migrator;
SQL

# Extensions need superuser; create them in the template so test databases get them too.
for target in template1 "$DB"; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$target" <<'SQL'
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
SQL
done

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$DB" <<'SQL'
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO scorecode_migrator;
GRANT USAGE ON SCHEMA public TO scorecode_app, scorecode_platform;
SQL
