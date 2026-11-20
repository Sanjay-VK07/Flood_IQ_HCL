"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutGrid,
  Waves,
  ShieldCheck,
  Megaphone,
  Radio,
  History,
  Server,
  RotateCcw,
  Menu,
  X,
  CloudRain,
  LogOut,
  UserCheck,
} from "lucide-react";
import { useAuth, roleHomePath } from "@/context/AuthContext";
import { useSimulation } from "@/context/SimulationContext";
import { ThemeToggle } from "@/components/ThemeToggle";

const NAV_ITEMS = [
  { href: "/", label: "Command Center", icon: LayoutGrid },
  { href: "/risk", label: "Flood Risk Intelligence", icon: Waves },
  { href: "/preparedness", label: "Preparedness", icon: ShieldCheck },
  { href: "/report", label: "Citizen Reporting", icon: Megaphone },
  { href: "/control-room", label: "Response Control Room", icon: Radio },
  { href: "/history", label: "Incident History", icon: History },
  { href: "/system", label: "System Information", icon: Server },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading: authLoading, logout } = useAuth();
  const { rainfallMm, useSimulation: isSim, setRainfallMm, setUseSimulation, resetDemo, resetting } =
    useSimulation();
  const [mobileOpen, setMobileOpen] = useState(false);

  const isStandalonePortal =
    pathname === "/login" || pathname.startsWith("/citizen") || pathname.startsWith("/team");

  useEffect(() => {
    if (authLoading || isStandalonePortal) return;
    if (!user) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    } else if (user.role !== "authority") {
      router.replace(roleHomePath(user.role));
    }
  }, [authLoading, isStandalonePortal, pathname, router, user]);

  if (isStandalonePortal) {
    return <>{children}</>;
  }

  if (authLoading || !user || user.role !== "authority") {
    return (
      <div className="min-h-screen bg-[var(--bg-canvas)] text-[var(--text-primary)] flex items-center justify-center p-6">
        <div className="bg-[var(--bg-panel)] border border-[var(--border-hairline)] rounded-[8px] p-6 max-w-sm w-full text-center space-y-3">
          <div className="text-[15px] font-bold text-[var(--text-primary)]">
            FloodIQ Disaster Management Platform
          </div>
          <p className="text-[12px] text-[var(--text-secondary)]">
            {authLoading ? "Verifying session..." : "Redirecting to portal sign-in..."}
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

  const presets = [
    { mm: 20, label: "20mm Light" },
    { mm: 50, label: "50mm Monsoon" },
    { mm: 100, label: "100mm Cloudburst" },
  ];

  const sidebarContent = (
    <div className="flex flex-col h-full justify-between p-3">
      <div>
        {/* Brand */}
        <div className="flex items-center justify-between pb-3 mb-3 border-b border-[var(--border-hairline)]">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-7 h-7 rounded-[6px] bg-[var(--teal)] text-[var(--teal-fg)] flex items-center justify-center shrink-0">
              <Waves className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <div className="text-[15px] font-bold tracking-tight text-[var(--text-primary)] leading-none">
                FloodIQ
              </div>
              <div className="text-[9.5px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)] mt-1 truncate">
                Disaster Platform
              </div>
            </div>
          </div>
          <span className="px-1.5 py-0.5 text-[9px] font-bold tracking-wider bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[var(--teal)] rounded-[3px] shrink-0">
            OPS
          </span>
        </div>

        {/* Navigation */}
        <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)] mb-2 px-1">
          Municipal Authority
        </div>
        <nav className="space-y-1">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className={`flex items-center gap-2.5 px-2.5 py-2 rounded-[6px] text-[12.5px] transition-colors ${
                  active
                    ? "bg-[var(--teal)] text-[var(--teal-fg)] font-bold"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)] hover:text-[var(--text-primary)] font-medium"
                }`}
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span className="truncate">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Sidebar Rainfall Control */}
        <div className="mt-4 pt-3 border-t border-[var(--border-hairline)]">
          <div className="flex items-center justify-between mb-2 px-1">
            <span className="text-[10px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)]">
              Rainfall Control
            </span>
            <button
              type="button"
              onClick={() => setUseSimulation(!isSim)}
              className={`px-1.5 py-0.5 rounded-[3px] text-[10px] font-bold uppercase border transition-colors ${
                isSim
                  ? "bg-[var(--teal)]/15 text-[var(--teal)] border-[var(--teal)]/40"
                  : "bg-[#ECFDF5] dark:bg-[#37C98A]/15 text-[#065F46] dark:text-[#37C98A] border-[#6EE7B7] dark:border-[#37C98A]/40"
              }`}
            >
              {isSim ? "Sim" : "Live"}
            </button>
          </div>
          {isSim ? (
            <div className="space-y-2 px-1">
              <div className="flex items-center justify-between text-[11px] text-[var(--text-secondary)]">
                <span>Scenario Input</span>
                <span className="font-bold text-[var(--teal)]">{rainfallMm} mm</span>
              </div>
              <input
                type="range"
                min={0}
                max={150}
                step={5}
                value={rainfallMm}
                onChange={(e) => setRainfallMm(Number(e.target.value))}
                className="w-full accent-[var(--teal)] cursor-pointer"
                aria-label="Scenario Rainfall (mm)"
              />
            </div>
          ) : (
            <p className="text-[11px] text-[var(--text-secondary)] px-1">
              Using Open-Meteo API with automatic offline fallback.
            </p>
          )}
        </div>
      </div>

      {/* Footer / User & Demo Reset */}
      <div className="pt-3 border-t border-[var(--border-hairline)] space-y-2">
        <div className="p-2 rounded-[6px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[11px] space-y-1.5">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 min-w-0">
              <UserCheck className="w-3.5 h-3.5 text-[var(--teal)] shrink-0" />
              <span className="font-semibold text-[var(--text-primary)] truncate">
                {user.full_name}
              </span>
            </div>
            <span className="px-1.5 py-0.5 rounded-[3px] bg-[var(--bg-panel)] text-[var(--teal)] text-[9px] font-bold uppercase border border-[var(--border-hairline)]">
              Officer
            </span>
          </div>
          <button
            type="button"
            onClick={async () => {
              await logout();
              router.replace("/login");
            }}
            className="w-full flex items-center justify-center gap-1.5 px-2 py-1 rounded-[4px] bg-[var(--bg-panel)] hover:border-[var(--teal)] border border-[var(--border-hairline)] text-[11px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors cursor-pointer"
          >
            <LogOut className="w-3 h-3" />
            <span>Sign Out / Switch Role</span>
          </button>
        </div>

        <button
          type="button"
          onClick={resetDemo}
          disabled={resetting}
          className="w-full flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded-[6px] bg-[var(--bg-elevated)] hover:border-[var(--teal)] border border-[var(--border-hairline)] text-[11.5px] font-semibold text-[var(--text-primary)] transition-colors disabled:opacity-50 cursor-pointer"
        >
          <RotateCcw className={`w-3.5 h-3.5 ${resetting ? "animate-spin" : ""}`} />
          <span>{resetting ? "Resetting..." : "Reset Demo Data"}</span>
        </button>

        <div className="p-2 rounded-[6px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[11px] space-y-1">
          <div className="flex justify-between">
            <span className="font-semibold text-[var(--text-primary)]">Hyderabad Pilot</span>
            <span className="text-[var(--teal)] font-semibold">5 Zones</span>
          </div>
          <div className="flex justify-between text-[var(--text-secondary)]">
            <span>Dispatch Gate</span>
            <span className="text-[var(--moderate)] font-semibold">Human Approval</span>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen flex bg-[var(--bg-canvas)] text-[var(--text-primary)]">
      {/* Desktop Sidebar */}
      <aside className="hidden lg:block w-[236px] shrink-0 bg-[var(--bg-rail)] border-r border-[var(--border-hairline)] sticky top-0 h-screen">
        {sidebarContent}
      </aside>

      {/* Mobile Drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden flex">
          <div className="w-[240px] bg-[var(--bg-rail)] border-r border-[var(--border-hairline)] h-full relative">
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              className="absolute top-3 right-3 text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              aria-label="Close navigation"
            >
              <X className="w-4 h-4" />
            </button>
            {sidebarContent}
          </div>
          <div className="flex-1 bg-black/50" onClick={() => setMobileOpen(false)} />
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Persistent Top Operational Bar */}
        <header className="sticky top-0 z-30 bg-[var(--bg-rail)]/95 backdrop-blur border-b border-[var(--border-hairline)] px-4 py-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2.5 flex-wrap">
              <button
                type="button"
                onClick={() => setMobileOpen(true)}
                className="lg:hidden p-1.5 rounded-[6px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[var(--text-primary)]"
                aria-label="Open navigation"
              >
                <Menu className="w-4 h-4" />
              </button>
              <span className="text-[12.5px] font-bold text-[var(--text-primary)]">
                FloodIQ Disaster Management Platform
              </span>
              <span
                className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-[4px] text-[10px] font-bold uppercase tracking-[0.06em] border ${
                  isSim
                    ? "bg-[#FEF2F2] text-[#991B1B] border-[#FCA5A5] dark:bg-[#FF5364]/15 dark:text-[#FF8E99] dark:border-[#FF5364]/45"
                    : "bg-[#ECFDF5] text-[#065F46] border-[#6EE7B7] dark:bg-[#37C98A]/15 dark:text-[#37C98A] dark:border-[#37C98A]/45"
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    isSim ? "bg-[var(--critical)]" : "bg-[var(--low)]"
                  }`}
                />
                {isSim ? "Simulation Active" : "Live Weather Feed"}
              </span>
              <span className="hidden sm:inline-flex items-center gap-1.5 px-2 py-0.5 rounded-[4px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[11px] text-[var(--text-secondary)]">
                <CloudRain className="w-3.5 h-3.5 text-[var(--teal)]" />
                {isSim ? `Scenario: ${rainfallMm} mm` : "Open-Meteo (Auto-Fallback)"}
              </span>
            </div>

            {/* Scenario Presets + Theme Toggle */}
            <div className="flex items-center gap-1.5 flex-wrap">
              {presets.map((p) => {
                const active = isSim && rainfallMm === p.mm;
                return (
                  <button
                    key={p.mm}
                    type="button"
                    onClick={() => {
                      setUseSimulation(true);
                      setRainfallMm(p.mm);
                    }}
                    className={`px-2 py-1 rounded-[5px] text-[11px] font-semibold border transition-colors cursor-pointer ${
                      active
                        ? "bg-[var(--teal)] text-[var(--teal-fg)] border-[var(--teal)] font-bold"
                        : "bg-[var(--bg-elevated)] text-[var(--text-secondary)] border-[var(--border-hairline)] hover:border-[var(--teal)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    {p.label}
                  </button>
                );
              })}
              <ThemeToggle />
            </div>
          </div>
        </header>

        <main className="flex-1 p-4 max-w-[1520px] w-full mx-auto">{children}</main>
      </div>
    </div>
  );
}
