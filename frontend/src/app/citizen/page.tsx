"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  ClipboardList,
  Clock,
  LayoutGrid,
  LogIn,
  LogOut,
  MapPin,
  Minus,
  Phone,
  Plus,
  Repeat,
  Search,
  ShieldCheck,
  Siren,
  Waves,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useSimulation } from "@/context/SimulationContext";
import { useAutoPoll } from "@/hooks/useAutoPoll";
import { api } from "@/lib/api";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Badge, toneFromBand } from "@/components/Badge";
import type {
  EvaluatedZone,
  Incident,
  IncidentUpdate,
  PublicTrackResponse,
  ZoneRaw,
} from "@/lib/types";

type CitizenTab = "overview" | "report" | "my-incidents" | "track" | "safety";

const CATEGORIES = [
  { id: "Water Rescue", label: "Water Rescue / Stranded", desc: "People trapped by rising floodwaters" },
  { id: "Road Blockage", label: "Road Inundation / Blocked", desc: "Submerged road or traffic impassable" },
  { id: "Drainage Blockage", label: "Drainage / Nala Overflow", desc: "Blocked storm drain or waterlogging" },
  { id: "Power Hazard", label: "Electrical / Power Hazard", desc: "Downed wire or flooded transformer" },
  { id: "Shelter / Relief", label: "Shelter & Relief Aid", desc: "Evacuation shelter or supply request" },
  { id: "Other", label: "Other Flood Incident", desc: "General urban flood hazard report" },
];

const STATUS_BADGE: Record<string, string> = {
  Triaged: "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE] dark:bg-[#55A8FF]/15 dark:text-[#55A8FF] dark:border-[#55A8FF]/40",
  "In Review": "bg-[#FFFBEB] text-[#92400E] border-[#FCD34D] dark:bg-[#E8C45A]/15 dark:text-[#E8C45A] dark:border-[#E8C45A]/40",
  "Team Assigned": "bg-[#F3E8FF] text-[#6B21A8] border-[#D8B4FE] dark:bg-[#A855F7]/15 dark:text-[#C084FC] dark:border-[#A855F7]/40",
  Acknowledged: "bg-[#F0FDFA] text-[#0F766E] border-[#99F6E4] dark:bg-[#21C7B7]/15 dark:text-[#21C7B7] dark:border-[#21C7B7]/40",
  "In Progress": "bg-[#FFF7ED] text-[#9A3412] border-[#FDBA74] dark:bg-[#F97316]/15 dark:text-[#FB923C] dark:border-[#F97316]/40",
  Resolved: "bg-[#ECFDF5] text-[#065F46] border-[#6EE7B7] dark:bg-[#37C98A]/15 dark:text-[#37C98A] dark:border-[#37C98A]/40",
};

export default function CitizenPortalPage() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const { rainfallMm, useSimulation: isSim } = useSimulation();

  const [tab, setTab] = useState<CitizenTab>("overview");
  const [zones, setZones] = useState<ZoneRaw[]>([]);
  const [riskZones, setRiskZones] = useState<EvaluatedZone[]>([]);
  const [myIncidents, setMyIncidents] = useState<Incident[]>([]);
  const [selectedTimeline, setSelectedTimeline] = useState<Record<string, IncidentUpdate[]>>({});
  const [loadingList, setLoadingList] = useState(false);

  const [zoneId, setZoneId] = useState("musi_riverfront");
  const [category, setCategory] = useState("Water Rescue");
  const [locationText, setLocationText] = useState("");
  const [peopleAffected, setPeopleAffected] = useState(1);
  const [description, setDescription] = useState("");
  const [photoDataUrl, setPhotoDataUrl] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submittedReceipt, setSubmittedReceipt] = useState<{
    incident: Incident;
    timeline: IncidentUpdate[];
  } | null>(null);

  const [trackId, setTrackId] = useState("");
  const [trackCode, setTrackCode] = useState("");
  const [trackResult, setTrackResult] = useState<PublicTrackResponse | null>(null);
  const [trackError, setTrackError] = useState<string | null>(null);
  const [trackingLoading, setTrackingLoading] = useState(false);

  const loadBaseData = useCallback(async () => {
    try {
      const [zList, riskRes] = await Promise.all([
        api.getZones(),
        api.simulateRisk(rainfallMm, isSim),
      ]);
      setZones(zList);
      setRiskZones(riskRes.zones);
      if (zList.length > 0 && !zList.some((z) => z.zone_id === zoneId)) {
        setZoneId(zList[0].zone_id);
      }
    } catch {
      // non-fatal
    }
  }, [isSim, rainfallMm, zoneId]);

  const loadMyIncidents = useCallback(async () => {
    if (!user || (user.role !== "citizen" && user.role !== "authority")) {
      setMyIncidents([]);
      return;
    }
    setLoadingList(true);
    try {
      const list = await api.listCitizenIncidents();
      setMyIncidents(list);
    } catch {
      setMyIncidents([]);
    } finally {
      setLoadingList(false);
    }
  }, [user]);

  useEffect(() => {
    void loadBaseData();
  }, [loadBaseData]);

  useEffect(() => {
    void loadMyIncidents();
  }, [loadMyIncidents]);

  useAutoPoll(
    useCallback(async () => {
      if (tab === "my-incidents" && user) {
        await loadMyIncidents();
        const expandedIds = Object.keys(selectedTimeline);
        if (expandedIds.length > 0) {
          const entries = await Promise.all(
            expandedIds.map(async (id) => [id, await api.getTimeline(id)] as const)
          );
          setSelectedTimeline((prev) => ({ ...prev, ...Object.fromEntries(entries) }));
        }
      } else if (tab === "track" && trackResult && trackId && trackCode) {
        try {
          const updated = await api.trackPublicIncident(trackId.trim(), trackCode.trim());
          setTrackResult(updated);
        } catch {
          // ignore transient poll error
        }
      }
    }, [loadMyIncidents, selectedTimeline, tab, trackCode, trackId, trackResult, user]),
    (tab === "my-incidents" && Boolean(user)) || (tab === "track" && Boolean(trackResult)),
    4000
  );

  function handlePhotoChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) {
      setPhotoDataUrl(null);
      return;
    }
    if (file.size > 450 * 1024) {
      setSubmitError("Photo must be under 450 KB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        setSubmitError(null);
        setPhotoDataUrl(reader.result);
      }
    };
    reader.readAsDataURL(file);
  }

  async function handleSubmitReport(e: React.FormEvent) {
    e.preventDefault();
    setSubmitError(null);
    setSubmitting(true);
    try {
      const res = await api.createIncident({
        zone_id: zoneId,
        reported_category: category,
        location_text: locationText,
        people_affected: peopleAffected,
        description,
        photo_data_url: photoDataUrl,
      });
      setSubmittedReceipt({ incident: res.incident, timeline: res.timeline });
      setTrackId(res.incident.incident_id);
      setTrackCode(res.incident.tracking_code || "");
      setDescription("");
      setLocationText("");
      setPhotoDataUrl(null);
      setPeopleAffected(1);
      await loadMyIncidents();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to submit incident.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTrackLookup(e: React.FormEvent) {
    e.preventDefault();
    setTrackError(null);
    setTrackResult(null);
    setTrackingLoading(true);
    try {
      const res = await api.trackPublicIncident(trackId.trim(), trackCode.trim());
      setTrackResult(res);
    } catch (err) {
      setTrackError(err instanceof Error ? err.message : "Incident not found.");
    } finally {
      setTrackingLoading(false);
    }
  }

  async function toggleTimeline(incId: string) {
    if (selectedTimeline[incId]) {
      setSelectedTimeline((prev) => {
        const next = { ...prev };
        delete next[incId];
        return next;
      });
      return;
    }
    try {
      const tl = await api.getTimeline(incId);
      setSelectedTimeline((prev) => ({ ...prev, [incId]: tl }));
    } catch {
      // ignore
    }
  }

  const highRiskCount = riskZones.filter(
    (z) => z.risk_level === "High" || z.risk_level === "Critical"
  ).length;
  const topZone = riskZones[0];

  const NAV_TABS = [
    { id: "overview" as const, label: "Dashboard", icon: LayoutGrid },
    { id: "report" as const, label: "Report", icon: Siren },
    { id: "my-incidents" as const, label: "My Reports", icon: ClipboardList },
    { id: "track" as const, label: "Tracking", icon: Search },
    { id: "safety" as const, label: "Safety", icon: ShieldCheck },
  ];

  return (
    <div className="min-h-screen bg-[var(--bg-canvas)] text-[var(--text-primary)] pb-24 md:pb-12">
      {/* Stitch Citizen Header */}
      <header className="sticky top-0 z-30 bg-[var(--bg-rail)]/95 backdrop-blur border-b border-[var(--border-hairline)] px-4 py-3">
        <div className="max-w-4xl mx-auto flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-[8px] bg-[var(--teal)] text-[var(--teal-fg)] flex items-center justify-center shrink-0">
              <Waves className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[15px] font-bold tracking-tight text-[var(--text-primary)]">
                  FloodIQ
                </span>
                <span className="px-2 py-0.5 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[var(--teal)] text-[10px] font-bold uppercase">
                  Citizen Portal
                </span>
              </div>
              <p className="text-[11px] text-[var(--text-muted)] truncate">
                {user
                  ? `${user.full_name} · Account Linked`
                  : "Guest Mode · Save tracking code after reporting"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <ThemeToggle compact />
            {user ? (
              <button
                type="button"
                onClick={async () => {
                  await logout();
                  router.push("/login");
                }}
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-[6px] bg-[var(--bg-elevated)] hover:border-[var(--teal)] border border-[var(--border-hairline)] text-[11.5px] font-semibold text-[var(--text-primary)] cursor-pointer"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Sign Out</span>
              </button>
            ) : (
              <Link
                href="/login"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[6px] bg-[var(--teal)] text-[var(--teal-fg)] text-[11.5px] font-bold"
              >
                <LogIn className="w-3.5 h-3.5" />
                <span>Sign In</span>
              </Link>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 pt-4 space-y-4">
        {/* Live Advisory Strip */}
        <div className="px-3 py-2 rounded-[8px] bg-[#FEF2F2] dark:bg-[#FF5364]/15 border border-[#FCA5A5] dark:border-[#FF5364]/40 flex items-center justify-between gap-2 text-[11.5px] font-bold text-[#991B1B] dark:text-[#FF8E99]">
          <div className="flex items-center gap-2 min-w-0">
            <span className="w-2 h-2 rounded-full bg-[#DC2626] dark:bg-[#FF5364] shrink-0" />
            <span className="truncate">
              LIVE ADVISORY: {highRiskCount} OF {riskZones.length || 5} HYDERABAD ZONES AT HIGH/CRITICAL RISK
            </span>
          </div>
          <span className="shrink-0 font-mono">{rainfallMm} mm</span>
        </div>

        {/* Tablet / Desktop Top Tab Bar */}
        <nav className="hidden md:grid grid-cols-5 gap-1.5 bg-[var(--bg-panel)] p-1.5 rounded-[10px] border border-[var(--border-hairline)]">
          {NAV_TABS.map((item) => {
            const Icon = item.icon;
            const active = tab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                className={`flex items-center justify-center gap-1.5 py-2 px-2 rounded-[7px] text-[12px] font-semibold transition-colors cursor-pointer ${
                  active
                    ? "bg-[var(--teal)] text-[var(--teal-fg)] font-bold"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)] hover:text-[var(--text-primary)]"
                }`}
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        {/* TAB 1: CITIZEN FLOOD DASHBOARD (Matches Stitch Light & Dark) */}
        {tab === "overview" && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Critical Telemetry / Zone Flood Advisory Card */}
              <div className="rounded-[12px] p-5 bg-[#DC2626] text-white space-y-3 shadow-sm">
                <div className="flex items-center justify-between text-[10.5px] font-bold uppercase tracking-[0.06em]">
                  <span className="px-2 py-0.5 rounded bg-white/15">Zone Risk Advisory</span>
                  <span>{isSim ? "Scenario Input" : "Open-Meteo"}</span>
                </div>
                <div className="flex items-start gap-2.5">
                  <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
                  <div>
                    <h1 className="text-[18px] font-bold leading-snug">
                      {topZone
                        ? `${topZone.zone_name}: ${topZone.risk_level} Flood Risk`
                        : "Hyderabad Pilot Flood Monitoring"}
                    </h1>
                    <p className="text-[12.5px] text-white/90 mt-1">
                      {topZone
                        ? `Current explainable risk index is ${topZone.risk_score}/100 under ${topZone.rainfall_mm} mm rainfall.`
                        : "Monitor local flood risk and submit emergency reports directly to Municipal Authority."}
                    </p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 pt-2 border-t border-white/20 text-[12px]">
                  <div>
                    <div className="text-[10px] uppercase text-white/80 font-bold">Highest Zone</div>
                    <div className="font-bold text-[15px]">
                      {topZone ? `${topZone.risk_score}/100` : "—"}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase text-white/80 font-bold">Rainfall Feed</div>
                    <div className="font-bold text-[15px]">{rainfallMm} mm</div>
                  </div>
                </div>
              </div>

              {/* Priority SOS Line CTA Card (Matches Stitch Teal Card) */}
              <div className="rounded-[12px] p-5 bg-[#00685F] dark:bg-[#0D4F49] text-white flex flex-col justify-between space-y-4 shadow-sm">
                <div className="space-y-2">
                  <span className="inline-block px-2 py-0.5 rounded bg-[#DC2626] text-white text-[10px] font-bold uppercase tracking-wider">
                    Priority SOS Line
                  </span>
                  <h2 className="text-[20px] font-bold leading-tight">
                    Report Flooding &amp; Request Aid
                  </h2>
                  <p className="text-[12.5px] text-white/90">
                    Direct pipeline to Municipal Authority Operations &amp; Emergency Response Teams.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setTab("report")}
                  className="w-full py-3 px-4 rounded-[8px] bg-white/15 hover:bg-white/25 border border-white/25 text-white text-[13.5px] font-bold flex items-center justify-between transition-colors cursor-pointer"
                >
                  <span>Submit Emergency Report</span>
                  <span>→</span>
                </button>
              </div>
            </div>

            {/* Rapid Emergency Desks */}
            <div className="space-y-2">
              <div className="flex items-center justify-between px-1">
                <span className="text-[11px] font-bold uppercase tracking-[0.06em] text-[var(--text-muted)]">
                  Rapid Emergency Desks
                </span>
                <span className="text-[11px] font-semibold text-[var(--teal)]">Toll-free 24/7</span>
              </div>
              <div className="grid grid-cols-3 gap-2.5">
                {[
                  { num: "112", label: "Flood Rescue" },
                  { num: "108", label: "Medical Desk" },
                  { num: "1800-FL", label: "Civic Control" },
                ].map((d) => (
                  <div
                    key={d.num}
                    style={{ boxShadow: "var(--card-shadow)" }}
                    className="p-3 rounded-[10px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] text-center space-y-1"
                  >
                    <Phone className="w-4 h-4 mx-auto text-[var(--teal)]" />
                    <div className="text-[15px] font-bold text-[var(--text-primary)]">{d.num}</div>
                    <div className="text-[11px] text-[var(--text-muted)]">{d.label}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Neighborhood Live Status (Real Backend Zone Data) */}
            <div
              style={{ boxShadow: "var(--card-shadow)" }}
              className="rounded-[12px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] p-4 space-y-3"
            >
              <div className="flex items-center justify-between">
                <h2 className="text-[15px] font-bold text-[var(--text-primary)]">
                  Neighborhood Live Status
                </h2>
                <span className="text-[11px] font-semibold text-[var(--teal)]">
                  5 Pilot Zones
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {riskZones.map((z) => (
                  <div
                    key={z.zone_id}
                    className="p-3 rounded-[8px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] flex items-center justify-between gap-3"
                  >
                    <div className="min-w-0">
                      <div className="text-[13.5px] font-bold text-[var(--text-primary)] truncate">
                        {z.zone_name}
                      </div>
                      <div className="text-[11.5px] text-[var(--text-secondary)]">
                        Risk: <strong className="text-[var(--text-primary)]">{z.risk_score}/100</strong> · Rain:{" "}
                        {z.rainfall_mm} mm
                      </div>
                    </div>
                    <Badge tone={toneFromBand(z.risk_level)}>{z.risk_level}</Badge>
                  </div>
                ))}
              </div>
            </div>

            {/* Quick My Reports / Track Banner */}
            <div
              style={{ boxShadow: "var(--card-shadow)" }}
              className="rounded-[12px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] p-4 flex flex-wrap items-center justify-between gap-3"
            >
              <div>
                <div className="text-[14px] font-bold text-[var(--text-primary)]">
                  {user ? `My Active Reports (${myIncidents.length})` : "Track Your Incident"}
                </div>
                <p className="text-[12px] text-[var(--text-secondary)]">
                  {user
                    ? "View live authority review, assigned response team, and chronological timeline."
                    : "Have an Incident ID and Tracking Code (TRK-...)? Check live dispatch status."}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setTab(user ? "my-incidents" : "track")}
                className="px-4 py-2 rounded-[8px] bg-[var(--teal)] hover:bg-[var(--teal-hover)] text-[var(--teal-fg)] text-[12.5px] font-bold cursor-pointer"
              >
                {user ? "Open My Reports" : "Track by Code"}
              </button>
            </div>
          </div>
        )}

        {/* TAB 2: REPORT EMERGENCY (Matches Stitch report_emergency.png) */}
        {tab === "report" && (
          <div
            style={{ boxShadow: "var(--card-shadow)" }}
            className="rounded-[12px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] p-5 space-y-5"
          >
            <div className="space-y-1 border-b border-[var(--border-hairline)] pb-3">
              <div className="flex items-center justify-between gap-2">
                <span className="px-2 py-0.5 rounded-[4px] bg-[#DC2626] text-white text-[10px] font-bold uppercase tracking-wider">
                  Priority Triage Channel
                </span>
                <span className="text-[11px] font-semibold text-[var(--teal)]">
                  {user ? "Account Linked" : "Guest Report"}
                </span>
              </div>
              <h2 className="text-[20px] font-bold text-[var(--text-primary)] pt-1">
                Report Flood Hazard or Request Rescue
              </h2>
              <p className="text-[12.5px] text-[var(--text-secondary)]">
                Your report is stored immediately and AI-assisted triage prioritizes municipal review.
              </p>
            </div>

            {submittedReceipt && (
              <div className="p-4 rounded-[10px] bg-[#ECFDF5] dark:bg-[#37C98A]/10 border border-[#6EE7B7] dark:border-[#37C98A]/40 space-y-2.5">
                <div className="flex items-center gap-2 text-[#065F46] dark:text-[#37C98A] font-bold text-[14px]">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Incident Submitted &amp; Triaged</span>
                </div>
                <div className="grid grid-cols-2 gap-2.5 text-[12px]">
                  <div className="p-2.5 rounded-[8px] bg-[var(--bg-panel)] border border-[var(--border-hairline)]">
                    <div className="text-[var(--text-muted)] text-[10px] uppercase font-bold">
                      Incident ID
                    </div>
                    <div className="font-mono font-bold text-[var(--text-primary)]">
                      {submittedReceipt.incident.incident_id}
                    </div>
                  </div>
                  <div className="p-2.5 rounded-[8px] bg-[var(--bg-panel)] border border-[var(--border-hairline)]">
                    <div className="text-[var(--text-muted)] text-[10px] uppercase font-bold">
                      Tracking Code
                    </div>
                    <div className="font-mono font-bold text-[var(--teal)]">
                      {submittedReceipt.incident.tracking_code}
                    </div>
                  </div>
                </div>
                <p className="text-[12px] text-[var(--text-secondary)]">
                  AI-assisted triage has been performed automatically after submission (
                  <strong>{submittedReceipt.incident.ai_category}</strong>,{" "}
                  <strong>{submittedReceipt.incident.ai_urgency}</strong> urgency) to help municipal
                  authorities prioritize review. Save your Incident ID and Tracking Code above to
                  check live status anytime.
                </p>
                <button
                  type="button"
                  onClick={() => setTab(user ? "my-incidents" : "track")}
                  className="text-[12.5px] font-bold text-[var(--teal)] underline cursor-pointer"
                >
                  View Status &amp; Timeline →
                </button>
              </div>
            )}

            {submitError && (
              <div className="p-3 rounded-[8px] bg-[#FEF2F2] dark:bg-[#FF5364]/15 border border-[#FCA5A5] dark:border-[#FF5364]/45 text-[12.5px] text-[#991B1B] dark:text-[#FF8E99]">
                {submitError}
              </div>
            )}

            <form onSubmit={handleSubmitReport} className="space-y-4">
              {/* Zone & Landmark */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label
                    htmlFor="citizen-zone"
                    className="block text-[11px] font-bold uppercase text-[var(--text-secondary)] mb-1"
                  >
                    Pilot Zone
                  </label>
                  <select
                    id="citizen-zone"
                    value={zoneId}
                    onChange={(e) => setZoneId(e.target.value)}
                    className="w-full px-3 py-2.5 rounded-[8px] bg-[var(--bg-input)] border border-[var(--border-active)] text-[13.5px] text-[var(--text-primary)]"
                  >
                    {zones.map((z) => (
                      <option key={z.zone_id} value={z.zone_id}>
                        {z.zone_name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label
                    htmlFor="citizen-landmark"
                    className="block text-[11px] font-bold uppercase text-[var(--text-secondary)] mb-1"
                  >
                    Landmark / Street Address
                  </label>
                  <input
                    id="citizen-landmark"
                    type="text"
                    required
                    value={locationText}
                    onChange={(e) => setLocationText(e.target.value)}
                    placeholder="e.g., Chaderghat Low Bridge Lane 4"
                    className="w-full px-3 py-2.5 rounded-[8px] bg-[var(--bg-input)] border border-[var(--border-active)] text-[13.5px] text-[var(--text-primary)]"
                  />
                </div>
              </div>

              {/* 1. Emergency Type Selector Cards */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[12px] font-bold text-[var(--text-primary)]">
                    1. Select Emergency Type
                  </span>
                  <span className="text-[10.5px] font-bold uppercase text-[var(--teal)]">
                    Select One
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {CATEGORIES.map((c) => {
                    const active = category === c.id;
                    return (
                      <button
                        key={c.id}
                        type="button"
                        onClick={() => setCategory(c.id)}
                        className={`p-3 rounded-[10px] border text-left transition-all cursor-pointer ${
                          active
                            ? "bg-[var(--bg-elevated)] border-[var(--teal)] ring-1 ring-[var(--teal)]/30"
                            : "bg-[var(--bg-panel)] border-[var(--border-hairline)] hover:border-[var(--border-active)]"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-[13px] font-bold text-[var(--text-primary)]">
                            {c.label}
                          </span>
                          <span
                            className={`w-4 h-4 rounded-full border flex items-center justify-center text-[10px] ${
                              active
                                ? "bg-[var(--teal)] border-[var(--teal)] text-[var(--teal-fg)]"
                                : "border-[var(--border-active)]"
                            }`}
                          >
                            {active ? "✓" : ""}
                          </span>
                        </div>
                        <p className="text-[11.5px] text-[var(--text-muted)] mt-0.5">{c.desc}</p>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* People at Location Stepper */}
              <div className="p-3.5 rounded-[10px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] flex items-center justify-between gap-3">
                <div>
                  <div className="text-[13px] font-bold text-[var(--text-primary)]">
                    People at Location
                  </div>
                  <div className="text-[11px] text-[var(--text-muted)]">
                    Helps municipal dispatch allocate rescue capacity
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    aria-label="Decrease people count"
                    onClick={() => setPeopleAffected((p) => Math.max(0, p - 1))}
                    className="w-9 h-9 rounded-[8px] bg-[var(--bg-panel)] border border-[var(--border-active)] flex items-center justify-center text-[var(--text-primary)] cursor-pointer"
                  >
                    <Minus className="w-4 h-4" />
                  </button>
                  <span className="w-8 text-center text-[16px] font-bold text-[var(--text-primary)]">
                    {peopleAffected}
                  </span>
                  <button
                    type="button"
                    aria-label="Increase people count"
                    onClick={() => setPeopleAffected((p) => Math.min(500, p + 1))}
                    className="w-9 h-9 rounded-[8px] bg-[var(--bg-panel)] border border-[var(--border-active)] flex items-center justify-center text-[var(--text-primary)] cursor-pointer"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Situation Details */}
              <div>
                <label
                  htmlFor="citizen-desc"
                  className="block text-[11px] font-bold uppercase text-[var(--text-secondary)] mb-1"
                >
                  Situation Details
                </label>
                <textarea
                  id="citizen-desc"
                  required
                  rows={3}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Describe water depth, stranded persons, elderly/medical needs, or immediate hazards..."
                  className="w-full px-3 py-2.5 rounded-[8px] bg-[var(--bg-input)] border border-[var(--border-active)] text-[13.5px] text-[var(--text-primary)]"
                />
              </div>

              {/* Optional Photo Evidence */}
              <div>
                <span className="block text-[11px] font-bold uppercase text-[var(--text-secondary)] mb-1">
                  Visual Evidence (Optional, Max 450 KB)
                </span>
                <label className="flex items-center gap-2 px-3 py-2.5 rounded-[8px] bg-[var(--bg-elevated)] border border-dashed border-[var(--border-active)] cursor-pointer text-[12.5px] text-[var(--text-secondary)] hover:border-[var(--teal)]">
                  <Camera className="w-4 h-4 text-[var(--teal)]" />
                  <span>{photoDataUrl ? "Photo attached (click to replace)" : "Upload photo"}</span>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handlePhotoChange}
                    className="hidden"
                  />
                </label>
                {photoDataUrl && (
                  <img
                    src={photoDataUrl}
                    alt="Uploaded flood report preview"
                    className="mt-2 max-h-40 rounded-[8px] border border-[var(--border-hairline)] object-cover"
                  />
                )}
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="w-full py-3 rounded-[8px] bg-[#DC2626] hover:bg-[#B91C1C] text-white text-[13.5px] font-bold uppercase tracking-wider transition-colors disabled:opacity-50 cursor-pointer"
              >
                {submitting ? "Transmitting Report..." : "Transmit Emergency Report"}
              </button>
            </form>
          </div>
        )}

        {/* TAB 3: MY SUBMITTED INCIDENTS */}
        {tab === "my-incidents" && (
          <div
            style={{ boxShadow: "var(--card-shadow)" }}
            className="rounded-[12px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] p-4 space-y-3"
          >
            <div className="flex items-center justify-between">
              <h2 className="text-[16px] font-bold text-[var(--text-primary)]">
                My Submitted Incidents
              </h2>
              {user && (
                <button
                  type="button"
                  onClick={() => void loadMyIncidents()}
                  className="text-[12px] text-[var(--teal)] font-semibold cursor-pointer"
                >
                  Auto-Syncing (4s) · Refresh
                </button>
              )}
            </div>

            {!user ? (
              <div className="p-5 rounded-[10px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-center space-y-3">
                <p className="text-[13px] text-[var(--text-secondary)]">
                  Sign in as a Citizen to view your linked incident history, or use the Tracking tab
                  with your Guest Tracking Code.
                </p>
                <div className="flex justify-center gap-2">
                  <Link
                    href="/login"
                    className="px-4 py-2 rounded-[6px] bg-[var(--teal)] text-[var(--teal-fg)] text-[12px] font-bold"
                  >
                    Sign In
                  </Link>
                  <button
                    type="button"
                    onClick={() => setTab("track")}
                    className="px-4 py-2 rounded-[6px] bg-[var(--bg-panel)] border border-[var(--border-active)] text-[12px] font-semibold text-[var(--text-primary)]"
                  >
                    Track Guest Report
                  </button>
                </div>
              </div>
            ) : loadingList && myIncidents.length === 0 ? (
              <p className="text-[12.5px] text-[var(--text-secondary)]">Loading your incidents...</p>
            ) : myIncidents.length === 0 ? (
              <p className="text-[12.5px] text-[var(--text-secondary)]">
                No incidents submitted from this account yet.
              </p>
            ) : (
              <div className="space-y-3">
                {myIncidents.map((inc) => {
                  const tl = selectedTimeline[inc.incident_id];
                  return (
                    <div
                      key={inc.incident_id}
                      className="p-4 rounded-[10px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] space-y-2.5"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-mono text-[12.5px] font-bold text-[var(--text-primary)]">
                              {inc.incident_id}
                            </span>
                            {inc.tracking_code && (
                              <span className="font-mono text-[11.5px] text-[var(--teal)] font-semibold">
                                {inc.tracking_code}
                              </span>
                            )}
                          </div>
                          <div className="text-[12px] text-[var(--text-secondary)] flex items-center gap-1 mt-0.5">
                            <MapPin className="w-3.5 h-3.5 text-[var(--teal)]" />
                            <span>
                              {inc.zone_id} {inc.location_text ? `· ${inc.location_text}` : ""}
                            </span>
                          </div>
                        </div>
                        <span
                          className={`px-2 py-0.5 rounded-[4px] text-[11px] font-bold border ${
                            STATUS_BADGE[inc.status] ||
                            "bg-[var(--bg-panel)] text-[var(--text-primary)] border-[var(--border-hairline)]"
                          }`}
                        >
                          {inc.status}
                        </span>
                      </div>

                      <p className="text-[13px] text-[var(--text-primary)]">{inc.description}</p>

                      {inc.assigned_team_id && (
                        <div className="text-[12px] text-[var(--teal)] font-semibold">
                          Assigned Team: {inc.assigned_team_id}
                        </div>
                      )}

                      <button
                        type="button"
                        onClick={() => void toggleTimeline(inc.incident_id)}
                        className="text-[12px] text-[var(--blue)] font-semibold flex items-center gap-1 cursor-pointer"
                      >
                        <Clock className="w-3.5 h-3.5" />
                        <span>{tl ? "Hide Status Timeline" : "View Status Timeline"}</span>
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
                              <span className="text-[var(--text-muted)] shrink-0 font-mono text-[11px]">
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
          </div>
        )}

        {/* TAB 4: PUBLIC / GUEST TRACKING */}
        {tab === "track" && (
          <div
            style={{ boxShadow: "var(--card-shadow)" }}
            className="rounded-[12px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] p-4 space-y-4"
          >
            <div>
              <h2 className="text-[16px] font-bold text-[var(--text-primary)]">
                Track Incident by Code
              </h2>
              <p className="text-[12.5px] text-[var(--text-secondary)] mt-0.5">
                Enter your Incident ID and Tracking Code (`TRK-...`) to view live status updates.
              </p>
            </div>

            <form onSubmit={handleTrackLookup} className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
              <input
                type="text"
                required
                value={trackId}
                onChange={(e) => setTrackId(e.target.value)}
                placeholder="Incident ID (e.g. FIQ-...)"
                className="px-3 py-2.5 rounded-[8px] bg-[var(--bg-input)] border border-[var(--border-active)] text-[13px] text-[var(--text-primary)]"
              />
              <input
                type="text"
                required
                value={trackCode}
                onChange={(e) => setTrackCode(e.target.value)}
                placeholder="Tracking Code (TRK-...)"
                className="px-3 py-2.5 rounded-[8px] bg-[var(--bg-input)] border border-[var(--border-active)] text-[13px] text-[var(--text-primary)]"
              />
              <button
                type="submit"
                disabled={trackingLoading}
                className="py-2.5 px-4 rounded-[8px] bg-[var(--teal)] text-[var(--teal-fg)] text-[13px] font-bold cursor-pointer"
              >
                {trackingLoading ? "Checking..." : "Track Status"}
              </button>
            </form>

            {trackError && (
              <div className="p-3 rounded-[8px] bg-[#FEF2F2] dark:bg-[#FF5364]/15 border border-[#FCA5A5] dark:border-[#FF5364]/45 text-[12px] text-[#991B1B] dark:text-[#FF8E99]">
                {trackError}
              </div>
            )}

            {trackResult && (
              <div className="p-4 rounded-[10px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="font-mono text-[13.5px] font-bold text-[var(--text-primary)]">
                      {trackResult.incident.incident_id}
                    </div>
                    <div className="text-[12px] text-[var(--text-secondary)]">
                      {trackResult.incident.zone_id} · {trackResult.incident.location_text}
                    </div>
                  </div>
                  <span
                    className={`px-2 py-0.5 rounded-[4px] text-[11px] font-bold border ${
                      STATUS_BADGE[trackResult.incident.status] ||
                      "bg-[var(--bg-panel)] text-[var(--text-primary)] border-[var(--border-hairline)]"
                    }`}
                  >
                    {trackResult.incident.status}
                  </span>
                </div>

                <div className="space-y-1.5 border-t border-[var(--border-hairline)] pt-2.5">
                  {trackResult.timeline.map((u) => (
                    <div key={u.update_id} className="text-[12px] flex justify-between gap-2">
                      <div>
                        <span className="font-bold text-[var(--teal)]">{u.new_status}</span>
                        <span className="text-[var(--text-secondary)]"> — {u.note}</span>
                      </div>
                      <span className="text-[var(--text-muted)] font-mono text-[11px] shrink-0">
                        {u.updated_at.slice(0, 16).replace("T", " ")}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 5: SAFETY & PREPAREDNESS */}
        {tab === "safety" && (
          <div
            style={{ boxShadow: "var(--card-shadow)" }}
            className="rounded-[12px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] p-5 space-y-3"
          >
            <h2 className="text-[16px] font-bold text-[var(--text-primary)]">
              Citizen Flood Safety &amp; Preparedness
            </h2>
            <ul className="space-y-2.5 text-[13px] text-[var(--text-secondary)] list-disc pl-5">
              <li>
                Move elderly residents, children, and medical supplies to upper floors before water
                rises.
              </li>
              <li>
                Avoid walking or driving through moving floodwater or near downed power lines.
              </li>
              <li>
                Keep emergency contacts, drinking water, flashlights, and medications in a
                waterproof kit.
              </li>
              <li>
                If trapped, submit a Water Rescue report immediately with exact landmark and people
                count.
              </li>
            </ul>
          </div>
        )}
      </main>

      {/* Mobile Bottom Navigation Bar (Matches Stitch Citizen Dashboard) */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-[var(--bg-rail)] border-t border-[var(--border-hairline)] grid grid-cols-5 py-1.5 px-1">
        {NAV_TABS.slice(0, 4).map((item) => {
          const Icon = item.icon;
          const active = tab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              className={`flex flex-col items-center justify-center gap-0.5 py-1 rounded-[6px] text-[10px] font-semibold ${
                active ? "text-[var(--teal)] font-bold" : "text-[var(--text-muted)]"
              }`}
            >
              <Icon className="w-4 h-4" />
              <span>{item.label}</span>
            </button>
          );
        })}
        <Link
          href="/login"
          className="flex flex-col items-center justify-center gap-0.5 py-1 rounded-[6px] text-[10px] font-semibold text-[var(--text-muted)]"
        >
          <Repeat className="w-4 h-4" />
          <span>Portals</span>
        </Link>
      </nav>
    </div>
  );
}
