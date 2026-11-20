"use client";

import dynamic from "next/dynamic";
import type { EvaluatedZone, Incident, ResponseTeam } from "@/lib/types";

const HyderabadMapInner = dynamic(() => import("./HyderabadMapInner"), {
  ssr: false,
  loading: () => (
    <div className="h-[410px] rounded-[4px] border border-[#1E384D] bg-[#0D1C28] flex items-center justify-center text-[12px] text-[#6A8294]">
      Loading Hyderabad GIS Map...
    </div>
  ),
});

export function HyderabadMap({
  zones,
  incidents = [],
  teams = [],
  highlightZoneId,
  height = 410,
  showEntitiesLegend = true,
}: {
  zones: EvaluatedZone[];
  incidents?: Incident[];
  teams?: ResponseTeam[];
  highlightZoneId?: string;
  height?: number;
  showEntitiesLegend?: boolean;
}) {
  return (
    <div>
      <HyderabadMapInner
        zones={zones}
        incidents={incidents}
        teams={teams}
        highlightZoneId={highlightZoneId}
        height={height}
      />
      <div className="mt-2 px-3 py-1.5 rounded-[4px] bg-[#122431] border border-[#1E384D] flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-semibold text-[#91A5B3]">
        <span className="text-[10px] uppercase tracking-wider text-[#6A8294]">Zone Risk:</span>
        <span className="inline-flex items-center gap-1.5">
          <i className="w-2 h-2 rounded-full bg-[#FF5364]" /> Critical (&ge;75)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <i className="w-2 h-2 rounded-full bg-[#FF9B48]" /> High (50–74)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <i className="w-2 h-2 rounded-full bg-[#E8C45A]" /> Moderate (30–49)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <i className="w-2 h-2 rounded-full bg-[#37C98A]" /> Low (&lt;30)
        </span>
        {showEntitiesLegend && (
          <>
            <span className="inline-flex items-center gap-1.5">
              <i className="w-2 h-2 rounded-[2px] bg-[#FF5364]" /> Active Incident
            </span>
            <span className="inline-flex items-center gap-1.5">
              <i className="w-2 h-2 rounded-full bg-[#21C7B7]" /> Demo Unit
            </span>
          </>
        )}
      </div>
    </div>
  );
}
