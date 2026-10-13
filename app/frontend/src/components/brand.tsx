import type { ReactNode } from "react";
import { APP_VERSION, C, FONT_MONO, FONT_SANS } from "@/theme";
import { cn } from "@/lib/utils";

export function CostObsMark({ className, whiteOrbit = false }: { className?: string; whiteOrbit?: boolean }) {
  const orbit = whiteOrbit ? C.white : C.navy;
  return (
    <svg viewBox="0 0 48 48" fill="none" className={className} aria-hidden="true">
      <path d="M3 24 a21 8 0 0 1 42 0" stroke={orbit} strokeWidth="2.6" strokeLinecap="round" />
      <rect x="11" y="11" width="26" height="26" rx="7" fill={C.lava} />
      <polyline points="15,19 20.5,25 24.5,21.5 31,28.5" stroke={C.white} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <circle cx="31" cy="28.5" r="2.4" fill={C.white} />
      <path d="M3 24 a21 8 0 0 0 42 0" stroke={orbit} strokeWidth="2.6" strokeLinecap="round" />
    </svg>
  );
}

export function CostObsLockup({
  variant = "light",
  className,
}: {
  variant?: "light" | "white";
  className?: string;
}) {
  const light = variant === "light";
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <CostObsMark className="h-[30px] w-[30px]" whiteOrbit={!light} />
      <span
        className="text-[21px] font-bold leading-none tracking-tight"
        style={{ color: light ? C.ink : C.white, fontFamily: FONT_SANS }}
      >
        cost-obs
      </span>
    </span>
  );
}

export function VersionPill({ className }: { className?: string }) {
  return (
    <span className={cn("co-version-pill", className)} title="cost-obs release tag on the deployed repo">
      {APP_VERSION}
    </span>
  );
}

export function PageHero({
  icon,
  title,
  subtitle,
  action,
}: {
  icon: ReactNode;
  title: string;
  subtitle?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div className="flex items-start gap-3">
        <div
          className="flex h-11 w-11 shrink-0 items-center justify-center"
          style={{
            background: C.coralTint,
            border: `1px solid ${C.coralBrd}`,
            borderRadius: 10,
            color: C.lava,
          }}
        >
          <span className="[&>svg]:h-5 [&>svg]:w-5">{icon}</span>
        </div>
        <div>
          <h2 className="text-2xl font-bold leading-tight" style={{ color: C.ink, fontFamily: FONT_SANS }}>
            {title}
          </h2>
          {subtitle && (
            <div className="mt-0.5 flex flex-wrap items-center gap-2 text-sm" style={{ color: C.slate }}>
              {subtitle}
            </div>
          )}
        </div>
      </div>
      {action}
    </div>
  );
}

type ChipKind = "neutral" | "serverless" | "historical" | "filter" | "idle" | "workspace";

const CHIP: Record<ChipKind, { bg: string; fg: string; border?: string }> = {
  neutral: { bg: C.oatPage, fg: C.ink, border: C.hairline },
  serverless: { bg: C.greenTint, fg: C.greenInk },
  historical: { bg: C.amberTint, fg: C.amberInk },
  filter: { bg: C.coralTint, fg: C.lavaHover },
  idle: { bg: C.maroonTint, fg: C.maroon },
  workspace: { bg: C.oatMed, fg: C.slate },
};

export function TabInfoBanner({
  title,
  items,
  minimized,
  onToggle,
  footer,
}: {
  title: string;
  items: { label: string; text: ReactNode }[];
  minimized: boolean;
  onToggle: (next: boolean) => void;
  footer?: ReactNode;
}) {
  return (
    <div className="p-4" style={{ background: C.oatMed, borderRadius: 10 }}>
      <div className="flex">
        <div className="flex-shrink-0" style={{ color: C.lava }}>
          <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
          </svg>
        </div>
        <div className="ml-3 flex-1">
          <button className="flex w-full items-center justify-between" onClick={() => onToggle(!minimized)}>
            <h3 className="text-sm font-semibold" style={{ color: C.navy }}>{title}</h3>
            <svg className={`h-4 w-4 transition-transform ${minimized ? "" : "rotate-180"}`} style={{ color: C.slate }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {!minimized && (
            <>
              <div className="mt-2 text-sm" style={{ color: C.body }}>
                <ul className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                  {items.map((item) => (
                    <li key={item.label}>
                      <strong style={{ color: C.navy }}>{item.label}:</strong> {item.text}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="mt-3 flex items-center justify-between gap-3">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={minimized}
                    onChange={(e) => onToggle(e.target.checked)}
                    className="h-3.5 w-3.5 rounded border-orange-300 text-orange-600 focus:ring-orange-500"
                  />
                  <span className="text-xs text-orange-600">Minimize from now on</span>
                </label>
                {footer}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export function Chip({ kind = "neutral", children, className }: { kind?: ChipKind; children: ReactNode; className?: string }) {
  const t = CHIP[kind];
  return (
    <span
      className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium", className)}
      style={{ background: t.bg, color: t.fg, border: t.border ? `1px solid ${t.border}` : undefined }}
    >
      {children}
    </span>
  );
}

export function changeTone(pct: number): { bg: string; fg: string; label: string } {
  if (Math.abs(pct) < 0.5) return { bg: C.oatMed, fg: C.slate, label: "±0.0%" };
  if (pct > 0) return { bg: C.coralTint, fg: C.lavaHover, label: `+${pct.toFixed(1)}%` };
  return { bg: C.greenTint, fg: C.greenInk, label: `${pct.toFixed(1)}%` };
}

export function ChartTooltipFrame({
  title,
  rows,
}: {
  title: string;
  rows: { label: string; value: string; color?: string; delta?: number }[];
}) {
  return (
    <div
      style={{
        background: C.inkDeep,
        borderRadius: 8,
        padding: "8px 10px",
        minWidth: 160,
        boxShadow: "var(--sh-menu)",
      }}
    >
      <div style={{ color: C.white, fontSize: 12.5, fontWeight: 600, marginBottom: 6 }}>{title}</div>
      {rows.map((r) => (
        <div key={r.label} className="flex items-center justify-between gap-3" style={{ fontFamily: FONT_MONO, fontSize: 12, color: C.white }}>
          <span className="flex items-center gap-1.5">
            {r.color && <span className="inline-block h-2 w-2 rounded-full" style={{ background: r.color }} />}
            {r.label}
          </span>
          <span>
            {r.value}
            {r.delta != null && (
              <span style={{ color: r.delta > 0 ? C.coral : r.delta < 0 ? C.deltaDown : C.muted, marginLeft: 6 }}>
                {r.delta > 0 ? "+" : ""}
                {r.delta.toFixed(1)}%
              </span>
            )}
          </span>
        </div>
      ))}
    </div>
  );
}
