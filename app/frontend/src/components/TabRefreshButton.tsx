import { useState } from "react";
import { Spinner } from "./Spinner";

interface TabRefreshButtonProps {
  onRefresh: () => Promise<void>;
  isRefreshing?: boolean;
}

export function TabRefreshButton({ onRefresh, isRefreshing }: TabRefreshButtonProps) {
  const [internalRefreshing, setInternalRefreshing] = useState(false);
  const [showTooltip, setShowTooltip] = useState(false);
  const refreshing = isRefreshing ?? internalRefreshing;

  const handleClick = async () => {
    if (refreshing) return;
    if (isRefreshing === undefined) setInternalRefreshing(true);
    try {
      await onRefresh();
    } finally {
      if (isRefreshing === undefined) {
        window.setTimeout(() => setInternalRefreshing(false), 600);
      }
    }
  };

  return (
    <div className="relative inline-flex" onMouseEnter={() => setShowTooltip(true)} onMouseLeave={() => setShowTooltip(false)}>
      <button
        onClick={handleClick}
        disabled={refreshing}
        aria-label="Refresh this tab"
        className="inline-flex h-[38px] w-[38px] items-center justify-center rounded-[var(--r-ctl)] border bg-white text-slate transition-colors hover:bg-oat-page disabled:cursor-not-allowed"
        style={{ borderColor: "var(--hairline)" }}
      >
        {refreshing ? (
          <Spinner size="sm" />
        ) : (
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        )}
      </button>

      {showTooltip && !refreshing && (
        <div className="pointer-events-none absolute right-0 top-full z-50 mt-2 w-64 rounded-lg border border-gray-200 bg-white px-3 py-2 shadow-lg">
          <p className="text-xs font-medium text-gray-700">Refresh this tab</p>
          <p className="mt-0.5 text-xs text-gray-500">
            Cancels pending queries, clears this tab&apos;s caches, and reloads this tab with the latest data from Databricks.
          </p>
          {/* Tooltip arrow */}
          <div className="absolute -top-1.5 right-3 h-3 w-3 rotate-45 border-l border-t border-gray-200 bg-white" />
        </div>
      )}
    </div>
  );
}
