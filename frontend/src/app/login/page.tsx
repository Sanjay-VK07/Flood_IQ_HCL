"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Eye,
  EyeOff,
  Lock,
  Mail,
  Waves,
} from "lucide-react";
import { roleHomePath, useAuth } from "@/context/AuthContext";
import { ThemeToggle } from "@/components/ThemeToggle";

const ROLES = [
  {
    key: "citizen" as const,
    label: "Citizen",
    hint: "Submit flood reports and track response status",
    email: "citizen@floodiq.demo",
    password: "Citizen@123",
  },
  {
    key: "authority" as const,
    label: "Municipal Authority",
    hint: "Command Center, AI triage review & dispatch approval",
    email: "authority@floodiq.demo",
    password: "Authority@123",
  },
  {
    key: "response_team" as const,
    label: "Response Team",
    hint: "Assigned field queue, acknowledgement & resolution",
    email: "bravo@floodiq.demo",
    password: "Team@123",
  },
];

const DEMO_ACCOUNTS = [
  {
    title: "Citizen Demo (Asha Reddy)",
    roleLabel: "Citizen",
    email: "citizen@floodiq.demo",
    password: "Citizen@123",
    roleKey: "citizen" as const,
  },
  {
    title: "Authority Demo (Officer Verma)",
    roleLabel: "Municipal Authority",
    email: "authority@floodiq.demo",
    password: "Authority@123",
    roleKey: "authority" as const,
  },
  {
    title: "Field Unit Demo (Bravo wrt_02)",
    roleLabel: "Response Team",
    email: "bravo@floodiq.demo",
    password: "Team@123",
    roleKey: "response_team" as const,
  },
  {
    title: "Field Unit Alt (Alpha wrt_01)",
    roleLabel: "Response Team",
    email: "alpha@floodiq.demo",
    password: "Team@123",
    roleKey: "response_team" as const,
  },
];

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [selectedRole, setSelectedRole] = useState<"citizen" | "authority" | "response_team">(
    "citizen"
  );
  const [email, setEmail] = useState("citizen@floodiq.demo");
  const [password, setPassword] = useState("Citizen@123");
  const [showPassword, setShowPassword] = useState(false);
  const [demoOpen, setDemoOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeRole = ROLES.find((r) => r.key === selectedRole) ?? ROLES[0];

  function handleSelectRole(roleKey: "citizen" | "authority" | "response_team") {
    const match = ROLES.find((r) => r.key === roleKey);
    if (!match) return;
    setSelectedRole(match.key);
    setEmail(match.email);
    setPassword(match.password);
    setError(null);
  }

  async function handleSignIn(targetEmail: string, targetPassword: string) {
    setError(null);
    if (!targetEmail.trim() || !targetPassword) {
      setError("Please enter both email address and password.");
      return;
    }
    setSubmitting(true);
    try {
      const signedInUser = await login(targetEmail.trim(), targetPassword);
      router.replace(roleHomePath(signedInUser.role));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid email or password.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative min-h-screen bg-[var(--bg-canvas)] text-[var(--text-primary)] flex flex-col justify-between overflow-hidden">
      {/* Subtle Topographic Flood-Contour Backdrop */}
      <svg
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 w-full h-full opacity-[0.045] dark:opacity-[0.07]"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <pattern id="fiq-contours" width="320" height="320" patternUnits="userSpaceOnUse">
            <path
              d="M0 160 Q80 110 160 160 T320 160 M0 80 Q90 35 180 85 T320 75 M0 245 Q75 200 155 240 T320 245"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
            />
            <circle cx="160" cy="160" r="92" fill="none" stroke="currentColor" strokeWidth="0.75" />
            <circle cx="160" cy="160" r="136" fill="none" stroke="currentColor" strokeWidth="0.6" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#fiq-contours)" />
      </svg>

      {/* Minimal Enterprise Header */}
      <header className="relative z-10 w-full max-w-5xl mx-auto px-5 pt-5 pb-2 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-8 h-8 rounded-[8px] bg-[var(--teal)] text-[var(--teal-fg)] flex items-center justify-center shrink-0">
            <Waves className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="text-[15px] font-bold tracking-tight text-[var(--text-primary)] leading-tight">
              FloodIQ
            </div>
            <div className="text-[11px] text-[var(--text-muted)] truncate">
              Urban Flood Intelligence &amp; Emergency Response
            </div>
          </div>
        </div>
        <ThemeToggle compact />
      </header>

      {/* Centered Authentication Container */}
      <main className="relative z-10 flex-1 flex items-center justify-center px-4 py-6">
        <div className="w-full max-w-[440px] space-y-3.5">
          {/* Primary Auth Card */}
          <section
            style={{ boxShadow: "var(--card-shadow)" }}
            className="rounded-[12px] bg-[var(--bg-panel)] border border-[var(--border-hairline)] p-6 sm:p-7 space-y-5"
          >
            <div className="space-y-1">
              <h1 className="text-[21px] font-bold tracking-tight text-[var(--text-primary)]">
                Welcome to FloodIQ
              </h1>
              <p className="text-[13px] text-[var(--text-secondary)]">
                Sign in to access your operational workspace.
              </p>
            </div>

            {/* Compact Role Selector */}
            <div className="space-y-1.5">
              <span className="block text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">
                Workspace Role
              </span>
              <div
                role="tablist"
                aria-label="Select operational role"
                className="grid grid-cols-3 gap-1 p-1 rounded-[8px] bg-[var(--bg-elevated)] border border-[var(--border-hairline)]"
              >
                {ROLES.map((role) => {
                  const active = selectedRole === role.key;
                  return (
                    <button
                      key={role.key}
                      type="button"
                      role="tab"
                      aria-selected={active}
                      onClick={() => handleSelectRole(role.key)}
                      className={`h-8 px-2 rounded-[6px] text-[11.5px] font-semibold transition-colors cursor-pointer truncate ${
                        active
                          ? "bg-[var(--bg-panel)] text-[var(--teal)] border border-[var(--teal)]/60 shadow-xs"
                          : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] border border-transparent"
                      }`}
                    >
                      {role.label}
                    </button>
                  );
                })}
              </div>
              <p className="text-[11.5px] text-[var(--text-muted)]">{activeRole.hint}</p>
            </div>

            {error && (
              <div
                role="alert"
                className="px-3 py-2.5 rounded-[8px] bg-[#FEF2F2] dark:bg-[#FF5364]/12 border border-[#FCA5A5] dark:border-[#FF5364]/40 text-[12.5px] text-[#991B1B] dark:text-[#FF8E99]"
              >
                {error}
              </div>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                void handleSignIn(email, password);
              }}
              className="space-y-4"
            >
              <div>
                <label
                  htmlFor="login-email"
                  className="block text-[12px] font-medium text-[var(--text-secondary)] mb-1.5"
                >
                  Email
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-[var(--text-muted)] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                  <input
                    id="login-email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@floodiq.demo"
                    className="w-full h-10 pl-9 pr-3 rounded-[8px] bg-[var(--bg-input)] border border-[var(--border-active)] focus:border-[var(--teal)] focus:outline-none text-[13.5px] text-[var(--text-primary)]"
                  />
                </div>
              </div>

              <div>
                <label
                  htmlFor="login-password"
                  className="block text-[12px] font-medium text-[var(--text-secondary)] mb-1.5"
                >
                  Password
                </label>
                <div className="relative">
                  <Lock className="w-4 h-4 text-[var(--text-muted)] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                  <input
                    id="login-password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    className="w-full h-10 pl-9 pr-10 rounded-[8px] bg-[var(--bg-input)] border border-[var(--border-active)] focus:border-[var(--teal)] focus:outline-none text-[13.5px] text-[var(--text-primary)]"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((prev) => !prev)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] cursor-pointer"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="w-full h-10 rounded-[8px] bg-[var(--teal)] hover:bg-[var(--teal-hover)] text-[var(--teal-fg)] text-[13.5px] font-semibold transition-colors cursor-pointer disabled:opacity-50"
              >
                {submitting ? "Signing In..." : "Sign In"}
              </button>
            </form>
          </section>

          {/* Separate Emergency Guest Action */}
          <Link
            href="/citizen"
            className="flex items-center justify-between gap-3 px-4 py-3 rounded-[10px] bg-[var(--bg-panel)] hover:border-[#DC2626]/70 border border-[var(--border-hairline)] transition-colors group"
          >
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-8 h-8 rounded-[7px] bg-[#FEF2F2] dark:bg-[#FF5364]/15 border border-[#FCA5A5] dark:border-[#FF5364]/35 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-4 h-4 text-[#DC2626] dark:text-[#FF5364]" />
              </div>
              <div className="min-w-0">
                <div className="text-[13px] font-semibold text-[var(--text-primary)]">
                  Report an Emergency
                </div>
                <div className="text-[11.5px] text-[var(--text-muted)] truncate">
                  Guest access — submit and track urgent flood hazards
                </div>
              </div>
            </div>
            <ArrowRight className="w-4 h-4 text-[var(--text-muted)] group-hover:text-[var(--text-primary)] shrink-0 transition-colors" />
          </Link>

          {/* Collapsible Demo Accounts */}
          <div className="rounded-[10px] bg-[var(--bg-panel)]/70 border border-[var(--border-hairline)] overflow-hidden">
            <button
              type="button"
              aria-expanded={demoOpen}
              onClick={() => setDemoOpen((prev) => !prev)}
              className="w-full px-4 py-2.5 flex items-center justify-between text-[12px] font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] cursor-pointer"
            >
              <span>Explore Demo Accounts</span>
              {demoOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>

            {demoOpen && (
              <div className="px-3 pb-3 pt-1 space-y-1.5 border-t border-[var(--border-hairline)]">
                {DEMO_ACCOUNTS.map((acct) => (
                  <button
                    key={acct.email}
                    type="button"
                    disabled={submitting}
                    onClick={() => {
                      setSelectedRole(acct.roleKey);
                      setEmail(acct.email);
                      setPassword(acct.password);
                      void handleSignIn(acct.email, acct.password);
                    }}
                    className="w-full px-3 py-2 rounded-[7px] bg-[var(--bg-elevated)] hover:border-[var(--teal)] border border-[var(--border-hairline)] flex items-center justify-between gap-2 text-left transition-colors cursor-pointer disabled:opacity-50"
                  >
                    <div className="min-w-0">
                      <div className="text-[12px] font-semibold text-[var(--text-primary)] truncate">
                        {acct.title}
                      </div>
                      <div className="text-[11px] font-mono text-[var(--text-muted)] truncate">
                        {acct.email}
                      </div>
                    </div>
                    <span className="text-[10.5px] font-semibold text-[var(--teal)] shrink-0">
                      {acct.roleLabel}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>

      <footer className="relative z-10 py-3 text-center text-[11px] text-[var(--text-muted)]">
        FloodIQ Disaster Management Platform · Hyderabad Pilot
      </footer>
    </div>
  );
}
