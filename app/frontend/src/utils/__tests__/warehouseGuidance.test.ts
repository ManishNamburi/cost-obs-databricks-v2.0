import { afterEach, describe, expect, it, vi } from "vitest";
import {
  classifyWarehouseSize,
  fetchWarehouseHealth,
  nextWarehouseWarmState,
  shouldGateDashboard,
  shouldShowDbuSkeleton,
  warehouseHealthPollInterval,
  warehouseManagementHref,
  warehouseWarningDismissalKey,
} from "../warehouseGuidance";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("warehouse cold-start gating", () => {
  it("gates warming and unavailable states until the first warm state", () => {
    expect(shouldGateDashboard("warming_up", false)).toBe(true);
    expect(shouldGateDashboard("unavailable", false)).toBe(true);
    expect(shouldGateDashboard("warm", false)).toBe(false);
  });

  it("never restores the full-screen gate after reaching warm", () => {
    const reachedWarm = nextWarehouseWarmState(false, "warm");
    expect(reachedWarm).toBe(true);
    expect(nextWarehouseWarmState(reachedWarm, "warming_up")).toBe(true);
    expect(shouldGateDashboard("warming_up", reachedWarm)).toBe(false);
    expect(shouldGateDashboard("unavailable", reachedWarm)).toBe(false);
  });

  it("preserves rebuild behavior during an initial warm-up", () => {
    expect(shouldGateDashboard("warming_up", false, true)).toBe(false);
  });

  it("keeps polling after endpoint errors and during cold start", () => {
    expect(warehouseHealthPollInterval(undefined, true)).toBe(15_000);
    expect(warehouseHealthPollInterval("warming_up", false)).toBe(5_000);
    expect(warehouseHealthPollInterval("warm", false)).toBe(15_000);
  });

  it("lets a successful DBU bundle replace the health-error skeleton", () => {
    expect(shouldShowDbuSkeleton(true, false)).toBe(false);
    expect(shouldShowDbuSkeleton(true, true)).toBe(true);
    expect(shouldShowDbuSkeleton(false, false)).toBe(true);
  });
});

describe("warehouse health fetching", () => {
  it("preserves an explicitly unavailable warehouse response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(
      JSON.stringify({ status: "unavailable", state: "NOT_CONFIGURED" }),
      { status: 200 },
    )));

    await expect(fetchWarehouseHealth()).resolves.toMatchObject({
      status: "unavailable",
      state: "NOT_CONFIGURED",
    });
  });

  it("rejects non-OK responses instead of synthesizing unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("starting", { status: 503 })));

    await expect(fetchWarehouseHealth()).rejects.toThrow(
      "Warehouse health check failed (503)",
    );
  });

  it("rejects network failures instead of synthesizing unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("network failed");
    }));

    await expect(fetchWarehouseHealth()).rejects.toThrow("network failed");
  });

  it("rejects an invalid response shape instead of synthesizing unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(
      JSON.stringify({ status: "bogus" }),
      { status: 200 },
    )));

    await expect(fetchWarehouseHealth()).rejects.toThrow(
      "Warehouse health check returned an invalid response",
    );
  });

  it("polls the REST health endpoint and never requests a SQL probe", async () => {
    const fetchMock = vi.fn(async () => new Response(
      JSON.stringify({
        status: "warm",
        state: "RUNNING",
        warehouse_size: "Small",
        warehouse_type: "SERVERLESS",
      }),
      { status: 200 },
    ));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchWarehouseHealth()).resolves.toMatchObject({
      status: "warm",
      warehouse_size: "Small",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/health/sql-warehouse");
  });
});

describe("warehouse size guidance", () => {
  it.each(["Small", "X-Small", "2X-Small", "x_small", "2xsmall"])(
    "classifies %s below Medium",
    (size) => expect(classifyWarehouseSize(size)).toBe("below-medium"),
  );

  it.each(["Medium", "Large", "X-Large", "2X-Large", "4XLARGE"])(
    "classifies %s as Medium-or-larger",
    (size) => expect(classifyWarehouseSize(size)).toBe("medium-or-larger"),
  );

  it("does not guess for missing or unfamiliar sizes", () => {
    expect(classifyWarehouseSize(null)).toBe("unknown");
    expect(classifyWarehouseSize("Custom")).toBe("unknown");
  });

  it("scopes dismissal to the warning version and warehouse ID", () => {
    expect(warehouseWarningDismissalKey("wh-1", "v1")).toBe(
      "coc-warehouse-size-guidance:v1:wh-1",
    );
    expect(warehouseWarningDismissalKey("wh-1", "v2")).not.toBe(
      warehouseWarningDismissalKey("wh-1", "v1"),
    );
    expect(warehouseWarningDismissalKey("wh-2", "v1")).not.toBe(
      warehouseWarningDismissalKey("wh-1", "v1"),
    );
  });

  it("builds the warehouse management detail href", () => {
    expect(warehouseManagementHref("dbc.example.com/", "wh/1")).toBe(
      "https://dbc.example.com/sql/warehouses/wh%2F1/edit",
    );
  });
});
