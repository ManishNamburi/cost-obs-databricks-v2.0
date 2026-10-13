import {
  type ReactNode,
  type RefObject,
  useEffect,
  useId,
  useRef,
} from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { useDocumentScrollLock } from "@/utils/scrolling";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  closeLabel?: string;
  closeOnBackdrop?: boolean;
  initialFocusRef?: RefObject<HTMLElement | null>;
}

export function Dialog({
  open,
  onClose,
  title,
  subtitle,
  children,
  className = "max-w-2xl",
  bodyClassName = "p-6",
  closeLabel = "Close dialog",
  closeOnBackdrop = true,
  initialFocusRef,
}: DialogProps) {
  const titleId = useId();
  const subtitleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  const initialFocusRefRef = useRef(initialFocusRef);
  useDocumentScrollLock(open);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    initialFocusRefRef.current = initialFocusRef;
  }, [initialFocusRef]);

  useEffect(() => {
    if (!open) return;
    const returnFocusTo = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;

    (initialFocusRefRef.current?.current ?? closeRef.current ?? panelRef.current)?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;

      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE),
      ).filter((element) => !element.hidden && element.getAttribute("aria-hidden") !== "true");
      if (focusable.length === 0) {
        event.preventDefault();
        panelRef.current.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      returnFocusTo?.focus();
    };
  }, [open]);

  if (!open) return null;

  return createPortal(
    <div
      className="animate-backdrop fixed inset-0 z-[9999] overflow-y-auto bg-black/50"
      onMouseDown={(event) => {
        if (closeOnBackdrop && event.target === event.currentTarget) {
          event.preventDefault();
          onCloseRef.current();
        }
      }}
    >
      <div
        className="flex min-h-full items-center justify-center p-4"
        onMouseDown={(event) => {
          if (closeOnBackdrop && event.target === event.currentTarget) {
            event.preventDefault();
            onCloseRef.current();
          }
        }}
      >
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          aria-describedby={subtitle ? subtitleId : undefined}
          tabIndex={-1}
          className={`animate-dialog relative w-full overflow-hidden rounded-xl bg-white shadow-2xl focus:outline-none ${className}`}
          onMouseDown={(event) => event.stopPropagation()}
        >
          <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
            <div className="min-w-0">
              <h2 id={titleId} className="text-lg font-semibold text-gray-900">
                {title}
              </h2>
              {subtitle && (
                <div id={subtitleId} className="mt-0.5 text-sm text-gray-500">
                  {subtitle}
                </div>
              )}
            </div>
            <button
              ref={closeRef}
              type="button"
              onClick={() => onCloseRef.current()}
              aria-label={closeLabel}
              className="ml-4 shrink-0 rounded-lg p-2 text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 focus-visible:outline-none focus-visible:shadow-(--focus)"
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>
          <div className={bodyClassName}>{children}</div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
