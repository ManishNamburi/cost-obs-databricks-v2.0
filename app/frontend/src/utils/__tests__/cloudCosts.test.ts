import { describe, expect, it } from "vitest";
import { applyInfraPricing, getCloudInstanceFamily } from "../cloudCosts";

describe("applyInfraPricing", () => {
  it("scales billed DBU dollars and leaves VM estimates unchanged", () => {
    const priced = applyInfraPricing({
      cloud: "AWS",
      cloud_display_name: "AWS",
      clusters: [],
      instance_families: [],
      total_estimated_cost: 40,
      total_dbu_hours: 10,
      billing_summary: {
        total_cost: 100,
        avg_cost_per_cluster: 25,
        avg_clusters_per_day: 4,
        days_in_range: 7,
      },
      start_date: "2026-01-01",
      end_date: "2026-01-07",
    }, 0.8);

    expect(priced?.billing_summary?.total_cost).toBe(80);
    expect(priced?.billing_summary?.avg_cost_per_cluster).toBe(20);
    expect(priced?.total_estimated_cost).toBe(40);
    expect(applyInfraPricing(priced, 1)).toBe(priced);
  });
});

describe("getCloudInstanceFamily", () => {
  it("splits AWS, Azure, and GCP types", () => {
    expect(getCloudInstanceFamily("m5.xlarge", "AWS")).toBe("m5");
    expect(getCloudInstanceFamily("Standard_E8ds_v5", "AZURE")).toBe("Standard_E");
    expect(getCloudInstanceFamily("n2-standard-8", "GCP")).toBe("n2");
  });
});
