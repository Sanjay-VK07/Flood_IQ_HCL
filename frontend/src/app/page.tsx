"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, AlertTriangle, Shield, Clock, Activity, Siren, ShieldCheck, Layers } from "lucide-react";
import { api } from "@/lib/api";
import type { DashboardResponse } from "@/lib/types";
import { useSimulation } from "@/context/SimulationContext";
import { useAutoPoll } from "@/hooks/useAutoPoll";
import { Badge, bandFromScore, toneFromBand } from "@/components/Badge";
import { HyderabadMap } from "@/components/HyderabadMap";

export default function CommandCenterPage() {
  const { rainfallMm, useSimulation: isSim, refreshTick } = useSimulation();
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    try {
      const res = await api.getDashboard(rainfallMm, isSim);
      setData(res);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Command Center.");
    }
  }, [rainfallMm, isSim]);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard, refreshTick]);

  useAutoPoll(loadDashboard, true, 4000);

  if (error) {
    return (
      <div className="p-4 rounded-[4px] bg-[#FF5364]/15 border border-[#FF5364]/40 text-[#FFB3BA] text-[13px]">
        Failed to load Command Center from FastAPI backend ({error}). Ensure Uvicorn is running on port 8000.
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-8 text-center text-[13px] text-[var(--text-secondary)]">
        Loading FloodIQ Command Center...
      </div>
    );
  }

  const zoneNameById = new Map(data.zones.map((z) => [z.zone_id, z.zone_name]));
  const teamNameById = new Map(data.teams.map((t) => [t.team_id, t.team_name]));

  const elevatedZones = data.zones.filter((z) => z.risk_level === "High" || z.risk_level === "Critical");
  const openIncidents = data.incidents.filter((i) => i.status !== "Resolved");
  const criticalIncidents = openIncidents.filter((i) => i.priority_score >= 75);
  const avgPriority =
    openIncidents.length > 0
      ? Math.round(openIncidents.reduce((s, i) => s + i.priority_score, 0) / openIncidents.length)
      : 0;
  const availTeams = data.teams.filter((t) => t.status === "Available");
  const assignedTeams = data.teams.filter((t) => t.status === "Assigned");

  return (
    <div className="space-y-4">
      {/* 4-Card KPI Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
        <div className="p-3 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)]">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)] inline-flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-[#FF9B48]" />
              Elevated-Risk Zones
            </span>
            <Badge tone={elevatedZones.length > 0 ? "high" : "low"}>
              {elevatedZones.length > 0 ? "High / Critical" : "Nominal"}
            </Badge>
          </div>
          <div className="mt-1.5 text-[24px] font-bold text-[var(--text-primary)] leading-tight">
            {elevatedZones.length}
            <span className="text-[13px] font-medium text-[var(--text-muted)]"> / {data.zones.length} pilot zones</span>
          </div>
          <div className="mt-1.5 text-[11px] text-[var(--text-muted)] truncate">
            {elevatedZones.length > 0
              ? elevatedZones.map((z) => z.zone_name).join(", ")
              : "All pilot sectors within nominal thresholds"}
          </div>
        </div>

        <div className="p-3 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)]">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)] inline-flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-[var(--teal)]" />
              Active Incidents
            </span>
            <Badge tone="teal">{data.incidents.length - openIncidents.length} Resolved</Badge>
          </div>
          <div className="mt-1.5 text-[24px] font-bold text-[var(--text-primary)] leading-tight">
            {openIncidents.length}
          </div>
          <div className="mt-1.5 text-[11px] text-[var(--text-secondary)]">
            {openIncidents.length > 0 ? `Avg priority ${avgPriority}/100` : "Queue clear"}
          </div>
        </div>

        <div
          className={`p-3 rounded-[4px] border ${
            criticalIncidents.length > 0
              ? "bg-gradient-to-b from-[#FF5364]/10 to-[#122431] border-[#FF5364]/45"
              : "bg-[var(--bg-panel)] border-[var(--border-hairline)]"
          }`}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)] inline-flex items-center gap-1.5">
              <Siren className="w-3.5 h-3.5 text-[#FF5364]" />
              Critical Incidents
            </span>
            <Badge tone={criticalIncidents.length > 0 ? "critical" : "low"}>
              {criticalIncidents.length > 0 ? "Action Urgent" : "Clear"}
            </Badge>
          </div>
          <div className="mt-1.5 text-[24px] font-bold text-[var(--text-primary)] leading-tight">
            {criticalIncidents.length}
          </div>
          <div className="mt-1.5 text-[11px] text-[var(--text-secondary)] truncate">
            {criticalIncidents.length > 0
              ? `Priority sector: ${zoneNameById.get(criticalIncidents[0].zone_id) || criticalIncidents[0].zone_id}`
              : "No immediate life-safety alerts"}
          </div>
        </div>

        <div className="p-3 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)]">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)] inline-flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-[#37C98A]" />
              Available Response Teams
            </span>
            <Badge tone={availTeams.length > 0 ? "low" : "critical"}>
              {availTeams.length} Standby
            </Badge>
          </div>
          <div className="mt-1.5 text-[24px] font-bold text-[var(--text-primary)] leading-tight">
            {availTeams.length}
            <span className="text-[13px] font-medium text-[var(--text-muted)]"> / {data.teams.length}</span>
          </div>
          <div className="mt-1.5 text-[11px] text-[var(--text-muted)]">
            {assignedTeams.length} deployed (illustrative demo data)
          </div>
        </div>
      </div>

      {/* Main 2-Column Operational Workspace */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
        {/* Left: Hyderabad Map */}
        <div className="xl:col-span-7 space-y-2">
          <div className="flex items-baseline justify-between border-b border-[var(--border-hairline)] pb-1.5">
            <h2 className="text-[14px] font-bold text-[var(--text-primary)]">Hyderabad Urban Catchment</h2>
            <span className="text-[11px] text-[var(--text-muted)]">
              {data.zones.length} Assessment Zones &middot;{" "}
              {isSim ? `${rainfallMm} mm Scenario` : "Open-Meteo Weather Data"}
            </span>
          </div>
          <HyderabadMap zones={data.zones} incidents={data.incidents} teams={data.teams} height={430} />
        </div>

        {/* Right: Priority Incident Queue */}
        <div className="xl:col-span-5 space-y-2">
          <div className="flex items-baseline justify-between border-b border-[var(--border-hairline)] pb-1.5">
            <h2 className="text-[14px] font-bold text-[var(--text-primary)]">Priority Incident Queue</h2>
            <span className="text-[11px] text-[var(--teal)] font-semibold">
              {openIncidents.length} Active &middot; Vulnerability First
            </span>
          </div>

          {openIncidents.length === 0 ? (
            <div className="p-4 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] text-[12.5px] text-[var(--text-secondary)]">
              No open incidents in queue. All reported incidents are resolved.
            </div>
          ) : (
            <div className="space-y-2.5">
              {openIncidents.slice(0, 4).map((inc) => {
                const band = bandFromScore(inc.priority_score);
                const tone = toneFromBand(band);
                const borderLeft =
                  band === "Critical"
                    ? "border-l-[#FF5364]"
                    : band === "High"
                    ? "border-l-[#FF9B48]"
                    : band === "Moderate"
                    ? "border-l-[#E8C45A]"
                    : "border-l-[#37C98A]";
                const zoneLabel = zoneNameById.get(inc.zone_id) || inc.zone_id;
                const unitLabel = inc.assigned_team_id
                  ? teamNameById.get(inc.assigned_team_id) || inc.assigned_team_id
                  : "Unassigned";

                return (
                  <div
                    key={inc.incident_id}
                    className={`p-3 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] border-l-[3px] ${borderLeft} space-y-2`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] font-bold text-[var(--text-muted)] tracking-wider">
                          #{inc.incident_id}
                        </span>
                        <Badge tone={tone}>{band}</Badge>
                      </div>
                      <span className="text-[14px] font-bold text-[var(--text-primary)]">
                        {Math.round(inc.priority_score)}
                        <span className="text-[11px] font-normal text-[var(--text-muted)]">/100</span>
                      </span>
                    </div>

                    <div>
                      <div className="text-[13.5px] font-semibold text-[var(--text-primary)]">
                        {inc.ai_category || inc.reported_category}
                      </div>
                      <div className="text-[12px] text-[var(--text-secondary)] mt-0.5">
                        {zoneLabel} &mdash; {inc.location_text || "Location specified in report"}
                      </div>
                    </div>

                    {(Boolean(inc.vulnerable_flag) || Boolean(inc.stranded)) && (
                      <div className="flex items-center gap-1.5 px-2 py-1 rounded-[3px] bg-[#FF5364]/10 border border-[#FF5364]/30 text-[11px] text-[#FFB3BA]">
                        <AlertTriangle className="w-3.5 h-3.5 text-[#FF5364] shrink-0" />
                        <span>
                          {[
                            inc.stranded ? `${inc.people_affected} Stranded` : null,
                            inc.vulnerable_flag ? `Vulnerable: ${inc.vulnerable_group}` : null,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      </div>
                    )}

                    <div className="flex items-center justify-between gap-2 pt-1 text-[11px] text-[var(--text-muted)]">
                      <span>
                        Status: <b className="text-[var(--text-secondary)]">{inc.status}</b> &middot; Unit:{" "}
                        <b className="text-[var(--text-secondary)]">{unitLabel}</b>
                      </span>
                      <Link
                        href={`/control-room?incident=${encodeURIComponent(inc.incident_id)}`}
                        className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-[4px] text-[11px] font-bold transition-colors ${
                          band === "Critical"
                            ? "bg-[var(--teal)] text-[var(--teal-fg)] hover:bg-[var(--teal-hover)]"
                            : "bg-[var(--bg-elevated)] text-[var(--text-primary)] border border-[var(--border-active)] hover:border-[var(--teal)]"
                        }`}
                      >
                        Review & Dispatch
                        <ArrowRight className="w-3 h-3" />
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Bottom Operational Strip: Recent Activity + Response Teams */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-7 space-y-2">
          <div className="flex items-baseline justify-between border-b border-[var(--border-hairline)] pb-1.5">
            <h2 className="text-[13px] font-bold text-[var(--text-primary)] flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-[var(--teal)]" /> Recent Incident Activity
            </h2>
            <span className="text-[11px] text-[var(--text-muted)]">Chronological SQLite audit log</span>
          </div>
          <div className="space-y-1.5">
            {data.recent_activity.slice(0, 4).map((ev) => (
              <div
                key={ev.update_id}
                className="px-3 py-2 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] border-l-[3px] border-l-[#21C7B7] text-[12px]"
              >
                <div className="text-[10.5px] font-semibold text-[var(--text-muted)]">
                  {ev.updated_at.slice(0, 19).replace("T", " ")} UTC &middot; {ev.incident_id}
                </div>
                <div className="text-[var(--text-primary)] font-medium mt-0.5">
                  <span className="text-[var(--teal)] font-bold">{ev.new_status}</span> &mdash; {ev.note}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="lg:col-span-5 space-y-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-[var(--border-hairline)] pb-1.5">
            <h2 className="text-[13px] font-bold text-[var(--text-primary)] flex items-center gap-1.5 whitespace-nowrap">
              <Shield className="w-3.5 h-3.5 text-[var(--teal)]" /> Response Team Availability
            </h2>
            <span className="text-[11px] text-[var(--text-muted)] whitespace-nowrap">
              {data.teams.length} registered teams
            </span>
          </div>
          <div className="space-y-1.5">
            {data.teams.map((t) => (
              <div
                key={t.team_id}
                className="px-3 py-2 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] flex items-center justify-between gap-2"
              >
                <div>
                  <div className="text-[12.5px] font-semibold text-[var(--text-primary)]">{t.team_name}</div>
                  <div className="text-[11px] text-[var(--text-muted)]">
                    {t.specialty} &middot; Base: {zoneNameById.get(t.base_zone) || t.base_zone}
                  </div>
                </div>
                <Badge tone={t.status === "Available" ? "low" : "critical"}>{t.status}</Badge>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
