-- Unity Catalog grants for the cost-obs app service principal
-- Run as a UC admin with privileges on the target catalog/schema
--
-- The app SP needs SELECT on system tables for billing/usage data,
-- and USE CATALOG / USE SCHEMA on the cost_obs catalog and schema.

-- Replace :catalog with your UC catalog (default: main)
-- Replace :schema with the target schema (default: cost_obs)
-- Replace :app_sp_name with the service principal's display name

-- Catalog and schema access
GRANT USE CATALOG ON CATALOG :catalog TO `system`;
GRANT USE SCHEMA ON SCHEMA :catalog.system TO `cost_obs_app_sp`;

-- Billing system tables
GRANT SELECT ON TABLE system.billing.usage TO `cost_obs_app_sp`;
GRANT SELECT ON TABLE system.billing.list_prices TO `cost_obs_app_sp`;
GRANT SELECT ON TABLE system.billing.billable_usage TO `cost_obs_app_sp`;

-- Compute system tables
GRANT SELECT ON TABLE system.compute.clusters TO `cost_obs_app_sp`;
GRANT SELECT ON TABLE system.compute.node_types TO `cost_obs_app_sp`;

-- Access system tables
GRANT SELECT ON TABLE system.access.audit TO `cost_obs_app_sp`;

-- App working schema (for materialized views, setup_state, etc.)
GRANT USE SCHEMA ON SCHEMA :catalog.:schema TO `cost_obs_app_sp`;
GRANT SELECT, MODIFY, CREATE TABLE ON SCHEMA :catalog.:schema TO `cost_obs_app_sp`;
