"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import type { Incident, PriorityBreakdown, ZoneRaw } from "@/lib/types";
import { Badge, bandFromScore, toneFromBand } from "@/components/Badge";

const CATEGORIES = [
  "Water Rescue",
  "Medical Emergency",
  "Road Blockage",
  "Infrastructure Damage",
  "Flooded Building",
  "Other",
];

export default function CitizenReportingPage() {
  const [zones, setZones] = useState<ZoneRaw[]>([]);
  const [zoneId, setZoneId] = useState("musi_riverfront");
  const [category, setCategory] = useState("Water Rescue");
  const [locationText, setLocationText] = useState("");
  const [peopleAffected, setPeopleAffected] = useState<number>(1);
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    incident: Incident;
    priority_breakdown: PriorityBreakdown;
  } | null>(null);

  useEffect(() => {
    api
      .getZones()
      .then((z) => {
        setZones(z);
        if (z.length > 0 && !z.some((item) => item.zone_id === zoneId)) {
          setZoneId(z[0].zone_id);
        }
      })
      .catch((err: Error) => setError(`Unable to load zones: ${err.message}`));
  }, [zoneId]);

  const loadPresetA = () => {
    setZoneId("musi_riverfront");
    setCategory("Water Rescue");
    setLocationText("Residential colony near Musi River bridge, Chaderghat");
    setPeopleAffected(3);
    setDescription(
      "Heavy rain has caused water to enter a residential building near the Musi Riverfront. Three people are stranded on the first floor, including an elderly person. Water levels are continuing to rise."
    );
    setError(null);
  };

  const loadPresetB = () => {
    setZoneId("ameerpet");
    setCategory("Road Blockage");
    setLocationText("Main road near Ameerpet Metro Station pillar 1042");
    setPeopleAffected(0);
    setDescription(
      "Road near Ameerpet metro station is partially waterlogged after heavy rain. Traffic is affected but no vehicles are stuck. Some pedestrians are wading through ankle-deep water."
    );
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!description.trim() || description.trim().length < 3) {
      setError("Please provide an incident description (at least 3 characters).");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.createIncident({
        zone_id: zoneId,
        description: description.trim(),
        location_text: locationText.trim(),
        reported_category: category,
        people_affected: Number(peopleAffected) || 0,
      });
      setResult({ incident: res.incident, priority_breakdown: res.priority_breakdown });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit incident.");
    } finally {
      setSubmitting(false);
    }
  };

  const zoneNameById = new Map(zones.map((z) => [z.zone_id, z.zone_name]));

  return (
    <div className="space-y-4">
      <div className="p-3.5 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.09em] text-[var(--teal)]">
            Tactical Intake & AI Triage
          </div>
          <h1 className="text-[19px] font-bold text-[var(--text-primary)] mt-0.5">
            Citizen Reporting / Emergency Intake & AI Triage
          </h1>
          <p className="text-[12px] text-[var(--text-secondary)]">
            Structured intake with Groq AI triage and automatic deterministic rule-based fallback.
          </p>
        </div>
        <Badge tone="teal">Auto-Fallback Protected</Badge>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left: Intake Form */}
        <div className="lg:col-span-7 p-4 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-hairline)] pb-2">
            <h2 className="text-[14px] font-bold text-[var(--text-primary)]">Submit Emergency Report</h2>
            <span className="text-[11px] text-[var(--text-muted)]">Quick Templates</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <button
              type="button"
              onClick={loadPresetA}
              className="px-3 py-1.5 rounded-[4px] bg-[#FF5364]/15 border border-[#FF5364]/40 text-[#FF8E99] hover:bg-[#FF5364]/25 text-[11.5px] font-semibold text-left transition-colors"
            >
              Template A: Stranded Elderly (Critical)
            </button>
            <button
              type="button"
              onClick={loadPresetB}
              className="px-3 py-1.5 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-active)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] text-[11.5px] font-semibold text-left transition-colors"
            >
              Template B: Waterlogged Road (Moderate)
            </button>
          </div>

          {error && (
            <div className="p-2.5 rounded-[4px] bg-[#FF5364]/15 border border-[#FF5364]/40 text-[#FFB3BA] text-[12px] flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-[11px] font-semibold text-[var(--text-secondary)] mb-1">
                  Incident Category (Optional)
                </label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full px-2.5 py-2 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[12.5px] text-[var(--text-primary)] focus:outline-none focus:border-[var(--teal)]"
                >
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-[var(--text-secondary)] mb-1">
                  Assessment Zone *
                </label>
                <select
                  value={zoneId}
                  onChange={(e) => setZoneId(e.target.value)}
                  className="w-full px-2.5 py-2 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[12.5px] text-[var(--text-primary)] focus:outline-none focus:border-[var(--teal)]"
                >
                  {zones.map((z) => (
                    <option key={z.zone_id} value={z.zone_id}>
                      {z.zone_name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-[var(--text-secondary)] mb-1">
                  Specific Location / Landmark
                </label>
                <input
                  type="text"
                  value={locationText}
                  onChange={(e) => setLocationText(e.target.value)}
                  placeholder="e.g. Near Community Hall, Pillar 45"
                  className="w-full px-2.5 py-2 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[12.5px] text-[var(--text-primary)] placeholder-[#6A8294] focus:outline-none focus:border-[var(--teal)]"
                />
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-[var(--text-secondary)] mb-1">
                  Affected People (if known)
                </label>
                <input
                  type="number"
                  min={0}
                  max={1000}
                  value={peopleAffected}
                  onChange={(e) => setPeopleAffected(Number(e.target.value))}
                  className="w-full px-2.5 py-2 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[12.5px] text-[var(--text-primary)] focus:outline-none focus:border-[var(--teal)]"
                />
              </div>
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-[var(--text-secondary)] mb-1">
                Incident Description (Citizen Text) *
              </label>
              <textarea
                rows={4}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe water levels, stranded individuals, vulnerable residents, or immediate hazards..."
                className="w-full px-2.5 py-2 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[12.5px] text-[var(--text-primary)] placeholder-[#6A8294] focus:outline-none focus:border-[var(--teal)]"
              />
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full py-2.5 rounded-[4px] bg-[var(--teal)] hover:bg-[var(--teal-hover)] text-[var(--teal-fg)] font-bold text-[12.5px] uppercase tracking-wider transition-colors disabled:opacity-50"
            >
              {submitting ? "Running AI Triage..." : "Submit Report & Run AI Triage"}
            </button>
          </form>
        </div>

        {/* Right: AI Triage Assessment */}
        <div className="lg:col-span-5 p-4 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] space-y-3">
          <div className="flex items-center justify-between border-b border-[var(--border-hairline)] pb-2">
            <h2 className="text-[14px] font-bold text-[var(--text-primary)]">AI Triage Assessment</h2>
            {result && <Badge tone="teal">ID: {result.incident.incident_id}</Badge>}
          </div>

          <div className="p-2.5 rounded-[4px] bg-[#FF5364]/10 border border-[#FF5364]/30 text-[11.5px] text-[#FFB3BA]">
            <b>PROTOTYPE NOTICE:</b> Triage output is assistive and unverified. Human operator review in the Control Room is required before dispatch.
          </div>

          {!result ? (
            <div className="p-6 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-center text-[12.5px] text-[var(--text-muted)]">
              Load a demo preset or submit a citizen report to inspect extracted vulnerability flags, urgency, and priority score.
            </div>
          ) : (
            <div className="space-y-3">
              <div className="p-3 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] space-y-2">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-muted)]">
                      Calculated Priority Score
                    </div>
                    <div className="text-[28px] font-bold text-[var(--text-primary)] leading-tight">
                      {Math.round(result.incident.priority_score)}
                      <span className="text-[13px] font-normal text-[var(--text-muted)]">/100</span>
                    </div>
                  </div>
                  <div className="text-right space-y-1">
                    <div>
                      <Badge tone={toneFromBand(bandFromScore(result.incident.priority_score))}>
                        {result.incident.ai_category} &middot; {bandFromScore(result.incident.priority_score)}
                      </Badge>
                    </div>
                    <div>
                      <Badge tone={result.incident.triage_mode === "groq" ? "low" : "blue"}>
                        Mode: {result.incident.triage_mode === "groq" ? "Groq AI" : "Rule-Based Fallback"}
                      </Badge>
                    </div>
                  </div>
                </div>
                <div className="h-1.5 w-full rounded-[2px] bg-[var(--bg-panel)] overflow-hidden">
                  <div
                    className="h-full rounded-[2px]"
                    style={{
                      width: `${Math.min(100, Math.max(0, result.incident.priority_score))}%`,
                      backgroundColor:
                        result.incident.priority_score >= 75
                          ? "#FF5364"
                          : result.incident.priority_score >= 50
                          ? "#FF9B48"
                          : result.incident.priority_score >= 30
                          ? "#E8C45A"
                          : "#37C98A",
                    }}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[12px]">
                <div className="p-2.5 rounded-[4px] bg-[var(--bg-rail)] border border-[var(--border-hairline)]">
                  <div className="text-[10px] uppercase text-[var(--text-muted)] font-bold">Stranded Status</div>
                  <div className="font-semibold text-[var(--text-primary)] mt-0.5">
                    {result.incident.stranded ? "Yes — Stranded" : "No"}
                  </div>
                </div>
                <div className="p-2.5 rounded-[4px] bg-[var(--bg-rail)] border border-[var(--border-hairline)]">
                  <div className="text-[10px] uppercase text-[var(--text-muted)] font-bold">Affected People</div>
                  <div className="font-semibold text-[var(--text-primary)] mt-0.5">
                    {result.incident.people_affected} person(s)
                  </div>
                </div>
                <div className="p-2.5 rounded-[4px] bg-[var(--bg-rail)] border border-[var(--border-hairline)]">
                  <div className="text-[10px] uppercase text-[var(--text-muted)] font-bold">Vulnerable Group</div>
                  <div className="font-semibold text-[var(--text-primary)] mt-0.5">
                    {result.incident.vulnerable_flag ? result.incident.vulnerable_group : "None reported"}
                  </div>
                </div>
                <div className="p-2.5 rounded-[4px] bg-[var(--bg-rail)] border border-[var(--border-hairline)]">
                  <div className="text-[10px] uppercase text-[var(--text-muted)] font-bold">Immediate Hazard</div>
                  <div className="font-semibold text-[var(--text-primary)] mt-0.5">
                    {result.incident.immediate_hazard ? "Yes — Active Hazard" : "No"}
                  </div>
                </div>
              </div>

              <div className="p-3 rounded-[4px] bg-[var(--bg-rail)] border border-[var(--border-hairline)] text-[12px] text-[var(--text-secondary)]">
                <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--teal)] mb-1">
                  Triage Rationale ({zoneNameById.get(result.incident.zone_id) || result.incident.zone_id})
                </div>
                {result.incident.ai_rationale}
              </div>

              <Link
                href={`/control-room?incident=${encodeURIComponent(result.incident.incident_id)}`}
                className="w-full inline-flex items-center justify-center gap-2 py-2.5 rounded-[4px] bg-[var(--teal)] hover:bg-[var(--teal-hover)] text-[var(--teal-fg)] font-bold text-[12.5px] transition-colors"
              >
                Forward to Response Control Room
                <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
