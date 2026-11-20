"use client";

import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { SystemStatusResponse } from "@/lib/types";
import { Badge } from "@/components/Badge";

export default function SystemInfoPage() {
  const [status, setStatus] = useState<SystemStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getSystemStatus()
      .then(setStatus)
      .catch((err: Error) => setError(err.message));
  }, []);

  if (error) {
    return (
      <div className="p-4 rounded-[4px] bg-[#FF5364]/15 border border-[#FF5364]/40 text-[#FFB3BA] text-[13px]">
        Failed to fetch system diagnostics: {error}
      </div>
    );
  }

  if (!status) {
    return <div className="p-8 text-center text-[13px] text-[var(--text-secondary)]">Loading System Diagnostics...</div>;
  }

  return (
    <div className="space-y-4">
      <div className="p-3.5 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.09em] text-[var(--teal)]">
            Architecture & Operational Integrity
          </div>
          <h1 className="text-[19px] font-bold text-[var(--text-primary)] mt-0.5">
            System Information & Diagnostics
          </h1>
          <p className="text-[12px] text-[var(--text-secondary)]">
            Live weather/AI service modes, explainable scoring formulas, and hackathon prototype disclosures.
          </p>
        </div>
        <Badge tone="teal">Prototype Environment</Badge>
      </div>

      {/* 3 Diagnostics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="p-3.5 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[13px] font-bold text-[var(--text-primary)]">Weather & Precipitation</span>
            <Badge tone={status.weather.connected ? "low" : "moderate"}>
              {status.weather.connected ? "Connected" : "Fallback"}
            </Badge>
          </div>
          <div className="text-[12px] text-[var(--text-secondary)]">
            {status.weather.connected
              ? `Open-Meteo API active (Latency: ${status.weather.latency_ms} ms)`
              : `Offline / Fallback active (${status.weather.error || "Using simulated or default rainfall"})`}
          </div>
        </div>

        <div className="p-3.5 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[13px] font-bold text-[var(--text-primary)]">AI Triage Service (Groq)</span>
            <Badge tone={status.ai.mode === "groq" ? "low" : status.ai.rate_limited ? "high" : "blue"}>
              {status.ai.mode === "groq" ? "Groq AI" : "Rule-Based Fallback"}
            </Badge>
          </div>
          <div className="text-[12px] text-[var(--text-secondary)] space-y-1">
            <div>
              Model: <b className="text-[var(--text-primary)]">{status.ai.model}</b> &middot; Status:{" "}
              <b className="text-[var(--text-primary)]">{status.ai.latest_provider_status || "ready"}</b>
            </div>
            <div className="text-[11px]">
              Configured: <b className="text-[var(--text-primary)]">{status.ai.groq_configured ? "Yes" : "No"}</b>
              {" · "}Cache Hits: <b className="text-[var(--text-primary)]">{status.ai.cache_hits ?? 0}</b>
              {status.ai.rate_limited && (
                <span className="text-[#F59E0B]">
                  {" · "}Cooldown: {status.ai.cooldown_remaining_seconds ?? 0}s
                </span>
              )}
            </div>
            <div className="text-[11px]">
              Last Success:{" "}
              <b className="text-[var(--text-primary)]">
                {status.ai.last_success_at ? status.ai.last_success_at.slice(0, 19).replace("T", " ") + " UTC" : "None yet"}
              </b>
            </div>
          </div>
        </div>

        <div className="p-3.5 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[13px] font-bold text-[var(--text-primary)]">Database & Persistence</span>
            <Badge tone="low">SQLite WAL</Badge>
          </div>
          <div className="text-[12px] text-[var(--text-secondary)]">
            Zones: <b className="text-[var(--text-primary)]">{status.database.zone_count}</b> &middot; Incidents:{" "}
            <b className="text-[var(--text-primary)]">{status.database.incident_count}</b> &middot; Teams:{" "}
            <b className="text-[var(--text-primary)]">{status.database.team_count}</b>
          </div>
        </div>
      </div>

      {/* Formulas + Limitations */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="p-4 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] space-y-3">
          <h2 className="text-[14px] font-bold text-[var(--text-primary)] border-b border-[var(--border-hairline)] pb-1.5">
            Explainable Scoring & Resilience
          </h2>
          <div className="p-2.5 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] font-mono text-[12px] text-[var(--teal)]">
            <div>Risk: {status.formulas.risk.expression}</div>
            <div className="mt-1">Priority: {status.formulas.priority.expression}</div>
          </div>
          <ul className="space-y-1.5 text-[12px] text-[var(--text-secondary)] list-disc pl-4">
            <li>
              <b className="text-[var(--text-primary)]">Zone Risk Heuristic:</b> Combines normalized rainfall (150 mm ceiling), drainage vulnerability, and low-lying terrain.
            </li>
            <li>
              <b className="text-[var(--text-primary)]">Vulnerability-First Priority:</b> Ensures stranded or vulnerable citizens outrank general traffic disruption.
            </li>
            <li>
              <b className="text-[var(--text-primary)]">Transaction Safety:</b> SQLite transactions prevent duplicate team assignments and enforce valid status transitions.
            </li>
          </ul>
        </div>

        <div className="p-4 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] space-y-3">
          <h2 className="text-[14px] font-bold text-[var(--text-primary)] border-b border-[var(--border-hairline)] pb-1.5">
            Prototype Scope & Limitations
          </h2>
          <ul className="space-y-2 text-[12px] text-[var(--text-secondary)] list-disc pl-4">
            {status.limitations.map((lim, idx) => (
              <li key={idx}>{lim}</li>
            ))}
          </ul>
        </div>
      </div>

      {/* 5-Stage Data & Decision Pipeline (matches Stitch 7_system_info.png) */}
      <div className="p-4 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] space-y-3">
        <div className="flex items-center justify-between border-b border-[var(--border-hairline)] pb-1.5">
          <h2 className="text-[14px] font-bold text-[var(--text-primary)]">
            End-to-End Decision &amp; Triage Pipeline
          </h2>
          <Badge tone="teal">Human-in-the-Loop</Badge>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2.5">
          {[
            { step: "01 // INTAKE", title: "Citizen Report", desc: "Structured form + landmark & affected count" },
            { step: "02 // TELEMETRY", title: "Weather & Risk", desc: "Open-Meteo or simulation + R = 0.4P + 0.3D + 0.3L" },
            { step: "03 // TRIAGE", title: "Groq + Fallback", desc: "Groq Structured Outputs with deterministic rule-based fallback" },
            { step: "04 // PRIORITY", title: "Vulnerability First", desc: "Weighted urgency, stranded & vulnerable flags" },
            { step: "05 // DISPATCH", title: "Operator Gate", desc: "Explicit human approval + SQLite audit log" },
          ].map((stage) => (
            <div key={stage.step} className="p-3 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] space-y-1">
              <div className="text-[10px] font-bold tracking-wider text-[var(--teal)]">{stage.step}</div>
              <div className="text-[13px] font-semibold text-[var(--text-primary)]">{stage.title}</div>
              <div className="text-[11px] text-[var(--text-secondary)]">{stage.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
