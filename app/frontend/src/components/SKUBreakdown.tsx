import { useMemo, useState, useEffect, useRef } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
  ResponsiveContainer,
  LabelList,
} from "recharts";
import type { SKUBreakdownResponse, WorkspaceBreakdown } from "@/types/billing";
import { formatCurrency } from "@/utils/formatters";

interface SKUBreakdownProps {
  data: SKUBreakdownResponse | undefined;
  isLoading: boolean;
  workspaces?: WorkspaceBreakdown[];
  dateRange?: { startDate: string; endDate: string };
  workspaceNameMap?: Record<string, string>;
}

const SKU_COLORS = [
  "#1B5162", "#FF3621", "#06B6D4", "#10B981", "#F59E0B",
  "#3B82F6", "#EC4899", "#EF4444", "#14B8A6", "#6B7280",
];

export function SKUBreakdown({ data, isLoading, workspaces, dateRange, workspaceNameMap }: SKUBreakdownProps) {
  const [selectedWorkspace, setSelectedWorkspace] = useState<string>("all");
  const [filteredData, setFilteredData] = useState<SKUBreakdownResponse | undefined>(undefined);
  const [filterLoading, setFilterLoading] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
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

    fetch(`/api/billing/sku-breakdown?${params}`)
      .then((res) => res.json())
      .then((json) => {
        setFilteredData(json);
        setFilterLoading(false);
      })
      .catch(() => {
        setFilterLoading(false);
      });
  }, [selectedWorkspace, dateRange?.startDate, dateRange?.endDate]);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    if (dropdownOpen) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [dropdownOpen]);

  const displayData = selectedWorkspace === "all" ? data : filteredData;
  const showLoading = isLoading || filterLoading;

  const selectedWorkspaceName = useMemo(() => {
    if (selectedWorkspace === "all" || !workspaces) return null;
    const ws = workspaces.find((w) => String(w.workspace_id) === selectedWorkspace);
    return workspaceNameMap?.[selectedWorkspace] || (ws ? (ws.workspace_name || String(ws.workspace_id)) : selectedWorkspace);
  }, [selectedWorkspace, workspaces, workspaceNameMap]);

  const workspaceOptions = workspaces || [];
  const selectedWsIds = selectedWorkspace === "all" ? [] : [selectedWorkspace];

  const triggerLabel = (() => {
    if (selectedWsIds.length === 0) return "All Workspaces";
    if (selectedWsIds.length === 1) return workspaceNameMap?.[selectedWsIds[0]] || selectedWsIds[0];
    return `Workspaces (${selectedWsIds.length})`;
  })();

  const workspaceSelector = workspaces && workspaces.length > 1 ? (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setDropdownOpen(!dropdownOpen)}
        className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
      >
        {triggerLabel}
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {dropdownOpen && (
        <div className="absolute right-0 z-10 mt-1 max-h-64 w-72 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg">
          <label className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50 cursor-pointer select-none">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-gray-300 text-[#FF3621] focus:ring-1 focus:ring-[#FF3621]"
              checked={selectedWorkspace === "all"}
              onChange={() => { setSelectedWorkspace("all"); setDropdownOpen(false); }}
            />
            <span className="text-sm text-gray-700">All Workspaces</span>
          </label>
          {workspaceOptions.map((ws) => {
            const wsId = String(ws.workspace_id);
            const isActive = selectedWorkspace === wsId;
            return (
              <label key={wsId} className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50 cursor-pointer select-none">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-gray-300 text-[#FF3621] focus:ring-1 focus:ring-[#FF3621]"
                  checked={isActive}
                  onChange={() => { setSelectedWorkspace(isActive ? "all" : wsId); setDropdownOpen(false); }}
                />
                <span className="truncate text-sm text-gray-700">{workspaceNameMap?.[wsId] || ws.workspace_name || ws.workspace_id}</span>
              </label>
            );
          })}
        </div>
      )}
    </div>
  ) : null;

  const barData = useMemo(() => {
    if (!displayData?.skus?.length) return [];
    return [...displayData.skus]
      .sort((a, b) => b.total_spend - a.total_spend)
      .slice(0, 10)
      .map((sku) => {
        const stripped = (sku.product ?? "").replace(/^(PREMIUM_|STANDARD_|ENTERPRISE_)/i, "");
        const parts = stripped.split("_");
        const label = parts.length > 4 ? parts.slice(0, 4).join(" ") + "…" : stripped.replace(/_/g, " ");
        return { name: label, total_spend: sku.total_spend };
      });
  }, [displayData]);

  if (showLoading) {
    return (
      <div className="rounded-lg bg-white p-6 border " style={{ borderColor: '#E5E5E5' }}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">Spend by SKU</h3>
          {workspaceSelector}
        </div>
        <div className="flex h-48 flex-col items-center justify-center gap-3">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-gray-200" style={{ borderTopColor: '#FF3621' }} />
          <p className="text-sm text-gray-500">Loading SKU breakdown...</p>
        </div>
      </div>
    );
  }

  if (!displayData || !displayData.skus?.length) {
    return (
      <div className="rounded-lg bg-white p-6 border " style={{ borderColor: '#E5E5E5' }}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">Spend by SKU</h3>
          {workspaceSelector}
        </div>
        <div className="flex h-80 flex-col items-center justify-center gap-2 text-gray-500">
          <p className="text-base font-medium">No SKU data available</p>
          <p className="text-sm">Try expanding the date range</p>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in rounded-lg bg-white p-6 border " style={{ borderColor: '#E5E5E5' }}>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900">Spend by SKU</h3>
          {selectedWorkspaceName && (
            <p className="text-sm text-orange-600 font-medium mt-0.5">
              Filtered to: {selectedWorkspaceName}
            </p>
          )}
        </div>
        {workspaceSelector}
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={barData} layout="vertical" margin={{ left: -25, right: 70 }}>
          <XAxis type="number" tickFormatter={(v) => formatCurrency(v)} stroke="#9ca3af" fontSize={12} tickMargin={8} />
          <YAxis
            type="category"
            dataKey="name"
            width={175}
            stroke="#9ca3af"
            fontSize={11}
            tickMargin={2}
            tickFormatter={(v: string) => v.length > 22 ? v.substring(0, 20) + "…" : v}
          />
          <Tooltip
            formatter={(value: number | undefined) => formatCurrency(value ?? 0)}
            labelFormatter={(label) => `SKU: ${label}`}
            contentStyle={{
              backgroundColor: "white",
              border: "1px solid #e5e7eb",
              borderRadius: "8px",
            }}
          />
          <Bar dataKey="total_spend" name="Spend" radius={[0, 4, 4, 0]}>
            {barData.map((_entry, idx) => (
              <Cell key={idx} fill={SKU_COLORS[idx % SKU_COLORS.length]} />
            ))}
            <LabelList dataKey="total_spend" position="right" formatter={(v: unknown) => formatCurrency(v as number)} style={{ fontSize: 11, fill: "#6b7280" }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
