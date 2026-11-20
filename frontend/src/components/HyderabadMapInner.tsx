"use client";

import React, { useEffect, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Marker, Popup, Tooltip } from "react-leaflet";
import L from "leaflet";
import { getApiBase } from "@/lib/api";
import type { EvaluatedZone, Incident, ResponseTeam } from "@/lib/types";
import { bandFromScore } from "./Badge";

const RISK_HEX: Record<string, string> = {
  Low: "#37C98A",
  Moderate: "#E8C45A",
  High: "#FF9B48",
  Critical: "#FF5364",
};

function makeIncidentIcon(band: string) {
  const color = RISK_HEX[band] || "#FF5364";
  return L.divIcon({
    className: "",
    html: `<div style="width:22px;height:22px;border-radius:4px;background:${color};border:2px solid #09131D;display:flex;align-items:center;justify-content:center;color:#09131D;font-weight:800;font-size:12px;box-shadow:0 0 10px ${color}80;">!</div>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
}

function makeTeamIcon(status: string) {
  const bg = status === "Available" ? "#21C7B7" : "#6A8294";
  return L.divIcon({
    className: "",
    html: `<div style="width:18px;height:18px;border-radius:999px;background:${bg};border:2px solid #09131D;display:flex;align-items:center;justify-content:center;color:#09131D;font-weight:800;font-size:9px;">U</div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}

export default function HyderabadMapInner({
  zones,
  incidents = [],
  teams = [],
  highlightZoneId,
  height = 410,
}: {
  zones: EvaluatedZone[];
  incidents?: Incident[];
  teams?: ResponseTeam[];
  highlightZoneId?: string;
  height?: number;
}) {
  const zoneCoords = new Map(zones.map((z) => [z.zone_id, [z.latitude, z.longitude] as [number, number]]));
  const zoneCounts = new Map<string, number>();

  const [radarUrl, setRadarUrl] = useState<string | null>(null);
  const [showRadar, setShowRadar] = useState(false);

  useEffect(() => {
    fetch(`${getApiBase()}/api/geo/radar`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data?.available && data?.tile_url_template) {
          setRadarUrl(data.tile_url_template);
        }
      })
      .catch(() => {
        // non-fatal
      });
  }, []);

  const openIncidents = incidents.filter((i) => i.status !== "Resolved");

  return (
    <div
      className="fiq-dark-map relative rounded-[4px] overflow-hidden border border-[#1E384D]"
      style={{ height }}
    >
      {radarUrl && (
        <button
          type="button"
          onClick={() => setShowRadar((prev) => !prev)}
          className={`absolute top-2.5 right-2.5 z-[400] px-2.5 py-1 rounded-[4px] text-[10.5px] font-bold border transition-colors ${
            showRadar
              ? "bg-[#21C7B7] text-[#09131D] border-[#21C7B7]"
              : "bg-[#0D1C28]/90 text-[#F0F5F8] border-[#24465F] hover:border-[#21C7B7]"
          }`}
        >
          {showRadar ? "Radar Imagery: ON" : "Radar Imagery (RainViewer)"}
        </button>
      )}
      <MapContainer
        center={[17.415, 78.46]}
        zoom={11}
        style={{ height: "100%", width: "100%" }}
        scrollWheelZoom={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {showRadar && radarUrl && (
          <TileLayer
            attribution='<a href="https://www.rainviewer.com" target="_blank" rel="noreferrer">Weather data by RainViewer</a>'
            url={radarUrl}
            opacity={0.55}
          />
        )}

        {zones.map((z) => {
          const color = RISK_HEX[z.risk_level] || "#21C7B7";
          const isHl = z.zone_id === highlightZoneId;
          return (
            <CircleMarker
              key={z.zone_id}
              center={[z.latitude, z.longitude]}
              radius={isHl ? 24 : 18}
              pathOptions={{
                color: isHl ? "#FFFFFF" : color,
                weight: isHl ? 3 : 2,
                fillColor: color,
                fillOpacity: 0.32,
              }}
            >
              <Tooltip>
                {z.zone_name} — {z.risk_level} ({z.risk_score.toFixed(0)}/100)
              </Tooltip>
              <Popup>
                <div style={{ fontFamily: "Inter, sans-serif", fontSize: 12, color: "#102530", minWidth: 195 }}>
                  <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>{z.zone_name}</div>
                  <div>
                    <b>Risk Score:</b> {z.risk_score.toFixed(1)}/100 ({z.risk_level})
                  </div>
                  <div>
                    <b>Rainfall:</b> {z.rainfall_mm.toFixed(1)} mm ({z.rainfall_source})
                  </div>
                  <div>
                    <b>Drainage Vuln.:</b> {z.drainage_score}/100
                  </div>
                  <div>
                    <b>Low-Lying:</b> {z.low_lying_score}/100
                  </div>
                  <div style={{ marginTop: 4, color: "#5c707a", fontSize: 11 }}>
                    Heuristic risk assessment score
                  </div>
                </div>
              </Popup>
            </CircleMarker>
          );
        })}

        {openIncidents.map((inc) => {
          const coords = zoneCoords.get(inc.zone_id);
          if (!coords) return null;
          const idx = zoneCounts.get(inc.zone_id) || 0;
          zoneCounts.set(inc.zone_id, idx + 1);
          const pos: [number, number] = [coords[0] + 0.003 * (idx + 1), coords[1] - 0.003 * (idx + 1)];
          const band = bandFromScore(inc.priority_score);
          return (
            <Marker key={inc.incident_id} position={pos} icon={makeIncidentIcon(band)}>
              <Tooltip>
                {inc.incident_id} ({band}, {inc.priority_score.toFixed(0)}/100)
              </Tooltip>
              <Popup>
                <div style={{ fontFamily: "Inter, sans-serif", fontSize: 12, color: "#102530", minWidth: 195 }}>
                  <div style={{ fontWeight: 700 }}>
                    {inc.incident_id} · {inc.ai_category || inc.reported_category}
                  </div>
                  <div>
                    <b>Priority:</b> {inc.priority_score.toFixed(0)}/100 ({band})
                  </div>
                  <div>
                    <b>Status:</b> {inc.status}
                  </div>
                  <div>
                    <b>Affected:</b> {inc.people_affected}
                  </div>
                  <div>
                    <b>Location:</b> {inc.location_text || inc.zone_id}
                  </div>
                </div>
              </Popup>
            </Marker>
          );
        })}

        {teams.map((t) => (
          <Marker key={t.team_id} position={[t.latitude, t.longitude]} icon={makeTeamIcon(t.status)}>
            <Tooltip>
              {t.team_name} ({t.status})
            </Tooltip>
            <Popup>
              <div style={{ fontFamily: "Inter, sans-serif", fontSize: 12, color: "#102530", minWidth: 185 }}>
                <div style={{ fontWeight: 700 }}>{t.team_name}</div>
                <div>
                  <b>Specialty:</b> {t.specialty}
                </div>
                <div>
                  <b>Status:</b> {t.status}
                </div>
                <div style={{ marginTop: 4, color: "#5c707a", fontSize: 11 }}>
                  Configured response unit base
                </div>
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
