interface SpinnerProps {
  size?: "xs" | "sm" | "md" | "lg";
  className?: string;
}

interface LoadingPanelsProps {
  sections: string[];
}

const SIZE_CLASS = {
  xs:  "h-3 w-3 border-[1.5px]",
  sm:  "h-4 w-4 border-2",
  md:  "h-8 w-8 border-[3px]",
  lg:  "h-12 w-12 border-4",
} as const;

export function Spinner({ size = "md", className = "" }: SpinnerProps) {
  return (
    <div
      role="status"
      aria-label="Loading"
      style={{ borderStyle: "solid", borderColor: "var(--hairline)", borderTopColor: "var(--lava)", animationDuration: "900ms" }}
      className={`co-arc-spin rounded-full shrink-0 ${SIZE_CLASS[size]}${className ? ` ${className}` : ""}`}
    />
  );
}

export function LoadingPanels({ sections }: LoadingPanelsProps) {
  return (
    <div className="grid gap-5 md:grid-cols-2">
      {sections.map((section) => (
        <div key={section} className="co-card bg-white p-5">
          <h3 className="text-base font-semibold text-gray-900">{section}</h3>
          <div className="flex h-36 flex-col items-center justify-center gap-3">
            <Spinner size="md" />
            <span className="text-sm text-gray-500">Loading…</span>
          </div>
        </div>
      ))}
    </div>
  );
}
