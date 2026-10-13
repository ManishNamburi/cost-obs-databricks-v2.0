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

export const WAREHOUSE_GUIDANCE_VERSION = "medium-v1";

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
