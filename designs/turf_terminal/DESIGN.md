---
name: Turf Terminal
colors:
  surface: '#111316'
  surface-dim: '#111316'
  surface-bright: '#37393d'
  surface-container-lowest: '#0c0e11'
  surface-container-low: '#1a1c1f'
  surface-container: '#1e2023'
  surface-container-high: '#282a2d'
  surface-container-highest: '#333538'
  on-surface: '#e2e2e6'
  on-surface-variant: '#bbcabf'
  inverse-surface: '#e2e2e6'
  inverse-on-surface: '#2f3034'
  outline: '#86948a'
  outline-variant: '#3c4a42'
  surface-tint: '#4edea3'
  primary: '#4edea3'
  on-primary: '#003824'
  primary-container: '#10b981'
  on-primary-container: '#00422b'
  inverse-primary: '#006c49'
  secondary: '#c4c6ce'
  on-secondary: '#2d3037'
  secondary-container: '#464950'
  on-secondary-container: '#b6b8c0'
  tertiary: '#ffb95f'
  on-tertiary: '#472a00'
  tertiary-container: '#e29100'
  on-tertiary-container: '#523200'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#6ffbbe'
  primary-fixed-dim: '#4edea3'
  on-primary-fixed: '#002113'
  on-primary-fixed-variant: '#005236'
  secondary-fixed: '#e1e2ea'
  secondary-fixed-dim: '#c4c6ce'
  on-secondary-fixed: '#191c22'
  on-secondary-fixed-variant: '#44474d'
  tertiary-fixed: '#ffddb8'
  tertiary-fixed-dim: '#ffb95f'
  on-tertiary-fixed: '#2a1700'
  on-tertiary-fixed-variant: '#653e00'
  background: '#111316'
  on-background: '#e2e2e6'
  surface-variant: '#333538'
typography:
  h1:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.02em
  h2:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  body:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  data-lg:
    fontFamily: JetBrains Mono
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 20px
  data-md:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 16px
  label-caps:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.05em
spacing:
  unit: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  gutter: 12px
  margin: 16px
---

## Brand & Style
This design system is engineered for the high-stakes environment of horse racing analysis, adopting a "Trading Terminal" aesthetic that prioritizes information density and split-second readability. The brand personality is clinical, authoritative, and fast-paced, catering to professional bettors and data analysts who require a "heads-up display" feel.

The design style is **Brutalist-Modern Hybrid**: it utilizes the structural rigidity of a grid-based terminal with the refined polish of modern SaaS. It avoids decorative fluff, focusing instead on high-contrast data visualization, sharp borders, and a systematic hierarchy that guides the eye through complex racing forms and live odds movements.

## Colors
The palette is rooted in a "Deep Dark" scheme to reduce eye strain during long analysis sessions. 

- **Foundations:** The primary canvas uses Deep Charcoal (#121417) for the lowest layer, while Dark Navy (#1A1D23) is used for elevated containers and cards to create subtle structural variance.
- **Accents:** Vibrant Emerald (#10B981) is reserved for "Value" indicators and shortening odds. Crimson Red (#EF4444) signals "Drifting" odds or poor performance metrics. Amber (#F59E0B) acts as a cautionary toggle for neutral trends or warnings.
- **Typography:** High-contrast Off-White (#E0E6ED) ensures core data is legible against the dark backdrop, while Muted Grey (#94A3B8) is used for labels and metadata to de-emphasize secondary noise.

## Typography
The typographic system utilizes a dual-font approach to separate interface navigation from analytical data.

- **UI & Interface:** Inter is the workhorse for all navigational elements, labels, and descriptive text. Its neutrality ensures the interface stays out of the way of the data.
- **Data & Odds:** A monospace font (JetBrains Mono) is strictly enforced for all numerical values, odds, and time-stamps. This ensures vertical alignment in tables, allowing users to scan columns of shifting prices without horizontal jitter.
- **Scale:** Type sizes are intentionally compact (primarily 13px-14px) to maximize the amount of information visible on a single screen.

## Layout & Spacing
This design system employs a **Fixed Grid** layout for dashboard views to maintain the "Terminal" feel, switching to a fluid model for mobile.

- **Grid:** A 12-column system with tight 12px gutters.
- **Rhythm:** A strict 4px baseline grid governs all spacing. Vertical padding in tables is kept to a minimum (sm: 8px) to increase row density.
- **Density:** High-density layout is the priority. Modules should be packed tightly with clear 1px borders as the primary separator rather than generous whitespace.

## Elevation & Depth
In this design system, depth is achieved through **Tonal Layers** and **Bold Borders** rather than shadows. 

- **Surface Levels:** The background sits at #121417. Component containers (cards, panels) use #1A1D23. 
- **Borders:** Every functional module must be contained within a 1px solid border (#2D3748). This creates a "panelized" look reminiscent of professional trading software.
- **Interactive States:** Hovering over a row or card should change its background color to a slightly lighter navy (#262B34) or increase border brightness. No blurred shadows are permitted; depth is strictly architectural.

## Shapes
To reinforce the authoritative and technical nature of the app, this design system uses **Sharp (0px)** or **Minimal (2px)** roundedness. 

Hard edges are preferred for all data tables, input fields, and structural containers. This maximizes screen real estate and aligns with the monospace aesthetic. Only high-level action buttons (like "Place Bet") may use a subtle 2px radius to distinguish them from data cells.

## Components
Consistent styling across the terminal ensures rapid user processing:

- **Data Tables:** These are the core of the system. They feature subtle zebra striping (alternate rows at #1E2229), 1px horizontal dividers, and fixed-width columns for monospace data.
- **Cards:** Clean, flat panels with a 1px border. Header areas within cards should have a distinct, slightly darker background or a bottom border.
- **Buttons:** 
    - *Primary:* Solid Emerald Green with black text for high visibility.
    - *Secondary/Outline:* 1px Grey border with Off-White text.
- **Chips/Badges:** Small, rectangular badges for "Form" (e.g., [ 1 ] [ 3 ] [ 2 ]) using neutral backgrounds, with color only applied to denote significant wins or losses.
- **Input Fields:** Dark background (#121417), 1px border, and monospace text for numerical inputs.
- **Sparklines/Charts:** Ultra-thin (1.5pt) line charts for price movement history, utilizing the Green/Red accent colors for trend direction.
- **Status Indicators:** Small, solid circles (10px) used next to horse names to indicate "Live," "Withdrawn," or "Late Loading."