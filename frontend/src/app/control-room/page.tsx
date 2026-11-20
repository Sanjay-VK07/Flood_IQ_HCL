"use client";

import React, { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, AlertTriangle, ChevronDown, ChevronUp, History } from "lucide-react";
import { api } from "@/lib/api";
import type { Incident, PriorityBreakdown, ResponseTeam, TeamRecommendation, ZoneRaw } from "@/lib/types";
import { useSimulation } from "@/context/SimulationContext";
import { useAutoPoll } from "@/hooks/useAutoPoll";
import { Badge, bandFromScore, toneFromBand } from "@/components/Badge";

function ControlRoomInner() {
  const searchParams = useSearchParams();
  const initialId = searchParams.get("incident");
  const { refreshTick, triggerRefresh } = useSimulation();

  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [zones, setZones] = useState<ZoneRaw[]>([]);
  const [teams, setTeams] = useState<ResponseTeam[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(initialId);
  const [detail, setDetail] = useState<{ incident: Incident; priority_breakdown: PriorityBreakdown } | null>(null);
  const [rec, setRec] = useState<TeamRecommendation | null>(null);
  const [chosenTeamId, setChosenTeamId] = useState<string>("");
  const [opNote, setOpNote] = useState<string>("");
  const [resNote, setResNote] = useState<string>("");
  const [showCompare, setShowCompare] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "ok" | "err"; msg: string } | null>(null);

  const loadList = useCallback(async () => {
    try {
      const [incs, zList, tList] = await Promise.all([api.listIncidents(), api.getZones(), api.getTeams()]);
      setIncidents(incs);
      setZones(zList);
      setTeams(tList);
      setSelectedId((prev) => {
        if (prev && incs.some((i) => i.incident_id === prev)) return prev;
        if (initialId && incs.some((i) => i.incident_id === initialId)) return initialId;
        return incs[0]?.incident_id ?? null;
      });
    } catch (err) {
      setFeedback({ type: "err", msg: err instanceof Error ? err.message : "Failed to load Control Room data." });
    }
  }, [initialId]);

  useEffect(() => {
    loadList();
  }, [loadList, refreshTick]);

  const loadSelectedDetail = useCallback(async () => {
    if (!selectedId) return;
    try {
      const [det, recRes] = await Promise.all([
        api.getIncident(selectedId),
        api.getRecommendations(selectedId),
      ]);
      setDetail({ incident: det.incident, priority_breakdown: det.priority_breakdown });
      setRec(recRes);
      setChosenTeamId((prev) => {
        if (prev && recRes.alternatives?.some((a) => a.team.team_id === prev)) return prev;
        return recRes.recommended_team ? recRes.recommended_team.team_id : "";
      });
    } catch {
      setDetail(null);
    }
  }, [selectedId]);

  useEffect(() => {
    void loadSelectedDetail();
  }, [loadSelectedDetail, refreshTick]);

  useAutoPoll(
    useCallback(async () => {
      await loadList();
      if (selectedId) await loadSelectedDetail();
    }, [loadList, loadSelectedDetail, selectedId]),
    true,
    4000
  );

  const zoneNameById = new Map(zones.map((z) => [z.zone_id, z.zone_name]));
  const teamNameById = new Map(teams.map((t) => [t.team_id, t.team_name]));

  const runAction = async (fn: () => Promise<void>, okMessage: string) => {
    setBusy(true);
    setFeedback(null);
    try {
      await fn();
      setFeedback({ type: "ok", msg: okMessage });
      triggerRefresh();
    } catch (err) {
      setFeedback({ type: "err", msg: err instanceof Error ? err.message : "Operation failed" });
    } finally {
      setBusy(false);
    }
  };

  const critCount = incidents.filter((i) => i.priority_score >= 75 && i.status !== "Resolved").length;
  const availableTeams = teams.filter((t) => t.status === "Available");

  return (
    <div className="space-y-4">
      <div className="p-3.5 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.09em] text-[var(--teal)]">
            Incident Triage & Tactical Dispatch
          </div>
          <h1 className="text-[19px] font-bold text-[var(--text-primary)] mt-0.5">Response Control Room</h1>
          <p className="text-[12px] text-[var(--text-secondary)]">
            Human-in-the-loop dispatch workspace. Operators hold sole authority over unit assignment.
          </p>
        </div>
        <Badge tone={critCount > 0 ? "critical" : "low"}>{critCount} Critical</Badge>
      </div>

      {feedback && (
        <div
          className={`p-2.5 rounded-[4px] border text-[12px] flex items-center gap-2 ${
            feedback.type === "ok"
              ? "bg-[#37C98A]/15 border-[#37C98A]/40 text-[#37C98A]"
              : "bg-[#FF5364]/15 border-[#FF5364]/40 text-[#FFB3BA]"
          }`}
        >
          {feedback.type === "ok" ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
          <span>{feedback.msg}</span>
        </div>
      )}

      {incidents.length === 0 ? (
        <div className="p-6 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] text-[13px] text-[var(--text-secondary)]">
          No incidents currently in the system.
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
          {/* Left: Incident Queue */}
          <div className="xl:col-span-3 space-y-2">
            <div className="flex items-baseline justify-between border-b border-[var(--border-hairline)] pb-1.5">
              <h2 className="text-[13px] font-bold text-[var(--text-primary)]">Active Incidents</h2>
              <span className="text-[11px] text-[var(--text-muted)]">{incidents.length} total</span>
            </div>
            <div className="space-y-2">
              {incidents.map((item) => {
                const band = bandFromScore(item.priority_score);
                const isSel = item.incident_id === selectedId;
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
                    key={item.incident_id}
                    type="button"
                    onClick={() => {
                      setSelectedId(item.incident_id);
                      setFeedback(null);
                    }}
                    className={`w-full text-left p-2.5 rounded-[4px] border border-l-[3px] ${borderLeft} transition-colors ${
                      isSel
                        ? "bg-[var(--bg-elevated)] border-[var(--teal)]"
                        : "bg-[var(--bg-panel)] border-[var(--border-hairline)] hover:border-[var(--border-active)]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10.5px] font-bold text-[var(--text-muted)]">#{item.incident_id}</span>
                      <Badge tone={toneFromBand(band)}>{Math.round(item.priority_score)}/100</Badge>
                    </div>
                    <div className="text-[12.5px] font-semibold text-[var(--text-primary)] mt-1">
                      {item.ai_category || item.reported_category}
                    </div>
                    <div className="flex justify-between text-[11px] text-[var(--text-secondary)] mt-1">
                      <span>{zoneNameById.get(item.zone_id) || item.zone_id}</span>
                      <span className="font-semibold">{item.status}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Center: Incident Details & Priority Breakdown */}
          <div className="xl:col-span-5 space-y-3">
            {detail && (
              <>
                <div className="flex items-baseline justify-between border-b border-[var(--border-hairline)] pb-1.5">
                  <h2 className="text-[13px] font-bold text-[var(--text-primary)]">
                    Priority Case #{detail.incident.incident_id}
                  </h2>
                  <Badge tone="teal">{detail.incident.status}</Badge>
                </div>

                <div className="p-3.5 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] space-y-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="text-[15px] font-bold text-[var(--text-primary)]">
                        {detail.incident.ai_category || detail.incident.reported_category}
                      </div>
                      <div className="text-[12px] text-[var(--text-secondary)]">
                        {zoneNameById.get(detail.incident.zone_id) || detail.incident.zone_id} &mdash;{" "}
                        {detail.incident.location_text || "N/A"}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-[22px] font-bold text-[var(--text-primary)] leading-none">
                        {Math.round(detail.incident.priority_score)}
                        <span className="text-[12px] font-normal text-[var(--text-muted)]">/100</span>
                      </div>
                    </div>
                  </div>

                  <div className="p-2.5 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[12px] text-[#D9E3F2] leading-relaxed">
                    &ldquo;{detail.incident.description}&rdquo;
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-[11px] text-[var(--text-secondary)]">
                    <div>
                      Affected: <b className="text-[var(--text-primary)]">{detail.incident.people_affected}</b>
                    </div>
                    <div>
                      Vulnerable:{" "}
                      <b className="text-[var(--text-primary)]">
                        {detail.incident.vulnerable_flag ? detail.incident.vulnerable_group : "None"}
                      </b>
                    </div>
                    <div>
                      Stranded: <b className="text-[var(--text-primary)]">{detail.incident.stranded ? "Yes" : "No"}</b>
                    </div>
                    <div>
                      Hazard: <b className="text-[var(--text-primary)]">{detail.incident.immediate_hazard ? "Yes" : "No"}</b>
                    </div>
                    <div>
                      Triage:{" "}
                      <Badge tone={detail.incident.triage_mode === "groq" ? "low" : "blue"}>
                        {detail.incident.triage_mode === "groq" ? "Groq AI" : "Rule-Based Fallback"}
                      </Badge>
                    </div>
                  </div>

                  <div className="text-[11.5px] text-[var(--text-secondary)] pt-2 border-t border-[var(--border-hairline)]">
                    <b className="text-[var(--teal)]">Triage Rationale:</b> {detail.incident.ai_rationale}
                  </div>
                </div>

                <div className="p-3.5 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] space-y-2">
                  <div className="text-[12px] font-bold text-[var(--text-primary)]">
                    Priority Score Breakdown (Vulnerability-First)
                  </div>
                  <table className="w-full text-[11.5px]">
                    <thead>
                      <tr className="border-b border-[var(--border-hairline)] text-[var(--text-muted)] text-left">
                        <th className="py-1.5 font-semibold">Factor</th>
                        <th className="py-1.5 font-semibold text-right">Raw</th>
                        <th className="py-1.5 font-semibold text-right">Contribution</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#1E384D]/60 text-[#D9E3F2]">
                      {[
                        ["Severity (S, 30%)", detail.priority_breakdown.factors.severity],
                        ["Stranded / Trapped (T, 25%)", detail.priority_breakdown.factors.stranded],
                        ["Vulnerability (V, 25%)", detail.priority_breakdown.factors.vulnerability],
                        ["People Count (N, 10%)", detail.priority_breakdown.factors.people_affected],
                        ["Immediate Hazard (H, 10%)", detail.priority_breakdown.factors.hazard],
                      ].map(([label, f]) => {
                        const factor = f as { score: number; contribution: number };
                        return (
                          <tr key={label as string}>
                            <td className="py-1.5">{label as string}</td>
                            <td className="py-1.5 text-right">{factor.score}</td>
                            <td className="py-1.5 text-right font-bold text-[var(--teal)]">{factor.contribution}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>

          {/* Right: Team Recommendation & Human Approval */}
          <div className="xl:col-span-4 space-y-3">
            <div className="flex items-baseline justify-between border-b border-[var(--border-hairline)] pb-1.5">
              <h2 className="text-[13px] font-bold text-[var(--text-primary)]">Tactical Dispatch & Authorization</h2>
              <span className="text-[11px] text-[var(--text-muted)]">Operator sign-off required</span>
            </div>

            <div className="p-2.5 rounded-[4px] bg-[#FF5364]/10 border border-[#FF5364]/35 text-[11px] text-[#FFB3BA]">
              <b>MANUAL OPERATOR DISPATCH MANDATORY</b> &mdash; Autonomous deployment is disabled. Team locations are illustrative demo data.
            </div>

            {rec?.recommended_team ? (
              <div className="p-3 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] border-l-[3px] border-l-[#21C7B7] space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--teal)]">
                    AI Recommended Unit
                  </span>
                  <Badge tone="teal">{rec.match_score?.toFixed(1)}/100 Match</Badge>
                </div>
                <div className="text-[14px] font-bold text-[var(--text-primary)]">{rec.recommended_team.team_name}</div>
                <div className="text-[11.5px] text-[var(--text-secondary)]">
                  {rec.recommended_team.specialty} &middot; Base:{" "}
                  {zoneNameById.get(rec.recommended_team.base_zone) || rec.recommended_team.base_zone} &middot;{" "}
                  {rec.distance_desc}
                </div>
                <div className="text-[11px] text-[var(--text-muted)]">{rec.match_reason}</div>

                {rec.alternatives.length > 0 && (
                  <div className="pt-2">
                    <button
                      type="button"
                      onClick={() => setShowCompare((s) => !s)}
                      className="inline-flex items-center gap-1 text-[11px] font-semibold text-[var(--teal)] hover:underline"
                    >
                      {showCompare ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                      Compare All Available Units ({rec.alternatives.length + 1})
                    </button>
                    {showCompare && (
                      <div className="mt-2 space-y-1 text-[11px]">
                        {[
                          {
                            id: rec.recommended_team.team_id,
                            name: rec.recommended_team.team_name,
                            dist: rec.distance_desc || "",
                            score: rec.match_score || 0,
                          },
                          ...rec.alternatives.map((a) => ({
                            id: a.team.team_id,
                            name: a.team.team_name,
                            dist: a.distance_desc,
                            score: a.match_score,
                          })),
                        ].map((u) => (
                          <div
                            key={u.id}
                            className="flex justify-between px-2 py-1 rounded-[3px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)]"
                          >
                            <span className="text-[var(--text-primary)]">{u.name}</span>
                            <span className="text-[var(--text-secondary)]">
                              {u.dist} &middot; <b className="text-[var(--teal)]">{u.score.toFixed(1)}</b>
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="p-3 rounded-[4px] bg-[#FF9B48]/15 border border-[#FF9B48]/40 text-[12px] text-[#FF9B48]">
                {rec?.match_reason || "No available units."}
              </div>
            )}

            {detail && (
              <div className="p-3 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] space-y-3">
                {/* Operational Workflow Stepper (matches Stitch 5_response_control.png) */}
                <div>
                  <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-muted)] mb-2">
                    Operational Workflow Stepper
                  </div>
                  <div className="grid grid-cols-5 gap-1 text-center">
                    {["Triaged", "In Review", "Team Assigned", "In Progress", "Resolved"].map((step, idx) => {
                      const order = ["New", "Triaged", "In Review", "Team Assigned", "In Progress", "Resolved"];
                      const curIdx = order.indexOf(detail.incident.status);
                      const stepIdx = idx + 1;
                      const done = curIdx > stepIdx;
                      const current = curIdx === stepIdx;
                      return (
                        <div key={step} className="flex flex-col items-center gap-1">
                          <div
                            className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold border ${
                              current
                                ? "bg-[#FF5364]/20 border-[#FF5364] text-[#FF5364]"
                                : done
                                ? "bg-[var(--teal)] border-[var(--teal)] text-[var(--teal-fg)]"
                                : "bg-[var(--bg-elevated)] border-[var(--border-hairline)] text-[var(--text-muted)]"
                            }`}
                          >
                            {stepIdx}
                          </div>
                          <span
                            className={`text-[9.5px] leading-tight ${
                              current ? "text-[var(--text-primary)] font-bold" : done ? "text-[var(--teal)]" : "text-[var(--text-muted)]"
                            }`}
                          >
                            {step === "Team Assigned" ? "Assigned" : step}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
                {(detail.incident.status === "Triaged" || detail.incident.status === "In Review") && (
                  <>
                    {detail.incident.status === "Triaged" && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() =>
                          runAction(
                            () =>
                              api
                                .updateStatus(
                                  detail.incident.incident_id,
                                  "In Review",
                                  "Operator took ownership for dispatch review."
                                )
                                .then(() => undefined),
                            "Incident marked In Review."
                          )
                        }
                        className="w-full py-1.5 rounded-[4px] bg-[var(--bg-elevated)] hover:bg-[#24465F] border border-[var(--border-active)] text-[12px] font-semibold text-[var(--text-primary)] transition-colors"
                      >
                        Mark &lsquo;In Review&rsquo; (Operator Acknowledged)
                      </button>
                    )}

                    <div>
                      <label className="block text-[11px] font-semibold text-[var(--text-secondary)] mb-1">
                        Select Response Unit to Dispatch
                      </label>
                      <select
                        value={chosenTeamId}
                        onChange={(e) => setChosenTeamId(e.target.value)}
                        disabled={availableTeams.length === 0}
                        className="w-full px-2.5 py-2 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[12px] text-[var(--text-primary)] focus:outline-none focus:border-[var(--teal)]"
                      >
                        {availableTeams.length === 0 ? (
                          <option value="">No teams available</option>
                        ) : (
                          availableTeams.map((t) => (
                            <option key={t.team_id} value={t.team_id}>
                              {t.team_name} ({t.specialty}) — {zoneNameById.get(t.base_zone) || t.base_zone}
                            </option>
                          ))
                        )}
                      </select>
                    </div>

                    <div>
                      <label className="block text-[11px] font-semibold text-[var(--text-secondary)] mb-1">
                        Duty Chief Dispatch Directive
                      </label>
                      <input
                        type="text"
                        value={opNote}
                        onChange={(e) => setOpNote(e.target.value)}
                        placeholder="e.g. Deploy with inflatable boat and medical kit"
                        className="w-full px-2.5 py-2 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[12px] text-[var(--text-primary)] placeholder-[#6A8294] focus:outline-none focus:border-[var(--teal)]"
                      />
                    </div>

                    <button
                      type="button"
                      disabled={busy || !chosenTeamId}
                      onClick={() =>
                        runAction(
                          () =>
                            api
                              .approveDispatch(detail.incident.incident_id, chosenTeamId, opNote || undefined)
                              .then(() => {
                                setOpNote("");
                              }),
                          "Operator approved dispatch. Team assigned."
                        )
                      }
                      className="w-full py-2.5 rounded-[4px] bg-[var(--teal)] hover:bg-[var(--teal-hover)] text-[var(--teal-fg)] font-bold text-[12.5px] uppercase tracking-wider transition-colors disabled:opacity-50"
                    >
                      Authorize & Dispatch Team
                    </button>
                  </>
                )}

                {detail.incident.status === "Team Assigned" && (
                  <div className="space-y-2.5">
                    <div className="p-2.5 rounded-[4px] bg-[var(--teal)]/10 border border-[var(--teal)]/35 text-[12px] text-[var(--text-primary)]">
                      Assigned Unit:{" "}
                      <b>
                        {teamNameById.get(detail.incident.assigned_team_id || "") ||
                          detail.incident.assigned_team_id}
                      </b>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() =>
                          runAction(
                            () =>
                              api
                                .updateStatus(
                                  detail.incident.incident_id,
                                  "In Progress",
                                  "Team on-site and rescue operation underway."
                                )
                                .then(() => undefined),
                            "Incident marked In Progress."
                          )
                        }
                        className="py-2 rounded-[4px] bg-[var(--teal)] hover:bg-[var(--teal-hover)] text-[var(--teal-fg)] font-bold text-[12px]"
                      >
                        Mark &lsquo;In Progress&rsquo;
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() =>
                          runAction(
                            () =>
                              api
                                .updateStatus(
                                  detail.incident.incident_id,
                                  "In Review",
                                  "Assignment revoked by operator for reassignment."
                                )
                                .then(() => undefined),
                            "Assignment revoked; unit returned to Available."
                          )
                        }
                        className="py-2 rounded-[4px] bg-[var(--bg-elevated)] hover:bg-[#24465F] border border-[var(--border-active)] text-[12px] font-semibold text-[var(--text-primary)]"
                      >
                        Revoke / Re-assign
                      </button>
                    </div>
                  </div>
                )}

                {detail.incident.status === "In Progress" && (
                  <div className="space-y-2.5">
                    <div className="p-2.5 rounded-[4px] bg-[#55A8FF]/15 border border-[#55A8FF]/35 text-[12px] text-[#A0C9FF]">
                      Response operation is actively underway.
                    </div>
                    <input
                      type="text"
                      value={resNote}
                      onChange={(e) => setResNote(e.target.value)}
                      placeholder="Resolution note (e.g. All 3 residents evacuated)"
                      className="w-full px-2.5 py-2 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[12px] text-[var(--text-primary)] placeholder-[#6A8294] focus:outline-none focus:border-[var(--teal)]"
                    />
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        runAction(
                          () =>
                            api
                              .updateStatus(
                                detail.incident.incident_id,
                                "Resolved",
                                resNote || "Incident successfully resolved."
                              )
                              .then(() => setResNote("")),
                          "Incident marked Resolved; unit released."
                        )
                      }
                      className="w-full py-2.5 rounded-[4px] bg-[#37C98A] hover:bg-[#2fb37a] text-[var(--teal-fg)] font-bold text-[12.5px] uppercase tracking-wider"
                    >
                      Mark Incident Resolved
                    </button>
                  </div>
                )}

                {detail.incident.status === "Resolved" && (
                  <div className="p-2.5 rounded-[4px] bg-[#37C98A]/15 border border-[#37C98A]/40 text-[12px] text-[#37C98A]">
                    Incident is Resolved. Assigned response unit has been released back to Available duty.
                  </div>
                )}

                <Link
                  href={`/history?incident=${encodeURIComponent(detail.incident.incident_id)}`}
                  className="w-full inline-flex items-center justify-center gap-1.5 py-1.5 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] hover:border-[var(--teal)] text-[11.5px] font-semibold text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                >
                  <History className="w-3.5 h-3.5" />
                  View Audit Timeline in Incident History
                </Link>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function ControlRoomPage() {
  return (
    <Suspense fallback={<div className="p-6 text-[13px] text-[var(--text-secondary)]">Loading Response Control Room...</div>}>
      <ControlRoomInner />
    </Suspense>
  );
}
