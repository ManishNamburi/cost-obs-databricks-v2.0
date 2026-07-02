import { memo, useState, useEffect, useMemo, useRef, useCallback } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  LabelList,
} from "recharts";
import type { ProductBreakdownResponse, WorkspaceBreakdown } from "@/types/billing";
import { formatCurrencyCompact as formatCurrency } from "@/utils/formatters";
import { VirtualizedList } from "./VirtualizedList";

// Hoisted formatters — inline lambdas create a new ref every render and churn
// Recharts' internal prop diffing, which contributes to LabelList flicker.
const fmtCurrency = (v: unknown) => formatCurrency(v as number);
const fmtTooltip = (value: number | undefined) => formatCurrency(value ?? 0);
const fmtTooltipLabel = (label: unknown) => `Product: ${label}`;
const fmtYTick = (v: string) => (v.length > 18 ? v.substring(0, 18) + "..." : v);
const TOOLTIP_STYLE = { backgroundColor: "white", border: "1px solid #e5e7eb", borderRadius: "8px" } as const;
const LABEL_STYLE = { fontSize: 11, fill: "#6b7280" } as const;

interface WsRowProps {
  wsId: string;
  wsName: string;
  active: boolean;
  onSelect: (id: string) => void;
}
const WsRow = memo(function WsRow({ wsId, wsName, active, onSelect }: WsRowProps) {
  return (
    <button
      onClick={() => onSelect(wsId)}
      className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-xs hover:bg-gray-50"
    >
      <div className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${active ? "border-orange-500 bg-orange-500" : "border-gray-300"}`}>
        {active && <svg className="h-3 w-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>}
      </div>
      <span className="truncate text-gray-700">{wsName}</span>
    </button>
  );
});

interface ProductBreakdownProps {
  data: ProductBreakdownResponse | undefined;
  isLoading: boolean;
  workspaces?: WorkspaceBreakdown[];
  dateRange?: { startDate: string; endDate: string };
  workspaceNameMap?: Record<string, string>;
}

const CATEGORY_COLORS: Record<string, string> = {
  "SQL - DBSQL": "#1B5162",
  "SQL - Genie": "#06B6D4",
  SQL: "#1B5162",
  "ETL - Batch": "#10B981",
  "ETL - Streaming": "#14B8A6",
  Interactive: "#F59E0B",
  Serverless: "#06B6D4",
  "Model Serving": "#EC4899",
  "AI Search": "#EF4444",
  "Fine-Tuning": "#F97316",
  "AI Functions": "#3B82F6",
  Other: "#6B7280",
};

const COLOR_ROTATION = [
  "#1B5162", "#FF3621", "#06B6D4", "#10B981", "#F59E0B",
  "#3B82F6", "#EC4899", "#EF4444", "#14B8A6", "#6B7280",
  "#3B82F6", "#F97316",
];

export const ProductBreakdown = memo(function ProductBreakdown({ data, isLoading, workspaces, dateRange, workspaceNameMap }: ProductBreakdownProps) {
  const [selectedWorkspace, setSelectedWorkspace] = useState<string>("all");
  const [filteredData, setFilteredData] = useState<ProductBreakdownResponse | undefined>(undefined);
  const [filterLoading, setFilterLoading] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [wsSearch, setWsSearch] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (selectedWorkspace === "all") {
      setFilteredData(undefined);
      return;
    }

    setFilterLoading(true);
    const params = new URLSearchParams();
    if (dateRange?.startDate) params.set("start_date", dateRange.startDate);
    if (dateRange?.endDate) params.set("end_date", dateRange.endDate);
    params.set("workspace_id", selectedWorkspace);

    fetch(`/api/billing/by-product?${params}`)
      .then((res) => res.json())
      .then((json) => {
        setFilteredData(json);
        setFilterLoading(false);
      })
      .catch(() => {
        setFilterLoading(false);
      });
  }, [selectedWorkspace, dateRange?.startDate, dateRange?.endDate]);

  // Close dropdown on outside click; reset search on close so reopening starts fresh
  useEffect(() => {
    if (!dropdownOpen) {
      setWsSearch("");
      return;
    }
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [dropdownOpen]);

  const displayData = selectedWorkspace === "all" ? data : filteredData;
  const showLoading = isLoading || filterLoading;

  const selectedWorkspaceName = useMemo(() => {
    if (selectedWorkspace === "all" || !workspaces) return null;
    const ws = workspaces.find((w) => String(w.workspace_id) === selectedWorkspace);
    return workspaceNameMap?.[selectedWorkspace] || (ws ? (ws.workspace_name || String(ws.workspace_id)) : selectedWorkspace);
  }, [selectedWorkspace, workspaces, workspaceNameMap]);

  const selectWs = useCallback((wsId: string) => {
    setSelectedWorkspace((prev) => (prev === wsId ? "all" : wsId));
    setDropdownOpen(false);
  }, []);
  const wsItems = useMemo(
    () => (workspaces || []).map((ws) => {
      const wsId = String(ws.workspace_id);
      return { wsId, wsName: workspaceNameMap?.[wsId] || ws.workspace_name || String(ws.workspace_id) };
    }),
    [workspaces, workspaceNameMap],
  );
  const filteredWsItems = useMemo(() => {
    if (!wsSearch.trim()) return wsItems;
    const q = wsSearch.toLowerCase();
    return wsItems.filter((it) => it.wsName.toLowerCase().includes(q) || it.wsId.toLowerCase().includes(q));
  }, [wsItems, wsSearch]);

  const workspaceSelector = workspaces && workspaces.length > 1 ? (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setDropdownOpen(!dropdownOpen)}
        className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${selectedWorkspace !== "all" ? "border-[#FF3621] text-[#FF3621]" : "border-gray-300 text-gray-700 hover:bg-gray-50"}`}
      >
        {selectedWorkspace !== "all" ? (selectedWorkspaceName || selectedWorkspace) : "Workspace"}
        {selectedWorkspace !== "all" && (
          <button onClick={(e) => { e.stopPropagation(); setSelectedWorkspace("all"); }} className="ml-0.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full bg-orange-100 text-orange-600 hover:bg-orange-200">
            <svg className="h-2 w-2" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        )}
        <svg className={`h-4 w-4 transition-transform ${dropdownOpen ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {dropdownOpen && (
        <div className="absolute right-0 top-full z-[9999] mt-1 min-w-[220px] rounded-lg border border-gray-200 bg-white shadow-lg">
          <div className="sticky top-0 flex items-center justify-between border-b border-gray-100 bg-white px-3 py-2">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">Workspace</span>
            {selectedWorkspace !== "all" && (
              <button onClick={(e) => { e.stopPropagation(); setSelectedWorkspace("all"); setDropdownOpen(false); }} className="text-xs text-gray-500 hover:text-gray-800">Clear</button>
            )}
          </div>
          <div className="border-b border-gray-100 p-2">
            <input
              type="text"
              value={wsSearch}
              onChange={(e) => setWsSearch(e.target.value)}
              placeholder="Search workspaces..."
              className="w-full rounded border border-gray-200 px-2 py-1 text-xs focus:border-[#FF3621] focus:outline-none focus:ring-1 focus:ring-[#FF3621]"
              autoFocus
            />
          </div>
          {filteredWsItems.length === 0 ? (
            <div className="px-3 py-2 text-xs text-gray-500">No matching workspaces</div>
          ) : (
            <VirtualizedList
              items={filteredWsItems}
              itemHeight={36}
              maxHeight={256}
              getKey={(it) => it.wsId}
              renderItem={(it) => (
                <WsRow wsId={it.wsId} wsName={it.wsName} active={selectedWorkspace === it.wsId} onSelect={selectWs} />
              )}
            />
          )}
        </div>
      )}
    </div>
  ) : null;

  // Memoize before early returns so hook count is stable across renders.
  const chartData = useMemo(
    () =>
      [...(displayData?.products ?? [])]
        .sort((a, b) => b.total_spend - a.total_spend)
        .map((p) => ({
          name: p.category,
          total_spend: p.total_spend,
          percentage: p.percentage,
        })),
    [displayData],
  );

  if (showLoading) {
    return (
      <div className="rounded-lg bg-white p-6 border " style={{ borderColor: '#E5E5E5' }}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">Spend by Product</h3>
          {workspaceSelector}
        </div>
        <div className="flex h-48 flex-col items-center justify-center gap-3">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-gray-200" style={{ borderTopColor: '#FF3621' }} />
          <p className="text-sm text-gray-500">Loading product breakdown...</p>
        </div>
      </div>
    );
  }

  if (!displayData || displayData.products.length === 0) {
    return (
      <div className="rounded-lg bg-white p-6 border " style={{ borderColor: '#E5E5E5' }}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">Spend by Product</h3>
          {workspaceSelector}
        </div>
        <div className="flex h-80 flex-col items-center justify-center gap-2" style={{ color: '#6B7280' }}>
          <p className="text-base font-medium">No product breakdown available</p>
          <p className="text-sm">Try expanding the date range to capture more billing data</p>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in rounded-lg bg-white p-6 border " style={{ borderColor: '#E5E5E5', overflow: 'visible' }}>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">Spend by Product</h3>
          {selectedWorkspaceName && (
            <p className="text-sm text-orange-600 font-medium mt-0.5">
              Filtered to: {selectedWorkspaceName}
            </p>
          )}
        </div>
        {workspaceSelector}
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={chartData} layout="vertical" margin={{ left: 0, right: 70 }}>
          <XAxis type="number" tickFormatter={fmtCurrency} stroke="#9ca3af" fontSize={12} tickMargin={8} />
          <YAxis
            type="category"
            dataKey="name"
            width={100}
            stroke="#9ca3af"
            fontSize={12}
            tickMargin={8}
            tickFormatter={fmtYTick}
          />
          <Tooltip
            formatter={fmtTooltip}
            labelFormatter={fmtTooltipLabel}
            contentStyle={TOOLTIP_STYLE}
          />
          <Bar dataKey="total_spend" name="Spend" radius={[0, 4, 4, 0]} isAnimationActive={false}>
            {chartData.map((entry, idx) => (
              <Cell key={entry.name} fill={CATEGORY_COLORS[entry.name] || COLOR_ROTATION[idx % COLOR_ROTATION.length]} />
            ))}
            <LabelList dataKey="total_spend" position="right" formatter={fmtCurrency} style={LABEL_STYLE} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
});
