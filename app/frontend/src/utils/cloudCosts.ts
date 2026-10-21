import type { InfraCostsResponse } from "@/types/billing";

export function getCloudInstanceFamily(
  instanceType: string | null | undefined,
  cloud: string,
): string {
  if (!instanceType) return "unknown";
  if (cloud.toUpperCase() === "AZURE") {
    const match = instanceType.match(/^(Standard_[A-Z]+)/);
    return match ? match[1] : "unknown";
  }
  if (cloud.toUpperCase() === "GCP") {
    return instanceType.split("-")[0] || "unknown";
  }
  return instanceType.split(".")[0] || "unknown";
}

/** Scale billed DBU dollars. Estimated VM costs stay list-rate cloud pricing. */
export function applyInfraPricing(
  data: InfraCostsResponse | undefined,
  multiplier: number,
): InfraCostsResponse | undefined {
  if (!data || multiplier === 1) return data;
  const scale = (value: number) => value * multiplier;
  const summary = data.billing_summary;
  return {
    ...data,
    billing_summary: summary
      ? {
          ...summary,
          total_cost: scale(summary.total_cost ?? 0),
          avg_cost_per_cluster: scale(summary.avg_cost_per_cluster ?? 0),
        }
      : undefined,
  };
}
