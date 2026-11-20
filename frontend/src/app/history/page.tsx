"use client";

import React, { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type { Incident, IncidentUpdate, ResponseTeam, ZoneRaw } from "@/lib/types";
import { useSimulation } from "@/context/SimulationContext";
import { useAutoPoll } from "@/hooks/useAutoPoll";
import { Badge, bandFromScore, toneFromBand } from "@/components/Badge";

const STATUSES = ["All", "New", "Triaged", "In Review", "Team Assigned", "Acknowledged", "In Progress", "Resolved"];

function IncidentHistoryInner() {
  const searchParams = useSearchParams();
  const initialId = searchParams.get("incident");
  const { refreshTick } = useSimulation();

  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [zones, setZones] = useState<ZoneRaw[]>([]);
  const [teams, setTeams] = useState<ResponseTeam[]>([]);
  const [statusFilter, setStatusFilter] = useState("All");
  const [zoneFilter, setZoneFilter] = useState("All");
  const [selectedId, setSelectedId] = useState<string | null>(initialId);
  const [timeline, setTimeline] = useState<IncidentUpdate[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.getZones(), api.getTeams()])
      .then(([zList, tList]) => {
        setZones(zList);
        setTeams(tList);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const incs = await api.listIncidents(statusFilter, zoneFilter);
      setIncidents(incs);
      setError(null);
      setSelectedId((prev) => {
        if (prev && incs.some((i) => i.incident_id === prev)) return prev;
        if (initialId && incs.some((i) => i.incident_id === initialId)) return initialId;
        return incs[0]?.incident_id ?? null;
      });
      if (selectedId) {
        const tl = await api.getTimeline(selectedId);
        setTimeline(tl);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load history.");
    }
  }, [statusFilter, zoneFilter, initialId, selectedId]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory, refreshTick]);

  useAutoPoll(loadHistory, true, 4000);

  useEffect(() => {
    if (!selectedId) {
      setTimeline([]);
      return;
    }
    let cancelled = false;
    api
      .getTimeline(selectedId)
      .then((tl) => {
        if (!cancelled) setTimeline(tl);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, refreshTick]);

  const zoneNameById = new Map(zones.map((z) => [z.zone_id, z.zone_name]));
  const teamNameById = new Map(teams.map((t) => [t.team_id, t.team_name]));
  const selectedInc = incidents.find((i) => i.incident_id === selectedId) || null;

  return (
    <div className="space-y-4">
      <div className="p-3.5 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.09em] text-[var(--teal)]">
            Operational Archive / Incident History
          </div>
          <h1 className="text-[19px] font-bold text-[var(--text-primary)] mt-0.5">
            Incident History & Chronological Timeline
          </h1>
          <p className="text-[12px] text-[var(--text-secondary)]">
            Immutable SQLite audit trail of reports, triage assessments, operator approvals, and resolutions.
          </p>
        </div>
        <Badge tone="teal">Append-Only Audit Log</Badge>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-3 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)]">
        <div>
          <label className="block text-[10.5px] font-bold uppercase tracking-wider text-[var(--text-muted)] mb-1">
            Filter by Status
          </label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="w-full px-2.5 py-1.5 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[12.5px] text-[var(--text-primary)] focus:outline-none focus:border-[var(--teal)]"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-[10.5px] font-bold uppercase tracking-wider text-[var(--text-muted)] mb-1">
            Filter by Zone
          </label>
          <select
            value={zoneFilter}
            onChange={(e) => setZoneFilter(e.target.value)}
            className="w-full px-2.5 py-1.5 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[12.5px] text-[var(--text-primary)] focus:outline-none focus:border-[var(--teal)]"
          >
            <option value="All">All Zones</option>
            {zones.map((z) => (
              <option key={z.zone_id} value={z.zone_id}>
                {z.zone_name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-[4px] bg-[#FF5364]/15 border border-[#FF5364]/40 text-[#FFB3BA] text-[13px]">
          Failed to load Incident History ({error}). Ensure FastAPI is running.
        </div>
      )}

      {incidents.length === 0 ? (
        <div className="p-6 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] text-[13px] text-[var(--text-secondary)]">
          No incidents match the selected filters.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          {/* Left: Ledger */}
          <div className="lg:col-span-5 space-y-2">
            <div className="flex items-baseline justify-between border-b border-[var(--border-hairline)] pb-1.5">
              <h2 className="text-[13px] font-bold text-[var(--text-primary)]">Historical Incident Ledger</h2>
              <span className="text-[11px] text-[var(--text-muted)]">{incidents.length} record(s)</span>
            </div>

            <div className="space-y-2">
              {incidents.map((inc) => {
                const band = bandFromScore(inc.priority_score);
                const isSel = inc.incident_id === selectedId;
                const unitLabel = inc.assigned_team_id
                  ? teamNameById.get(inc.assigned_team_id) || inc.assigned_team_id
                  : "Unassigned";
                const borderLeft =
                  band === "Critical"
                    ? "border-l-[#FF5364]"
                    : band === "High"
                    ? "border-l-[#FF9B48]"
                    : band === "Moderate"
                    ? "border-l-[#E8C45A]"
                    : "border-l-[#37C98A]";
                return (
                  <button
                    key={inc.incident_id}
                    type="button"
                    onClick={() => setSelectedId(inc.incident_id)}
                    className={`w-full text-left p-3 rounded-[4px] border border-l-[3px] ${borderLeft} transition-colors ${
                      isSel
                        ? "bg-[var(--bg-elevated)] border-[var(--teal)]"
                        : "bg-[var(--bg-panel)] border-[var(--border-hairline)] hover:border-[var(--border-active)]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11px] font-bold text-[var(--text-muted)]">#{inc.incident_id}</span>
                      <Badge tone={toneFromBand(band)}>{Math.round(inc.priority_score)}/100</Badge>
                    </div>
                    <div className="text-[13px] font-semibold text-[var(--text-primary)] mt-1">
                      {inc.ai_category || inc.reported_category} &middot;{" "}
                      {zoneNameById.get(inc.zone_id) || inc.zone_id}
                    </div>
                    <div className="flex justify-between text-[11px] text-[var(--text-secondary)] mt-1">
                      <span>
                        Status: <b className="text-[var(--text-primary)]">{inc.status}</b>
                      </span>
                      <span>Unit: {unitLabel}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Right: Chronological Timeline */}
          <div className="lg:col-span-7 space-y-2">
            {selectedInc && (
              <>
                <div className="flex items-baseline justify-between border-b border-[var(--border-hairline)] pb-1.5">
                  <h2 className="text-[13px] font-bold text-[var(--text-primary)]">
                    Incident Audit Trail: #{selectedInc.incident_id}
                  </h2>
                  <span className="text-[11px] text-[var(--text-muted)]">
                    Logged {selectedInc.created_at.slice(0, 19).replace("T", " ")} UTC
                  </span>
                </div>

                <div className="p-3 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] border-l-[3px] border-l-[#55A8FF] text-[12px] text-[#D9E3F2]">
                  <div>{selectedInc.description}</div>
                  <div className="text-[11px] text-[var(--text-secondary)] mt-1.5">
                    Location: <b>{selectedInc.location_text || "N/A"}</b> &middot; Affected:{" "}
                    <b>{selectedInc.people_affected}</b>
                  </div>
                </div>

                <div className="relative pl-5 space-y-2.5 pt-1 before:content-[''] before:absolute before:left-[7px] before:top-3 before:bottom-3 before:w-[2px] before:bg-[#1E384D]">
                  {timeline.map((u) => {
                    const isResolved = u.new_status === "Resolved";
                    const isAssigned = u.new_status === "Team Assigned" || u.new_status === "In Progress";
                    const dotColor = isResolved ? "#37C98A" : isAssigned ? "#21C7B7" : "#55A8FF";
                    return (
                      <div key={u.update_id} className="relative">
                        <span
                          className="absolute -left-5 top-3.5 w-3.5 h-3.5 rounded-full border-2 border-[#09131D]"
                          style={{ backgroundColor: dotColor }}
                        />
                        <div className="p-3 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)]">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-[10.5px] font-bold text-[var(--text-muted)]">
                              {u.updated_at.slice(0, 19).replace("T", " ")} UTC
                            </span>
                            <Badge tone={isResolved ? "low" : isAssigned ? "teal" : "blue"}>
                              {u.new_status || "Update"}
                            </Badge>
                          </div>
                          <div className="text-[13px] font-bold text-[var(--text-primary)] mt-0.5">
                            {u.old_status || "Created"} &rarr; <span className="text-[var(--teal)]">{u.new_status}</span>
                          </div>
                          <div className="text-[12px] text-[var(--text-secondary)] mt-0.5">{u.note}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function IncidentHistoryPage() {
  return (
    <Suspense fallback={<div className="p-6 text-[13px] text-[var(--text-secondary)]">Loading Incident History...</div>}>
      <IncidentHistoryInner />
    </Suspense>
  );
}
