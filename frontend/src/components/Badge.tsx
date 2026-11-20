import React from "react";

export type BadgeTone = "critical" | "high" | "moderate" | "low" | "teal" | "blue" | "neutral";

const TONE_CLASSES: Record<BadgeTone, string> = {
  critical:
    "bg-[#FEF2F2] text-[#991B1B] border-[#FCA5A5] dark:bg-[#FF5364]/15 dark:text-[#FF8E99] dark:border-[#FF5364]/40",
  high:
    "bg-[#FFF7ED] text-[#9A3412] border-[#FDBA74] dark:bg-[#FF9B48]/15 dark:text-[#FF9B48] dark:border-[#FF9B48]/40",
  moderate:
    "bg-[#FFFBEB] text-[#92400E] border-[#FCD34D] dark:bg-[#E8C45A]/15 dark:text-[#E8C45A] dark:border-[#E8C45A]/40",
  low:
    "bg-[#ECFDF5] text-[#065F46] border-[#6EE7B7] dark:bg-[#37C98A]/15 dark:text-[#37C98A] dark:border-[#37C98A]/40",
  teal:
    "bg-[#F0FDFA] text-[#0F766E] border-[#99F6E4] dark:bg-[#21C7B7]/15 dark:text-[#21C7B7] dark:border-[#21C7B7]/40",
  blue:
    "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE] dark:bg-[#55A8FF]/15 dark:text-[#55A8FF] dark:border-[#55A8FF]/40",
  neutral:
    "bg-[var(--bg-elevated)] text-[var(--text-secondary)] border-[var(--border-hairline)]",
};

export function toneFromBand(band?: string | null): BadgeTone {
  switch ((band || "").toLowerCase()) {
    case "critical":
      return "critical";
    case "high":
      return "high";
    case "moderate":
    case "medium":
      return "moderate";
    case "low":
      return "low";
    default:
      return "neutral";
  }
}

export function bandFromScore(score: number): "Critical" | "High" | "Moderate" | "Low" {
  if (score >= 75) return "Critical";
  if (score >= 50) return "High";
  if (score >= 30) return "Moderate";
  return "Low";
}

export function Badge({
  children,
  tone = "neutral",
  className = "",
}: {
  children: React.ReactNode;
  tone?: BadgeTone;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-[4px] border text-[10px] font-bold uppercase tracking-[0.05em] whitespace-nowrap ${TONE_CLASSES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
