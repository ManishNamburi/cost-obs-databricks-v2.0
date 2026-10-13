import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsResources } from "../SettingsResources";

const config = {
  warehouse: { id: "warehouse-id", name: "Serverless Starter Warehouse", size: "Medium", state: "RUNNING" },
  identity: { display_name: "app-cost-obs", user_name: "client-id" },
  storage_location: { catalog: "east1_serverless", schema: "cost_obs_schema" },
  version: { commit_sha: "abc123def456", branch: "main", repo: "cost-obs-app-v2", commit_date: "2026-08-30T21:29:46Z" },
};

const tables = {
  catalog: "east1_serverless",
  schema: "cost_obs_schema",
  tables: [
    { name: "daily_usage_summary", exists: true },
    { name: "daily_workspace_breakdown", exists: true },
    { name: "app_user_permissions", exists: true },
    { name: "daily_product_breakdown", exists: false },
  ],
};

function mockApis(overrides: Record<string, unknown> = {}) {
  vi.stubGlobal("fetch", vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    const json = (body: unknown, status = 200) => Promise.resolve(
      new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
    );
    if (url.includes("/api/settings/config")) return json(overrides.config ?? config, overrides.configStatus as number | undefined);
    if (url.includes("/api/settings/auth-status")) return json(overrides.authStatus ?? { sp_display_name: "app-cost-obs", sp_client_id: "client-id" });
    if (url.includes("/api/settings/app-links")) return json(overrides.appLinks ?? {
      app_page_url: "https://dbc.example.com/apps/cost-obs",
      source_code_url: "https://github.com/example/cost-obs",
    });
    if (url.includes("/api/settings/tables")) return json(overrides.tables ?? tables, overrides.tablesStatus as number | undefined);
    if (url.includes("/api/settings/mv-sources")) return json(overrides.mvSources ?? {
      sources: [{ label: "west", catalog: "west_share", schema: "cost_obs" }],
    });
    if (url.includes("/api/settings/cloud-connections")) return json(overrides.cloudConnections ?? [
      { id: "connection-1", name: "AWS CUR", provider: "aws" },
    ]);
    return json({});
  }));
}

function renderResources() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SettingsResources />
    </QueryClientProvider>,
  );
}

describe("SettingsResources", () => {
  beforeEach(() => {
    mockApis();
  });

  it("renders runtime, inventory, and source cards from existing settings APIs", async () => {
    renderResources();

    expect(await screen.findByText("App runtime")).toBeVisible();
    expect(screen.getByText("Managed data inventory")).toBeVisible();
    expect(screen.getByText("Data sources & scope")).toBeVisible();
    expect(screen.getByText("app-cost-obs")).toBeVisible();
    expect(screen.getByText("Aggregate tables (2)")).toBeVisible();
    expect(screen.getByText("State tables (1)")).toBeVisible();
    expect(screen.getByText("Shared data sources (1)")).toBeVisible();
    expect(screen.getByText("Cloud-cost connections (1)")).toBeVisible();
    expect(screen.getByText("east1_serverless.cost_obs_schema.app_user_permissions")).toBeVisible();
  });

  it("shows empty source copy when no shared sources or cloud connections exist", async () => {
    mockApis({ mvSources: { sources: [] }, cloudConnections: [] });
    renderResources();

    expect(await screen.findByText("Shared data sources (0)")).toBeVisible();
    expect(screen.getByText("Only this workspace's managed data is configured.")).toBeVisible();
    expect(screen.getByText("No cloud billing connections are configured.")).toBeVisible();
  });

  it("keeps the visual shell and retry when table inventory is unavailable", async () => {
    mockApis({ tablesStatus: 500, tables: { error: "failed" } });
    renderResources();

    expect(await screen.findByText(/resource details are temporarily unavailable \(managed data inventory\)/i)).toBeVisible();
    expect(screen.getByText("App runtime")).toBeVisible();
    expect(screen.getByRole("button", { name: "Retry" })).toBeVisible();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
  });

  it("renders only valid HTTPS app links and no secrets", async () => {
    renderResources();

    const app = await screen.findByRole("link", { name: /App resource/ });
    expect(app).toHaveAttribute("href", "https://dbc.example.com/apps/cost-obs");
    expect(screen.getByRole("link", { name: /Source/ })).toHaveAttribute("href", "https://github.com/example/cost-obs");
    expect(document.body.textContent).not.toMatch(/client_secret|access_key|token-value/i);
  });

  it("shows the error empty state when config cannot be loaded", async () => {
    mockApis({ configStatus: 500 });
    renderResources();

    expect(await screen.findByRole("alert")).toHaveTextContent(/resource metadata is unavailable/i);
    expect(screen.getByRole("button", { name: "Retry" })).toBeVisible();
  });
});
