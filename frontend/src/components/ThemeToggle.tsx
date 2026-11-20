"use client";

import React from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/context/ThemeContext";

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      title={isDark ? "Switch to Light Mode" : "Switch to Dark Mode"}
      aria-label={isDark ? "Switch to Light Mode" : "Switch to Dark Mode"}
      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-[6px] bg-[var(--bg-elevated)] hover:border-[var(--teal)] border border-[var(--border-hairline)] text-[11.5px] font-semibold text-[var(--text-primary)] transition-colors cursor-pointer"
    >
      {isDark ? (
        <Sun className="w-3.5 h-3.5 text-[#E8C45A]" />
      ) : (
        <Moon className="w-3.5 h-3.5 text-[#0D9488]" />
      )}
      {!compact && <span>{isDark ? "Light" : "Dark"}</span>}
    </button>
  );
}
