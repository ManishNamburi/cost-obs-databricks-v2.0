import { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

interface MvSource {
  label: string;
  catalog: string;
  schema: string;
  tables?: string[];
}

interface PreviewTable {
  table: string;
  status: "match" | "mismatch" | "absent";
}

interface PreviewResult {
  matched: number;
  total: number;
  tables: PreviewTable[];
}

// Settings → Config: register additional materialized-view source locations
// (typically Delta-shared in from another workspace) whose tables share the app's
// MV structure. They are unioned into every MV read (additive — local data always
// included) and tagged with the source's label for later filtering. After a
// catalog + schema is chosen, the views actually present in that schema are listed
// and the user multiselects which ones to include.
export function MvSourcesSection() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<{ sources: MvSource[]; local_label: string }>({
    queryKey: ["mv-sources"],
    queryFn: () => fetch("/api/settings/mv-sources").then((r) => r.json()).catch(() => ({ sources: [], local_label: "" })),
    staleTime: 30 * 1000,
  });
  const sources = data?.sources ?? [];

  const [open, setOpen] = useState(false);
  const [catalog, setCatalog] = useState("");
  const [schema, setSchema] = useState("");
  const [label, setLabel] = useState("");
  const [catalogs, setCatalogs] = useState<string[]>([]);
  const [schemas, setSchemas] = useState<string[]>([]);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load catalogs when the add form opens.
  useEffect(() => {
    if (!open || catalogs.length) return;
    fetch("/api/setup/list-catalogs").then((r) => r.json()).then((r) => setCatalogs(r.catalogs ?? [])).catch(() => setCatalogs([]));
  }, [open, catalogs.length]);

  // Load schemas whenever the catalog changes.
  useEffect(() => {
    setSchema("");
    setSchemas([]);
    setPreview(null);
    setSelected(new Set());
    if (!catalog) return;
    fetch(`/api/setup/list-schemas?catalog=${encodeURIComponent(catalog)}`)
      .then((r) => r.json()).then((r) => setSchemas(r.schemas ?? [])).catch(() => setSchemas([]));
  }, [catalog]);

  // Probe the chosen location whenever a full catalog.schema is selected; default the
  // selection to every view whose structure matches this app's.
  useEffect(() => {
    setPreview(null);
    setSelected(new Set());
    if (!catalog || !schema) return;
    setPreviewing(true);
    fetch(`/api/settings/mv-sources/preview?catalog=${encodeURIComponent(catalog)}&schema=${encodeURIComponent(schema)}`)
      .then((r) => r.json())
      .then((r: PreviewResult) => {
        setPreview(r);
        setSelected(new Set((r.tables || []).filter((t) => t.status === "match").map((t) => t.table)));
      })
      .catch(() => setPreview(null))
      .finally(() => setPreviewing(false));
  }, [catalog, schema]);

  // Views actually present in the shared schema (match or column-mismatch); absent
  // ones aren't shown. Only matching views can be selected — a column mismatch can't
  // be unioned into the app's structure.
  const presentTables = (preview?.tables ?? []).filter((t) => t.status !== "absent");
  const matchableCount = presentTables.filter((t) => t.status === "match").length;

  const toggle = (table: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(table)) next.delete(table);
      else next.add(table);
      return next;
    });
  };

  const canAdd = Boolean(label.trim() && catalog && schema && selected.size > 0 && !busy);

  const resetForm = () => {
    setCatalog(""); setSchema(""); setLabel(""); setPreview(null); setSelected(new Set()); setError(null);
  };

  const addSource = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/settings/mv-sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: label.trim(), catalog, schema, tables: Array.from(selected) }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
      // Refresh the sources list AND every dashboard tab — the unified views just
      // changed, so all visuals should refetch (the global progress bar reflects it).
      await queryClient.invalidateQueries();
      resetForm();
      setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const removeSource = async (lbl: string) => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/settings/mv-sources?label=${encodeURIComponent(lbl)}`, { method: "DELETE" });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
      // Refresh the sources list AND every dashboard tab — the unified views just
      // changed, so all visuals should refetch (the global progress bar reflects it).
      await queryClient.invalidateQueries();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const selectClass =
    "w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm text-gray-900 focus:border-[#2272B4] focus:outline-none focus:ring-1 focus:ring-[#2272B4] disabled:bg-gray-100 disabled:text-gray-500";

  return (
    <div className="mb-3 rounded-lg border border-gray-200 bg-white p-3">
      <h4 className="mb-2 text-sm font-semibold text-gray-900">Additional data (shared views)</h4>

      {isLoading ? (
        <div className="text-xs text-gray-500">Loading…</div>
      ) : sources.length > 0 ? (
        <div className="space-y-1.5">
          {sources.map((s) => (
            <div key={s.label} className="flex items-center gap-2 rounded-md border border-gray-100 bg-gray-50 px-2.5 py-1.5">
              <span className="rounded-full border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">{s.label}</span>
              <span className="min-w-0 flex-1 truncate font-mono text-xs text-gray-600">{s.catalog}.{s.schema}</span>
              <span className="shrink-0 text-[10px] text-gray-500">
                {s.tables ? `${s.tables.length} view${s.tables.length === 1 ? "" : "s"}` : "all views"}
              </span>
              <button onClick={() => removeSource(s.label)} disabled={busy} className="shrink-0 text-xs font-medium text-gray-500 hover:text-red-600 disabled:opacity-50">
                Remove
              </button>
            </div>
          ))}
        </div>
      ) : null}

      {/* Browse is the primary affordance for adding a Delta-shared source. */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="mt-2 inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold text-white transition-colors"
          style={{ backgroundColor: "#2272B4" }}
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
          </svg>
          Browse{sources.length > 0 ? " for another source" : ""}
        </button>
      )}

      {open && (
        <div className="mt-2 space-y-2 rounded-lg border border-gray-200 bg-gray-50 p-3">
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <label className="block text-[11px] font-medium text-gray-700">Catalog</label>
              <select value={catalog} onChange={(e) => setCatalog(e.target.value)} className={selectClass}>
                <option value="">Select…</option>
                {catalogs.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="space-y-1">
              <label className="block text-[11px] font-medium text-gray-700">Schema</label>
              <select value={schema} onChange={(e) => setSchema(e.target.value)} disabled={!catalog} className={selectClass}>
                <option value="">Select…</option>
                {schemas.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>

          {catalog && schema && (
            <div className="space-y-1.5">
              {previewing ? (
                <span className="text-[11px] text-gray-500">Reading views in this schema…</span>
              ) : preview ? (
                presentTables.length === 0 ? (
                  <span className="text-[11px] text-red-600">
                    No summary views found at this location — check that the shared schema holds this app's views.
                  </span>
                ) : (
                  <>
                    <div className="flex items-center justify-between">
                      <label className="block text-[11px] font-medium text-gray-700">
                        Views to include ({selected.size} of {matchableCount})
                      </label>
                      {matchableCount > 0 && (
                        <button
                          type="button"
                          onClick={() =>
                            setSelected(
                              selected.size === matchableCount
                                ? new Set()
                                : new Set(presentTables.filter((t) => t.status === "match").map((t) => t.table))
                            )
                          }
                          className="text-[10px] font-medium text-[#2272B4] hover:underline"
                        >
                          {selected.size === matchableCount ? "Clear all" : "Select all"}
                        </button>
                      )}
                    </div>
                    <div className="max-h-40 space-y-1 overflow-y-auto rounded-md border border-gray-200 bg-white p-1.5">
                      {presentTables.map((t) => {
                        const isMatch = t.status === "match";
                        return (
                          <label
                            key={t.table}
                            className={`flex items-center gap-2 rounded px-1.5 py-1 text-xs ${isMatch ? "cursor-pointer hover:bg-gray-50" : "cursor-not-allowed opacity-60"}`}
                          >
                            <input
                              type="checkbox"
                              disabled={!isMatch}
                              checked={selected.has(t.table)}
                              onChange={() => toggle(t.table)}
                              className="h-3.5 w-3.5 rounded border-gray-300 text-[#2272B4] focus:ring-[#2272B4]"
                            />
                            <span className="min-w-0 flex-1 truncate font-mono text-gray-700">{t.table}</span>
                            {isMatch ? (
                              <span className="shrink-0 rounded-full bg-green-50 px-1.5 py-0.5 text-[10px] font-medium text-green-700">matches</span>
                            ) : (
                              <span className="shrink-0 rounded-full bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-500" title="Column structure differs from this app's view — cannot be unioned.">structure differs</span>
                            )}
                          </label>
                        );
                      })}
                    </div>
                  </>
                )
              ) : null}
            </div>
          )}

          <div className="space-y-1">
            <label className="block text-[11px] font-medium text-gray-700">Label</label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. EU workspace"
              className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:border-[#2272B4] focus:outline-none focus:ring-1 focus:ring-[#2272B4]"
            />
            <p className="text-[10px] text-gray-500">Used to tag this source's rows so you can filter by it in the dashboard.</p>
          </div>

          {error && <div className="rounded bg-red-50 px-2 py-1 text-[11px] text-red-700">{error}</div>}

          <div className="flex items-center justify-end gap-2 pt-0.5">
            <button onClick={() => { setOpen(false); resetForm(); }} className="rounded-md px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-100">
              Cancel
            </button>
            <button
              onClick={addSource}
              disabled={!canAdd}
              className="rounded-md px-3 py-1.5 text-xs font-bold text-white transition-colors disabled:cursor-not-allowed"
              style={{ backgroundColor: canAdd ? "#2272B4" : "#A9C6DC" }}
            >
              {busy ? "Adding…" : "Add source"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
