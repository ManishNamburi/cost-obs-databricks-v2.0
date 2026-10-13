import { useQuery } from "@tanstack/react-query";
import { Group, LinkButton, MonoChip, Row, SectionTitle, T } from "./dubois";
import type { AppConfigInfo } from "./SettingsConfig";
import "./settings.css";

const AGGREGATE_TABLES = new Set([
  "daily_usage_summary",
  "daily_product_breakdown",
  "daily_workspace_breakdown",
  "sql_tool_attribution",
  "daily_query_stats",
  "dbsql_cost_per_query",
]);

const externalIcon = (
  <svg aria-hidden="true" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4M14 4h6m0 0v6m0-6L10 14" />
  </svg>
);

function safeExternalUrl(value?: string | null): string | null {
  try {
    const url = new URL(value ?? "");
    if (url.protocol !== "https:" || url.username || url.password) return null;
    return url.toString();
  } catch {
    return null;
  }
}

function formatTimestamp(value?: string | null): string {
  if (!value) return "Unavailable";
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime())
    ? value
    : timestamp.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function summarize(items: string[], limit = 5): string {
  const visible = items.slice(0, limit);
  const remaining = items.length - visible.length;
  return `${visible.join(" | ")}${remaining > 0 ? ` | +${remaining} more` : ""}`;
}

function InventoryList({ names, empty }: { names: string[]; empty: string }) {
  if (!names.length) {
    return <span style={{ fontSize: 12, color: T.textSecondary }}>{empty}</span>;
  }
  return (
    <div className="flex max-w-110 flex-wrap justify-end gap-1.5">
      {names.map((name) => (
        <MonoChip key={name}>{name}</MonoChip>
      ))}
    </div>
  );
}

interface TablesStatus {
  catalog: string | null;
  schema: string | null;
  error?: string | null;
  tables?: Array<{ name: string; exists: boolean | null }>;
}

interface AppLinks {
  app_page_url?: string;
  source_code_url?: string;
}

interface AuthStatus {
  sp_display_name?: string;
  sp_client_id?: string;
}

interface MvSourcesPayload {
  sources?: Array<{ label: string; catalog: string; schema: string }>;
}

interface CloudConnection {
  id?: string;
  name: string;
  provider: string;
}

export function SettingsResources() {
  const {
    data: appConfig,
    isLoading: configLoading,
    isError: configError,
    refetch: refetchConfig,
  } = useQuery<AppConfigInfo>({
    queryKey: ["app-config"],
    queryFn: async () => {
      const response = await fetch("/api/settings/config");
      if (!response.ok) throw new Error(`Config request failed (${response.status})`);
      return response.json();
    },
    staleTime: 60 * 1000,
  });
  const { data: authStatus } = useQuery<AuthStatus | null>({
    queryKey: ["settings-auth-status"],
    queryFn: () => fetch("/api/settings/auth-status").then((r) => (r.ok ? r.json() : null)).catch(() => null),
    staleTime: 60 * 1000,
  });
  const { data: appLinks } = useQuery<AppLinks | null>({
    queryKey: ["settings-app-links"],
    queryFn: () => fetch("/api/settings/app-links").then((r) => (r.ok ? r.json() : null)).catch(() => null),
    staleTime: 5 * 60 * 1000,
  });
  const {
    data: tablesStatus,
    isError: tablesError,
    refetch: refetchTables,
  } = useQuery<TablesStatus>({
    queryKey: ["settings-tables-status"],
    queryFn: async () => {
      const response = await fetch("/api/settings/tables");
      if (!response.ok) throw new Error(`Tables request failed (${response.status})`);
      return response.json();
    },
    staleTime: 15 * 60 * 1000,
  });
  const { data: mvSources } = useQuery<MvSourcesPayload | null>({
    queryKey: ["mv-sources"],
    queryFn: () => fetch("/api/settings/mv-sources").then((r) => (r.ok ? r.json() : null)).catch(() => null),
    staleTime: 60 * 1000,
  });
  const { data: cloudConnections } = useQuery<CloudConnection[] | null>({
    queryKey: ["cloud-connections"],
    queryFn: () => fetch("/api/settings/cloud-connections").then((r) => (r.ok ? r.json() : null)).catch(() => null),
    staleTime: 5 * 60 * 1000,
  });

  if (configLoading && !appConfig) {
    return (
      <div>
        <SectionTitle title="Resources" subtitle="Authoritative Databricks App resources and managed-data inventory." />
        <div className="flex items-center justify-center gap-3 py-12" style={{ color: T.textSecondary }}>
          <span aria-hidden="true" className="settings-save-spinner" style={{ width: 20, height: 20, borderRadius: 999, border: `2px solid ${T.borderControl}`, borderTopColor: T.primary, display: "inline-block" }} />
          <span style={{ fontSize: 13 }}>Loading resources…</span>
        </div>
      </div>
    );
  }

  if (configError || !appConfig) {
    return (
      <div>
        <SectionTitle title="Resources" subtitle="Authoritative Databricks App resources and managed-data inventory." />
        <div role="alert" style={{ border: `1px solid ${T.dangerBorder}`, backgroundColor: T.dangerBg, color: T.dangerFg, borderRadius: 8, padding: "12px 14px", fontSize: 13 }}>
          Resource metadata is unavailable. No deployment state has been assumed.{" "}
          <button type="button" onClick={() => refetchConfig()} style={{ color: T.dangerFg, fontWeight: 600, textDecoration: "underline" }}>Retry</button>
        </div>
      </div>
    );
  }

  const warehouse = appConfig.warehouse;
  const loc = appConfig.storage_location;
  const configuredLocation = loc?.catalog && loc?.schema ? `${loc.catalog}.${loc.schema}` : "Not configured";
  const permissionsTable = loc?.catalog && loc?.schema
    ? `${loc.catalog}.${loc.schema}.app_user_permissions`
    : "Not configured";
  const spName = authStatus?.sp_display_name || appConfig.identity?.display_name || "Unavailable";
  const spClientId = authStatus?.sp_client_id || appConfig.identity?.user_name;
  const appPageUrl = safeExternalUrl(appLinks?.app_page_url);
  const sourceCodeUrl = safeExternalUrl(appLinks?.source_code_url);
  const existingTables = (tablesStatus?.tables ?? []).filter((table) => table.exists);
  const aggregateNames = existingTables.filter((table) => AGGREGATE_TABLES.has(table.name)).map((table) => table.name);
  const stateNames = existingTables.filter((table) => !AGGREGATE_TABLES.has(table.name)).map((table) => table.name);
  const sharedSources = mvSources?.sources ?? [];
  const connections = cloudConnections ?? [];
  const inventoryUnavailable = tablesError || tablesStatus?.error;

  return (
    <div>
      <SectionTitle title="Resources" subtitle="Authoritative Databricks App resources, managed data, and integrations." />
      {inventoryUnavailable && (
        <div role="status" style={{ border: `1px solid ${T.warningBorder}`, backgroundColor: T.warningBg, color: T.warningFg, borderRadius: 8, padding: "10px 12px", marginBottom: 12, fontSize: 12 }}>
          Some resource details are temporarily unavailable (managed data inventory).{" "}
          <button type="button" onClick={() => refetchTables()} style={{ color: T.warningFg, fontWeight: 600, textDecoration: "underline" }}>Retry</button>
        </div>
      )}

      <Group label="App runtime">
        <Row
          first
          label="App service principal"
          helper="Databricks Apps injects this execution identity. Credentials and tokens are never shown."
          control={
            <span className="inline-flex max-w-110 flex-wrap items-center justify-end gap-2">
              <MonoChip>{spName}</MonoChip>
              {spClientId && spClientId !== spName && <MonoChip>{spClientId}</MonoChip>}
            </span>
          }
        />
        <Row
          label="SQL warehouse"
          helper={warehouse
            ? `${warehouse.name || warehouse.id || "Unnamed warehouse"} · ${warehouse.size || "Size unavailable"}`
            : "No warehouse resource is bound."}
          control={<MonoChip>{warehouse?.state || "NOT_CONFIGURED"}</MonoChip>}
        />
        <Row label="Catalog & schema" helper="Configured Unity Catalog location for app-managed data." control={<MonoChip>{configuredLocation}</MonoChip>} />
        <Row
          label="Deployment"
          helper={[
            appConfig.version?.repo || null,
            appConfig.version?.branch ? `branch ${appConfig.version.branch}` : null,
            appConfig.version?.commit_sha ? `commit ${appConfig.version.commit_sha.slice(0, 12)}` : null,
          ].filter(Boolean).join(" · ") || "Deployment metadata unavailable."}
          control={<span style={{ fontSize: 12, color: T.textSecondary }}>{formatTimestamp(appConfig.version?.commit_date)}</span>}
        />
        {(appPageUrl || sourceCodeUrl) && (
          <Row
            label="Databricks App links"
            control={
              <span className="inline-flex items-center gap-4">
                {appPageUrl && <LinkButton href={appPageUrl}><span className="inline-flex items-center gap-1">App resource {externalIcon}</span></LinkButton>}
                {sourceCodeUrl && <LinkButton href={sourceCodeUrl}><span className="inline-flex items-center gap-1">Source {externalIcon}</span></LinkButton>}
              </span>
            }
          />
        )}
      </Group>

      <Group label="Managed data inventory">
        <Row
          first
          label={`Aggregate tables (${aggregateNames.length})`}
          helper="Bounded pre-aggregations maintained by the app."
          control={<InventoryList names={aggregateNames} empty={inventoryUnavailable ? "Unavailable" : "None"} />}
        />
        <Row
          label={`State tables (${stateNames.length})`}
          helper="Durable app tables. Roles persist in app_user_permissions across redeploys."
          control={<InventoryList names={stateNames} empty={inventoryUnavailable ? "Unavailable" : "None"} />}
        />
        <Row
          label="Cache layers"
          helper="In-process and durable cache metadata is not exposed by the current settings APIs."
          control={<span style={{ fontSize: 12, color: T.textSecondary }}>Unavailable</span>}
        />
        <Row
          label="Shared routing views"
          helper="Unified shared-source views are not exposed by the current settings APIs."
          control={<span style={{ fontSize: 12, color: T.textSecondary }}>Unavailable</span>}
        />
      </Group>

      <Group label="Data sources & scope">
        <Row
          first
          label={`Shared data sources (${sharedSources.length})`}
          helper={sharedSources.length
            ? summarize(sharedSources.map((source) => `${source.label} · ${source.catalog}.${source.schema}`))
            : "Only this workspace's managed data is configured."}
          control={<span style={{ fontSize: 12, color: T.textSecondary }}>{sharedSources.length ? "Delta Sharing" : "None"}</span>}
        />
        <Row
          label={`Cloud-cost connections (${connections.length})`}
          helper={connections.length
            ? summarize(connections.map((connection) => `${connection.name} (${connection.provider.toUpperCase()})`))
            : "No cloud billing connections are configured."}
          control={<span style={{ fontSize: 12, color: T.textSecondary }}>{connections.length ? "Metadata only" : "None"}</span>}
        />
        <Row
          label="Workspace filter pool"
          helper="Set via COST_OBS_WORKSPACES at deploy time. The current pool count is not returned by a settings API."
          control={<span style={{ fontSize: 12, color: T.textSecondary }}>Redeploy to change</span>}
        />
        <Row label="Permissions table" helper="App roles persist here across deployments." control={<MonoChip>{permissionsTable}</MonoChip>} />
      </Group>
    </div>
  );
}
