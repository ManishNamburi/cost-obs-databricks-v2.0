import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  WarehouseGuidanceBanner,
  WarehouseHealthCheckBanner,
} from "../WarehouseGuidanceBanner";

const smallWarehouse = {
  status: "warm" as const,
  warehouse_id: "warehouse-123",
  warehouse_name: "Cost Observability",
  warehouse_size: "X-Small",
  warehouse_type: "SERVERLESS",
};

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("WarehouseGuidanceBanner", () => {
  it("keeps title, warehouse chip, and actions on one vertical alignment", () => {
    render(
      <WarehouseGuidanceBanner
        warehouse={smallWarehouse}
        workspaceHost="https://dbc.example.com"
      />,
    );

    const alert = screen.getByRole("alert");
    expect(alert).toHaveClass("items-center");
    expect(screen.getByText("Warehouse sizing recommendation").parentElement).toHaveClass("items-center");
    expect(screen.getByRole("link", { name: /Manage warehouse/i }).parentElement).toHaveClass("items-center");
    expect(screen.getByText("Cost Observability · warehouse-123")).toBeInTheDocument();
  });

  it("persists dismissal only after the rendered warning is dismissed", async () => {
    const user = userEvent.setup();
    const key = "coc-warehouse-size-guidance:test-v1:warehouse-123";
    render(
      <WarehouseGuidanceBanner
        warehouse={smallWarehouse}
        workspaceHost="dbc.example.com"
        warningVersion="test-v1"
      />,
    );

    await user.click(screen.getByRole("button", { name: /Dismiss warehouse size recommendation/i }));
    expect(localStorage.getItem(key)).toBe("1");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("WarehouseHealthCheckBanner", () => {
  it("keeps status copy and retry on one row", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<WarehouseHealthCheckBanner isRetrying={false} onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveClass("items-center");
    await user.click(screen.getByRole("button", { name: "Retry status check" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
