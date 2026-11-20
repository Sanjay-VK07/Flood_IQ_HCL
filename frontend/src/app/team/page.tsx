"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  CheckCircle2,
  Clock,
  LogOut,
  MapPin,
  Play,
  Radio,
  RefreshCw,
  ShieldAlert,
  Users,
  Waves,
} from "lucide-react";
import { roleHomePath, useAuth } from "@/context/AuthContext";
import { useAutoPoll } from "@/hooks/useAutoPoll";
import { api } from "@/lib/api";
import { ThemeToggle } from "@/components/ThemeToggle";
import type { Incident, IncidentUpdate, ResponseTeam } from "@/lib/types";

const STATUS_BADGE: Record<string, string> = {
  "Team Assigned":
    "bg-[#F3E8FF] text-[#6B21A8] border-[#D8B4FE] dark:bg-[#A855F7]/15 dark:text-[#C084FC] dark:border-[#A855F7]/40",
  Acknowledged:
    "bg-[#F0FDFA] text-[#0F766E] border-[#99F6E4] dark:bg-[#21C7B7]/15 dark:text-[#21C7B7] dark:border-[#21C7B7]/40",
  "In Progress":
    "bg-[#FFF7ED] text-[#9A3412] border-[#FDBA74] dark:bg-[#F97316]/15 dark:text-[#FB923C] dark:border-[#F97316]/40",
  Resolved:
    "bg-[#ECFDF5] text-[#065F46] border-[#6EE7B7] dark:bg-[#37C98A]/15 dark:text-[#37C98A] dark:border-[#37C98A]/40",
};

export default function TeamPortalPage() {
  const router = useRouter();
  const { user, loading: authLoading, logout } = useAuth();

  const [team, setTeam] = useState<ResponseTeam | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [timelines, setTimelines] = useState<Record<string, IncidentUpdate[]>>({});

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace("/login?next=/team");
    } else if (user.role !== "response_team") {
      router.replace(roleHomePath(user.role));
    }
  }, [authLoading, router, user]);

  const loadAssigned = useCallback(async () => {
    if (!user || user.role !== "response_team") return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.listTeamIncidents();
      setTeam(res.team);
      setIncidents(res.incidents);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load assigned incidents.");
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    void loadAssigned();
  }, [loadAssigned]);

  useAutoPoll(
    useCallback(async () => {
      if (!user || user.role !== "response_team") return;
      try {
        const res = await api.listTeamIncidents();
        setTeam(res.team);
        setIncidents(res.incidents);
      } catch {
        // silent background poll
      }
    }, [user]),
    Boolean(user && user.role === "response_team"),
    4000
  );

  async function handleStatusTransition(incidentId: string, nextStatus: string) {
    setUpdatingId(incidentId);
    setError(null);
    try {
      const note = notes[incidentId]?.trim() || undefined;
      await api.updateStatus(incidentId, nextStatus, note);
      setNotes((prev) => ({ ...prev, [incidentId]: "" }));
      await loadAssigned();
      if (timelines[incidentId]) {
        const tl = await api.getTimeline(incidentId);
        setTimelines((prev) => ({ ...prev, [incidentId]: tl }));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update incident status.");
    } finally {
      setUpdatingId(null);
    }
  }

  async function toggleTimeline(incidentId: string) {
    if (timelines[incidentId]) {
      setTimelines((prev) => {
        const next = { ...prev };
        delete next[incidentId];
        return next;
      });
      return;
    }
    try {
      const tl = await api.getTimeline(incidentId);
      setTimelines((prev) => ({ ...prev, [incidentId]: tl }));
    } catch {
      // ignore
    }
  }

  if (authLoading || !user || user.role !== "response_team") {
    return (
      <div className="min-h-screen bg-[var(--bg-canvas)] text-[var(--text-primary)] flex items-center justify-center p-6">
        <div className="bg-[var(--bg-panel)] border border-[var(--border-hairline)] rounded-[10px] p-6 max-w-sm w-full text-center space-y-3">
          <div className="text-[15px] font-bold">Emergency Response Team Portal</div>
          <p className="text-[12px] text-[var(--text-secondary)]">
            {authLoading ? "Verifying team credentials..." : "Redirecting to sign in..."}
          </p>
          <Link
            href="/login"
            className="inline-block px-4 py-2 rounded-[6px] bg-[var(--teal)] text-[var(--teal-fg)] text-[12px] font-bold"
          >
            Go to Sign In
          </Link>
        </div>
      </div>
    );
  }

  const assignedCount = incidents.filter((i) => i.status === "Team Assigned").length;
  const activeCount = incidents.filter(
    (i) => i.status === "Acknowledged" || i.status === "In Progress"
  ).length;
  const resolvedCount = incidents.filter((i) => i.status === "Resolved").length;

  return (
    <div className="min-h-screen bg-[var(--bg-canvas)] text-[var(--text-primary)] pb-16">
      {/* Stitch Field Responder Header */}
      <header className="sticky top-0 z-30 bg-[var(--bg-rail)]/95 backdrop-blur border-b border-[var(--border-hairline)] px-4 py-3">
        <div className="max-w-4xl mx-auto flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-[8px] bg-[var(--teal)] text-[var(--teal-fg)] flex items-center justify-center shrink-0">
              <Waves className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[15px] font-bold text-[var(--text-primary)] truncate">
                  FloodIQ Field Responder
                </span>
                <span className="px-2 py-0.5 rounded-[4px] bg-[#FFFBEB] dark:bg-[#F59E0B]/15 border border-[#FCD34D] dark:border-[#F59E0B]/40 text-[#92400E] dark:text-[#F59E0B] text-[10px] font-bold uppercase">
                  Field Ops
                </span>
              </div>
              <p className="text-[11px] text-[var(--text-muted)] truncate">
                {team ? `${team.team_name} · ${team.specialty}` : user.email}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <ThemeToggle compact />
            <button
              type="button"
              onClick={() => void loadAssigned()}
              className="p-2 rounded-[6px] bg-[var(--bg-elevated)] hover:border-[var(--teal)] border border-[var(--border-hairline)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] cursor-pointer"
              aria-label="Refresh assigned queue"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            </button>
            <button
              type="button"
              onClick={async () => {
                await logout();
                router.replace("/login");
              }}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-[6px] bg-[var(--bg-elevated)] hover:border-[var(--teal)] border border-[var(--border-hairline)] text-[11.5px] font-semibold text-[var(--text-primary)] cursor-pointer"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Sign Out</span>
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 pt-4 space-y-4">
        {/* Tactical Unit Banner (Matches Stitch field_responder.png) */}
        <div className="p-3.5 rounded-[10px] bg-[#0B1C30] text-white flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#21C7B7]" />
            <div>
              <div className="text-[12px] font-bold uppercase tracking-wider text-[#21C7B7]">
                {team?.team_name || user.full_name} · {team?.team_id || user.team_id}
              </div>
              <div className="text-[11px] text-white/80">
                Base Zone: {team?.base_zone || "Assigned Sector"} · Auto-Sync Active (4s)
              </div>
            </div>
          </div>
          <span className="px-2.5 py-1 rounded-[6px] bg-white/10 border border-white/15 text-[11px] font-bold text-[#21C7B7]">
            <Radio className="w-3.5 h-3.5 inline mr-1" />
            DISPATCH LINKED
          </span>
        </div>

        {/* Queue KPIs */}
        <div className="grid grid-cols-3 gap-3">
          <div
            style={{ boxShadow: "var(--card-shadow)" }}
            className="bg-[var(--bg-panel)] border border-[var(--border-hairline)] rounded-[10px] p-3.5"
          >
            <div className="text-[10.5px] font-bold uppercase text-[var(--text-muted)]">
              New Dispatch
            </div>
            <div className="text-[22px] font-bold text-[#6B21A8] dark:text-[#C084FC] mt-0.5">
              {assignedCount}
            </div>
          </div>
          <div
            style={{ boxShadow: "var(--card-shadow)" }}
            className="bg-[var(--bg-panel)] border border-[var(--border-hairline)] rounded-[10px] p-3.5"
          >
            <div className="text-[10.5px] font-bold uppercase text-[var(--text-muted)]">
              Active Field
            </div>
            <div className="text-[22px] font-bold text-[var(--teal)] mt-0.5">{activeCount}</div>
          </div>
          <div
            style={{ boxShadow: "var(--card-shadow)" }}
            className="bg-[var(--bg-panel)] border border-[var(--border-hairline)] rounded-[10px] p-3.5"
          >
            <div className="text-[10.5px] font-bold uppercase text-[var(--text-muted)]">
              Resolved
            </div>
            <div className="text-[22px] font-bold text-[var(--low)] mt-0.5">{resolvedCount}</div>
          </div>
        </div>

        <div className="p-3 rounded-[8px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[12px] text-[var(--text-secondary)] flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-[var(--teal)] shrink-0" />
          <span>
            Showing only incidents approved and dispatched to{" "}
            <strong className="text-[var(--text-primary)]">{team?.team_id || user.team_id}</strong>{" "}
            by Municipal Authority.
          </span>
        </div>

        {error && (
          <div className="p-3 rounded-[8px] bg-[#FEF2F2] dark:bg-[#FF5364]/15 border border-[#FCA5A5] dark:border-[#FF5364]/45 text-[12.5px] text-[#991B1B] dark:text-[#FF8E99]">
            {error}
          </div>
        )}

        {/* Assigned Incidents List */}
        {loading && incidents.length === 0 ? (
          <div className="bg-[var(--bg-panel)] border border-[var(--border-hairline)] rounded-[12px] p-6 text-center text-[13px] text-[var(--text-secondary)]">
            Loading assigned dispatch queue...
          </div>
        ) : incidents.length === 0 ? (
          <div
            style={{ boxShadow: "var(--card-shadow)" }}
            className="bg-[var(--bg-panel)] border border-[var(--border-hairline)] rounded-[12px] p-6 text-center space-y-2"
          >
            <div className="text-[15px] font-bold text-[var(--text-primary)]">
              No Assigned Incidents
            </div>
            <p className="text-[12.5px] text-[var(--text-secondary)]">
              Your unit currently has no dispatched incidents. Stand by for Municipal Authority
              approval.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {incidents.map((inc) => {
              const isBusy = updatingId === inc.incident_id;
              const tl = timelines[inc.incident_id];
              return (
                <div
                  key={inc.incident_id}
                  style={{ boxShadow: "var(--card-shadow)" }}
                  className="bg-[var(--bg-panel)] border border-[var(--border-hairline)] rounded-[12px] p-4 sm:p-5 space-y-3.5"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="px-2 py-0.5 rounded-[4px] bg-[#DC2626] text-white text-[10.5px] font-bold uppercase">
                          Priority {inc.priority_score}
                        </span>
                        <span className="font-mono text-[12.5px] font-bold text-[var(--text-muted)]">
                          #{inc.incident_id}
                        </span>
                        {Boolean(inc.vulnerable_flag) && (
                          <span className="px-2 py-0.5 rounded-[4px] bg-[#FFFBEB] dark:bg-[#F59E0B]/15 border border-[#FCD34D] dark:border-[#F59E0B]/40 text-[#92400E] dark:text-[#F59E0B] text-[10.5px] font-bold">
                            {inc.vulnerable_group || "Vulnerable Group"}
                          </span>
                        )}
                      </div>
                      <div className="text-[13px] font-semibold text-[var(--text-secondary)] flex items-center gap-1.5 mt-1.5">
                        <MapPin className="w-4 h-4 text-[var(--teal)]" />
                        <span>
                          {inc.zone_id} {inc.location_text ? `· ${inc.location_text}` : ""}
                        </span>
                      </div>
                    </div>

                    <span
                      className={`px-2.5 py-1 rounded-[5px] text-[11px] font-bold border shrink-0 ${
                        STATUS_BADGE[inc.status] ||
                        "bg-[var(--bg-elevated)] text-[var(--text-primary)] border-[var(--border-hairline)]"
                      }`}
                    >
                      {inc.status}
                    </span>
                  </div>

                  <p className="text-[14px] text-[var(--text-primary)] leading-relaxed">
                    {inc.description}
                  </p>

                  {/* 3-Card Telemetry Row */}
                  <div className="grid grid-cols-3 gap-2 text-[12px]">
                    <div className="p-2.5 rounded-[8px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)]">
                      <div className="text-[10px] font-bold uppercase text-[var(--text-muted)]">
                        Affected
                      </div>
                      <div className="font-bold text-[var(--text-primary)] flex items-center gap-1 mt-0.5">
                        <Users className="w-3.5 h-3.5 text-[var(--teal)]" />
                        {inc.people_affected}
                      </div>
                    </div>
                    <div className="p-2.5 rounded-[8px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)]">
                      <div className="text-[10px] font-bold uppercase text-[var(--text-muted)]">
                        Category
                      </div>
                      <div className="font-bold text-[var(--text-primary)] truncate mt-0.5">
                        {inc.ai_category || inc.reported_category}
                      </div>
                    </div>
                    <div className="p-2.5 rounded-[8px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)]">
                      <div className="text-[10px] font-bold uppercase text-[var(--text-muted)]">
                        Urgency
                      </div>
                      <div className="font-bold text-[var(--critical)] mt-0.5">
                        {inc.ai_urgency || "Medium"}
                      </div>
                    </div>
                  </div>

                  {inc.ai_rationale && (
                    <div className="p-3 rounded-[8px] bg-[var(--bg-elevated)] border-l-4 border-[var(--teal)] text-[12px] text-[var(--text-secondary)]">
                      <strong className="text-[var(--teal)] uppercase text-[10.5px] block mb-0.5">
                        Command Triage Note ({inc.triage_mode === "groq" ? "Groq AI" : "Rule-Based"})
                      </strong>
                      {inc.ai_rationale}
                    </div>
                  )}

                  {inc.photo_data_url && (
                    <img
                      src={inc.photo_data_url}
                      alt="Citizen uploaded incident evidence"
                      className="max-h-48 rounded-[8px] border border-[var(--border-hairline)] object-cover"
                    />
                  )}

                  {inc.status !== "Resolved" && (
                    <div className="pt-3 border-t border-[var(--border-hairline)] space-y-2.5">
                      <div className="text-[10.5px] font-bold uppercase tracking-[0.06em] text-[var(--text-muted)]">
                        Field Execution Controls
                      </div>
                      <input
                        type="text"
                        value={notes[inc.incident_id] || ""}
                        onChange={(e) =>
                          setNotes((prev) => ({ ...prev, [inc.incident_id]: e.target.value }))
                        }
                        placeholder="Field note (e.g., En route via Chaderghat, 2 boats deployed)..."
                        className="w-full px-3 py-2.5 rounded-[8px] bg-[var(--bg-input)] border border-[var(--border-active)] text-[12.5px] text-[var(--text-primary)]"
                      />

                      <div className="flex flex-wrap gap-2">
                        {inc.status === "Team Assigned" && (
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => void handleStatusTransition(inc.incident_id, "Acknowledged")}
                            className="flex-1 min-w-[160px] py-3 px-4 rounded-[8px] bg-[var(--teal)] hover:bg-[var(--teal-hover)] text-[var(--teal-fg)] text-[13px] font-bold flex items-center justify-center gap-2 disabled:opacity-50 cursor-pointer"
                          >
                            <CheckCircle2 className="w-4 h-4" />
                            <span>Acknowledge Assignment</span>
                          </button>
                        )}

                        {(inc.status === "Team Assigned" || inc.status === "Acknowledged") && (
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => void handleStatusTransition(inc.incident_id, "In Progress")}
                            className="flex-1 min-w-[160px] py-3 px-4 rounded-[8px] bg-[#D97706] hover:bg-[#B45309] text-white text-[13px] font-bold flex items-center justify-center gap-2 disabled:opacity-50 cursor-pointer"
                          >
                            <Play className="w-4 h-4" />
                            <span>On-Scene / Start Response</span>
                          </button>
                        )}

                        {inc.status === "In Progress" && (
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => void handleStatusTransition(inc.incident_id, "Resolved")}
                            className="flex-1 min-w-[160px] py-3 px-4 rounded-[8px] bg-[#059669] hover:bg-[#047857] text-white text-[13px] font-bold flex items-center justify-center gap-2 disabled:opacity-50 cursor-pointer"
                          >
                            <CheckCircle2 className="w-4 h-4" />
                            <span>Mark Mission Resolved</span>
                          </button>
                        )}
                      </div>
                    </div>
                  )}

                  <button
                    type="button"
                    onClick={() => void toggleTimeline(inc.incident_id)}
                    className="text-[12px] text-[var(--blue)] font-semibold flex items-center gap-1 cursor-pointer"
                  >
                    <Clock className="w-3.5 h-3.5" />
                    <span>{tl ? "Hide Timeline" : "View Incident Timeline"}</span>
                  </button>

                  {tl && (
                    <div className="pt-2 border-t border-[var(--border-hairline)] space-y-1.5">
                      {tl.map((u) => (
                        <div key={u.update_id} className="text-[12px] flex justify-between gap-2">
                          <div>
                            <span className="font-bold text-[var(--text-primary)]">
                              {u.new_status}
                            </span>
                            <span className="text-[var(--text-secondary)]"> — {u.note}</span>
                          </div>
                          <span className="text-[var(--text-muted)] font-mono text-[11px] shrink-0">
                            {u.updated_at.slice(0, 16).replace("T", " ")}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
