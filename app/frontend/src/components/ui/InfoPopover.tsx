import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";

interface InfoPopoverProps {
  text?: string;
  content?: ReactNode;
  children?: ReactNode;
  label?: string;
  className?: string;
  triggerClassName?: string;
  panelClassName?: string;
  placement?: "top" | "bottom";
  stopClick?: boolean;
  size?: "default" | "compact";
  interactive?: boolean;
}

export function InfoPopover({
  text,
  content,
  children,
  label = "More information",
  className = "ml-1.5",
  triggerClassName,
  panelClassName = "w-72",
  placement = "top",
  stopClick = false,
  size = "default",
  interactive = false,
}: InfoPopoverProps) {
  const id = useId();
  const rootRef = useRef<HTMLSpanElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLSpanElement>(null);
  const closeTimerRef = useRef<number | null>(null);
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });

  const cancelScheduledClose = () => {
    if (closeTimerRef.current !== null) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  };

  const show = () => {
    cancelScheduledClose();
    const rect = triggerRef.current?.getBoundingClientRect();
    if (rect) {
      setPosition({
        top: placement === "bottom" ? rect.bottom + 8 : Math.max(8, rect.top - 8),
        left: rect.left + rect.width / 2,
      });
    }
    setOpen(true);
  };

  const scheduleClose = () => {
    cancelScheduledClose();
    closeTimerRef.current = window.setTimeout(() => {
      if (!pinned && document.activeElement !== triggerRef.current) setOpen(false);
      closeTimerRef.current = null;
    }, 180);
  };

  const positionPanel = (panel: HTMLSpanElement | null) => {
    if (!panel) return;
    const trigger = triggerRef.current?.getBoundingClientRect();
    if (!trigger) return;
    const panelRect = panel.getBoundingClientRect();
    const halfWidth = panelRect.width / 2;
    const left = Math.min(
      Math.max(8 + halfWidth, trigger.left + trigger.width / 2),
      Math.max(8 + halfWidth, window.innerWidth - 8 - halfWidth),
    );
    const fitsAbove = trigger.top - 8 - panelRect.height >= 8;
    const fitsBelow = trigger.bottom + 8 + panelRect.height <= window.innerHeight - 8;
    const renderBelow = placement === "bottom"
      ? fitsBelow || !fitsAbove
      : !fitsAbove && fitsBelow;
    panel.style.top = `${renderBelow ? trigger.bottom + 8 : trigger.top - 8}px`;
    panel.style.left = `${left}px`;
    panel.style.transform = renderBelow ? "translateX(-50%)" : "translate(-50%, -100%)";
  };

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        setPinned(false);
        triggerRef.current?.focus();
      }
    };
    const closeOutside = (event: PointerEvent) => {
      if (
        !rootRef.current?.contains(event.target as Node)
        && !panelRef.current?.contains(event.target as Node)
      ) {
        setOpen(false);
        setPinned(false);
      }
    };
    document.addEventListener("keydown", closeOnEscape);
    document.addEventListener("pointerdown", closeOutside);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      document.removeEventListener("pointerdown", closeOutside);
    };
  }, [open]);

  useEffect(() => () => {
    if (closeTimerRef.current !== null) window.clearTimeout(closeTimerRef.current);
  }, []);

  return (
    <span
      ref={rootRef}
      className={`inline-flex ${className}`}
      onMouseEnter={show}
      onMouseLeave={(event) => {
        if (
          interactive
          && event.relatedTarget instanceof Node
          && panelRef.current?.contains(event.relatedTarget)
        ) return;
        if (interactive) {
          scheduleClose();
        } else if (!pinned && document.activeElement !== triggerRef.current) {
          setOpen(false);
        }
      }}
    >
      <button
        ref={triggerRef}
        type="button"
        aria-label={label}
        aria-describedby={open && !interactive ? id : undefined}
        aria-controls={open && interactive ? id : undefined}
        aria-expanded={open}
        onFocus={show}
        onBlur={() => {
          window.setTimeout(() => {
            if (
              !rootRef.current?.contains(document.activeElement)
              && !panelRef.current?.contains(document.activeElement)
            ) {
              setOpen(false);
              setPinned(false);
            }
          }, 0);
        }}
        onClick={(event) => {
          if (stopClick) event.stopPropagation();
          if (pinned) {
            setOpen(false);
            setPinned(false);
          } else {
            show();
            setPinned(true);
          }
        }}
        className={triggerClassName ?? "inline-flex h-4 w-4 shrink-0 items-center justify-center rounded text-[var(--slate)] transition-colors hover:text-[var(--ink)] focus-visible:outline-none focus-visible:shadow-(--focus)"}
      >
        {children ?? <Info size={14} strokeWidth={1.8} aria-hidden="true" />}
      </button>
      {open && createPortal(
        <span
          ref={(panel) => {
            panelRef.current = panel;
            positionPanel(panel);
          }}
          id={id}
          role={interactive ? "dialog" : "tooltip"}
          aria-label={interactive ? `${label} details` : undefined}
          onMouseEnter={() => {
            if (interactive) {
              cancelScheduledClose();
              setOpen(true);
            }
          }}
          onPointerDown={() => {
            if (interactive) {
              cancelScheduledClose();
              setPinned(true);
            }
          }}
          onMouseLeave={() => {
            if (interactive && !pinned && !rootRef.current?.contains(document.activeElement)) scheduleClose();
          }}
          className={`${interactive ? "pointer-events-auto" : "pointer-events-none"} fixed z-[10000] max-w-[calc(100vw-1rem)] whitespace-normal rounded-lg border border-white/10 bg-[var(--ink-deep)] font-normal normal-case text-white shadow-[0_8px_28px_rgba(11,32,38,.24)] ${
            size === "compact"
              ? "px-2 py-1.5 text-[11px] leading-snug"
              : "px-3 py-2 text-xs leading-relaxed"
          } ${panelClassName}`}
          style={{ top: position.top, left: position.left }}
        >
          {content ?? text}
        </span>,
        document.body,
      )}
    </span>
  );
}
