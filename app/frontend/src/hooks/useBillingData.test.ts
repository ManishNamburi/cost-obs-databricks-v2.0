import { afterEach, describe, expect, it } from "vitest";
import {
  buildFilteredUrl,
  getActiveSourceLabels,
  getActiveSourceRouting,
  getActiveSourceTables,
  setActiveSourceLabels,
  setActiveSourceRouting,
  setActiveSourceTables,
} from "./useBillingData";

afterEach(() => {
  setActiveSourceLabels([]);
  setActiveSourceRouting([], []);
  setActiveSourceTables(null);
});

describe("active source getters", () => {
  it("stores labels, request routing, and published tables independently", () => {
    setActiveSourceLabels(["west4"]);
    setActiveSourceRouting(["local"], ["2"]);
    setActiveSourceTables(["daily_usage_summary"]);

    expect(getActiveSourceLabels()).toEqual(["west4"]);
    expect(getActiveSourceRouting()).toEqual({
      requestLabels: ["local"],
      workspaceIds: ["2"],
      tables: ["daily_usage_summary"],
    });
    expect(getActiveSourceTables()).toEqual(["daily_usage_summary"]);
  });

  it("repeats source_labels so commas in a label round-trip", () => {
    setActiveSourceLabels([]);
    setActiveSourceRouting(["east,1", "west"], []);

    const url = new URL(buildFilteredUrl("/api/billing/summary"), "https://example.test");
    expect(url.searchParams.getAll("source_labels")).toEqual(["east,1", "west"]);
  });
});
