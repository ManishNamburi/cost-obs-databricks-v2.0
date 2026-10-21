import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CloudCostsView } from "../CloudCostsView";

describe("CloudCostsView recovery", () => {
  it("shows a failed load instead of an empty cluster table", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <CloudCostsView
          data={undefined}
          isLoading={false}
          timeseriesData={undefined}
          timeseriesLoading={false}
          host={null}
          loadError="503: SQL capacity is full"
        />
      </QueryClientProvider>,
    );

    expect(screen.getByText("Cloud cost data could not be loaded")).toBeInTheDocument();
    expect(screen.getByText(/after automatic retries/i)).toBeInTheDocument();
    expect(screen.getByText(/503: SQL capacity is full/i)).toBeInTheDocument();
  });
});
