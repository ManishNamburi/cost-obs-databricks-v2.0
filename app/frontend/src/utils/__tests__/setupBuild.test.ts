import { describe, expect, it } from "vitest";
import { MAX_FAILED_POLLS, isAccessError, isGrantableCatalogError, setupBuildOutcome } from "../setupBuild";

describe("setupBuildOutcome", () => {
  it("stops waiting as soon as one table fails, while the server finishes the rest", () => {
    const outcome = setupBuildOutcome(
      {
        status: "running",
        error: null,
        table_progress: { daily_usage_summary: "error", daily_query_stats: "running" },
        table_errors: { daily_usage_summary: "[INSUFFICIENT_PERMISSIONS] no SELECT on system.billing.usage" },
      },
      0,
    );
    expect(outcome).toEqual({
      kind: "failed",
      message: "Creating `daily_usage_summary` failed: [INSUFFICIENT_PERMISSIONS] no SELECT on system.billing.usage",
      serverBusy: true,
    });
  });

  it("uses the server's final message once the build has ended", () => {
    expect(
      setupBuildOutcome({ status: "error", error: "Catalog `x` does not exist.", table_progress: {} }, 0),
    ).toEqual({ kind: "failed", message: "Catalog `x` does not exist.", serverBusy: false });
  });

  it("still fails a table that reported no reason", () => {
    const outcome = setupBuildOutcome({ status: "running", error: null, table_progress: { t: "error" } }, 0);
    expect(outcome).toMatchObject({ kind: "failed", message: "Creating `t` failed." });
  });

  it("keeps waiting through a few missed polls, then gives up", () => {
    expect(setupBuildOutcome(null, MAX_FAILED_POLLS - 1)).toEqual({ kind: "running" });
    expect(setupBuildOutcome(null, MAX_FAILED_POLLS)).toMatchObject({ kind: "lost" });
  });

  it("finishes when every table is done, and keeps waiting while they run", () => {
    expect(setupBuildOutcome({ status: "running", error: null, table_progress: { a: "done", b: "done" } }, 0)).toEqual({
      kind: "done",
    });
    expect(setupBuildOutcome({ status: "running", error: null, table_progress: { a: "done", b: "running" } }, 0)).toEqual({
      kind: "running",
    });
  });
});

describe("permission detection", () => {
  it("leaves catalog grants to the grant helper", () => {
    expect(isGrantableCatalogError("`sp` needs CREATE SCHEMA permission. GRANT CREATE SCHEMA ON CATALOG c TO `sp`")).toBe(true);
  });

  it("recognises other access failures", () => {
    expect(isAccessError("[INSUFFICIENT_PERMISSIONS] User does not have SELECT on Table 'system.billing.usage'")).toBe(true);
    expect(isAccessError("PERMISSION_DENIED: not allowed")).toBe(true);
    expect(isAccessError("Creating `t` failed: [PARSE_SYNTAX_ERROR] near 'FROM'")).toBe(false);
  });
});
