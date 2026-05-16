# DESIGN.md — Hilo Dispatch (Hackathon)

Pinned in Pass 5 of /plan-design-review. Frontend implementation lives in `frontend/`.

## Posture
Dispatch console. Reference: Bloomberg Terminal, Palantir Foundry, ATC consoles.
Calm, dense, monospace numerals, color used only for signal. Reads at 1m and at 20m.

## Typography
- Display & numerals: **JetBrains Mono** (`tnum` feature on), 32/18/14
- Body: **Inter** 400/500, 14/12/11
- Severity labels: Inter 11px ALL CAPS, letter-spacing 0.08em
- Never `system-ui` or default stacks as primary.

## Color tokens (CSS variables via Tailwind)
```
--sev-immediate: #EF4444   /* red, AA contrast 5.94:1 on dark map */
--sev-delayed:   #FACC15   /* yellow, contrast 11.49:1 */
--sev-minor:     #22C55E   /* green, contrast 6.55:1 */
--sev-deceased:  #1F2937   /* dim, white halo for visibility */

--bg-base:   #0B0F19
--bg-panel:  #0F172A
--bg-elev:   #1E293B
--border-strong: #334155

--fg-primary:   #F1F5F9
--fg-secondary: #94A3B8
--fg-muted:     #64748B

--status-good: #10B981
--status-warn: #F59E0B
```

## Spacing scale
4 / 8 / 12 / 16 / 24 / 32 / 48

## Border radius scale
0 (panels) / 2 (badges) / 4 (cards, toasts). Never above 4.

## Motion
- Severity flash: 200ms halo + 2s × 3 pulses (`animate-severity-pulse`)
- Counter animation: 1s ease-out cubic via `requestAnimationFrame`
- Toast slide-in: 200ms ease-out, 8s auto-dismiss, max 2 visible
- Tile flash: 600ms background fade
- Page transitions: none (single-screen console)

## Severity shapes paired with color (a11y)
- Immediate: circle
- Delayed:   square
- Minor:     triangle
- Deceased:  circle with X overlay (white halo for visibility on dark map)

## Hard rules
- No purple/violet gradients.
- No 3-column feature grids.
- No decorative blobs or wavy SVGs.
- No emoji as design elements.
- No icons in colored circles for the 5 Snowflake tiles. The data shape IS the visual.
- No system-ui / -apple-system as primary font.
- No uniform bubbly border-radius.
- `prefers-reduced-motion` honored.

## Layout (1440×900 baseline, 1280×720 minimum)
- Top bar: 56px. "▲ HILO DISPATCH" + live counts + dispatcher buttons.
- Map: ~60% of viewport. Dominant.
- Incident list: 360px right rail.
- Infrastructure + Snowflake tiles: 180px bottom strip (280px infra + remaining 4 peer tiles).
- Cortex alert: floating toast top-right of map, slide-in.

## Empty state
"3 units staged. Awaiting incidents." centered, 14px regular + 14px italic. No card.
