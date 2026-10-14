import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SourceLabelFilter } from "../SourceLabelFilter";
import {
  buildFilteredUrl,
  getActiveSourceLabels,
  getActiveSourceRouting,
  setActiveSourceLabels,
  setActiveSourceRouting,
  setActiveSourceTables,
} from "@/hooks/useBillingData";
import { SourceCapabilityNotice } from "../brand";

const sourceData = (labels: string[]) => ({
  local_label: "local",
  sources: labels
    .filter((label) => label !== "local")
    .map((label) => ({ label, catalog: "shared", schema: "cost_obs" })),
});

afterEach(() => {
  setActiveSourceLabels([]);
  setActiveSourceRouting([], []);
  setActiveSourceTables(null);
  vi.unstubAllGlobals();
});

describe("source label capability getters", () => {
  it("lists only aggregates actually missing from the selected source", () => {
    setActiveSourceLabels(["west4"]);
    setActiveSourceTables(["daily_workspace_breakdown"]);

    render(
      <SourceCapabilityNotice
        title="Platform detail unavailable"
        description="Some shared detail is unavailable."
        requiredAggregates={[
          "daily_query_stats",
          "daily_workspace_breakdown",
          "dbsql_cost_per_query",
        ]}
      />,
    );

    expect(screen.getByText(/Missing from selected source/)).toBeVisible();
    expect(screen.getByText("daily_query_stats")).toBeVisible();
    expect(screen.getByText("dbsql_cost_per_query")).toBeVisible();
    expect(screen.queryByText("daily_workspace_breakdown")).not.toBeInTheDocument();
  });

  it("encodes a conflicting workspace and source selection as an empty scope", () => {
    setActiveSourceLabels(["west4"]);
    setActiveSourceRouting(["local"], ["2"]);

    const url = new URL(
      buildFilteredUrl("/api/test", new URLSearchParams(), ["1"]),
      "https://example.test",
    );

    expect(url.searchParams.get("workspace_ids")).toBe("source-scope-no-overlap");
    expect(url.searchParams.getAll("source_labels")).toEqual(["local"]);
  });

  it("updates module scope before invoking the App refresh callback", async () => {
    const current = sourceData(["local", "west"]);
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => current,
    })));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(["mv-sources"], current);
    const scopesSeen: string[][] = [];

    render(
      <QueryClientProvider client={client}>
        <SourceLabelFilter onApplied={async () => {
          scopesSeen.push(getActiveSourceLabels());
        }} />
      </QueryClientProvider>,
    );

    await userEvent.click(await screen.findByRole("button", { name: "2 Sources" }));
    await userEvent.click(screen.getByRole("checkbox", { name: /west/i }));
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => expect(scopesSeen).toEqual([["local"]]));
  });

  it("routes a same-account source through its workspace ID", async () => {
    const current = {
      local_label: "local",
      sources: [{
        label: "west4",
        catalog: "west4_share",
        schema: "cost_obs",
        tables: ["daily_usage_summary"],
      }],
    };
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => current,
    })));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(["mv-sources"], current);
    const urls: string[] = [];

    render(
      <QueryClientProvider client={client}>
        <SourceLabelFilter
          localWorkspaces={[
            { id: "1", name: "east1-serverless" },
            { id: "2", name: "west4-serverless" },
          ]}
          onApplied={() => {
            urls.push(buildFilteredUrl("/api/test"));
          }}
        />
      </QueryClientProvider>,
    );

    await userEvent.click(await screen.findByRole("button", { name: "2 Sources" }));
    await userEvent.click(screen.getByRole("checkbox", { name: /local/i }));
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => expect(urls).toHaveLength(1));
    expect(urls[0]).toContain("workspace_ids=2");
    expect(urls[0]).toContain("source_labels=local");
    expect(getActiveSourceLabels()).toEqual(["west4"]);
    expect(getActiveSourceRouting()).toMatchObject({
      requestLabels: ["local"],
      workspaceIds: ["2"],
      tables: ["daily_usage_summary"],
    });
  });

  it("records published tables for a shared-only source", async () => {
    const current = {
      local_label: "local",
      sources: [{
        label: "west4",
        catalog: "west4_share",
        schema: "cost_obs",
        tables: ["daily_usage_summary"],
      }],
    };
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => current,
    })));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(["mv-sources"], current);

    render(
      <QueryClientProvider client={client}>
        <SourceLabelFilter onApplied={async () => undefined} />
      </QueryClientProvider>,
    );

    await userEvent.click(await screen.findByRole("button", { name: "2 Sources" }));
    await userEvent.click(screen.getByRole("checkbox", { name: /local/i }));
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() => expect(getActiveSourceLabels()).toEqual(["west4"]));
    expect(getActiveSourceRouting().tables).toEqual(["daily_usage_summary"]);
  });
});
