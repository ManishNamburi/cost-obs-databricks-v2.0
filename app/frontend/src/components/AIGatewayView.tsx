import { useState } from "react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { format, parseISO } from "date-fns";
import type {
  AIGatewayDashboardBundle,
  AIGatewayModelRow,
  AIGatewayRouteRow,
  AIGatewayTimeseriesRow,
} from "@/types/billing";
import { formatCurrency } from "@/utils/formatters";

// ── Number formatting helpers ─────────────────────────────────────────────────

function fmtTokens(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function fmtRequests(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function fmtLatency(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms)}ms`;
}

// ── KPI card ──────────────────────────────────────────────────────────────────

function KpiCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg bg-white border p-4" style={{ borderColor: "#E5E5E5" }}>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">{label}</p>
      <p className="mt-1 text-2xl font-bold text-gray-900">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-gray-500">{sub}</p>}
    </div>
  );
}

// ── Not-configured banner ─────────────────────────────────────────────────────

function NotConfiguredBanner({ message }: { message?: string }) {
  return (
    <div className="rounded-lg bg-white border p-8 flex flex-col items-center justify-center gap-3 text-center" style={{ borderColor: "#E5E5E5" }}>
      <div className="flex h-12 w-12 items-center justify-center rounded-full" style={{ background: "rgba(255,54,33,0.08)" }}>
        <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" style={{ color: "#FF3621" }}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </div>
      <h3 className="text-base font-semibold text-gray-900">AI Gateway data not configured</h3>
      <p className="max-w-md text-sm text-gray-500">
        {message ?? (
          <>
            An account admin must create a derived table from <code className="bg-gray-100 px-1 rounded text-xs">system.ai_gateway.usage</code> and set{" "}
            <code className="bg-gray-100 px-1 rounded text-xs">AI_GATEWAY_USAGE_TABLE</code> in the app environment.
          </>
        )}
      </p>
      <a
        href="https://docs.databricks.com/en/admin/system-tables/ai-gateway.html"
        target="_blank"
        rel="noopener noreferrer"
        className="mt-1 text-xs font-medium hover:underline"
        style={{ color: "#FF3621" }}
      >
        View setup documentation →
      </a>
    </div>
  );
}

// ── Model table ───────────────────────────────────────────────────────────────

function ModelTable({ rows }: { rows: AIGatewayModelRow[] }) {
  const total = rows.reduce((s, r) => s + r.request_count, 0);
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full">
        <thead className="bg-gray-50">
          <tr className="border-b border-gray-200">
            <th className="px-3 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Model</th>
            <th className="px-3 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">Requests</th>
            <th className="px-3 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">Tokens</th>
            <th className="px-3 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">Avg Latency</th>
            <th className="px-3 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">Errors</th>
            <th className="px-3 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">Est. Cost</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {rows.map((r, i) => {
            const sharePct = total > 0 ? (r.request_count / total * 100) : 0;
            return (
              <tr key={i} className="hover:bg-gray-50">
                <td className="px-3 py-3">
                  <div className="text-sm font-medium text-gray-900 max-w-[220px] truncate" title={r.model_name}>
                    {r.model_name || "(unknown)"}
                  </div>
                  <div className="mt-0.5 h-1 w-full rounded-full bg-gray-100">
                    <div className="h-1 rounded-full" style={{ width: `${sharePct}%`, background: "#FF3621" }} />
                  </div>
                </td>
                <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-gray-900">
                  {fmtRequests(r.request_count)}
                  <span className="ml-1 text-xs text-gray-400">{sharePct.toFixed(0)}%</span>
                </td>
                <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-gray-600">
                  {fmtTokens(r.total_tokens)}
                </td>
                <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-gray-600">
                  {fmtLatency(r.avg_latency_ms)}
                </td>
                <td className="whitespace-nowrap px-3 py-3 text-right text-sm">
                  {r.error_count > 0 ? (
                    <span className="text-red-600 font-medium">{fmtRequests(r.error_count)}</span>
                  ) : (
                    <span className="text-gray-400">—</span>
                  )}
                </td>
                <td className="whitespace-nowrap px-3 py-3 text-right text-sm">
                  {r.cost_source === "unavailable" ? (
                    <span className="text-gray-400">—</span>
                  ) : (
                    <span className={r.cost_source === "token_estimate" ? "text-amber-600" : "text-gray-900"}>
                      {formatCurrency(r.estimated_cost_usd)}
                      {r.cost_source === "token_estimate" && (
                        <span className="ml-1 text-[10px] text-gray-400" title="Token-based estimate">~</span>
                      )}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Route table ───────────────────────────────────────────────────────────────

function RouteTable({ rows }: { rows: AIGatewayRouteRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full">
        <thead className="bg-gray-50">
          <tr className="border-b border-gray-200">
            <th className="px-3 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Route</th>
            <th className="px-3 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">Model</th>
            <th className="px-3 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">Requests</th>
            <th className="px-3 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">Tokens</th>
            <th className="px-3 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">Avg Latency</th>
            <th className="px-3 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">Est. Cost</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {rows.map((r, i) => (
            <tr key={i} className="hover:bg-gray-50">
              <td className="px-3 py-3 text-sm font-medium text-gray-900 max-w-[180px] truncate" title={r.route_name}>
                {r.route_name}
              </td>
              <td className="px-3 py-3 text-sm text-gray-600 max-w-[160px] truncate" title={r.model_name}>
                {r.model_name}
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-gray-900">
                {fmtRequests(r.request_count)}
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-gray-600">
                {fmtTokens(r.total_tokens)}
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-gray-600">
                {fmtLatency(r.avg_latency_ms)}
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right text-sm">
                {r.cost_source === "unavailable" ? (
                  <span className="text-gray-400">—</span>
                ) : (
                  <span className={r.cost_source === "token_estimate" ? "text-amber-600" : "text-gray-900"}>
                    {formatCurrency(r.estimated_cost_usd)}
                    {r.cost_source === "token_estimate" && (
                      <span className="ml-1 text-[10px] text-gray-400">~</span>
                    )}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Timeseries chart ──────────────────────────────────────────────────────────

function TimeseriesChart({ rows }: { rows: AIGatewayTimeseriesRow[] }) {
  // Aggregate by date across all models for the area chart
  const byDate = new Map<string, { requests: number; tokens: number }>();
  for (const r of rows) {
    const d = r.usage_date;
    const cur = byDate.get(d) ?? { requests: 0, tokens: 0 };
    byDate.set(d, {
      requests: cur.requests + r.request_count,
      tokens: cur.tokens + r.total_tokens,
    });
  }
  const chartData = Array.from(byDate.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, vals]) => ({
      date,
      label: format(parseISO(date), "MMM d"),
      requests: vals.requests,
      tokens_k: Math.round(vals.tokens / 1000),
    }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="label" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
        <YAxis yAxisId="req" tick={{ fontSize: 11 }} tickFormatter={fmtRequests} />
        <YAxis yAxisId="tok" orientation="right" tick={{ fontSize: 11 }} tickFormatter={v => `${v}K`} />
        <Tooltip
          contentStyle={{ fontSize: 12, borderRadius: 8 }}
          formatter={(v: number | undefined, name: string | undefined) =>
            name === "Requests"
              ? [fmtRequests(v ?? 0), name ?? ""]
              : [`${(v ?? 0).toLocaleString()}K tokens`, "Tokens"]
          }
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Area yAxisId="req" type="monotone" dataKey="requests" name="Requests" stroke="#FF3621" fill="rgba(255,54,33,0.12)" strokeWidth={2} dot={false} />
        <Area yAxisId="tok" type="monotone" dataKey="tokens_k" name="Tokens" stroke="#06B6D4" fill="rgba(6,182,212,0.08)" strokeWidth={2} dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ── Top users table ───────────────────────────────────────────────────────────

function TopUsersTable({ rows }: { rows: Array<{ client_user: string; request_count: number; routes_used: number; total_tokens: number }> }) {
  const total = rows.reduce((s, r) => s + r.request_count, 0);
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full">
        <thead className="bg-gray-50">
          <tr className="border-b border-gray-200">
            <th className="px-3 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">User / SP</th>
            <th className="px-3 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">Requests</th>
            <th className="px-3 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">Routes</th>
            <th className="px-3 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">Tokens</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {rows.slice(0, 10).map((r, i) => (
            <tr key={i} className="hover:bg-gray-50">
              <td className="px-3 py-3 text-sm text-gray-900 max-w-[220px] truncate" title={r.client_user}>
                {r.client_user}
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-gray-900">
                {fmtRequests(r.request_count)}
                <span className="ml-1 text-xs text-gray-400">
                  {total > 0 ? (r.request_count / total * 100).toFixed(0) : 0}%
                </span>
              </td>
              <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-gray-600">{r.routes_used}</td>
              <td className="whitespace-nowrap px-3 py-3 text-right text-sm text-gray-600">{fmtTokens(r.total_tokens)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

type SubTab = "overview" | "models" | "routes" | "users";

interface AIGatewayViewProps {
  data: AIGatewayDashboardBundle | undefined;
  isLoading: boolean;
}

export function AIGatewayView({ data, isLoading }: AIGatewayViewProps) {
  const [subTab, setSubTab] = useState<SubTab>("overview");

  if (isLoading) {
    return (
      <div className="rounded-lg bg-white p-8 border flex items-center justify-center gap-3" style={{ borderColor: "#E5E5E5" }}>
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gray-200" style={{ borderTopColor: "#FF3621" }} />
        <p className="text-sm text-gray-500">Loading AI Gateway data…</p>
      </div>
    );
  }

  if (!data || !data.configured) {
    return <NotConfiguredBanner message={data?.message} />;
  }

  const s = data.summary!;
  const models = data.by_model ?? [];
  const routes = data.by_route ?? [];
  const users = data.top_users ?? [];
  const timeseries = data.timeseries ?? [];

  const SUB_TABS: { id: SubTab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "models", label: `Models (${models.length})` },
    { id: "routes", label: `Routes (${routes.length})` },
    { id: "users", label: "Top Users" },
  ];

  return (
    <div className="animate-fade-in space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-gray-900">AI Gateway</h2>
          <p className="text-sm text-gray-500">
            Request volume, token consumption, and cost attribution
            {data.table && (
              <span className="ml-2 text-xs text-gray-400">← {data.table}</span>
            )}
          </p>
        </div>
        {/* Sub-tab toggle */}
        <div className="flex rounded-lg border border-gray-200 overflow-hidden text-xs font-medium">
          {SUB_TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setSubTab(tab.id)}
              className={`px-3 py-1.5 transition-colors ${subTab === tab.id ? "text-white" : "text-gray-600 hover:bg-gray-50"}`}
              style={subTab === tab.id ? { backgroundColor: "#1B3139" } : {}}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        <KpiCard label="Total Requests" value={fmtRequests(s.total_requests)} />
        <KpiCard label="Total Tokens" value={fmtTokens(s.total_tokens)} sub={`${fmtTokens(s.total_input_tokens)} in / ${fmtTokens(s.total_output_tokens)} out`} />
        <KpiCard label="Models" value={String(s.model_count)} />
        <KpiCard label="Routes" value={String(s.route_count)} />
        <KpiCard label="Avg Latency" value={fmtLatency(s.avg_latency_ms)} />
        <KpiCard
          label="Error Rate"
          value={`${s.error_rate_pct.toFixed(1)}%`}
          sub={`${fmtRequests(s.error_count)} errors`}
        />
      </div>

      {/* Cost summary */}
      {s.total_estimated_cost_usd > 0 && (
        <div className="rounded-lg border px-4 py-3 flex items-center gap-3 text-sm" style={{ borderColor: "#E5E5E5", background: "rgba(255,54,33,0.03)" }}>
          <svg className="h-4 w-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" style={{ color: "#FF3621" }}>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span className="font-medium text-gray-900">{formatCurrency(s.total_estimated_cost_usd)}</span>
          <span className="text-gray-500">estimated total cost (token-based estimate for external models; billing-correlated for Databricks 1P models)</span>
        </div>
      )}

      {/* Sub-tab content */}
      {subTab === "overview" && (
        <div className="space-y-5">
          <div className="rounded-lg bg-white border p-5" style={{ borderColor: "#E5E5E5" }}>
            <h3 className="mb-3 text-sm font-semibold text-gray-700">Request & Token Volume</h3>
            <TimeseriesChart rows={timeseries} />
          </div>

          {models.length > 0 && (
            <div className="rounded-lg bg-white border p-5" style={{ borderColor: "#E5E5E5" }}>
              <h3 className="mb-3 text-sm font-semibold text-gray-700">Top Models by Request Count</h3>
              <ResponsiveContainer width="100%" height={Math.min(models.length * 32 + 40, 280)}>
                <BarChart
                  layout="vertical"
                  data={models.slice(0, 8)}
                  margin={{ top: 4, right: 80, left: 8, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={fmtRequests} />
                  <YAxis type="category" dataKey="model_name" tick={{ fontSize: 11 }} width={130} />
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8 }}
                    formatter={(v: number | undefined) => [fmtRequests(v ?? 0), "Requests"]}
                  />
                  <Bar dataKey="request_count" name="Requests" fill="#FF3621" radius={[0, 3, 3, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {subTab === "models" && (
        <div className="rounded-lg bg-white border p-5" style={{ borderColor: "#E5E5E5" }}>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-700">By Model</h3>
            <p className="text-xs text-gray-400">~ = token-based cost estimate for external models</p>
          </div>
          <ModelTable rows={models} />
        </div>
      )}

      {subTab === "routes" && (
        <div className="rounded-lg bg-white border p-5" style={{ borderColor: "#E5E5E5" }}>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-700">By Route</h3>
            <p className="text-xs text-gray-400">AI Gateway routes with their backing models</p>
          </div>
          <RouteTable rows={routes} />
        </div>
      )}

      {subTab === "users" && (
        <div className="rounded-lg bg-white border p-5" style={{ borderColor: "#E5E5E5" }}>
          <h3 className="mb-3 text-sm font-semibold text-gray-700">Top Users by Request Volume</h3>
          {users.length > 0 ? (
            <TopUsersTable rows={users} />
          ) : (
            <p className="py-6 text-center text-sm text-gray-500">No user data available for this period.</p>
          )}
        </div>
      )}
    </div>
  );
}
