import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ReadinessChecks, normalizeReadinessResult } from "./ReadinessChecks";
import type { ReadinessResult } from "./ReadinessChecks";
import { READINESS_QUERY_KEY } from "@/hooks/useFeatureAvailability";
import { Group, Row, Select, SecondaryButton, LinkButton, MonoChip, Callout, useToast, T, MONO } from "./dubois";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

interface UserPermissions {
  admins: string[];
  consumers: string[];
  table_location?: string | null;
  current_user?: string | null;
}

interface AuthStatus {
  user_token_active: boolean;
  identity: "user_oauth" | "service_principal";
  locked_to_sp: boolean;
  has_sql_scope: boolean | null;
  auth_mode: "unknown" | "user" | "sp";
  token_present: boolean;
  token_scopes: string[];
  user_email: string | null;
  override_mode: "sp" | "auto" | null;
  sp_client_id: string;
  sp_display_name: string;
  catalog: string;
  schema: string;
}

export function SettingsPermissions() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [readinessOpen, setReadinessOpen] = useState(false);
  // Open by default: the exact GRANT SQL is what an admin needs on hand when the app
  // runs as a service principal (the common case), matching the pre-revamp behavior.
  const [grantsOpen, setGrantsOpen] = useState(true);

  const { data: permissions, isLoading } = useQuery<UserPermissions>({
    queryKey: ["user-permissions"],
    queryFn: async () => {
      const res = await fetch("/api/settings/user-permissions");
      if (!res.ok) throw new Error("Failed to fetch");
      return res.json();
    },
  });

  const { data: authStatus } = useQuery<AuthStatus>({
    queryKey: ["settings-auth-status"],
    queryFn: () => fetch("/api/settings/auth-status").then(r => r.json()),
    staleTime: 10 * 1000,
    refetchInterval: 30 * 1000,
  });

  // Shared readiness query — same key as useFeatureAvailability so all components read one cache entry.
  const {
    data: readiness,
    isLoading: readinessLoading,
    error: readinessQueryError,
  } = useQuery<ReadinessResult | null>({
    queryKey: READINESS_QUERY_KEY,
    queryFn: () =>
      fetch("/api/setup/readiness")
        .then(r => r.ok ? r.json() : null)
        .then(normalizeReadinessResult)
        .catch(() => null),
    staleTime: 5 * 60 * 1000,
    retry: false,
    refetchOnWindowFocus: false,
  });

  const handleReadinessRecheck = () => {
    queryClient.refetchQueries({ queryKey: READINESS_QUERY_KEY });
  };

  const saveMutation = useMutation({
    mutationFn: async (data: UserPermissions) => {
      const res = await fetch("/api/settings/user-permissions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? "Failed to save");
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user-permissions"] });
      queryClient.refetchQueries({ queryKey: ["user"] });
      toast("Users updated");
    },
    onError: (e) => toast(e instanceof Error ? e.message : "Save failed"),
  });

  const [newUserEmail, setNewUserEmail] = useState("");
  const [newUserRole, setNewUserRole] = useState<"admin" | "consumer">("consumer");

  const allUsers = [
    ...(permissions?.admins ?? []).map(e => ({ email: e, role: "admin" as const })),
    ...(permissions?.consumers ?? []).map(e => ({ email: e, role: "consumer" as const })),
  ].sort((a, b) => a.email.localeCompare(b.email));

  const addUser = () => {
    const email = newUserEmail.trim();
    if (!email) return;
    if (!EMAIL_RE.test(email)) { toast("Enter a valid email address"); return; }
    if (allUsers.some((u) => u.email.toLowerCase() === email.toLowerCase())) { toast("That user is already listed"); return; }
    const admins = [
      ...(permissions?.admins ?? []).filter(e => e !== email),
      ...(newUserRole === "admin" ? [email] : []),
    ];
    const consumers = [
      ...(permissions?.consumers ?? []).filter(e => e !== email),
      ...(newUserRole === "consumer" ? [email] : []),
    ];
    saveMutation.mutate({ admins, consumers });
    setNewUserEmail("");
  };

  const removeUser = (email: string) => {
    saveMutation.mutate({
      admins: (permissions?.admins ?? []).filter(e => e !== email),
      consumers: (permissions?.consumers ?? []).filter(e => e !== email),
    });
  };

  const changeRole = (email: string, newRole: "admin" | "consumer") => {
    const admins = newRole === "admin"
      ? [...(permissions?.admins ?? []).filter(e => e !== email), email]
      : (permissions?.admins ?? []).filter(e => e !== email);
    const consumers = newRole === "consumer"
      ? [...(permissions?.consumers ?? []).filter(e => e !== email), email]
      : (permissions?.consumers ?? []).filter(e => e !== email);
    saveMutation.mutate({ admins, consumers });
  };

  const isSP = authStatus?.identity === "service_principal";
  const noToken = !authStatus?.token_present;

  if (isLoading) {
    return <div style={{ padding: "32px 0", textAlign: "center", fontSize: 13, color: T.textSecondary }}>Loading permissions…</div>;
  }

  const overall = readiness?.overall;
  const ready = overall === "ready";
  const bannerTone = ready ? { fg: T.successFg, bg: T.successBg, border: T.successBorder }
    : overall === "core_ready" ? { fg: T.warningFg, bg: T.warningBg, border: T.warningBorder }
    : overall ? { fg: T.dangerFg, bg: T.dangerBg, border: T.dangerBorder }
    : { fg: T.textSecondary, bg: T.navBg, border: T.borderGroup };
  const bannerLabel = ready ? "System tables access verified — billing.usage · query.history · schema grants"
    : overall === "core_ready" ? "Core system tables verified — some optional grants missing"
    : overall === "needs_action" ? "System-table grants pending — some metrics show unavailable"
    : overall === "not_ready" ? "System tables not accessible — run the grants below"
    : readinessLoading ? "Checking system-table access…" : "System-table access status unknown";

  const spName = authStatus?.sp_display_name || authStatus?.sp_client_id || "<service-principal>";
  const cat = authStatus?.catalog || "<your_catalog>";
  const sch = authStatus?.schema || "<your_schema>";
  const userEmail = authStatus?.user_email;
  const appGrants =
`-- System tables (billing + query history + compute + lakeflow)
-- WHO: Must be run by a metastore admin or account admin.
-- WHEN: Required once when the app is first created (SP is tied to the app, not the code).
GRANT USE CATALOG ON CATALOG system TO \`${spName}\`;
GRANT USE SCHEMA ON SCHEMA system.billing TO \`${spName}\`;
GRANT SELECT ON TABLE system.billing.usage TO \`${spName}\`;
GRANT SELECT ON TABLE system.billing.list_prices TO \`${spName}\`;
GRANT SELECT ON TABLE system.billing.account_prices TO \`${spName}\`;
GRANT USE SCHEMA ON SCHEMA system.query TO \`${spName}\`;
GRANT SELECT ON TABLE system.query.history TO \`${spName}\`;
GRANT USE SCHEMA ON SCHEMA system.compute TO \`${spName}\`;
GRANT SELECT ON TABLE system.compute.clusters TO \`${spName}\`;
GRANT USE SCHEMA ON SCHEMA system.lakeflow TO \`${spName}\`;
GRANT SELECT ON TABLE system.lakeflow.pipelines TO \`${spName}\`;
GRANT USE SCHEMA ON SCHEMA system.serving TO \`${spName}\`;
GRANT SELECT ON TABLE system.serving.served_entities TO \`${spName}\`;

-- App schema (materialized views)
GRANT USE CATALOG ON CATALOG \`${cat}\` TO \`${spName}\`;
GRANT USE SCHEMA ON SCHEMA \`${cat}\`.\`${sch}\` TO \`${spName}\`;
GRANT CREATE TABLE ON SCHEMA \`${cat}\`.\`${sch}\` TO \`${spName}\`;
GRANT SELECT ON SCHEMA \`${cat}\`.\`${sch}\` TO \`${spName}\`;`;

  const preStyle: React.CSSProperties = { backgroundColor: "#11171C", color: "#E8ECF0", borderRadius: 6, padding: 10, fontFamily: MONO, fontSize: 11.5, overflowX: "auto", whiteSpace: "pre", margin: 0 };

  return (
    <div>
      {/* ── Readiness banner ── */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ border: `1px solid ${bannerTone.border}`, backgroundColor: bannerTone.bg, borderRadius: 8, padding: "10px 14px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
            <span style={{ width: 8, height: 8, borderRadius: 999, backgroundColor: bannerTone.fg, flexShrink: 0 }} />
            <span style={{ fontSize: 13, color: bannerTone.fg, fontWeight: 500 }}>{bannerLabel}</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}>
            <LinkButton onClick={handleReadinessRecheck}>Re-check</LinkButton>
            <LinkButton onClick={() => setReadinessOpen(o => !o)}>{readinessOpen ? "Hide checks" : "View checks"}</LinkButton>
          </div>
        </div>
        {readinessOpen && (
          <div style={{ border: `1px solid ${T.borderGroup}`, borderTop: "none", borderRadius: "0 0 8px 8px", padding: "12px 14px" }}>
            <ReadinessChecks
              result={readiness ?? null}
              loading={readinessLoading}
              fetchError={readinessQueryError ? String(readinessQueryError) : null}
              onRecheck={handleReadinessRecheck}
            />
          </div>
        )}
      </div>

      {/* ── Users ── */}
      <div style={{ fontSize: 13, fontWeight: 600, color: T.text, marginBottom: 4, display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <span>Users</span>
        <span style={{ fontSize: 12, fontWeight: 400, color: T.textSecondary }}>Anyone not listed is a Consumer (dashboards only)</span>
      </div>
      <div style={{ border: `1px solid ${T.borderGroup}`, borderRadius: 8, overflow: "hidden" }}>
        {allUsers.length === 0 ? (
          <div style={{ padding: "12px 16px", fontSize: 12, color: T.textSecondary, fontStyle: "italic" }}>
            {permissions?.current_user ? `${permissions.current_user} (you) is the implicit default admin. ` : ""}
            No users explicitly configured — everyone is a Consumer. Add users below to elevate access.
          </div>
        ) : (
          allUsers.map(({ email, role }, i) => (
            <div key={email} className="flex items-center justify-between gap-4" style={{ padding: "10px 16px", borderTop: i === 0 ? "none" : `1px solid ${T.borderRow}` }}>
              <span style={{ fontSize: 13, color: T.text, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>{email}</span>
              <div className="flex items-center gap-3 shrink-0">
                <Select value={role} onChange={(v) => changeRole(email, v as "admin" | "consumer")}
                  options={[{ value: "admin", label: "Admin" }, { value: "consumer", label: "Consumer" }]} disabled={saveMutation.isPending} />
                <LinkButton onClick={() => removeUser(email)}>Remove</LinkButton>
              </div>
            </div>
          ))
        )}
        {/* Add-user row */}
        <div className="flex items-center gap-2" style={{ padding: "10px 16px", borderTop: `1px solid ${T.borderRow}`, backgroundColor: T.navBg }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <input
              type="email" placeholder="user@example.com" value={newUserEmail}
              onChange={e => setNewUserEmail(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") addUser(); }}
              style={{ width: "100%", height: 32, borderRadius: 4, border: `1px solid ${T.borderControl}`, padding: "0 10px", fontSize: 13, color: T.text }}
            />
          </div>
          <Select value={newUserRole} onChange={(v) => setNewUserRole(v as "admin" | "consumer")}
            options={[{ value: "consumer", label: "Consumer" }, { value: "admin", label: "Admin" }]} />
          <SecondaryButton onClick={addUser} disabled={!newUserEmail.trim() || saveMutation.isPending}>
            {saveMutation.isPending ? "Saving…" : "Add user"}
          </SecondaryButton>
        </div>
      </div>
      {permissions?.table_location && (
        <p style={{ fontSize: 11, color: T.textSecondary, margin: "6px 2px 20px" }}>
          Roles are stored in <MonoChip>{permissions.table_location}</MonoChip> and persist across deploys.
        </p>
      )}

      {/* ── Query authentication ── */}
      <div style={{ marginTop: 20 }}>
        <Group label="Query authentication">
          <Row first label="Mode" helper="How the app authenticates to the SQL warehouse."
            control={<span style={{ display: "inline-flex", alignItems: "center", gap: 6, borderRadius: 999, backgroundColor: T.successBg, border: `1px solid ${T.successBorder}`, color: T.successFg, padding: "2px 10px", fontSize: 12, fontWeight: 600 }}><span style={{ width: 6, height: 6, borderRadius: 999, backgroundColor: T.successFg }} />Service principal</span>} />
          <Row label="Running as" helper="The service principal this app queries as."
            control={<MonoChip>{authStatus?.sp_display_name || authStatus?.sp_client_id || "Service principal"}</MonoChip>} />
        </Group>

        {(isSP || noToken) && authStatus && (
          <>
            {overall && overall !== "ready" && (
              <div style={{ marginBottom: 12 }}>
                <Callout tone="warning">
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>System-table grants pending</div>
                  <div style={{ marginBottom: 8 }}>Each new app deploy gets a fresh service principal, so grants don't carry over. Until they run, affected metrics show <em>unavailable</em> (never $0.00). Run this as a metastore admin, then re-check.</div>
                  <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 6 }}>
                    <LinkButton onClick={() => { navigator.clipboard?.writeText(appGrants); toast("GRANT SQL copied"); }}>Copy SQL</LinkButton>
                  </div>
                  <pre style={preStyle}>{appGrants}</pre>
                </Callout>
              </div>
            )}
            <div style={{ border: `1px solid ${T.borderGroup}`, borderRadius: 8, overflow: "hidden" }}>
              <button type="button" onClick={() => setGrantsOpen(o => !o)}
                style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 14px", background: "none", border: "none", cursor: "pointer", fontSize: 13, fontWeight: 500, color: T.text }}>
                App runtime grants — exact SQL (run as metastore admin)
                <span style={{ color: T.textSecondary }}>{grantsOpen ? "▲" : "▼"}</span>
              </button>
              {grantsOpen && (
                <div style={{ borderTop: `1px solid ${T.borderRow}`, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 8 }}>
                  <div style={{ fontSize: 12, color: T.textSecondary }}>Target SP: <MonoChip>{spName}</MonoChip> · Warehouse <strong>CAN_USE</strong> can't be granted via SQL — set it in SQL Warehouses → Permissions (the app also attempts this on startup).</div>
                  <div style={{ display: "flex", justifyContent: "flex-end" }}>
                    <LinkButton onClick={() => { navigator.clipboard?.writeText(appGrants); toast("GRANT SQL copied"); }}>Copy SQL</LinkButton>
                  </div>
                  <pre style={preStyle}>{appGrants}</pre>
                  {userEmail && userEmail !== spName && (
                    <>
                      <div style={{ fontSize: 12, color: T.textSecondary, marginTop: 4 }}>Optional — user read access for {userEmail}:</div>
                      <pre style={preStyle}>{`GRANT SELECT ON SCHEMA \`${cat}\`.\`${sch}\` TO \`${userEmail}\`;`}</pre>
                    </>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
