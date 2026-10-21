import { describe, expect, it } from "vitest";
import { formatKpiCurrency, formatNumber } from "./formatters";

describe("KPI abbreviations", () => {
  it("compacts million-dollar KPI values", () => {
    expect(formatKpiCurrency(14_121_083)).toBe("$14.12M");
    expect(formatKpiCurrency(12)).toBe("$12");
  });

  it("compacts large workspace counts", () => {
    expect(formatNumber(5481)).toBe("5.5K");
    expect(formatNumber(4179)).toBe("4.2K");
  });
});
