-- ALTER DEFAULT PRIVILEGES for Lakebase schema
-- Ensures any table created by the setup role is automatically
-- accessible to the app OAuth role without re-running grants.
--
-- Run as the Lakebase superuser after schema creation.
-- Replace :setup_role with the role used by setup notebooks (typically pg_superuser)
-- Replace :app_role with the app SP's UUID-based role
-- Replace :schema with the target schema (default: cost_obs)

ALTER DEFAULT PRIVILEGES FOR ROLE :setup_role IN SCHEMA :schema
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :app_role;

ALTER DEFAULT PRIVILEGES FOR ROLE :setup_role IN SCHEMA :schema
  GRANT USAGE, SELECT ON SEQUENCES TO :app_role;
