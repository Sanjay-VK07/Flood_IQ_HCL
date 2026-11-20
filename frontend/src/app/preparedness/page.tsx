"use client";

import React, { useEffect, useState } from "react";
import { CheckSquare, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import type { EvaluatedZone, ResponseTeam, ZoneRaw } from "@/lib/types";
import { useSimulation } from "@/context/SimulationContext";
import { Badge, toneFromBand } from "@/components/Badge";

export default function PreparednessPage() {
  const { rainfallMm, useSimulation: isSim, refreshTick } = useSimulation();
  const [zones, setZones] = useState<EvaluatedZone[]>([]);
  const [rawZones, setRawZones] = useState<ZoneRaw[]>([]);
  const [teams, setTeams] = useState<ResponseTeam[]>([]);
  const [selectedZoneId, setSelectedZoneId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.simulateRisk(rainfallMm, isSim), api.getZones(), api.getTeams()])
      .then(([riskRes, rawList, teamList]) => {
        if (cancelled) return;
        setZones(riskRes.zones);
        setRawZones(rawList);
        setTeams(teamList);
        setError(null);
        setSelectedZoneId((prev) =>
          prev && riskRes.zones.some((z) => z.zone_id === prev) ? prev : riskRes.zones[0]?.zone_id || ""
        );
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [rainfallMm, isSim, refreshTick]);

  const activeZone = zones.find((z) => z.zone_id === selectedZoneId) || zones[0];
  const rawZone = rawZones.find((z) => z.zone_id === activeZone?.zone_id);

  if (error) {
    return (
      <div className="p-4 rounded-[4px] bg-[#FF5364]/15 border border-[#FF5364]/40 text-[#FFB3BA] text-[13px]">
        Failed to load Preparedness data ({error}). Ensure FastAPI is running.
      </div>
    );
  }

  if (!activeZone) {
    return <div className="p-8 text-center text-[13px] text-[var(--text-secondary)]">Loading Preparedness...</div>;
  }

  const availCount = teams.filter((t) => t.status === "Available").length;
  const tone = toneFromBand(activeZone.risk_level);

  return (
    <div className="space-y-4">
      <div className="p-3.5 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.09em] text-[var(--teal)]">
            Readiness & SOP Activation
          </div>
          <h1 className="text-[19px] font-bold text-[var(--text-primary)] mt-0.5">Preparedness & Readiness</h1>
          <p className="text-[12px] text-[var(--text-secondary)]">
            Risk-driven operational checklists updated dynamically by each zone&rsquo;s current scenario risk band.
          </p>
        </div>
        <Badge tone="teal">Active Input: {activeZone.rainfall_mm.toFixed(0)} mm</Badge>
      </div>

      {/* Zone Selector + 3 KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
        <div className="p-3 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)]">
          <label className="block text-[10.5px] font-bold uppercase tracking-wider text-[var(--text-muted)] mb-1">
            Pilot GIS Sub-Zone
          </label>
          <select
            value={activeZone.zone_id}
            onChange={(e) => setSelectedZoneId(e.target.value)}
            className="w-full px-2.5 py-1.5 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[12.5px] text-[var(--text-primary)] focus:outline-none focus:border-[var(--teal)]"
          >
            {zones.map((z) => (
              <option key={z.zone_id} value={z.zone_id}>
                {z.zone_name} ({z.risk_level})
              </option>
            ))}
          </select>
        </div>

        <div className="p-3 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)]">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)]">Illustrative Risk Score</span>
            <Badge tone={tone}>{activeZone.risk_level}</Badge>
          </div>
          <div className="mt-1 text-[22px] font-bold text-[var(--text-primary)]">
            {activeZone.risk_score.toFixed(1)}
            <span className="text-[12px] text-[var(--text-muted)]">/100</span>
          </div>
        </div>

        <div className="p-3 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)]">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)]">Scenario Rainfall</span>
            <Badge tone="teal">{activeZone.rainfall_source}</Badge>
          </div>
          <div className="mt-1 text-[22px] font-bold text-[var(--text-primary)]">
            {activeZone.rainfall_mm.toFixed(1)} <span className="text-[12px] text-[var(--text-muted)]">mm</span>
          </div>
        </div>

        <div className="p-3 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)]">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)]">Available Demo Units</span>
            <Badge tone={availCount > 0 ? "low" : "critical"}>Standby</Badge>
          </div>
          <div className="mt-1 text-[22px] font-bold text-[var(--text-primary)]">
            {availCount} <span className="text-[12px] text-[var(--text-muted)]">/ {teams.length}</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left: Checklist */}
        <div className="lg:col-span-8 space-y-2">
          <div className="flex items-baseline justify-between border-b border-[var(--border-hairline)] pb-1.5">
            <h2 className="text-[14px] font-bold text-[var(--text-primary)]">
              Zone Emergency Action Checklist &mdash; {activeZone.zone_name}
            </h2>
            <span className="text-[11px] text-[var(--teal)] font-semibold">
              {activeZone.risk_level} Readiness Tier
            </span>
          </div>

          <div className="space-y-2">
            {activeZone.prep_checklist.map((item, idx) => {
              const urgent = activeZone.risk_level === "High" || activeZone.risk_level === "Critical";
              return (
                <div
                  key={idx}
                  className={`p-3 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] border-l-[3px] ${
                    urgent ? "border-l-[#FF9B48]" : "border-l-[#21C7B7]"
                  } space-y-1`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[13px] font-semibold text-[var(--text-primary)] inline-flex items-center gap-2">
                      {urgent ? (
                        <AlertCircle className="w-4 h-4 text-[#FF9B48] shrink-0" />
                      ) : (
                        <CheckSquare className="w-4 h-4 text-[var(--teal)] shrink-0" />
                      )}
                      <span>
                        {idx + 1}. {item.action}
                      </span>
                    </span>
                    <Badge
                      tone={
                        activeZone.risk_level === "Critical"
                          ? "critical"
                          : activeZone.risk_level === "High"
                          ? "high"
                          : "teal"
                      }
                    >
                      {urgent ? "Action Required" : "Recommended"}
                    </Badge>
                  </div>
                  <div className="text-[12px] text-[var(--text-secondary)] pl-6">
                    <b className="text-[#D9E3F2]">Why:</b> {item.reason}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right: Zone Profile + Demo Units */}
        <div className="lg:col-span-4 space-y-3">
          <div
            className={`p-3.5 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] border-l-4 ${
              activeZone.risk_level === "Critical"
                ? "border-l-[#FF5364]"
                : activeZone.risk_level === "High"
                ? "border-l-[#FF9B48]"
                : activeZone.risk_level === "Moderate"
                ? "border-l-[#E8C45A]"
                : "border-l-[#37C98A]"
            } space-y-2`}
          >
            <div className="flex items-center justify-between">
              <h2 className="text-[13px] font-bold text-[var(--text-primary)]">Zone Vulnerability Profile</h2>
              <Badge tone={tone}>{activeZone.risk_level}</Badge>
            </div>
            <p className="text-[12px] text-[var(--text-secondary)] leading-relaxed">
              {rawZone?.description || "Urban residential and commercial catchment area."}
            </p>
            <div className="flex justify-between text-[11.5px] text-[var(--text-secondary)] pt-2 border-t border-[var(--border-hairline)]">
              <span>
                Drainage Vuln.: <b className="text-[var(--text-primary)]">{activeZone.drainage_score}/100</b>
              </span>
              <span>
                Low-Lying: <b className="text-[var(--text-primary)]">{activeZone.low_lying_score}/100</b>
              </span>
            </div>
          </div>

          <div className="p-3.5 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] space-y-2">
            <h2 className="text-[13px] font-bold text-[var(--text-primary)]">Illustrative Response Fleet</h2>
            <div className="space-y-1.5">
              {teams.map((t) => (
                <div
                  key={t.team_id}
                  className="px-2.5 py-1.5 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] flex items-center justify-between gap-2"
                >
                  <div>
                    <div className="text-[12px] font-semibold text-[var(--text-primary)]">{t.team_name}</div>
                    <div className="text-[10.5px] text-[var(--text-muted)]">{t.specialty}</div>
                  </div>
                  <Badge tone={t.status === "Available" ? "low" : "critical"}>{t.status}</Badge>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
