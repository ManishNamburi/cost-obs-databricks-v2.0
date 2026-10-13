import { useState, useEffect, useMemo, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { setActiveSourceLabels } from "@/hooks/useBillingData";
import { C } from "@/theme";
import { Spinner } from "./Spinner";

interface MvSource {
  label: string;
  catalog: string;
  schema: string;
}

interface SourceLabelFilterProps {
  variant?: "header" | "rail";
}

// Top-nav multi-select for filtering dashboard data by MV source label. Only
// rendered when additional MV sources are configured (otherwise there's a single
// local label and nothing to filter). Default is all sources (combined); the
// selection is pushed to the data layer and queries are invalidated to refetch.
export function SourceLabelFilter({ variant = "header" }: SourceLabelFilterProps) {
  const queryClient = useQueryClient();
  const { data } = useQuery<{ sources: MvSource[]; local_label: string }>({
    queryKey: ["mv-sources"],
    queryFn: () => fetch("/api/settings/mv-sources").then((r) => r.json()).catch(() => ({ sources: [], local_label: "" })),
    staleTime: 60 * 1000,
  });

  const allLabels = useMemo(() => {
    const local = data?.local_label ? [data.local_label] : [];
    const extra = (data?.sources ?? []).map((s) => s.label);
    return Array.from(new Set([...local, ...extra])).filter(Boolean);
  }, [data]);

  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [applying, setApplying] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const lastAppliedRef = useRef<string>("");

  // Start with everything selected once labels are known.
  useEffect(() => {
    setSelected(new Set(allLabels));
  }, [allLabels]);

  const hasSources = (data?.sources?.length ?? 0) > 0;
  if (!hasSources || allLabels.length === 0) return null;

  const allSelected = selected.size === allLabels.length;

  const apply = async (next: Set<string>) => {
    // At least one source is always selected (the toggle enforces it); a full
    // selection means "all" (empty filter = every source).
    const effective = next.size === 0 || next.size === allLabels.length ? [] : Array.from(next);
    // Skip the refetch when the effective selection hasn't changed (e.g. closing
    // the dropdown without edits).
    const key = [...effective].sort().join("\u0001");
    if (key === lastAppliedRef.current) return;
    lastAppliedRef.current = key;
    setActiveSourceLabels(effective);
    // Tactile "Applying…" feedback until the refetch settles — invalidateQueries
    // resolves once the invalidated active queries have refetched.
    setApplying(true);
    setErr(null);
    try {
      await queryClient.invalidateQueries();
      const failed = queryClient.getQueryCache().getAll().some((q) => q.isActive() && q.state.status === "error");
      setErr(failed ? "Some data failed to refresh — try again." : null);
    } catch {
      setErr("Some data failed to refresh — try again.");
    } finally {
      setApplying(false);
    }
  };

  const toggle = (label: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(label)) {
        // At least one source must always stay selected — refuse to clear the last one.
        if (next.size <= 1) return prev;
        next.delete(label);
      } else {
        next.add(label);
      }
      return next;
    });
  };

  const label = () => {
    if (allSelected) return "All sources";
    if (selected.size === 1) return Array.from(selected)[0];
    return `${selected.size} sources`;
  };

  const rail = variant === "rail";

  return (
    <div className={rail ? "relative min-w-0 shrink" : "relative"}>
      {open && <div className="fixed inset-0 z-10" onClick={() => { setOpen(false); apply(selected); }} />}
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={applying ? "Updating sources" : label()}
        className={rail
          ? "rail-source-filter rail-control-border flex h-[28px] w-[116px] items-center gap-[6px] whitespace-nowrap rounded-[7px] border bg-white/[.07] px-[8px] text-[11.5px] font-medium text-[#E9EFED] transition-colors hover:bg-white/[.12] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#FF3621]/35 focus-visible:ring-offset-1 focus-visible:ring-offset-[#1B3139] min-[1280px]:w-[190px] min-[1280px]:gap-[8px] min-[1280px]:px-[10px]"
          : "co-filter flex items-center gap-2 whitespace-nowrap px-3"
        }
        title="Filter by data source"
      >
        {applying ? (
          <Spinner size="sm" />
        ) : (
          <svg className={rail ? "h-[14px] w-[14px] shrink-0 opacity-70" : "h-4 w-4 shrink-0 text-gray-500"} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7h16M6 12h12M9 17h6" />
          </svg>
        )}
        <span className={rail ? "max-w-[68px] truncate min-[1280px]:max-w-[140px]" : "max-w-[140px] truncate"}>
          {applying ? "Updating…" : (
            rail ? (
              <>
                <span className="min-[1180px]:hidden">
                  {allSelected
                    ? `${allLabels.length} ${allLabels.length === 1 ? "source" : "sources"}`
                    : selected.size === 1 ? "1 source" : `${selected.size} sources`}
                </span>
                <span className="hidden min-[1180px]:inline">{label()}</span>
              </>
            ) : label()
          )}
        </span>
        <svg className={`${rail ? "h-[12px] w-[12px] opacity-70" : "h-4 w-4 text-gray-500"} ml-auto shrink-0 transition-transform ${open ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="co-filter-menu absolute right-0 z-20 mt-2 min-w-[220px] p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">Data source</span>
            {/* No "Clear" — at least one source must stay selected. "All" selects every source. */}
            <button onClick={() => setSelected(new Set(allLabels))} className="text-xs text-gray-500 hover:text-gray-800">All</button>
          </div>
          <div className="max-h-60 space-y-1 overflow-y-auto">
            {allLabels.map((lbl) => {
              const checked = selected.has(lbl);
              const isLocal = lbl === data?.local_label;
              return (
                <label key={lbl} className={`flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 ${checked ? "bg-orange-50 hover:bg-orange-100" : "hover:bg-gray-50"}`}>
                  <input type="checkbox" checked={checked} onChange={() => toggle(lbl)} className="h-3.5 w-3.5 rounded border-gray-300 accent-lava" />
                  <span className="flex-1 truncate text-sm text-gray-700">{lbl}</span>
                  {isLocal && <span className="shrink-0 rounded-full bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-500">this workspace</span>}
                </label>
              );
            })}
          </div>
          {err && <div className="mt-2 rounded bg-red-50 px-2 py-1 text-[11px] text-red-700">{err}</div>}
          <div className="mt-3 flex items-center justify-between border-t border-gray-100 pt-2">
            <span className="text-[11px] text-gray-500">{allSelected ? `All ${allLabels.length}` : `${selected.size} of ${allLabels.length}`} selected</span>
            <button
              onClick={() => { apply(selected); setOpen(false); }}
              disabled={applying}
              className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium text-white transition-colors disabled:cursor-not-allowed"
              style={{ backgroundColor: applying ? C.busy : C.lava }}
            >
              {applying && <Spinner size="xs" />}
              {applying ? "Applying…" : "Apply"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
