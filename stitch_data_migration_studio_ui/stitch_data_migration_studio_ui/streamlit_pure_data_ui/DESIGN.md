---
name: Streamlit Pure Data UI
colors:
  surface: '#faf8ff'
  surface-dim: '#d6d9ec'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3ff'
  surface-container: '#eaedff'
  surface-container-high: '#e4e7fa'
  surface-container-highest: '#dee2f5'
  on-surface: '#171b29'
  on-surface-variant: '#5b403e'
  inverse-surface: '#2c303e'
  inverse-on-surface: '#eef0ff'
  outline: '#906f6d'
  outline-variant: '#e4bdba'
  surface-tint: '#bb1522'
  primary: '#b81120'
  on-primary: '#ffffff'
  primary-container: '#dc3135'
  on-primary-container: '#fffbff'
  inverse-primary: '#ffb3ae'
  secondary: '#5d5e68'
  on-secondary: '#ffffff'
  secondary-container: '#e2e1ee'
  on-secondary-container: '#63636e'
  tertiary: '#005bb1'
  on-tertiary: '#ffffff'
  tertiary-container: '#2074d5'
  on-tertiary-container: '#fefcff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#ffdad7'
  primary-fixed-dim: '#ffb3ae'
  on-primary-fixed: '#410004'
  on-primary-fixed-variant: '#930014'
  secondary-fixed: '#e2e1ee'
  secondary-fixed-dim: '#c6c5d1'
  on-secondary-fixed: '#1a1b24'
  on-secondary-fixed-variant: '#454650'
  tertiary-fixed: '#d6e3ff'
  tertiary-fixed-dim: '#a9c7ff'
  on-tertiary-fixed: '#001b3d'
  on-tertiary-fixed-variant: '#00468b'
  background: '#faf8ff'
  on-background: '#171b29'
  surface-variant: '#dee2f5'
typography:
  headline-xl:
    fontFamily: Source Sans 3
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
  headline-xl-mobile:
    fontFamily: Source Sans 3
    fontSize: 30px
    fontWeight: '700'
    lineHeight: 38px
  headline-lg:
    fontFamily: Source Sans 3
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
  headline-md:
    fontFamily: Source Sans 3
    fontSize: 22px
    fontWeight: '600'
    lineHeight: 28px
  headline-sm:
    fontFamily: Source Sans 3
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  body-lg:
    fontFamily: Source Sans 3
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Source Sans 3
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Source Sans 3
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-lg:
    fontFamily: Source Sans 3
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 18px
  label-md:
    fontFamily: Source Sans 3
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
  label-sm:
    fontFamily: Source Sans 3
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-desktop: 1.5rem
  margin: 1rem
  margin-desktop: 2.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
---

## Brand & Style

This design system delivers a streamlined, utility-first aesthetic native to Python data apps, modern analytical workspaces, and machine learning consoles. Built around the classic Streamlit visual grammar, it emphasizes low-latency perception, functional clarity, and zero-distraction data storytelling. 

The aesthetic is clean, objective, and developer-centric:
- **Tone:** Analytical, dependable, transparent, and effortlessly agile.
- **Audience:** Data scientists, ML engineers, analytics translators, and business decision-makers requiring rapid clarity from complex underlying models.
- **Design Movement:** Modern Data Minimalist. It pairs high-clarity white card containers against a cooling, soft-slate structural canvas (`#F0F2F6`), anchored decisively by the signature coral red (`#FF4B4B`). Visual weight is assigned through precise spatial alignment and clean typographic hierarchy rather than heavy ornamental gradients or floating 3D layers.

## Colors

The palette establishes an immediate sense of familiar data workspace utility, combining an ultra-clean foundation with decisive semantic accents.

### Core Swatches
- **Primary (`#FF4B4B`):** Signature Streamlit Coral Red. Used for interactive primary buttons, active tab indicators, selected radio stems, slider thumbs, and high-priority action points.
- **Secondary (`#262730`):** Charcoal Body Ink. Serves as the primary content ink, delivering crisp legibility for titles, data numbers, and dense analytical reading without the harsh glare of pure `#000000`.
- **Tertiary (`#0068C9`):** Interactive Data Blue. Applied to informational banners (`st.info`), linked data references, interactive table column filters, and secondary chart strokes.
- **Neutral (`#808495`):** Slate Neutral. Bridges structural boundaries, sub-labels, input helper text, and secondary state icons.

### Surface Architecture & Semantics
- **Canvas Base:** `#F0F2F6` (App-level canvas, drawer backdrops, and sidebar foundation).
- **Surface Elevation (Cards):** `#FFFFFF` (Crisp data containers, metrics boxes, dataframe backdrops).
- **Subtle Surface Tint:** `#F9FAFC` (Table header fills, code block containers, disabled control backings).
- **Semantic Callouts:**
  - **Success (`#09AB3B`):** Trend metrics, positive state chips, and `st.success` banners.
  - **Warning (`#FFBD45`):** Caution states, amber metric variances, and `st.warning` boxes.
  - **Error (`#FF4B4B`):** Pipeline failures, model exceptions, and `st.error` notifications.

## Typography

The type system uses `Source Sans 3` across all hierarchy levels to preserve absolute consistency, dense vertical scans, and comfortable reading in data-heavy screens. Code blocks, tabular figures, and JSON payloads should reference a system monospaced stack (`Roboto Mono`, `Source Code Pro`, monospace) with optical alignment to `body-md`.

Typographic Rules:
- **Headline Rhythm:** Keep headers concise; maintain tight vertical margins above associated metric cards or data visualizations.
- **Tabular Figures:** Numbers in `st.metric` values and dataframe rows must use tabular numeral spacing (`font-variant-numeric: tabular-nums`) to prevent horizontal jitter during reactive state recalculations.
- **Microcopy:** Use `label-sm` in uppercase with subtle letter-spacing for metric deltas and input category metadata.

## Layout & Spacing

The layout is built on a responsive 12-column fluid grid that adapts between full-width responsive dashboards and fixed analytical reports.

### Architecture & Breakpoints
- **Desktop (≥ 1024px):** Persistent 300px sidebar (`#F0F2F6`) or top sticky tab navigation. Main canvas features a controlled maximum reading width of 1200px or an optional full-width toggle for wide dataframes. Gutters sit at `1.5rem` (`gutter-desktop`) with `2.5rem` canvas margins (`margin-desktop`).
- **Tablet (768px – 1023px):** Sidebar collapses into a slide-over flyout triggered via a top-left hamburger menu. Grid compresses to 6 columns with `1rem` gutters.
- **Mobile (< 768px):** Single-column vertical stream. Sidebars convert into modal sheets. All cards and metrics reflow to 100% width with `1rem` outer canvas padding (`margin`).

### Spacing Philosophy
Spacing tokens are applied strictly as relational distance:
- `space-xs` (4px): Micro gaps between metric labels and directional chevron indicators.
- `space-sm` (8px): Form input inner paddings, list-item separations, chip internal padding.
- `space-md` (16px): Standard gap between neighboring form components, metric card internals, and list blocks.
- `space-lg` (24px): Boundary separations between distinct application segments (e.g., metric row to chart canvas).
- `space-xl` (32px): Major vertical demarcations between analytical sections.

## Elevation & Depth

Visual depth follows a disciplined flat-to-low-profile structure. Layers are established primarily via **tonal surface separation** and **subtle, high-precision outlines** rather than heavy drop shadows.

### Elevation Hierarchy
1. **Level 0 (Canvas Backdrop):** Solid `#F0F2F6`. Forms the bedrock surface behind all cards, control panels, and application sidebars.
2. **Level 1 (Card & Content Tier):** Solid `#FFFFFF` enclosed with a 1px border of `rgba(38, 39, 48, 0.08)`. Zero shadow is applied by default. This hosts `st.metric`, plot widgets, dataframes, and callout cards.
3. **Level 2 (Active / Hover / Interactive Surface):** Applied to floating select menus, tooltips, popovers, and hovered cards. A subtle, crisp ambient shadow is introduced: `0 4px 16px rgba(38, 39, 48, 0.08)`.
4. **Level 3 (Modals & Sticky Navigation Bars):** Highest interactive tier. Top bar uses `#FFFFFF` with a 1px bottom border (`rgba(38, 39, 48, 0.12)`) and an ambient wash of `0 2px 8px rgba(0, 0, 0, 0.04)`.

## Shapes

The design system adopts a soft, disciplined geometry (Roundedness Level `1`):
- **Base Components:** Form controls, buttons, chips, alert banners, and input fields utilize a subtle `0.25rem` (4px) corner radius.
- **Card Containers (`rounded-lg`):** Data cards, metrics wrappers, and dataframe panels use `0.5rem` (8px) to soften analytical density while maintaining geometric structure.
- **Modal Containers (`rounded-xl`):** Flyouts and modals use `0.75rem` (12px).
- **Circular Elements:** Badges, avatar placeholders, and status indicators retain complete pill radius (`9999px`).

## Components

### Buttons
- **Primary:** Filled `#FF4B4B` with white bold text. Sharp 4px corner radius. On hover, darken to `#E03A3A`. On active/press, scale slightly to `0.98`. Focus ring is a 2px offset outline of `rgba(255, 75, 75, 0.4)`.
- **Secondary:** White background (`#FFFFFF`) with a 1px border of `rgba(38, 39, 48, 0.2)` and `#262730` text. On hover, background shifts to `#F0F2F6`.
- **Tertiary / Ghost:** No border or fill. `#262730` text that transitions to `#FF4B4B` text on hover.

### Metrics Cards (`st.metric`)
- **Structure:** White card (`#FFFFFF`), 1px outline of `rgba(38, 39, 48, 0.08)`, 4px corner radius, `1rem` internal padding.
- **Label:** `label-md` in `#808495`, tracking tight.
- **Value:** `headline-lg` in `#262730`, bold, tabular numbers.
- **Delta Indicator:** `label-sm` accompanied by a micro-arrow icon. Positive delta uses `#09AB3B` with a light tint background (`rgba(9, 171, 59, 0.1)`). Negative delta uses `#FF4B4B` with `rgba(255, 75, 75, 0.1)`.

### Callout Boxes (`st.info`, `st.warning`, `st.success`, `st.error`)
- Rectangular strip containers with 4px corner radius, 12px horizontal padding, and a prominent 4px solid left border.
- **Info:** Tinted blue background (`#EBF3FC`), left border `#0068C9`, icon in Tertiary blue.
- **Success:** Tinted green background (`#EDF7ED`), left border `#09AB3B`, icon in Success green.
- **Warning:** Tinted amber background (`#FFF8E6`), left border `#FFBD45`, icon in Amber.
- **Error:** Tinted red background (`#FFEFEF`), left border `#FF4B4B`, icon in Coral Red.

### Data Tables & Dataframes
- Container encased in `#FFFFFF` with a 1px border. Header row is styled in `#F9FAFC` with bold `label-sm` typography and a solid 1px bottom border (`rgba(38, 39, 48, 0.1)`).
- Alternate row striping is optional; standard is clean white rows with `0.5rem` vertical cell padding and `#262730` body-sm copy. Hovered row acquires an ultra-subtle highlight of `#F0F2F6`.

### Form Controls & Inputs
- **Text Inputs & Dropdowns:** Pure `#FFFFFF` background, 1px border in `rgba(38, 39, 48, 0.2)`, 4px radius, 36px height. Active focus shifts the border directly to `#FF4B4B` with zero ambient glow.
- **Checkboxes & Radios:** 16px square or circular bounds. Selected state fills `#FF4B4B` with a crisp white checkmark or center dot.
- **File Uploader Zone:** Dashed border (2px stroke, 4px dash gap) in `rgba(38, 39, 48, 0.2)` over `#F9FAFC` background. Dragging over shifts background to `rgba(255, 75, 75, 0.05)` and border to `#FF4B4B`.
- **Progress Bars:** 6px track height, rounded to 4px. Track background `#E6E8ED`, progress fill animated in solid `#FF4B4B`.

### Navigation Tabs
- Horizontal strip resting flush against the main page header. Active tab features a 2px bottom underline in `#FF4B4B` with primary text weight. Inactive tabs sit in `#808495` and brighten to `#262730` on hover without shifting vertical layout height.