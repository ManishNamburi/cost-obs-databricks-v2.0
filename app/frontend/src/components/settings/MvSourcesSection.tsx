import { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

interface MvSource {
  label: string;
  catalog: string;
  schema: string;
}

interface PreviewResult {
  matched: number;
  total: number;
  tables: { table: string; status: "match" | "mismatch" | "absent" }[];
}

// Settings → Config: register additional materialized-view source locations
// (typically Delta-shared in from another workspace) whose tables share the app's
// MV structure. They are unioned into every MV read (additive — local data always
// included) and tagged with the source's label for later filtering.
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
    if (!catalog) return;
    fetch(`/api/setup/list-schemas?catalog=${encodeURIComponent(catalog)}`)
      .then((r) => r.json()).then((r) => setSchemas(r.schemas ?? [])).catch(() => setSchemas([]));
  }, [catalog]);

  // Probe structure match whenever a full location is chosen.
  useEffect(() => {
    setPreview(null);
    if (!catalog || !schema) return;
    setPreviewing(true);
    fetch(`/api/settings/mv-sources/preview?catalog=${encodeURIComponent(catalog)}&schema=${encodeURIComponent(schema)}`)
      .then((r) => r.json())
      .then((r) => setPreview(r))
      .catch(() => setPreview(null))
      .finally(() => setPreviewing(false));
  }, [catalog, schema]);

  const canAdd = Boolean(label.trim() && catalog && schema && preview && preview.matched > 0 && !busy);

  const resetForm = () => {
    setCatalog(""); setSchema(""); setLabel(""); setPreview(null); setError(null);
  };

  const addSource = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/settings/mv-sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: label.trim(), catalog, schema }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
      await queryClient.invalidateQueries({ queryKey: ["mv-sources"] });
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
      await queryClient.invalidateQueries({ queryKey: ["mv-sources"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const selectClass =
    "w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm text-gray-900 focus:border-[#FF3621] focus:outline-none focus:ring-1 focus:ring-[#FF3621] disabled:bg-gray-100 disabled:text-gray-500";

  return (
    <div className="mb-3 rounded-lg border border-gray-200 bg-white p-3">
      <div className="mb-1 flex items-center justify-between">
        <h4 className="text-sm font-semibold text-gray-900">Additional data (shared views)</h4>
        {!open && (
          <button onClick={() => setOpen(true)} className="text-xs font-medium text-[#FF3621] hover:underline">
            + Add source
          </button>
        )}
      </div>
      <p className="mb-2 text-xs text-gray-500">
        Include summary views shared in from another workspace (Delta Sharing). They must match this
        app's view structure and are added on top of this workspace's data{data?.local_label ? <> (<span className="font-mono">{data.local_label}</span>)</> : null}, never replacing it.
      </p>

      {isLoading ? (
        <div className="text-xs text-gray-500">Loading…</div>
      ) : sources.length === 0 && !open ? (
        <div className="text-xs text-gray-500">No additional sources. Only this workspace's data is shown.</div>
      ) : (
        <div className="space-y-1.5">
          {sources.map((s) => (
            <div key={s.label} className="flex items-center gap-2 rounded-md border border-gray-100 bg-gray-50 px-2.5 py-1.5">
              <span className="rounded-full border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">{s.label}</span>
              <span className="min-w-0 flex-1 truncate font-mono text-xs text-gray-600">{s.catalog}.{s.schema}</span>
              <button onClick={() => removeSource(s.label)} disabled={busy} className="shrink-0 text-xs font-medium text-gray-500 hover:text-red-600 disabled:opacity-50">
                Remove
              </button>
            </div>
          ))}
        </div>
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
            <div className="text-[11px]">
              {previewing ? (
                <span className="text-gray-500">Checking view structure…</span>
              ) : preview ? (
                preview.matched > 0 ? (
                  <span className="text-green-700">{preview.matched} of {preview.total} views match and will be included.</span>
                ) : (
                  <span className="text-red-600">No matching views found at this location — check that the shared schema holds this app's summary views.</span>
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
              className="w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:border-[#FF3621] focus:outline-none focus:ring-1 focus:ring-[#FF3621]"
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
              style={{ backgroundColor: canAdd ? "#FF3621" : "#FFA390" }}
            >
              {busy ? "Adding…" : "Add source"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
