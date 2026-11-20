"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  KeyRound,
  PlayCircle,
  Radio,
  Shield,
  Waves,
} from "lucide-react";
import { roleHomePath, useAuth } from "@/context/AuthContext";
import { ThemeToggle } from "@/components/ThemeToggle";

const ROLE_CARDS = [
  {
    key: "citizen",
    label: "Citizen Portal",
    badge: "DIRECT PUBLIC ACCESS",
    desc: "Neighborhood flood alerts, quick hazard reporting, and live incident tracking.",
    meta: "Public Telemetry · Guest or Account",
    email: "citizen@floodiq.demo",
    password: "Citizen@123",
    icon: Shield,
    badgeClass:
      "bg-[#F0FDFA] text-[#0F766E] border-[#99F6E4] dark:bg-[#21C7B7]/15 dark:text-[#21C7B7] dark:border-[#21C7B7]/40",
    dotColor: "bg-[#0D9488] dark:bg-[#21C7B7]",
  },
  {
    key: "authority",
    label: "Municipal Authority",
    badge: "OPERATIONS CENTER",
    desc: "Command center oversight, AI-assisted triage review, and human-approved dispatch.",
    meta: "Hyderabad Pilot · Dispatch Gate",
    email: "authority@floodiq.demo",
    password: "Authority@123",
    icon: Building2,
    badgeClass:
      "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE] dark:bg-[#55A8FF]/15 dark:text-[#55A8FF] dark:border-[#55A8FF]/40",
    dotColor: "bg-[#2563EB] dark:bg-[#55A8FF]",
  },
  {
    key: "response_team",
    label: "Emergency Response Team",
    badge: "TACTICAL FIELD UNIT",
    desc: "Assigned dispatch queue, assignment acknowledgement, field notes, and resolution.",
    meta: "Unit wrt_02 (Bravo) · Live Sync",
    email: "bravo@floodiq.demo",
    password: "Team@123",
    icon: Radio,
    badgeClass:
      "bg-[#FEF2F2] text-[#991B1B] border-[#FCA5A5] dark:bg-[#FF5364]/15 dark:text-[#FF8E99] dark:border-[#FF5364]/40",
    dotColor: "bg-[#DC2626] dark:bg-[#FF5364]",
  },
];

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [selectedRole, setSelectedRole] = useState<string>("citizen");
  const [email, setEmail] = useState("citizen@floodiq.demo");
  const [password, setPassword] = useState("Citizen@123");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSignIn(targetEmail: string, targetPassword: string) {
    setError(null);
    setSubmitting(true);
    try {
      const signedInUser = await login(targetEmail, targetPassword);
      router.replace(roleHomePath(signedInUser.role));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-[var(--bg-canvas)] text-[var(--text-primary)] px-4 py-6">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Top Bar */}
        <div className="flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--bg-elevated)] border border-[var(--border-hairline)] text-[11px] font-bold uppercase tracking-[0.06em] text-[var(--teal)]">
            <span className="w-2 h-2 rounded-full bg-[var(--teal)]" />
            <span>Live Civic Hydrological Network</span>
          </div>
          <ThemeToggle />
        </div>

        {/* Brand Header */}
        <div className="text-center max-w-2xl mx-auto space-y-2">
          <div className="inline-flex items-center gap-3 justify-center">
            <div className="w-11 h-11 rounded-[10px] bg-[var(--teal)] text-[var(--teal-fg)] flex items-center justify-center shadow-sm">
              <Waves className="w-6 h-6" />
            </div>
            <div className="text-left">
              <h1 className="text-[22px] sm:text-[26px] font-bold tracking-tight text-[var(--text-primary)] leading-tight">
                FloodIQ Disaster Management Platform
              </h1>
              <p className="text-[12.5px] font-semibold text-[var(--teal)]">
                AI-Assisted Urban Flood Intelligence &amp; Emergency Response Coordination
              </p>
            </div>
          </div>
          <p className="text-[13.5px] text-[var(--text-secondary)]">
            Unified decision-support connecting citizens, municipal authorities, and emergency
            response teams in synchronized real-time.
          </p>
        </div>

        {/* Main 2-Column Responsive Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
          {/* Left: Role Portal Cards + Guest Emergency Banner */}
          <div className="lg:col-span-7 space-y-3.5">
            <div className="flex items-center justify-between px-1">
              <span className="text-[11px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                Select Active Operational Role
              </span>
              <span className="text-[11.5px] font-semibold text-[var(--teal)]">RBAC Protected</span>
            </div>

            {ROLE_CARDS.map((card) => {
              const Icon = card.icon;
              const isSelected = selectedRole === card.key;
              return (
                <button
                  key={card.key}
                  type="button"
                  disabled={submitting}
                  onClick={() => {
                    setSelectedRole(card.key);
                    setEmail(card.email);
                    setPassword(card.password);
                    void handleSignIn(card.email, card.password);
                  }}
                  style={{ boxShadow: "var(--card-shadow)" }}
                  className={`w-full text-left p-4 rounded-[12px] bg-[var(--bg-panel)] border transition-all flex items-center justify-between gap-3 cursor-pointer disabled:opacity-50 ${
                    isSelected
                      ? "border-[var(--teal)] ring-1 ring-[var(--teal)]/30"
                      : "border-[var(--border-hairline)] hover:border-[var(--border-active)]"
                  }`}
                >
                  <div className="flex items-start gap-3.5 min-w-0">
                    <div className="relative p-2.5 rounded-[10px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)] shrink-0">
                      <Icon className="w-5 h-5 text-[var(--text-primary)]" />
                      <span
                        className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-[var(--bg-panel)] ${card.dotColor}`}
                      />
                    </div>
                    <div className="min-w-0 space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[15px] font-bold text-[var(--text-primary)]">
                          {card.label}
                        </span>
                        <span
                          className={`px-2 py-0.5 rounded-[4px] border text-[10px] font-bold uppercase tracking-[0.05em] ${card.badgeClass}`}
                        >
                          {card.badge}
                        </span>
                      </div>
                      <p className="text-[12.5px] text-[var(--text-secondary)] leading-snug">
                        {card.desc}
                      </p>
                      <div className="text-[11px] font-medium text-[var(--text-muted)]">
                        {card.meta}
                      </div>
                    </div>
                  </div>
                  <ArrowRight className="w-4 h-4 text-[var(--text-muted)] shrink-0" />
                </button>
              );
            })}

            {/* Red Guest Hazard Banner (matches Stitch) */}
            <Link
              href="/citizen"
              className="block p-4 rounded-[12px] bg-[#DC2626] hover:bg-[#B91C1C] text-white transition-colors shadow-sm"
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-[8px] bg-white/15 shrink-0">
                    <AlertTriangle className="w-5 h-5 text-white" />
                  </div>
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-white/90">
                      Immediate Hazard Alert
                    </div>
                    <div className="text-[14px] font-bold leading-snug">
                      Need to report an active flood without logging in?
                    </div>
                  </div>
                </div>
                <div className="p-2 rounded-[8px] bg-white text-[#DC2626] shrink-0">
                  <ArrowRight className="w-4 h-4" />
                </div>
              </div>
            </Link>
          </div>

          {/* Right: Credentials Form + 1-Tap Demo Switcher */}
          <div className="lg:col-span-5 space-y-4">
            <div
              style={{ boxShadow: "var(--card-shadow)" }}
              className="p-5 rounded-[12px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] space-y-4"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <KeyRound className="w-4 h-4 text-[var(--teal)]" />
                  <h2 className="text-[15px] font-bold text-[var(--text-primary)]">
                    Authenticate Session
                  </h2>
                </div>
                <div className="inline-flex rounded-[6px] bg-[var(--bg-elevated)] p-0.5 border border-[var(--border-hairline)] text-[11px] font-semibold">
                  {[
                    { id: "citizen", label: "Public" },
                    { id: "authority", label: "Ops" },
                    { id: "response_team", label: "Field" },
                  ].map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => {
                        const match = ROLE_CARDS.find((r) => r.key === t.id);
                        if (match) {
                          setSelectedRole(match.key);
                          setEmail(match.email);
                          setPassword(match.password);
                        }
                      }}
                      className={`px-2 py-1 rounded-[4px] transition-colors ${
                        selectedRole === t.id
                          ? "bg-[var(--bg-panel)] text-[var(--text-primary)] shadow-xs"
                          : "text-[var(--text-muted)]"
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>

              {error && (
                <div className="p-3 rounded-[6px] bg-[#FEF2F2] dark:bg-[#FF5364]/15 border border-[#FCA5A5] dark:border-[#FF5364]/40 text-[12px] text-[#991B1B] dark:text-[#FF8E99]">
                  {error}
                </div>
              )}

              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void handleSignIn(email, password);
                }}
                className="space-y-3.5"
              >
                <div>
                  <label
                    htmlFor="login-email"
                    className="block text-[11px] font-bold uppercase tracking-[0.06em] text-[var(--text-secondary)] mb-1"
                  >
                    Email Address
                  </label>
                  <input
                    id="login-email"
                    name="email"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="user@floodiq.demo"
                    className="w-full px-3 py-2.5 rounded-[8px] bg-[var(--bg-input)] border border-[var(--border-active)] focus:border-[var(--teal)] focus:outline-none text-[13.5px] text-[var(--text-primary)]"
                  />
                </div>

                <div>
                  <label
                    htmlFor="login-password"
                    className="block text-[11px] font-bold uppercase tracking-[0.06em] text-[var(--text-secondary)] mb-1"
                  >
                    Password
                  </label>
                  <input
                    id="login-password"
                    name="password"
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full px-3 py-2.5 rounded-[8px] bg-[var(--bg-input)] border border-[var(--border-active)] focus:border-[var(--teal)] focus:outline-none text-[13.5px] text-[var(--text-primary)]"
                  />
                </div>

                <button
                  type="submit"
                  disabled={submitting}
                  className="w-full py-2.5 rounded-[8px] bg-[var(--teal)] hover:bg-[var(--teal-hover)] text-[var(--teal-fg)] text-[13.5px] font-bold transition-colors cursor-pointer disabled:opacity-50"
                >
                  {submitting ? "Authenticating..." : "Authenticate Session"}
                </button>
              </form>
            </div>

            {/* Demo Switcher Card (matches Stitch) */}
            <div
              style={{ boxShadow: "var(--card-shadow)" }}
              className="p-4 rounded-[12px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] space-y-2.5"
            >
              <div className="flex items-center justify-between">
                <span className="text-[13px] font-bold text-[var(--text-primary)]">
                  Demo Profile Switcher
                </span>
                <span className="px-2 py-0.5 rounded-[4px] bg-[#F0FDFA] dark:bg-[#21C7B7]/15 text-[#0F766E] dark:text-[#21C7B7] text-[10px] font-bold">
                  1-Tap Load
                </span>
              </div>
              <div className="space-y-1.5">
                {[
                  {
                    title: "Load Citizen Demo (Asha Reddy)",
                    sub: "citizen@floodiq.demo",
                    pw: "Citizen@123",
                  },
                  {
                    title: "Load Authority Demo (Officer Verma)",
                    sub: "authority@floodiq.demo",
                    pw: "Authority@123",
                  },
                  {
                    title: "Load Field Unit Demo (Bravo wrt_02)",
                    sub: "bravo@floodiq.demo",
                    pw: "Team@123",
                  },
                  {
                    title: "Load Field Unit Alt (Alpha wrt_01)",
                    sub: "alpha@floodiq.demo",
                    pw: "Team@123",
                  },
                ].map((d) => (
                  <button
                    key={d.sub}
                    type="button"
                    disabled={submitting}
                    onClick={() => {
                      setEmail(d.sub);
                      setPassword(d.pw);
                      void handleSignIn(d.sub, d.pw);
                    }}
                    className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-[8px] bg-[var(--bg-elevated)] hover:border-[var(--teal)] border border-[var(--border-hairline)] text-left transition-colors cursor-pointer"
                  >
                    <div className="min-w-0">
                      <div className="text-[12px] font-semibold text-[var(--text-primary)] truncate">
                        {d.title}
                      </div>
                      <div className="text-[10.5px] font-mono text-[var(--text-muted)] truncate">
                        {d.sub}
                      </div>
                    </div>
                    <PlayCircle className="w-4 h-4 text-[var(--teal)] shrink-0" />
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
