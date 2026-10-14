export type UserRole = "admin" | "consumer";

export interface PermissionOwner {
  email: string | null;
  source:
    | "databricks_apps_api"
    | "release_environment"
    | "deployment_metadata"
    | "permission_store"
    | "first_configured_admin"
    | "unavailable";
  verified: boolean;
  deployment_creator?: string | null;
}

export interface UserPermissionsPayload {
  admins: string[];
  consumers: string[];
  table_location?: string | null;
  current_user?: string | null;
  current_role?: UserRole;
  owner?: PermissionOwner;
  role_capabilities?: Record<UserRole, {
    summary: string;
    can_view_dashboards: boolean;
    can_view_settings: boolean;
    can_manage_settings: boolean;
    can_manage_users: boolean;
    can_manage_data: boolean;
  }>;
}

export interface AuthStatusPayload {
  user_token_active: boolean;
  identity: "user_oauth" | "service_principal";
  locked_to_sp: boolean;
  has_sql_scope: boolean | null;
  auth_mode: "unknown" | "user" | "sp";
  token_present: boolean;
  token_scopes: string[];
  user_email: string | null;
  override_mode: "sp" | "auto" | null;
  sp_client_id: string;
  sp_display_name: string;
  sp_user_name?: string;
  sp_object_id?: string;
  sp_identity_url?: string;
  effective_oauth_scopes?: string[];
  oauth_scope_source?: "databricks_apps_oauth_m2m" | "unavailable";
  catalog: string;
  schema: string;
}

export interface ResourceInventoryGroup {
  count: number;
  names: string[];
}

export interface SettingsResourcesPayload {
  generated_at: string;
  subsections?: Record<string, {
    available: boolean;
    reason?: "temporarily_unavailable";
  }>;
  app: {
    name: string;
    url: string;
    page_url: string;
    source_code_url: string;
    deployment: {
      deployed_at: string | null;
      deployer: string | null;
      commit_sha: string | null;
      available: boolean;
      source: string;
    };
    version: {
      commit_sha?: string;
      branch?: string;
      repo?: string;
      commit_date?: string;
    };
  };
  service_principal: {
    display_name: string;
    client_id: string;
    object_id: string;
    user_name: string;
    identity_url: string;
    execution_identity: "service_principal";
    execution_explanation: string;
    effective_oauth_scopes: string[];
    oauth_scope_source?: string;
  };
  warehouse: {
    id: string | null;
    name: string | null;
    size: string | null;
    state: string;
    source: "app_resource" | "http_path" | "none";
  } | null;
  storage: {
    catalog: string;
    schema: string;
    permissions_table: string;
  };
  inventory: {
    aggregates: ResourceInventoryGroup;
    state: ResourceInventoryGroup;
    cache: ResourceInventoryGroup & {
      process_entries: number;
      process_max_entries: number;
      process_ttl_seconds: number;
    };
    unified_views: ResourceInventoryGroup;
    observed_tables: {
      checked_at: string;
      available: number;
      total: number;
    } | null;
  };
  shared_data_sources: Array<{
    label: string;
    catalog: string;
    schema: string;
    tables?: string[];
    cloud?: string;
    added_at?: string;
  }>;
  cloud_cost_connections: Array<{
    id?: string;
    name: string;
    provider: string;
    created_at?: string;
  }>;
  workspace_filter: {
    mode: "restricted" | "all_workspaces";
    count: number;
  };
  refresh: {
    schedule: {
      enabled: boolean;
      frequency: "nightly" | "weekly" | "monthly";
      hour_utc: number;
      lookback_days: number;
    };
    status: {
      last_refresh_utc?: string | null;
      last_attempt_utc?: string | null;
      hours_since_refresh?: number | null;
      stale?: boolean;
      status?: string;
      refresh_history?: Array<{
        timestamp?: string;
        status?: string;
        trigger?: string;
        operation?: string;
      }>;
    } | null;
  };
}
