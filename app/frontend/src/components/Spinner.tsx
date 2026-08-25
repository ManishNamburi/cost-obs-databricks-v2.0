interface SpinnerProps {
  size?: "xs" | "sm" | "md" | "lg";
  className?: string;
}

const SIZE_CLASS = {
  xs:  "h-3 w-3 border-[1.5px]",
  sm:  "h-4 w-4 border-2",
  md:  "h-8 w-8 border-[3px]",
  lg:  "h-12 w-12 border-4",
} as const;

export function Spinner({ size = "md", className = "" }: SpinnerProps) {
  // Ring color + style are set inline (not via `border-gray-200 border-t-[#FF3621]`
  // classes) so the visible orange arc never depends on Tailwind cascade order or
  // arbitrary-value generation — that class combo can resolve to a uniform gray
  // (invisible) ring in some builds, which reads as a static "empty circle".
  // Width still comes from SIZE_CLASS; borderTopColor is listed after borderColor
  // so it wins for the top edge.
  return (
    <div
      role="status"
      aria-label="Loading"
      style={{ borderStyle: "solid", borderColor: "#E5E7EB", borderTopColor: "#FF3621" }}
      className={`animate-spin rounded-full shrink-0 ${SIZE_CLASS[size]}${className ? ` ${className}` : ""}`}
    />
  );
}
