import type {
  BudgetDashboardBundle,
  BudgetConfiguration,
  BudgetPolicy,
  AlertConfiguration,
} from "@/types/billing";
import { formatCurrency } from "@/utils/formatters";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtThreshold(a: AlertConfiguration): string {
  const qty = a.quantity_threshold ?? "—";
  const type = a.quantity_type?.replace(/_/g, " ") ?? "";
  const period = a.time_period?.replace(/_/g, " ") ?? "";
  return `${qty} ${type} / ${period}`.trim();
}

function SpendBar({ spend, threshold }: { spend: number | null; threshold: string | null }) {
  if (spend === null || !threshold) return null;
  const limit = parseFloat(threshold);
  if (isNaN(limit) || limit <= 0) return null;
  const pct = Math.min((spend / limit) * 100, 100);
  const color = pct >= 90 ? "#EF4444" : pct >= 70 ? "#F59E0B" : "#22C55E";
  return (
    <div className="mt-2">
      <div className="flex justify-between text-xs text-gray-500 mb-1">
        <span>Est. MTD: {formatCurrency(spend)}</span>
        <span>Limit: {formatCurrency(limit)}</span>
      </div>
      <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
        <div
          className="h-2 rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

function AlertBadge({ alert }: { alert: AlertConfiguration }) {
  const trigger = alert.trigger_type ?? "";
  const isBreached = trigger === "CUMULATIVE_SPENDING_EXCEEDED";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium border ${
        isBreached
          ? "bg-red-50 text-red-700 border-red-200"
          : "bg-amber-50 text-amber-700 border-amber-200"
      }`}
    >
      {isBreached ? "Breach alert" : "Forecast alert"}: {fmtThreshold(alert)}
    </span>
  );
}

function BudgetCard({ cfg }: { cfg: BudgetConfiguration }) {
  const primaryAlert = cfg.alert_configurations[0] ?? null;
  const threshold = primaryAlert?.quantity_threshold ?? null;

  const filterWorkspaces =
    cfg.filter?.workspace_id?.values?.length
      ? cfg.filter.workspace_id.values.map(String)
      : null;

  const filterTags = cfg.filter?.tags ?? [];

  return (
    <div className="rounded-lg bg-white border p-4" style={{ borderColor: "#E5E5E5" }}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold text-gray-900 truncate">
            {cfg.display_name ?? cfg.budget_configuration_id ?? "Unnamed Budget"}
          </p>
          {filterWorkspaces && (
            <p className="mt-0.5 text-xs text-gray-500">
              Workspaces: {filterWorkspaces.join(", ")}
            </p>
          )}
          {filterTags.length > 0 && (
            <p className="mt-0.5 text-xs text-gray-500">
              Tags: {filterTags.map((t) => `${t.key}`).join(", ")}
            </p>
          )}
          {!filterWorkspaces && filterTags.length === 0 && (
            <p className="mt-0.5 text-xs text-gray-500">Scope: all workspaces</p>
          )}
        </div>
      </div>

      {cfg.alert_configurations.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {cfg.alert_configurations.map((a, i) => (
            <AlertBadge key={a.alert_configuration_id ?? i} alert={a} />
          ))}
        </div>
      )}

      {cfg.estimated_spend_mtd !== null && primaryAlert && (
        <SpendBar spend={cfg.estimated_spend_mtd} threshold={threshold} />
      )}

      {cfg.estimated_spend_mtd !== null && !primaryAlert && (
        <p className="mt-2 text-sm text-gray-700">
          MTD spend:{" "}
          <span className="font-semibold">{formatCurrency(cfg.estimated_spend_mtd)}</span>
        </p>
      )}
    </div>
  );
}

function PolicyCard({ policy }: { policy: BudgetPolicy }) {
  return (
    <div className="rounded-lg bg-white border p-4" style={{ borderColor: "#E5E5E5" }}>
      <p className="font-semibold text-gray-900 truncate">
        {policy.policy_name ?? policy.policy_id ?? "Unnamed Policy"}
      </p>

      {policy.binding_workspace_ids.length > 0 && (
        <p className="mt-1 text-xs text-gray-500">
          Bound workspaces: {policy.binding_workspace_ids.join(", ")}
        </p>
      )}
      {policy.binding_workspace_ids.length === 0 && (
        <p className="mt-1 text-xs text-gray-500">Bound workspaces: all</p>
      )}

      {policy.custom_tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {policy.custom_tags.map((t, i) => (
            <span
              key={i}
              className="rounded border bg-gray-50 px-2 py-0.5 text-xs text-gray-700 border-gray-200"
            >
              {t.key}: {t.value}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function NotConfiguredBanner({ message }: { message?: string }) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-center">
      <p className="text-sm font-medium text-amber-800">Account APIs not available</p>
      <p className="mt-1 text-xs text-amber-700">
        {message ??
          "Set DATABRICKS_ACCOUNT_ID in the app environment and ensure the service principal has account_admin role."}
      </p>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

interface BudgetViewProps {
  data: BudgetDashboardBundle | undefined;
  isLoading: boolean;
}

export function BudgetView({ data, isLoading }: BudgetViewProps) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-24 rounded-lg bg-gray-100 animate-pulse" />
        ))}
      </div>
    );
  }

  if (!data) {
    return <NotConfiguredBanner />;
  }

  if (!data.available) {
    return <NotConfiguredBanner message={data.error} />;
  }

  const hasConfigs = data.configurations.length > 0;
  const hasPolicies = data.policies.length > 0;

  return (
    <div className="space-y-8">
      {/* ── Account Budgets ─────────────────────────────────────── */}
      <section>
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="text-base font-semibold text-gray-900" style={{ color: "#1B3139" }}>
            Account Budgets
          </h2>
          <span className="text-xs text-gray-500">
            {data.total_configurations} budget{data.total_configurations !== 1 ? "s" : ""}
          </span>
        </div>

        {hasConfigs ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.configurations.map((cfg) => (
              <BudgetCard key={cfg.budget_configuration_id} cfg={cfg} />
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed p-6 text-center text-sm text-gray-500">
            No account budgets configured. Create budgets in the Databricks account console
            or via the account CLI.
          </div>
        )}
      </section>

      {/* ── Serverless Usage Policies ───────────────────────────── */}
      <section>
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="text-base font-semibold text-gray-900" style={{ color: "#1B3139" }}>
            Serverless Usage Policies
          </h2>
          <span className="text-xs text-gray-500">
            {data.total_policies} polic{data.total_policies !== 1 ? "ies" : "y"}
          </span>
        </div>
        <p className="mb-3 text-xs text-gray-500">
          Usage policies tag future serverless workloads — tags surface in{" "}
          <code className="rounded bg-gray-100 px-1 py-0.5 font-mono text-[11px]">
            system.billing.usage.custom_tags
          </code>
          . Policies are non-retroactive.
        </p>

        {hasPolicies ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.policies.map((p) => (
              <PolicyCard key={p.policy_id} policy={p} />
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed p-6 text-center text-sm text-gray-500">
            No serverless usage policies configured. Create policies via the Databricks account
            CLI (<code className="font-mono text-xs">databricks account budget-policy create</code>
            ).
          </div>
        )}
      </section>

      {data.errors && data.errors.length > 0 && (
        <p className="text-xs text-amber-600">
          Partial data — some API calls failed: {data.errors.join("; ")}
        </p>
      )}

      {data.as_of && (
        <p className="text-xs text-gray-500">
          Data as of {new Date(data.as_of).toLocaleString()}
        </p>
      )}
    </div>
  );
}
