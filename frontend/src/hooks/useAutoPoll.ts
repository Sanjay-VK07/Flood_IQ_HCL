"use client";

import { useEffect, useRef } from "react";

/**
 * Lightweight polling hook for active incident views.
 * Polls every `intervalMs` (default 4000 ms) only while `enabled` is true
 * and the browser tab is visible (`document.visibilityState === "visible"`).
 */
export function useAutoPoll(
  callback: () => void | Promise<void>,
  enabled: boolean,
  intervalMs = 4000
): void {
  const savedCallback = useRef(callback);
  savedCallback.current = callback;

  useEffect(() => {
    if (!enabled) return;

    const runIfVisible = () => {
      if (typeof document !== "undefined" && document.visibilityState !== "visible") {
        return;
      }
      void savedCallback.current();
    };

    const timer = window.setInterval(runIfVisible, intervalMs);
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void savedCallback.current();
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [enabled, intervalMs]);
}
