import { useEffect } from "react";

const SCROLL_ACTIVE_CLASS = "is-scroll-active";
const SCROLLBAR_EDGE_CLASS = "is-scrollbar-edge-hover";
const SCROLL_ACTIVITY_MS = 700;
const SCROLLBAR_EDGE_PX = 18;

let scrollLockCount = 0;
let savedBodyOverflow = "";
let savedBodyPaddingRight = "";
let appliedBodyPaddingRight = false;

function supportsStableScrollbarGutter(): boolean {
  return typeof CSS !== "undefined"
    && typeof CSS.supports === "function"
    && CSS.supports("scrollbar-gutter: stable");
}

/**
 * Lock page scrolling without moving the app chrome.
 *
 * Locks are reference counted so a nested dialog cannot restore scrolling while
 * its parent is still open. Browsers without stable scrollbar gutters receive
 * measured body padding for the missing classic scrollbar.
 */
export function lockDocumentScroll(): () => void {
  let released = false;
  if (scrollLockCount === 0) {
    savedBodyOverflow = document.body.style.overflow;
    savedBodyPaddingRight = document.body.style.paddingRight;
    appliedBodyPaddingRight = false;

    const scrollbarWidth = Math.max(
      0,
      window.innerWidth - document.documentElement.clientWidth,
    );
    if (!supportsStableScrollbarGutter() && scrollbarWidth > 0) {
      const currentPadding = Number.parseFloat(
        window.getComputedStyle(document.body).paddingRight,
      ) || 0;
      document.body.style.paddingRight = `${currentPadding + scrollbarWidth}px`;
      appliedBodyPaddingRight = true;
    }

    document.body.style.overflow = "hidden";
    document.body.dataset.scrollLocked = "true";
  }

  scrollLockCount += 1;
  document.body.dataset.scrollLockCount = String(scrollLockCount);

  return () => {
    if (released) return;
    released = true;
    scrollLockCount = Math.max(0, scrollLockCount - 1);

    if (scrollLockCount > 0) {
      document.body.dataset.scrollLockCount = String(scrollLockCount);
      return;
    }

    document.body.style.overflow = savedBodyOverflow;
    if (appliedBodyPaddingRight) {
      document.body.style.paddingRight = savedBodyPaddingRight;
    }
    delete document.body.dataset.scrollLocked;
    delete document.body.dataset.scrollLockCount;
    appliedBodyPaddingRight = false;
  };
}

export function useDocumentScrollLock(active: boolean): void {
  useEffect(() => {
    if (!active) return;
    return lockDocumentScroll();
  }, [active]);
}

function scrollElementFromTarget(target: EventTarget | null): HTMLElement | null {
  if (target instanceof Document) {
    return document.scrollingElement instanceof HTMLElement
      ? document.scrollingElement
      : document.documentElement;
  }
  return target instanceof HTMLElement ? target : null;
}

function verticalScrollerNearEdge(
  target: EventTarget | null,
  clientX: number,
): HTMLElement | null {
  let element = target instanceof HTMLElement ? target : null;
  while (element) {
    const rect = element.getBoundingClientRect();
    const nearRightEdge = clientX >= rect.right - SCROLLBAR_EDGE_PX
      && clientX <= rect.right + 1;
    if (nearRightEdge && element.scrollHeight > element.clientHeight) {
      return element;
    }
    element = element.parentElement;
  }

  const root = document.documentElement;
  return root.scrollHeight > root.clientHeight
    && clientX >= root.clientWidth - SCROLLBAR_EDGE_PX
    ? root
    : null;
}

/**
 * Reveal only the scrollbar being used, then return it to the quiet resting
 * state. Scroll events are captured so keyboard, touch, wheel and programmatic
 * scrolling all receive the same feedback.
 */
export function installTransientScrollbarBehavior(
  root: Document = document,
): () => void {
  const timers = new Map<HTMLElement, number>();
  let edgeHover: HTMLElement | null = null;

  const revealForScroll = (element: HTMLElement) => {
    element.classList.add(SCROLL_ACTIVE_CLASS);
    const previousTimer = timers.get(element);
    if (previousTimer !== undefined) window.clearTimeout(previousTimer);
    timers.set(element, window.setTimeout(() => {
      element.classList.remove(SCROLL_ACTIVE_CLASS);
      timers.delete(element);
    }, SCROLL_ACTIVITY_MS));
  };

  const onScroll = (event: Event) => {
    const element = scrollElementFromTarget(event.target);
    if (element) revealForScroll(element);
  };

  const onPointerMove = (event: PointerEvent) => {
    const next = verticalScrollerNearEdge(event.target, event.clientX);
    if (next === edgeHover) return;
    edgeHover?.classList.remove(SCROLLBAR_EDGE_CLASS);
    edgeHover = next;
    edgeHover?.classList.add(SCROLLBAR_EDGE_CLASS);
  };

  const onPointerLeave = () => {
    edgeHover?.classList.remove(SCROLLBAR_EDGE_CLASS);
    edgeHover = null;
  };

  root.addEventListener("scroll", onScroll, true);
  root.addEventListener("pointermove", onPointerMove);
  root.addEventListener("pointerleave", onPointerLeave);

  return () => {
    root.removeEventListener("scroll", onScroll, true);
    root.removeEventListener("pointermove", onPointerMove);
    root.removeEventListener("pointerleave", onPointerLeave);
    onPointerLeave();
    for (const [element, timer] of timers) {
      window.clearTimeout(timer);
      element.classList.remove(SCROLL_ACTIVE_CLASS);
    }
    timers.clear();
  };
}

export function useTransientScrollbarBehavior(): void {
  useEffect(() => installTransientScrollbarBehavior(), []);
}
