import { CostObsLockup, VersionPill } from "@/components/brand";
import { C, FONT_MONO } from "@/theme";

const TABLES = [
  ["system.billing.usage", "https://docs.databricks.com/en/administration-guide/system-tables/billing.html"],
  ["system.billing.list_prices", "https://docs.databricks.com/en/administration-guide/system-tables/billing.html"],
  ["system.query.history", "https://docs.databricks.com/en/administration-guide/system-tables/query-history.html"],
  ["system.compute.clusters", "https://docs.databricks.com/en/administration-guide/system-tables/compute.html"],
  ["system.lakeflow.jobs", "https://docs.databricks.com/en/administration-guide/system-tables/lakeflow.html"],
  ["system.lakeflow.job_runs", "https://docs.databricks.com/en/administration-guide/system-tables/lakeflow.html"],
  ["system.access.table_lineage", "https://docs.databricks.com/en/administration-guide/system-tables/access.html"],
] as const;

const RESOURCES = [
  ["cost-obs on GitHub", "https://github.com/smathews13/cost-obs-databricks-v2.0"],
  ["System Tables Documentation", "https://docs.databricks.com/en/administration-guide/system-tables/index.html"],
  ["Usage & Billing Guide", "https://docs.databricks.com/en/administration-guide/account-settings/usage.html"],
  ["Databricks Pricing", "https://www.databricks.com/product/pricing"],
  ["SQL Alerts Documentation", "https://docs.databricks.com/en/sql/user/alerts.html"],
  ["Databricks Apps", "https://www.databricks.com/product/databricks-apps"],
  ["Databricks SDK (Python)", "https://github.com/databricks/databricks-sdk-py"],
] as const;

export function Footer() {
  return (
    <footer className="mt-8 py-8" style={{ background: C.navy, color: C.white }}>
      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
        <div className="mb-6 flex flex-wrap items-center justify-center gap-3">
          <CostObsLockup variant="white" />
          <VersionPill />
        </div>
        <div className="flex justify-center gap-16 text-left">
          <div>
            <h3 className="mb-2 text-[11px] font-bold uppercase tracking-widest" style={{ color: "rgba(255,255,255,0.6)" }}>
              Databricks System Tables
            </h3>
            <ul className="space-y-1 text-xs">
              {TABLES.map(([name, href]) => (
                <li key={name}>
                  <a href={href} target="_blank" rel="noopener noreferrer" className="hover:underline" style={{ color: C.white, fontFamily: FONT_MONO }}>
                    {name}
                  </a>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="mb-2 text-[11px] font-bold uppercase tracking-widest" style={{ color: "rgba(255,255,255,0.6)" }}>
              Resources & Documentation
            </h3>
            <ul className="space-y-1 text-xs">
              {RESOURCES.map(([name, href]) => (
                <li key={name}>
                  <a href={href} target="_blank" rel="noopener noreferrer" className="hover:underline" style={{ color: C.white }}>
                    {name}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>
        <p className="mt-8 text-center text-xs" style={{ color: "rgba(255,255,255,0.5)" }}>
          Built with Databricks Apps • Powered by System Tables
        </p>
      </div>
    </footer>
  );
}
