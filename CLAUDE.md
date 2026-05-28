# self-host-planning-poker (marloeuyjr fork)

Source for the Driftsprognoser-branded planning poker app deployed at <https://poker.marloeuy.com>. Built and pushed to `ghcr.io/marloeuyjr/self-host-planning-poker` via `.github/workflows/publish.yml` on `v*` tags. The deployment manifests and decisions log live in the sibling repo at `~/projects/dpro-poker/`.

Tag flow: edit → PR + squash-merge → `git tag -a vX.Y.Z && git push origin vX.Y.Z` → CI builds + pushes `{X.Y.Z, X.Y, X}` semver-fanout image tags. Then bump `image:` in `~/projects/dpro-poker/k8s/deployment.yaml` and `kubectl apply -k`.

## Stack
- Angular 17 + ng-bootstrap 16 + Bootstrap 5.3
- Transloco for i18n (en/fr/de/it/pl); see `angular/src/assets/i18n/*.json`
- Flask + Flask-SocketIO + eventlet on the server side; SQLite persistence in `/data/games.db`
- `replicas: 1` mandatory — Socket.IO state is in-process eventlet, no Redis adapter

## Build-time gotcha
Angular's prerender step strips visible content out of `index.html` (including `<title>`). For any *visible* text change, edit `angular/src/assets/i18n/*.json` (Transloco at runtime) or route titles in `angular/src/main.ts`. Editing `index.html` and expecting a visible result will not work.

## Brand assets
- `angular/src/assets/icon.svg` — favicon-family source (referenced by `index.html` + favicon PNGs)
- `angular/src/assets/nav-logo.svg` — navbar `<img>` source (referenced by `navigation-bar.component.html:5`)
Change one, not both, unless brand consistency requires it.

---

## Design Context

### Users
Internal — the Driftsprognoser team running sprint-planning sessions on `https://poker.marloeuy.com`. Insider tone is acceptable. The product does not need to onboard strangers; users already know what planning poker is and what the team is. Sessions happen on desktop browsers during work hours.

### Brand Personality
**Technical, utilitarian, opinionated.** This is an operations-room interface, not a party game. Function over feel; minimal decoration. Think Grafana, Datadog, `k9s`, terminal-adjacent — dense, calm, fast, decisive. The name "Driftsprognoser" (Norwegian: *operational forecasts*) and the dashed-trend-line motif in the logo encode this: estimation as forecasting, not gamification.

Three-word personality: **calm · operational · decisive**.

### Aesthetic Direction
- **Theme**: dark. Work-hour estimation on desktop monitors; the slate-900 background is non-negotiable and already established in the logo + favicon family.
- **Palette** (already set in `assets/icon.svg` and `assets/nav-logo.svg`):
  - Background slate-900 `#0F172A` (oklch ≈ 0.21 0.04 265)
  - Emerald-500 `#10B981` (primary accent — voting cards, primary CTAs)
  - Emerald-400 `#34D399` (mid accent — hover states, links)
  - Emerald-300 `#6EE7B7` (highlight — confirmations, selected states)
  - Slate-600 `#475569` for muted lines (matches the dashed forecast line in the nav logo)
- **References**: Grafana panels, Linear command bar, k9s terminal UI, Stripe API docs sidebar. Anti-references: anything resembling Slack, Notion playful illustrations, generic "poker night" casino felt, or AI-slop gradient hero sections.
- **Typography**: utilitarian. Display + body should not feel "designy." Consider a single utilitarian sans (avoid Inter / Plex / DM family — they're reflex picks). A geometric grotesque or industrial sans with a paired monospace for numeric/data accents fits the ops-room ethos.
- **Motion**: minimal. State changes get 150-200ms ease-out transitions. No bouncy easings. Confetti on full agreement stays (already shipped) — it's the one permitted moment of celebration in an otherwise restrained UI.

### Design Principles
1. **The slate+emerald palette is the brand.** Replace residual Bootstrap green throughout; thread the tokens through SCSS variables before the Bootstrap `@import` so the whole component library inherits the brand, not just the navbar.
2. **Operational restraint.** No card-on-card nesting, no glassmorphism, no decorative gradients, no border-left accent stripes, no gradient text. Density is preferred to whitespace-padding when both are valid.
3. **Numbers are primary content.** Vote values, averages, agreement percentages, deck names — these are the meaningful tokens. Treat them like a dashboard treats metrics: large, precise, monospaced where it aids alignment.
4. **Dark mode is the default, light mode is the courtesy.** Both must work, but every design decision is made dark-first.
5. **Forecasting motif as the through-line.** The dashed velocity-trend line in the logo can echo subtly in dividers, focus rings, or the empty-state-before-first-vote moment. Use sparingly so it stays a signature rather than decoration.
