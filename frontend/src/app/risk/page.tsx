"use client";

import React, { useEffect, useState } from "react";
import { Download, RefreshCw } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid } from "recharts";
import { api, getApiBase } from "@/lib/api";
import type { DatasetStatusResponse, HistoricalWeatherResponse, RiskResponse } from "@/lib/types";
import { useSimulation } from "@/context/SimulationContext";
import { Badge, toneFromBand } from "@/components/Badge";
import { HyderabadMap } from "@/components/HyderabadMap";

export default function FloodRiskPage() {
  const { rainfallMm, useSimulation: isSim, setRainfallMm, setUseSimulation, refreshTick } = useSimulation();
  const [data, setData] = useState<RiskResponse | null>(null);
  const [dsStatus, setDsStatus] = useState<DatasetStatusResponse | null>(null);
  const [histWeather, setHistWeather] = useState<HistoricalWeatherResponse | null>(null);
  const [refreshingDs, setRefreshingDs] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .simulateRisk(rainfallMm, isSim)
      .then((res) => {
        if (!cancelled) {
          setData(res);
          setError(null);
          const topZoneId = res.zones[0]?.zone_id;
          if (topZoneId) {
            api.getHistoricalWeather(topZoneId, 30).then((hw) => {
              if (!cancelled) setHistWeather(hw);
            }).catch(() => {});
          }
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });

    api.getDatasetStatus().then((ds) => {
      if (!cancelled) setDsStatus(ds);
    }).catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [rainfallMm, isSim, refreshTick]);

  const handleRefreshDataset = async () => {
    setRefreshingDs(true);
    try {
      const updated = await api.refreshDataset();
      setDsStatus(updated);
    } catch {
      // handled silently; cached status remains visible
    } finally {
      setRefreshingDs(false);
    }
  };

  if (error) {
    return (
      <div className="p-4 rounded-[4px] bg-[#FF5364]/15 border border-[#FF5364]/40 text-[#FFB3BA] text-[13px]">
        Failed to load Flood Risk Intelligence ({error}). Ensure FastAPI is running.
      </div>
    );
  }

  if (!data) {
    return <div className="p-8 text-center text-[13px] text-[var(--text-secondary)]">Loading Flood Risk Intelligence...</div>;
  }

  const focusZone = data.zones[0];
  const chartData = data.zones.map((z) => ({
    name: z.zone_name,
    "Rainfall (40%)": z.score_breakdown.rainfall.contribution,
    "Drainage (30%)": z.score_breakdown.drainage.contribution,
    "Low-Lying (30%)": z.score_breakdown.low_lying.contribution,
  }));

  return (
    <div className="space-y-4">
      <div className="p-3.5 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.09em] text-[var(--teal)]">
            Geospatial Catchment Analysis
          </div>
          <h1 className="text-[19px] font-bold text-[var(--text-primary)] mt-0.5">Flood Risk Intelligence</h1>
          <p className="text-[12px] text-[var(--text-secondary)]">
            Heuristic flood-risk assessment combining rainfall, drainage capacity, and terrain elevation.
          </p>
        </div>
        <Badge tone="teal">Heuristic Risk Model</Badge>
      </div>

      {/* Inline Scenario Presets + Slider Bar (matches Stitch 2_flood_risk.png) */}
      <div className="p-3 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-muted)]">
            Scenario Presets:
          </span>
          {[
            { mm: 20, label: "20mm Light" },
            { mm: 50, label: "50mm Monsoon" },
            { mm: 100, label: "100mm Cloudburst" },
          ].map((p) => {
            const active = isSim && rainfallMm === p.mm;
            return (
              <button
                key={p.mm}
                type="button"
                onClick={() => {
                  setUseSimulation(true);
                  setRainfallMm(p.mm);
                }}
                className={`px-2.5 py-1 rounded-[4px] text-[11px] font-semibold border transition-colors ${
                  active
                    ? "bg-[var(--teal)] text-[var(--teal-fg)] border-[var(--teal)] font-bold"
                    : "bg-[var(--bg-elevated)] text-[var(--text-secondary)] border-[var(--border-hairline)] hover:border-[var(--border-active)] hover:text-[var(--text-primary)]"
                }`}
              >
                {p.label}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-3 flex-1 min-w-[240px] max-w-[420px]">
          <span className="text-[11px] text-[var(--text-secondary)] whitespace-nowrap">Scenario Rainfall:</span>
          <input
            type="range"
            min={0}
            max={150}
            step={5}
            value={rainfallMm}
            onChange={(e) => {
              setUseSimulation(true);
              setRainfallMm(Number(e.target.value));
            }}
            className="w-full accent-[#21C7B7] cursor-pointer"
            aria-label="Scenario Rainfall (mm)"
          />
          <span className="text-[12px] font-bold text-[var(--teal)] whitespace-nowrap">{rainfallMm} mm</span>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
        <div className="xl:col-span-6 space-y-2">
          <div className="flex items-baseline justify-between border-b border-[var(--border-hairline)] pb-1.5">
            <h2 className="text-[14px] font-bold text-[var(--text-primary)]">Catchment Risk Zones</h2>
            <span className="text-[11px] text-[var(--text-muted)]">{data.source_label}</span>
          </div>
          <HyderabadMap zones={data.zones} height={425} showEntitiesLegend={false} />
        </div>

        <div className="xl:col-span-6 space-y-3">
          <div className="p-3 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] border-l-[3px] border-l-[#21C7B7]">
            <div className="text-[11px] font-bold uppercase tracking-wider text-[var(--teal)]">
              Heuristic Calculation Engine
            </div>
            <div className="text-[13px] font-mono font-semibold text-[var(--text-primary)] mt-1">
              R = 0.40 &times; P (Rainfall) + 0.30 &times; D (Drainage) + 0.30 &times; L (Low-Lying)
            </div>
            <div className="text-[11px] text-[var(--text-secondary)] mt-1">
              Normalization: <span className="font-mono text-[#D9E3F2]">P = min(100, (rainfall_mm / 150) &times; 100)</span>. Bands: 0–29 Low, 30–49 Moderate, 50–74 High, 75–100 Critical.
            </div>
          </div>

          {focusZone && (
            <div className="p-3 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] space-y-2.5">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-muted)]">
                    Highest-Risk Sector
                  </div>
                  <div className="text-[15px] font-bold text-[var(--text-primary)]">{focusZone.zone_name}</div>
                </div>
                <div className="text-right">
                  <div className="text-[22px] font-bold text-[var(--text-primary)] leading-none">
                    {focusZone.risk_score.toFixed(1)}
                    <span className="text-[12px] text-[var(--text-muted)]">/100</span>
                  </div>
                  <Badge tone={toneFromBand(focusZone.risk_level)} className="mt-1">
                    {focusZone.risk_level}
                  </Badge>
                </div>
              </div>

              {/* Factor Progress Bars matching Stitch Design */}
              <div className="space-y-1.5 pt-1">
                {[
                  {
                    label: "Rainfall Exposure (40% weight)",
                    raw: focusZone.score_breakdown.rainfall.raw,
                    contrib: focusZone.score_breakdown.rainfall.contribution,
                    color: "#21C7B7",
                  },
                  {
                    label: "Drainage Vulnerability (30% weight)",
                    raw: focusZone.score_breakdown.drainage.raw,
                    contrib: focusZone.score_breakdown.drainage.contribution,
                    color: "#FF9B48",
                  },
                  {
                    label: "Low-Lying Terrain (30% weight)",
                    raw: focusZone.score_breakdown.low_lying.raw,
                    contrib: focusZone.score_breakdown.low_lying.contribution,
                    color: "#55A8FF",
                  },
                ].map((f) => (
                  <div key={f.label} className="space-y-0.5">
                    <div className="flex justify-between text-[11px] text-[var(--text-secondary)]">
                      <span>{f.label}</span>
                      <span>
                        {f.raw.toFixed(0)}/100 (<b style={{ color: f.color }}>+{f.contrib.toFixed(1)}</b>)
                      </span>
                    </div>
                    <div className="h-1.5 w-full rounded-[2px] bg-[var(--bg-elevated)] overflow-hidden">
                      <div
                        className="h-full rounded-[2px]"
                        style={{ width: `${Math.min(100, Math.max(0, f.raw))}%`, backgroundColor: f.color }}
                      />
                    </div>
                  </div>
                ))}
              </div>

              {focusZone.reasons.length > 0 && (
                <div className="pt-2 border-t border-[var(--border-hairline)] text-[11.5px] text-[var(--text-secondary)] space-y-0.5">
                  <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-muted)]">
                    Explainable Drivers
                  </div>
                  {focusZone.reasons.map((r, i) => (
                    <div key={i}>&bull; {r}</div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="p-3 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)]">
            <div className="text-[12px] font-bold text-[var(--text-primary)] mb-2">
              Weighted Risk Contribution by Zone ({data.source_label})
            </div>
            <div className="h-[235px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1E384D" />
                  <XAxis dataKey="name" tick={{ fill: "#91A5B3", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#91A5B3", fontSize: 11 }} domain={[0, 100]} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0D1C28",
                      borderColor: "#24465F",
                      color: "#F0F5F8",
                      fontSize: 12,
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, color: "#91A5B3" }} />
                  <Bar dataKey="Rainfall (40%)" stackId="a" fill="#21C7B7" />
                  <Bar dataKey="Drainage (30%)" stackId="a" fill="#FF9B48" />
                  <Bar dataKey="Low-Lying (30%)" stackId="a" fill="#55A8FF" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>

      {/* 5-Zone Comparison Matrix */}
      <div className="p-3.5 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] overflow-x-auto">
        <div className="flex items-baseline justify-between mb-2">
          <h2 className="text-[13px] font-bold text-[var(--text-primary)]">5-Zone Comparison Matrix</h2>
          <span className="text-[11px] text-[var(--text-muted)]">Sorted highest illustrative risk first</span>
        </div>
        <p className="text-[11px] text-[var(--text-secondary)] mb-2">
          The next 6-hour Open-Meteo precipitation outlook is shown separately; it does not change the illustrative heuristic risk score or represent a flood probability.
        </p>
        <table className="w-full text-[12px]">
          <thead>
            <tr className="border-b border-[var(--border-hairline)] text-[10.5px] uppercase tracking-wider text-[var(--text-muted)] text-left">
              <th className="py-2 pr-3">Zone</th>
              <th className="py-2 pr-3">SRTM Elev.</th>
              <th className="py-2 pr-3">Current Rain</th>
              <th className="py-2 pr-3">Forecast Rain (6h)</th>
              <th className="py-2 pr-3">Drainage Vuln.</th>
              <th className="py-2 pr-3">Low-Lying</th>
              <th className="py-2 pr-3">Risk Score</th>
              <th className="py-2 pr-3">Band</th>
              <th className="py-2">Key Drivers</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1E384D]/70 text-[#D9E3F2]">
            {data.zones.map((z) => {
              const dotColor =
                z.risk_level === "Critical"
                  ? "#FF5364"
                  : z.risk_level === "High"
                  ? "#FF9B48"
                  : z.risk_level === "Moderate"
                  ? "#E8C45A"
                  : "#37C98A";
              return (
                <tr key={z.zone_id}>
                  <td className="py-2 pr-3 font-semibold text-[var(--text-primary)]">
                    <span className="inline-flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: dotColor }} />
                      {z.zone_name}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-[var(--text-secondary)]">
                    {z.elevation_m != null ? `${z.elevation_m.toFixed(0)} m` : "—"}
                  </td>
                  <td className="py-2 pr-3">
                    {z.rainfall_mm.toFixed(1)} mm <span className="text-[var(--text-muted)]">({z.rainfall_source})</span>
                  </td>
                  <td className="py-2 pr-3" title={z.forecast_source || "Forecast unavailable in simulation or fallback mode"}>
                    {z.forecast_precipitation_6h_mm != null ? (
                      <span>
                        {z.forecast_precipitation_6h_mm.toFixed(1)} mm
                        {z.forecast_window_start && z.forecast_window_end && (
                          <span className="block text-[10px] text-[var(--text-muted)]">
                            {z.forecast_window_start.slice(11, 16)}–{z.forecast_window_end.slice(11, 16)} IST
                          </span>
                        )}
                      </span>
                    ) : (
                      <span className="text-[var(--text-muted)]">Unavailable</span>
                    )}
                  </td>
                  <td className="py-2 pr-3">{z.drainage_score}/100</td>
                  <td className="py-2 pr-3">{z.low_lying_score}/100</td>
                  <td className="py-2 pr-3 font-bold text-[var(--text-primary)]">{z.risk_score.toFixed(1)}/100</td>
                  <td className="py-2 pr-3">
                    <Badge tone={toneFromBand(z.risk_level)}>{z.risk_level}</Badge>
                  </td>
                  <td className="py-2 text-[var(--text-secondary)]">{z.reasons.slice(0, 2).join("; ")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Real-World Dataset & Historical Context Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="p-3.5 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] space-y-2.5">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-hairline)] pb-1.5">
            <h2 className="text-[13px] font-bold text-[var(--text-primary)]">
              Real-World Dataset &amp; Model Status
            </h2>
            <Badge tone="teal">Explainable Heuristic (Data-Driven)</Badge>
          </div>
          {dsStatus?.available ? (
            <div className="space-y-2 text-[12px] text-[var(--text-secondary)]">
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                <div className="p-2 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)]">
                  <div className="text-[10px] uppercase text-[var(--text-muted)] font-bold">Training Rows</div>
                  <div className="text-[15px] font-bold text-[var(--text-primary)]">
                    {dsStatus.record_count?.toLocaleString()}
                  </div>
                </div>
                <div className="p-2 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)]">
                  <div className="text-[10px] uppercase text-[var(--text-muted)] font-bold">Zenodo India / Hyd</div>
                  <div className="text-[15px] font-bold text-[var(--text-primary)]">
                    {dsStatus.geographic_coverage?.zenodo_india_records} /{" "}
                    {dsStatus.geographic_coverage?.zenodo_within_300km_hyderabad}
                  </div>
                </div>
                <div className="p-2 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)]">
                  <div className="text-[10px] uppercase text-[var(--text-muted)] font-bold">Confirmed Events (1)</div>
                  <div className="text-[15px] font-bold text-[var(--teal)]">
                    {dsStatus.class_distribution?.["1"] ?? 0}
                  </div>
                </div>
              </div>
              <p className="text-[11px] text-[var(--text-secondary)]">
                Sources: Open-Meteo Historical Archive (2010–2025), Zenodo Global Flood Records (19288171), and NASA SRTM 90m.
                Supervised ML was intentionally omitted because only 3 distinct regional flood events appear in 2010–2025.
              </p>
              <div className="flex flex-wrap gap-2 pt-1">
                <a
                  href={`${getApiBase()}/api/dataset/download`}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[4px] bg-[var(--teal)] hover:bg-[var(--teal-hover)] text-[var(--teal-fg)] font-bold text-[11.5px]"
                >
                  <Download className="w-3.5 h-3.5" />
                  Download Training CSV
                </a>
                <button
                  type="button"
                  onClick={handleRefreshDataset}
                  disabled={refreshingDs}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-active)] hover:border-[var(--teal)] text-[var(--text-primary)] font-semibold text-[11.5px] disabled:opacity-50"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${refreshingDs ? "animate-spin" : ""}`} />
                  {refreshingDs ? "Refreshing..." : "Refresh Dataset"}
                </button>
              </div>
            </div>
          ) : (
            <div className="text-[12px] text-[var(--text-secondary)]">Dataset metadata unavailable.</div>
          )}
        </div>

        <div className="p-3.5 rounded-[4px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] space-y-2.5">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-hairline)] pb-1.5">
            <h2 className="text-[13px] font-bold text-[var(--text-primary)]">
              Historical Rainfall Context ({histWeather?.zone_name || "Top Zone"})
            </h2>
            <Badge tone="blue">Open-Meteo Archive 2010–2025</Badge>
          </div>
          {histWeather?.summary ? (
            <div className="space-y-2 text-[12px] text-[var(--text-secondary)]">
              <div className="grid grid-cols-3 gap-2">
                <div className="p-2 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)]">
                  <div className="text-[10px] uppercase text-[var(--text-muted)] font-bold">Max 24h Peak</div>
                  <div className="text-[15px] font-bold text-[#FF5364]">
                    {histWeather.summary.max_24h_mm ?? "—"} mm
                  </div>
                </div>
                <div className="p-2 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)]">
                  <div className="text-[10px] uppercase text-[var(--text-muted)] font-bold">95th Pct (24h)</div>
                  <div className="text-[15px] font-bold text-[#FF9B48]">
                    {histWeather.summary.p95_24h_mm ?? "—"} mm
                  </div>
                </div>
                <div className="p-2 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)]">
                  <div className="text-[10px] uppercase text-[var(--text-muted)] font-bold">SRTM Elevation</div>
                  <div className="text-[15px] font-bold text-[var(--text-primary)]">
                    {histWeather.elevation_m != null ? `${histWeather.elevation_m} m` : "—"}
                  </div>
                </div>
              </div>
              <p className="text-[11px] text-[var(--text-secondary)]">
                Observed across <b className="text-[var(--text-primary)]">{histWeather.summary.total_days?.toLocaleString()}</b> historical days.
                Active scenario (<b className="text-[var(--teal)]">{data.source_label}</b>) is clearly separated from historical archive statistics.
              </p>
            </div>
          ) : (
            <div className="text-[12px] text-[var(--text-muted)]">Loading historical archive summary...</div>
          )}
        </div>
      </div>
    </div>
  );
}
