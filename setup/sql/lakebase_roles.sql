-- Lakebase role setup for the cost-obs app service principal
-- Run as the Lakebase superuser (generated credential with pg_superuser role)
--
-- Creates an OAuth role mapped to the app's service principal UUID,
-- grants schema usage, and sets ALTER DEFAULT PRIVILEGES so future
-- tables created by the setup role are automatically readable.

-- Replace :app_sp_uuid with the service principal's UUID (not client ID)
-- Replace :schema with the target schema (default: cost_obs)

CREATE ROLE IF NOT EXISTS ":app_sp_uuid" LOGIN;

GRANT USAGE ON SCHEMA ":schema" TO ":app_sp_uuid";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ":schema" TO ":app_sp_uuid";

-- Ensure future tables inherit permissions automatically
ALTER DEFAULT PRIVILEGES IN SCHEMA ":schema"
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ":app_sp_uuid";
