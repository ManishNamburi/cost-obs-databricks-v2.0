import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TabRefreshRegion } from "../TabRefreshRegion";

describe("TabRefreshRegion", () => {
  it("reserves space so date chips are not covered by the refresh button", () => {
    const { container } = render(
      <TabRefreshRegion
        isLoading={false}
        isRefreshing={false}
        loadingSections={[]}
        onRefresh={vi.fn()}
        onDismissRefreshError={vi.fn()}
      >
        <div>Date range</div>
      </TabRefreshRegion>,
    );
    expect(screen.getByRole("button", { name: "Refresh this tab" })).toBeVisible();
    expect(container.querySelector(".pr-14")).toBeTruthy();
  });
});
