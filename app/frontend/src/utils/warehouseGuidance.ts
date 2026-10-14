export type WarehouseHealthStatus = "warm" | "warming_up" | "unavailable";

export interface WarehouseHealth {
  status: WarehouseHealthStatus;
  state?: string | null;
  warehouse_id?: string | null;
  warehouse_name?: string | null;
  warehouse_size?: string | null;
  warehouse_type?: string | null;
}

export type WarehouseSizeClass = "below-medium" | "medium-or-larger" | "unknown";

export const WAREHOUSE_WARM_SESSION_KEY = "coc-warehouse-warmed";
export const WAREHOUSE_GUIDANCE_VERSION = "medium-v1";

export async function fetchWarehouseHealth(): Promise<WarehouseHealth> {
  const response = await fetch("/api/health/sql-warehouse");
  if (!response.ok) {
    throw new Error(`Warehouse health check failed (${response.status})`);
  }

  const payload: unknown = await response.json();
  if (
    !payload
    || typeof payload !== "object"
    || !["warm", "warming_up", "unavailable"].includes(
      String((payload as { status?: unknown }).status),
    )
  ) {
    throw new Error("Warehouse health check returned an invalid response");
  }
  return payload as WarehouseHealth;
}

export function warehouseHealthPollInterval(
  status: WarehouseHealthStatus | undefined,
  hasError: boolean,
): number {
  if (hasError) return 15_000;
  return status === "warming_up" || status === undefined ? 5_000 : 15_000;
}

export function shouldShowDbuSkeleton(
  warehouseQueriesAllowed: boolean,
  bundleLoading: boolean,
): boolean {
  return !warehouseQueriesAllowed || bundleLoading;
}

function normalizeWarehouseSize(size: string | null | undefined): string {
  return (size ?? "").trim().toUpperCase().replace(/[\s_-]+/g, "");
}

export function classifyWarehouseSize(size: string | null | undefined): WarehouseSizeClass {
  const normalized = normalizeWarehouseSize(size);
  if (["2XSMALL", "XXSMALL", "XSMALL", "SMALL"].includes(normalized)) {
    return "below-medium";
  }
  if (/^(MEDIUM|(?:[234]?X)?LARGE)$/.test(normalized)) {
    return "medium-or-larger";
  }
  return "unknown";
}

export function nextWarehouseWarmState(
  hasReachedWarm: boolean,
  status: WarehouseHealthStatus | undefined,
): boolean {
  return hasReachedWarm || status === "warm";
}

export function shouldGateDashboard(
  status: WarehouseHealthStatus | undefined,
  hasReachedWarm: boolean,
  rebuildInProgress = false,
): boolean {
  if (hasReachedWarm || status === undefined || status === "warm") return false;
  if (status === "warming_up" && rebuildInProgress) return false;
  return true;
}

export function warehouseWarningDismissalKey(
  warehouseId: string,
  warningVersion = WAREHOUSE_GUIDANCE_VERSION,
): string {
  return `coc-warehouse-size-guidance:${warningVersion}:${warehouseId}`;
}

export function warehouseManagementHref(
  host: string | null | undefined,
  warehouseId: string | null | undefined,
): string | null {
  const trimmedHost = host?.trim();
  const trimmedId = warehouseId?.trim();
  if (!trimmedHost || !trimmedId) return null;
  const base = (trimmedHost.startsWith("http://") || trimmedHost.startsWith("https://")
    ? trimmedHost
    : `https://${trimmedHost}`
  ).replace(/\/+$/, "");
  return `${base}/sql/warehouses/${encodeURIComponent(trimmedId)}/edit`;
}
