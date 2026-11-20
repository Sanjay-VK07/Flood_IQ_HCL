# FloodIQ Disaster Management Platform — Design System & Visual Source of Truth

**Official Product Name:** FloodIQ Disaster Management Platform  
**Tagline:** AI-Assisted Urban Flood Intelligence & Emergency Response Coordination  
**Authoritative Source:** Google Stitch Project `projects/331710229541389276` (*Urban Resilience Intelligence*) & `projects/16111334424151507466` (*FloodIQ Command Center*)

---

## 1. Brand Identity
- **Tone:** High-trust institutional civic intelligence — calm, daylight-readable in Light Mode, tactical high-contrast in Dark Mode, free of clutter.
- **Logo Mark:** Rounded square (`8px` radius) in primary teal (`#0d9488` / `#21c7b7`) containing a wave/shield glyph, paired with **FloodIQ** and **Disaster Management Platform** / portal subtitle.
- **Terminology:** Always distinguish AI-assisted incident triage (`Groq AI` vs `Rule-Based Fallback`) from deterministic flood-risk heuristics (`R = 0.40P + 0.30D + 0.30L`) and radar imagery (`RainViewer`).

---

## 2. Typography
- **Font Family:** `Inter` (`--font-inter`, sans-serif) with `font-variant-numeric: tabular-nums` for telemetry, scores, timestamps, and counts.
- **Scale (Stitch Tokens):**
  - `display`: `40px / 48px`, `700`, `-0.025em`
  - `headline-lg`: `32px / 40px`, `700`, `-0.02em` (mobile `26px / 34px`)
  - `headline-md`: `24px / 32px`, `600`, `-0.015em`
  - `headline-sm`: `20px / 28px`, `600`, `-0.01em`
  - `title-md`: `17px / 24px`, `600`, `-0.005em`
  - `body-lg`: `16px / 26px`, `400`
  - `body-md`: `15px / 24px`, `400`
  - `label-md`: `13px / 18px`, `500`, `0.01em`
  - `label-sm`: `11px / 16px`, `600`, `0.04em` (uppercase tracking tags)
  - `code`: `13px / 18px`, `500`

---

## 3. Color Tokens (Light & Dark Themes)

| Semantic Token | Light Mode (*Urban Resilience Intelligence*) | Dark Mode (*Tactical Operations*) | Usage |
| :--- | :--- | :--- | :--- |
| `--bg-canvas` | `#f8f9ff` | `#09131d` | Page background |
| `--bg-rail` | `#ffffff` | `#0d1c28` | Sidebar rail & sticky headers |
| `--bg-panel` | `#ffffff` | `#122431` | Cards, forms, tables |
| `--bg-elevated` | `#eff4ff` | `#192f3d` | Nested panels, hover states, soft containers |
| `--border-hairline` | `#e2e8f0` | `#1e384d` | Card & table hairlines |
| `--border-active` | `#cbd5e1` | `#24465f` | Interactive & focus borders |
| `--teal` | `#0d9488` | `#21c7b7` | Primary CTA, active nav, focus ring |
| `--teal-hover` | `#0f766e` | `#1eb2a4` | Primary hover |
| `--teal-fg` | `#ffffff` | `#09131d` | Text on primary teal buttons/tabs |
| `--text-primary` | `#0b1c30` | `#f0f5f8` | Headlines & primary body |
| `--text-secondary` | `#3d4947` | `#91a5b3` | Subtitles & metadata |
| `--text-muted` | `#64748b` | `#6a8294` | Captions & labels |
| `--critical` | `#dc2626` | `#ff5364` | Critical risk / SOS / immediate hazard |
| `--high` | `#d97706` | `#ff9b48` | High risk / active warning |
| `--moderate` | `#ca8a04` | `#e8c45a` | Moderate advisory |
| `--low` | `#059669` | `#37c98a` | Nominal / resolved |

---

## 4. Screen-to-Route Mapping (Stitch -> Next.js)

| Stitch Screen (Project `331710229541389276`) | Device | Next.js Route | Role |
| :--- | :--- | :--- | :--- |
| `FloodIQ - Role Portal & Access` (`8a0690ad...`) | Mobile / Responsive | `/login` | All Roles & Guest CTA |
| `Citizen Flood Dashboard` (`13282651...` Light, `4a149b03...` Dark) | Mobile-first | `/citizen` | `citizen` / Guest |
| `Report Flood Emergency` (`a6231efd...`) | Mobile-first | `/citizen` (`Report` tab) | `citizen` / Guest |
| `Field Responder Operations` (`582feeb0...`) | Mobile-first | `/team` | `response_team` |
| `Municipal Authority — Command Center` (`a4c232f1...`) | Desktop | `/` | `authority` |
| Authority Secondary Screens (`16111334424151507466`) | Desktop | `/risk`, `/preparedness`, `/report`, `/control-room`, `/history`, `/system` | `authority` |

---

## 5. Responsive Behavior & Navigation
- **Desktop (`1440x900`, `1280x720`)**: Authority portal uses fixed `236px` left sidebar + sticky operational topbar + 12-column grids (`max-w-[1520px]`). Login uses 2-column split.
- **Tablet (`768x1024`)**: Authority sidebar collapses into slide-out drawer (`lg:hidden`); multi-column cards stack into 2-column or 1-column grids.
- **Mobile (`390x844`)**: Citizen & Response Team portals are mobile-first (`max-w-3xl` centered); Citizen uses a fixed bottom navigation bar (`Dashboard`, `Report`, `Tracking`, `Safety`, `Portals`) on mobile (`md:hidden`) and top tabs on larger screens; minimum `44px` tap targets.
