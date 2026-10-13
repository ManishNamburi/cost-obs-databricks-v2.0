import {
  useCallback,
  useEffect,
  useRef,
  type HTMLAttributes,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";

interface FloatingMenuProps extends HTMLAttributes<HTMLDivElement> {
  anchorRef: RefObject<HTMLElement | null>;
  align?: "start" | "end";
  side?: "bottom" | "right";
  gap?: number;
  viewportPadding?: number;
}

export function FloatingMenu({
  anchorRef,
  align = "end",
  side = "bottom",
  gap = 4,
  viewportPadding = 8,
  className = "",
  children,
  onMouseDown,
  ...props
}: FloatingMenuProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  const positionPanel = useCallback((panel: HTMLDivElement | null) => {
    if (!panel) return;
    const anchor = anchorRef.current?.getBoundingClientRect();
    if (!anchor) {
      panel.style.visibility = "hidden";
      return;
    }

    const panelRect = panel.getBoundingClientRect();
    const preferredLeft = side === "right"
      ? anchor.right + gap
      : align === "start"
        ? anchor.left
        : anchor.right - panelRect.width;
    const left = Math.min(
      Math.max(viewportPadding, preferredLeft),
      Math.max(viewportPadding, window.innerWidth - panelRect.width - viewportPadding),
    );
    const below = anchor.bottom + gap;
    const above = anchor.top - panelRect.height - gap;
    const preferredTop = side === "right"
      ? anchor.top
      : (
        below + panelRect.height <= window.innerHeight - viewportPadding
        || above < viewportPadding
      ) ? below : above;
    const top = Math.min(
      Math.max(viewportPadding, preferredTop),
      Math.max(viewportPadding, window.innerHeight - panelRect.height - viewportPadding),
    );

    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
    panel.style.visibility = "visible";
  }, [align, anchorRef, gap, side, viewportPadding]);

  useEffect(() => {
    const reposition = () => positionPanel(panelRef.current);
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
  }, [positionPanel]);

  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      {...props}
      ref={(panel) => {
        panelRef.current = panel;
        positionPanel(panel);
      }}
      data-floating-menu
      className={`co-floating-menu fixed ${className}`}
      style={{ visibility: "hidden", ...props.style }}
      onMouseDown={(event) => {
        event.stopPropagation();
        onMouseDown?.(event);
      }}
    >
      {children}
    </div>,
    document.body,
  );
}
