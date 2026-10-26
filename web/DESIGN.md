---
name: Analyst Buddy
description: An AI data analyst for business owners, staged as the Monday whiteboard where the week's numbers get written up.
colors:
  enamel: "#fcfdfd"
  enamel-shade: "#e4e8eb"
  paper: "#fdfdfc"
  ink: "#1b1e23"
  ink-2: "#474d57"
  ink-3: "#646a74"
  blue: "#1f4fd8"
  action: "#1f4fd8"
  action-hover: "#173da9"
  on-action: "#ffffff"
  action-shadow: "rgba(23, 61, 169, 0.65)"
  red: "#d7262e"
  green: "#128a4b"
  green-text: "#0c6e3b"
  magnet: "#ffc93c"
  magnet-hover: "#fff4d1"
  on-magnet: "#1b1e23"
  alu-hi: "#eef0f2"
  alu: "#c9ced3"
  alu-lo: "#9aa1a8"
  rule: "rgba(31, 79, 216, 0.07)"
  line: "#cfd3d8"
  line-soft: "#dde0e4"
  wash: "rgba(27, 30, 35, 0.06)"
  q-bg: "#e9eefc"
  q-ink: "#173da9"
  chart-mat: "#ffffff"
typography:
  display:
    fontFamily: "'Permanent Marker', 'Archivo Variable', sans-serif"
    fontSize: "clamp(4rem, 8vw, 6rem)"
    fontWeight: 400
    lineHeight: 1
  headline:
    fontFamily: "'Archivo Variable', 'Archivo', system-ui, sans-serif"
    fontSize: "clamp(2.3rem, 4.4vw, 4.1rem)"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.025em"
    fontVariation: "'wdth' 108"
  headline-signin:
    fontFamily: "'Archivo Variable', 'Archivo', system-ui, sans-serif"
    fontSize: "clamp(2.2rem, 4vw, 3.4rem)"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.025em"
    fontVariation: "'wdth' 108"
  title:
    fontFamily: "'Archivo Variable', 'Archivo', system-ui, sans-serif"
    fontSize: "clamp(2rem, 3.6vw, 3rem)"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.025em"
    fontVariation: "'wdth' 108"
  title-closing:
    fontFamily: "'Archivo Variable', 'Archivo', system-ui, sans-serif"
    fontSize: "clamp(2rem, 4vw, 3.3rem)"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.025em"
    fontVariation: "'wdth' 108"
  card-title:
    fontFamily: "'Archivo Variable', 'Archivo', system-ui, sans-serif"
    fontSize: "1.6rem"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.025em"
    fontVariation: "'wdth' 108"
  step-title:
    fontFamily: "'Archivo Variable', 'Archivo', system-ui, sans-serif"
    fontSize: "1.35rem"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.025em"
  small-title:
    fontFamily: "'Archivo Variable', 'Archivo', system-ui, sans-serif"
    fontSize: "1.1rem"
    fontWeight: 800
    lineHeight: 1.05
  starter-title:
    fontFamily: "'Archivo Variable', 'Archivo', system-ui, sans-serif"
    fontSize: "1.05rem"
    fontWeight: 800
  rail-heading:
    fontFamily: "'Archivo Variable', 'Archivo', system-ui, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 800
    letterSpacing: "-0.01em"
  lead:
    fontFamily: "'Archivo Variable', 'Archivo', system-ui, sans-serif"
    fontSize: "1.15rem"
    fontWeight: 400
    lineHeight: 1.55
  body:
    fontFamily: "'Archivo Variable', 'Archivo', system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.6
    fontFeature: "'tnum' 1"
  label:
    fontFamily: "'Archivo Variable', 'Archivo', system-ui, sans-serif"
    fontSize: "0.9rem"
    fontWeight: 700
    lineHeight: 1.3
  chip:
    fontFamily: "'Archivo Variable', 'Archivo', system-ui, sans-serif"
    fontSize: "0.85rem"
    fontWeight: 700
  source:
    fontFamily: "'Archivo Variable', 'Archivo', system-ui, sans-serif"
    fontSize: "0.78rem"
    fontWeight: 600
    fontVariation: "'wdth' 90"
  annotation:
    fontFamily: "'Permanent Marker', 'Archivo Variable', sans-serif"
    fontSize: "1.25rem"
    fontWeight: 400
    lineHeight: 1.2
rounded:
  print: "2px"
  bar: "3px"
  tail: "4px"
  tag: "6px"
  board: "8px"
  control: "10px"
  tile: "12px"
  card: "14px"
  frame: "18px"
  pill: "999px"
spacing:
  xs: "6px"
  sm: "8px"
  md: "14px"
  lg: "22px"
  xl: "28px"
  ruled-line: "40px"
  section: "clamp(80px, 10vw, 128px)"
components:
  button-blue:
    backgroundColor: "{colors.action}"
    textColor: "{colors.on-action}"
    rounded: "{rounded.control}"
    padding: "11px 18px"
    typography: "{typography.label}"
  button-blue-hover:
    backgroundColor: "{colors.action-hover}"
    textColor: "{colors.on-action}"
  button-outline:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "11px 18px"
  button-outline-hover:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.control}"
    padding: "11px 18px"
  button-ghost-hover:
    backgroundColor: "{colors.wash}"
    textColor: "{colors.ink}"
  icon-button:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.board}"
    padding: "0 10px"
    height: "38px"
  icon-button-hover:
    backgroundColor: "{colors.wash}"
    textColor: "{colors.ink}"
  icon-button-up:
    textColor: "{colors.green}"
  icon-button-down:
    textColor: "{colors.red}"
  theme-toggle:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    size: "40px"
  magnet-toggle:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "5px 12px"
    typography: "{typography.chip}"
  magnet-toggle-hover:
    backgroundColor: "{colors.magnet-hover}"
  magnet-toggle-on:
    backgroundColor: "{colors.magnet}"
    textColor: "{colors.on-magnet}"
  field-input:
    backgroundColor: "{colors.enamel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "12px 14px"
  field-input-focus:
    backgroundColor: "{colors.paper}"
  composer-input:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "12px 14px"
  magnet-card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "30px 26px 26px"
  answer-card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.board}"
    padding: "24px 28px 14px"
  question-bubble:
    backgroundColor: "{colors.q-bg}"
    textColor: "{colors.q-ink}"
    rounded: "{rounded.card}"
    padding: "12px 16px"
  chart-mat:
    backgroundColor: "{colors.chart-mat}"
    rounded: "{rounded.tag}"
    padding: "8px"
  source-tag:
    backgroundColor: "{colors.wash}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.tag}"
    padding: "2px 8px"
    typography: "{typography.source}"
  rail-company:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.tile}"
    padding: "12px 14px"
  board-frame:
    backgroundColor: "{colors.alu}"
    rounded: "{rounded.frame}"
    padding: "12px"
---

# Design System: Analyst Buddy

## Overview

**Creative North Star: "The Monday Board"**

Every week starts at the board: what the numbers did, why, and who acts. The whole product is staged as a white dry-erase board in an aluminium frame, hung in a pale grey room. Findings are written on it in marker, printouts and cards are pinned to it with yellow magnets, and a marker tray runs along the bottom edge. The landing page (Persuade) shows one real weekly review on that board; the workspace (Operate) is the same board turned into a desk, with a frame-colored rail and composer around a ruled enamel feed.

Density is moderate and editorial on the landing page, practical in the workspace. The ruled lines on the enamel (one every 40px) are the board's own grid. Color is ink by default: four marker colors, each with one job, and nothing decorative. The one number that matters is written five times larger than everything else, in a marker hand, circled. Every figure carries a small source tag that says what was read and run, because the product's promise is that every number is computed.

The world has two lights. By day it is the white board in a pale grey room. After hours (dark theme) it is the same board with the lights down: graphite enamel, dark paper cards that sit slightly lighter than the board, brightened marker inks, the same yellow magnets, and no neon glow anywhere. The world refuses the category default: no dark gradient hero, no dashboard screenshot, no row of icon cards. Depth is physical and soft (paper lifted off enamel, a frame lifted off the wall), never glossy and never a hard offset block.

**Key Characteristics:**
- White enamel board with faint blue ruled lines, inside a neutral aluminium-colored frame with a marker tray.
- Four marker inks with strict jobs: ink for text, blue for actions, red for misses, green for hits.
- Yellow magnet discs pin white paper cards and printouts to the board, often at a slight tilt.
- Archivo variable grotesk for all copy, widened on headings; Permanent Marker only for the hero figure and handwritten annotations.
- Soft, layered, offset-free shadows; no gradients except the ruled lines.
- Signature motion: figures and notes write on in marker strokes; switching the example dataset erases and rewrites the board.
- Light and dark themes from one token set: the board in daylight and the same board after hours.

## Colors

A near-white board and paper world written on in four marker inks, held in a cool grey frame; after hours the same roles on graphite.

Every color is a custom property on `:root` in `src/index.css`. The frontmatter holds the light values. Dark values are redefined under `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) }` and again under `:root[data-theme="dark"]`, and are listed in the table below and in the sidecar (`colorMeta.<token>.dark`). Components use the tokens, never literal hex, so both themes come from the same rules.

### Primary
- **Action Marker Blue** (action): the only action fill. Primary buttons and the send button. Text and icons on it use **On Action** (on-action). Hover deepens to **Action Hover** (action-hover). Its lift shadow is tinted by **Action Shadow** (action-shadow). In dark, the action is a light blue fill with dark text.
- **Marker Blue** (blue): action color as ink: links, focus rings, the text caret, focused field borders, icons on actionable starters, the working squiggle, and the blue marker cap in the tray. Same value as action in light; brightened in dark.

### Secondary
- **Miss Marker Red** (red): misses only. A falling headline figure, a ranked note about something that went wrong, the dipping bar in a chart, error text, and a thumbs-down that has been pressed.
- **Hit Marker Green** (green): hits only. A rising figure, a goal on pace, the "Got it" confirmation, the live status dot, and a thumbs-up that has been pressed. Small green text uses **Hit Green Text** (green-text) for contrast.

### Tertiary
- **Magnet Yellow** (magnet): the physical magnets that pin cards, the active state of the example toggle (Sales, Support tickets, Website), and text selection. Identical in both themes. Text on it is always **On Magnet** (on-magnet, the light ink, in both themes). Inactive toggle hover takes **Magnet Hover** (magnet-hover), a pale yellow by day and a dim olive after hours. Never text, never an action color.

### Neutral
- **Board Enamel** (enamel): the writing surface of every board and the workspace feed; also input wells, the desk header and rail icon tiles.
- **Wall Grey** (enamel-shade): the page behind the boards, the sticky top bar, and the browser theme-color for each scheme.
- **Paper White** (paper): cards, printouts, answers, outline buttons, the theme toggle and the composer field pinned on the enamel.
- **Marker Black** (ink): all text and headings by default; neutral ranked notes, trust icons, rail goal icons, landing mini-chart axis.
- **Faded Ink** (ink-2): body copy under headings, lead paragraphs, secondary links, source tags, icon buttons at rest, rail file icons, and the neutral bars of the landing mini-chart.
- **Ghost Ink** (ink-3): placeholders, example labels, printout footers, the composer hint, the hand-drawn flow arrows.
- **Frame Light / Frame / Frame Shadow** (alu-hi, alu, alu-lo): the frame, the workspace rail and composer (alu-hi with an alu border), the marker tray (alu-lo), and scrollbar thumbs.
- **Ruled Line** (rule): the faint blue line every 40px on the enamel.
- **Field Line** (line): 2px borders on fields, the composer and the theme toggle; dashed dividers in printout and answer footers.
- **Hairline** (line-soft): the top bar and desk header bottom borders, and table cell borders in answers.
- **Ink Wash** (wash): a translucent ink tint for source tags, table header cells, inline code and code blocks, and ghost and icon button hover.
- **Question Tint / Question Ink** (q-bg, q-ink): the user's own question bubbles, on the landing printout and in the workspace feed.
- **Chart Mat** (chart-mat): the white mat behind agent chart images. White in both themes because the agent's matplotlib PNGs are drawn on white.

### Light and Dark Values

| Token | Light | Dark |
|---|---|---|
| enamel | #fcfdfd | #1a1e22 |
| enamel-shade | #e4e8eb | #121518 |
| paper | #fdfdfc | #232830 |
| ink | #1b1e23 | #e9ecef |
| ink-2 | #474d57 | #b7bdc5 |
| ink-3 | #646a74 | #959ca6 |
| blue | #1f4fd8 | #8aa8ff |
| action | #1f4fd8 | #8aa8ff |
| action-hover | #173da9 | #a9c0ff |
| on-action | #ffffff | #0d1530 |
| action-shadow | rgba(23, 61, 169, 0.65) | rgba(0, 0, 0, 0.6) |
| red | #d7262e | #ff6b6f |
| green | #128a4b | #3ecf85 |
| green-text | #0c6e3b | #5fd99a |
| magnet | #ffc93c | #ffc93c (unchanged) |
| magnet-hover | #fff4d1 | #3a3320 |
| on-magnet | #1b1e23 | #1b1e23 (unchanged) |
| alu-hi | #eef0f2 | #1f2429 |
| alu | #c9ced3 | #2c3238 |
| alu-lo | #9aa1a8 | #3d444c |
| rule | rgba(31, 79, 216, 0.07) | rgba(138, 168, 255, 0.06) |
| line | #cfd3d8 | #3d444c |
| line-soft | #dde0e4 | #333a41 |
| wash | rgba(27, 30, 35, 0.06) | rgba(255, 255, 255, 0.07) |
| q-bg | #e9eefc | #1f2a4a |
| q-ink | #173da9 | #cdd9ff |
| chart-mat | #ffffff | #ffffff (unchanged) |

### Theme Choice
The theme follows the system (`prefers-color-scheme`) unless the user picks one with the theme toggle. The choice is stored in localStorage under `analyst-theme` and applied as `data-theme` on the root by an inline script in `index.html` before first paint, so there is no flash. `color-scheme` is set per theme so native controls and scrollbars follow. Two `theme-color` metas match Wall Grey for each scheme.

### Named Rules
**The Four Inks Rule.** Red marks misses only, green marks hits only, blue marks actions only; everything else is written in ink. If a color would only decorate, it is ink.

**The Brightest Board Rule.** The board enamel is the brightest surface in the room. Cards are neutral white paper sitting on it and separate from it by shadow, not by tint. The wall around the board is darker (enamel-shade).

**The After Hours Rule.** The dark-mode form of the Brightest Board Rule. In the dark, elevation reads as lighter: the wall is darkest (enamel-shade), the board is graphite (enamel), and paper sits slightly lighter than the board (paper), still separated by a deeper shadow. Marker inks brighten to stay legible; the magnet stays the same yellow, and sticky notes (questions, goals) stay bright marker-yellow paper (--note #ffd84a with dark --note-ink), the one surface that does not dim; nothing glows.

**The Magnet Is Not A Color Rule.** Yellow belongs to magnets: pins, the active toggle, selection. It never carries text meaning.

**The Token Only Rule.** Components read color from the tokens above, never from literal hex, so every surface exists in both themes. A new color is a new token with a light and a dark value.

## Typography

**Display Font:** Permanent Marker (self-hosted via @fontsource/permanent-marker, falls back to Archivo Variable)
**Body Font:** Archivo Variable with the wdth axis (self-hosted via @fontsource-variable/archivo/wdth.css, falls back to Archivo, system-ui)

**Character:** A sturdy, slightly widened grotesk does all the talking, like a senior analyst's clear print; the marker hand appears only where someone would actually write on a whiteboard. Numerals are tabular everywhere.

### Hierarchy
- **Display** (Permanent Marker 400, clamp(4rem, 8vw, 6rem), line-height 1): the single hero figure, colored by its meaning and circled by a hand-drawn stroke.
- **Headline** (Archivo 800, width 108%, clamp(2.3rem, 4.4vw, 4.1rem), line-height 1.05, -0.025em): page h1, max about 15ch, balanced wrap. The sign-in board uses a slightly smaller step (headline-signin, clamp(2.2rem, 4vw, 3.4rem), max 14ch).
- **Title** (Archivo 800, width 108%, clamp(2rem, 3.6vw, 3rem)): section h2 on the landing page; the closing board runs slightly larger (title-closing, clamp(2rem, 4vw, 3.3rem)).
- **Card Title** (Archivo 800, width 108%, 1.6rem): titles on magnet cards; workspace desk title uses 1.25rem.
- **Step Title** (Archivo 800, 1.35rem): the three flow step headings.
- **Small Title** (Archivo 800, 1.1rem): the company name on the rail card (width 108%) and headings inside answers.
- **Starter Title** (Archivo 800, 1.05rem): the title line on a starter card, beside its icon.
- **Rail Heading** (Archivo 800, 0.95rem, -0.01em): Goals and Data section headings in the rail.
- **Lead** (Archivo 400, 1.15rem, line-height 1.55, faded ink, max 46ch): the paragraph under a headline.
- **Body** (Archivo 400, 1rem, line-height 1.5 to 1.6): answers (max 72ch), steps, trust copy, max 30 to 34ch in short notes. Answer tables run at 0.92rem.
- **Label** (Archivo 700, 0.9rem): form labels and buttons (buttons widen to 105%); the feedback question label runs at 0.92rem.
- **Chip** (Archivo 700, 0.85rem): the example toggle (Sales, Support tickets, Website) and the workspace status line.
- **Source** (Archivo 600, width 90%, 0.78rem): provenance tags under figures and answers; the composer hint uses the same size in ghost ink.
- **Annotation** (Permanent Marker, 1.25rem; 2rem to 3rem when big): handwritten notes such as the empty-workspace prompt and the "Got it" check.

### Named Rules
**The Marker Is For Writing Rule.** The marker face is used only for the big hero figure and handwritten annotations. Never set numerals in lists, ranks or steps in the marker face: its "1" reads as ")". Ranked notes and flow numbers are Archivo 800.

**The Wide Heading Rule.** Headings and the wordmark use the wdth axis at 108 to 112%; source tags narrow to 90%. Width is the type's emphasis tool, not color.

## Layout

The board is the layout. On the landing page the hero board sits in its frame with a 12 to 32px wall margin and fills the viewport under a slim sticky top bar (min-height calc(100vh - 110px)). Inside, a two-column grid puts the headline, figure and three ranked notes on the left (flexible) and a 300 to 380px magnet card on the right. The ruled lines every 40px set the board's vertical texture.

Below the hero, sections sit on the wall in a 1180px column with generous vertical rhythm (clamp(80px, 10vw, 128px) between sections): a three-step flow joined by hand-drawn arrows, then a proof row pairing trust points with a tilted printout. The page closes on a second framed board with a centered compact access card.

The workspace is a full-height two-column grid: a 290px frame-colored rail (wordmark and theme toggle, the collapsible company panel with goals and data files, sign out) beside the desk (header with status, ruled enamel feed, frame-colored composer). The feed is a column of turns, 30px apart; each turn groups the user's question (right-aligned, up to min(640px, 85%)) with its answer card (left-aligned, up to 820px) 14px below it.

Responsive: at 980px and below every two-column board collapses to one column, cards lose their tilt, the flow stacks and its arrows hide, starters stack. At 640px and below the frame thins to 8px, the tray hides, top bar links hide except Sign in and the theme toggle, the workspace rail stacks above the desk with the company panel folded by default, the composer becomes sticky at the bottom and its keyboard hint hides.

## Elevation & Depth

In the workspace the chat sits on a framed board (10px aluminium border, recessed enamel via --board-inset). Notes, the answer and the chart folder carry a faint paper grain (--grain, an SVG noise texture, not a gradient) and --shadow-note, which pulls the shadow toward the bottom-right corner so the paper reads as lifting there. Magnets are domed with inset highlight and shade (--magnet-dome). The monitor has a webcam dot, a lit rim (--mon-rim) and a dark glass edge over the screen (--mon-glass). Depth is physical and soft: things pinned on the board lift off the enamel, the framed board lifts off the wall. Shadows are always blurred and layered (a tight contact shadow plus a long, negatively spread drop), never a zero-blur offset block. There are no gradients anywhere except the ruled lines on the enamel. After hours the same shadows turn to pure black at higher opacity, and paper also reads lighter than the board (see The After Hours Rule); there are no glows.

### Shadow Vocabulary
- **Pinned Paper** (`--shadow-card`; light `0 2px 3px rgba(27, 30, 35, 0.08), 0 14px 28px -12px rgba(27, 30, 35, 0.28)`, dark `0 2px 3px rgba(0, 0, 0, 0.35), 0 14px 28px -12px rgba(0, 0, 0, 0.75)`): magnet cards, printouts, answers, starters, the rail company panel, trust icon tiles.
- **Hung Frame** (`--shadow-frame`; light `0 3px 6px rgba(27, 30, 35, 0.12), 0 30px 60px -28px rgba(27, 30, 35, 0.45)`, dark `0 3px 6px rgba(0, 0, 0, 0.4), 0 30px 60px -28px rgba(0, 0, 0, 0.8)`): the aluminium frame around every board.
- **Magnet** (`--shadow-magnet`; light `0 3px 5px -1px rgba(27, 30, 35, 0.4)`, dark `0 3px 5px -1px rgba(0, 0, 0, 0.7)`): the yellow magnet discs.
- **Action Lift** (`0 6px 14px -6px var(--action-shadow)`, hover `0 10px 20px -8px var(--action-shadow)`, active `0 2px 6px -2px var(--action-shadow)`): the primary action button only.
- **Tray Drop** (`--shadow-tray`: light `0 6px 10px -6px rgba(27, 30, 35, 0.5)`, dark `0 6px 10px -6px rgba(0, 0, 0, 0.8)`): the marker tray hanging under the board.

### Named Rules
**The Soft Offset Rule.** Every shadow has blur. Zero-blur hard offset shadows do not exist in this world.

**The Tilt Rule.** Pinned paper may tilt slightly (between -0.8deg and 1.2deg) to read as hand-placed; it straightens on hover and on narrow screens.

## Shapes

Gently rounded and physical. The frame is the softest corner (18px), cards and question bubbles 14px, small tiles (trust icons, the rail company panel, the printout question) 12px, controls, starters and the theme toggle 10px, the board surface, answers and icon buttons 8px, tags and the chart mat 6px, and printouts are nearly square (2px) like real paper. Question bubbles have one tight 4px corner at bottom right, a speech tail pointing at the asker. Marker caps and chart bars use a 3px corner. The example toggle (Sales, Support tickets, Website) is a full pill. Magnets are perfect circles (26px, or 16px small) placed overlapping a card's top edge. Hand-drawn SVG strokes (the circle around the hero figure, flow arrows, the working squiggle) use 3 to 3.5px round-capped lines. Inputs, the composer, outline buttons and the theme toggle use a 2px stroke.

## Components

### Buttons
Tactile and plain, like a marker cap pressed down.
- **Shape:** gently rounded (10px), 2px border slot, 11px 18px padding, Archivo 700 at width 105%.
- **Primary (action):** action fill with on-action text and the Action Lift shadow. Used for the one action on a card (request access, sign in, ask, save feedback). Blue with white text by day; light blue with dark text after hours.
- **Hover / Focus:** hover moves to action-hover and lifts 1px; active presses down 1px with a shorter shadow; disabled drops to 55% opacity. Focus everywhere is a 3px blue outline at 3px offset. Transitions 0.18s on cubic-bezier(0.2, 0.8, 0.2, 1).
- **Outline:** paper fill, ink border and text; inverts to ink fill with paper text on hover. Used for Sign in, Upload data and Try again.
- **Ghost:** transparent, faded ink text, the ink wash on hover. Used for Sign out and Cancel.
- **Text link:** blue, 700, underlined with a 3px offset.
- **Icon button:** 38px tall, at least 38px wide, 8px radius, transparent with faded ink icon (17px); hover takes the ink wash and full ink. Can carry a short 0.8rem 700 label beside the icon (the "Copied" confirmation). Pressed feedback states color the icon by meaning: thumbs up in green, thumbs down in red. Once rated, the pair locks; the unpressed one fades to 35%.
- **Theme toggle:** 40px square, 10px radius, 2px field-line border on paper, ink icon (18px): a moon in light, a sun in dark. Border darkens to ink on hover. Sits at the right of the top bar and at the top of the workspace rail.

### Chips
- **Magnet toggle:** pill with a 2px ink border on paper, chip type. The active option fills with magnet yellow (border too) and on-magnet text; inactive hover takes magnet-hover. Used for the example dataset switch.
- **Source tag:** 6px-rounded tag with the ink wash, faded ink text in source type. Sits under every figure, note and answer to state rows read and code run.

### Cards / Containers
- **Corner Style:** 14px for magnet cards, 12px rail company panel, 10px starters, 8px answers, 2px printouts.
- **Background:** paper on enamel.
- **Shadow Strategy:** Pinned Paper (see Elevation & Depth).
- **Border:** none; separation is by shadow (and, after hours, by paper being lighter than the board).
- **Internal Padding:** 30px 26px 26px on magnet cards; 22px 18px 18px on starters; 24px up to 28px on answers.
- Every pinned card carries a yellow magnet straddling its top edge.

### Inputs / Fields
- **Style:** enamel well, 2px field-line border, 10px radius, 12px 14px padding, label above in Archivo 700 0.9rem with optional hints in ghost ink.
- **Focus:** border turns blue and the well brightens to paper; no glow.
- **Error:** red 600 text below the field group.
- **Composer:** a paper-filled textarea with the same border and radius that grows with its content from 50px up to 180px, then scrolls. Enter sends, Shift and Enter adds a line; a keyboard hint in ghost ink at source size sits under it and hides on phones. The Ask button beside it matches its 50px resting height and stays bottom-aligned as the field grows.

### Navigation
- **Top bar:** sticky, wall-grey background with a hairline bottom border. Wordmark at left (logo icon and text both in ink, Archivo 800 at width 110%), text links in faded ink that darken and underline on hover, theme toggle and outline Sign in button at right. Below 640px the text links hide.
- **Workspace rail:** frame-light background with an aluminium border. Wordmark and theme toggle at top, then the company panel, then a ghost Sign out pinned at the bottom.
- **Company panel:** a disclosure whose summary is a paper tile (12px radius, Pinned Paper) with an enamel icon square, the company name in small-title type, and a chevron drawn from two 2px faded-ink borders that turns on open (0.2s). Inside: company description, Goals (ink goal icons) and Data (paper file rows with faded-ink file icons, outline Upload data button). Open by default on wider screens, folded on phones so the chat is first.

### Conversation Turn (signature)
One question and its answer read as one turn.
- **Question bubble:** right-aligned, q-bg fill with q-ink text at 600, 12px 16px padding, rounded 14px with a 4px tail corner at bottom right.
- **Question note:** right-aligned yellow sticky note (note / note-ink), small centred magnet, tilted 1.2deg; Archivo, not marker, because questions carry numerals.
- **Sandbox monitor:** a dark screen (no stand) (mon-* tokens, the same in both themes) between question and answer: title bar, `In [n]:` prompts, typed code, output wells, a chin with a status LED and "Skip to answer".
- **Answer card:** left-aligned sticky note (note-ai, folded 18px bottom-left corner, small magnet at the top left, -0.3deg tilt). Markdown body using the note's full width, GitHub tables (remark-gfm) with hairline cell borders and wash header cells; cells never wrap and the table scrolls sideways. Inline code and code blocks sit on the ink wash.
- **Markers:** the chat board has its own tray under its frame: blue, red and green plain markers and the AI marker (pale violet barrel lettered "AI", violet cap; --magic / --magic-body), which breathes a soft violet glow (--magic-glow, a pulsing drop-shadow; steady under reduced motion) so it reads as the one pen that talks to the AI. Clicking one picks it up: it uncaps (the cap stays in the tray) and flies onto the board, then its nib follows the pointer (the system cursor hides over the board). Letting go of the button ends the stroke and sends the marker back into its cap, so each pick-up is one stroke; plain markers just draw. Before drawing, it can also be put back by clicking its place in the tray (the empty slot stays clickable; only its cap shows there), Esc, or a click off the board. The AI marker is circle to search: one circle, drawn as a dotted violet trail, and the lines, table rows (with their header), monitor code/output and charts inside it go to the analyst as text with the next question, together with a picture of exactly the circled area (src/capture.js, html-to-image, drawn without the ink); up to 5 circles can be collected before asking (the pen dims and refuses a sixth), each shown as a thumbnail with its own remove button above the composer and on the question note, the circle fades off the board once it is captured, and the pen goes back into its cap by itself. Every stroke from the plain markers stays on the board and scrolls with it, even after the question is sent. The tray's eraser (navy plastic handle over grey felt; --eraser / --felt) is lent out the same way: it flies onto the board and follows the pointer, and rubbing takes off exactly the ink under its 20px radius, clipping strokes at its edge and splitting what is left (rub in src/marker.js, tested). Letting go after a rub lays it back in the tray; while it is in hand the status line also offers Erase everything. A status line above the composer says what is happening or what was circled (Clear drops the context, the circle stays drawn); the question note keeps an "About the circled area" disclosure. Phone trays shrink the markers to fit, and shrunken markers or reduced motion skip the flight and just draw. The trip is built from lendMarker (takeOut, hold, putBack) in src/markers.js. Drawing has undo, redo and clear (each stroke, rub or clear is one step; history helpers in src/marker.js, tested): a small toolbar pinned to the board's top right corner while there is a drawing or something to undo, plus Ctrl+Z, Ctrl+Shift+Z and Ctrl+Y outside text fields. The conversation and its drawings are saved in the tab's sessionStorage for the length of the sign-in (src/saved.js; charts are dropped first if storage is full) and come back after a reload without replaying; signing out forgets them. While the analyst works, Ask becomes an outline Stop button with a square; the analyst stops after the step it is on, nothing from the stopped question is kept, and the turn shows a neutral "Stopped" note with Ask again. The ink lives in its own InkLayer component: the stroke in progress is written straight to its SVG path on every coalesced pointer sample (no re-render of the answers), strokes are drawn as smoothed curves through the samples (pathOf), and the finished strokes are kept by the workspace so they survive switching to the reports tab.
- **Chart folder:** an answer's charts are filed in a manila folder (folder / folder-tab / folder-ink) as a vertical "Charts · n" tab sticking out of the answer note's right edge. Clicking it lays the open folder over the answer (charts on their mats, "Close folder" button, Escape closes, focus returns to the folder).
- **Chart:** agent charts sit on the chart mat (white in both themes, 8px padding, 6px radius) so their white PNGs never glare as a bare rectangle on dark paper.
- **Answer footer:** a dashed field-line rule, then the source tag at left and the action group at right: copy, thumbs up, thumbs down as icon buttons.
- **Feedback form:** after thumbs down, an inline form under the footer asks "What was wrong?" with a field-style textarea (min 64px, vertical resize) and a row of Save feedback (primary) and Cancel (ghost).
- **Feedback message:** a quiet 0.88rem 600 faded-ink line confirming the feedback was saved.
- **Error answer:** the answer card in red 600 text with an outline Try again when the failure is retryable.
- **Working:** an answer-shaped row with the blue squiggle and "Writing and running code on your data" in faded ink.

### The Board (signature)
A framed enamel surface: 12px aluminium-colored frame (8px on mobile) at 18px radius with the Hung Frame shadow, an 8px-radius enamel board with ruled lines every 40px, and a marker tray (alu-lo, Tray Drop shadow) hanging centered off the bottom edge holding blue, red and green marker caps. Used for the landing hero, the closing call, and sign in. The workspace feed reuses the ruled enamel without the frame.

### Ranked Notes and the Hero Figure (signature)
The hero figure is the one number that matters, in the marker face at five times body size, colored red or green by meaning and circled with a hand-drawn stroke that draws itself in. Beside it, three notes ranked most urgent first: each has a 32px circled rank number in Archivo 800 (circle and number in the note's meaning color), a 1.12rem 600 two-line note, and a source tag. The printout's mini-chart draws neutral bars in faded ink with the dipping bar in red, over an ink baseline.

### Motion
On load, figures and notes write on left to right with a clip-path wipe (0.6s, cubic-bezier(0.25, 0.8, 0.25, 1), staggered 140ms); the circle is drawn by hand: the marker matching the figure's color slides 30px out of its cap (0.26s; the nib is at the cap end and the cap stays lying in the tray, layered above the barrel), lifts and turns into a pen grip with its shadow growing (0.76s), traces the circle with its tip on the stroke (0.9s, same easing as the stroke, the nib is placed each frame from the stroke animation's own progress in useMarkerDraw, so it never drifts ahead of the ink), flies back the same way in reverse (0.7s) and pushes into its cap (0.24s), landing on the exact pixels of the tray marker it replaced. It replays on every example switch. The access card's Request access button starts as an empty dashed outline (disabled) and is coloured in by the blue marker once the email is valid: the same uncap-fly-trace-recap trip (markerTrip) scribbles a 20px zigzag across it left to right while a white copy of the label wipes in on the same timing, then the solid blue button takes over. Editing the email back to invalid empties it again; without the tray or under reduced motion it fills instantly. The sign-in board uses all three markers: green underlines "company's board." in the headline on load, blue colours in Sign in once both fields have text (MarkerButton), and red circles each new sign-in error. The shared pieces live in src/markers.js (useMarkerStroke, useMarkerFill) and src/MarkerButton.jsx. Hand-drawn SVGs that use pathLength dashing keep a viewBox close to their box's real shape instead of non-scaling-stroke, which breaks the dash length. Without the tray (phones) or under reduced motion, the circle just draws itself after 0.55s. Changing the example dataset erases the board (0.42s fade, blur and slide) and rewrites it. While the analyst works, the sandbox monitor streams live: each code cell types out as soon as the agent writes it, "running in the sandbox" blinks until its real output arrives, and a thinking line blinks between steps. Typing speeds up when it falls behind and can be skipped; the answer note pins on once the screen has caught up. Small controls (icon buttons, theme toggle, fields) transition color and border in 0.15s. All animation and transitions are removed under prefers-reduced-motion.

### Icons
Icons8 fluent-systems-regular PNGs, locked in icons8.json (19 icons, including thumb-up, thumb-down, copy, sun and moon), rendered as CSS masks so they take the current text color, at 16 to 28px. Icons are ink or faded ink by default; only actionable starter icons are blue. The "Icons by Icons8" credit stays visible in the footer.

## Do's and Don'ts

### Do:
- **Do** write everything in ink unless it is an action (blue), a miss (red) or a hit (green).
- **Do** put a source tag under every figure and every answer, stating rows read and code run.
- **Do** keep one oversized marker figure per board and rank the notes beside it most urgent first.
- **Do** pin paper cards to the enamel with a yellow magnet and the Pinned Paper shadow.
- **Do** keep the enamel the brightest surface by day, with cards as neutral white paper on it; after hours, keep paper slightly lighter than the board and the wall darkest.
- **Do** read every color from a token and give every new token a light and a dark value.
- **Do** put agent chart images on the white chart mat in both themes.
- **Do** use Icons8 fluent-systems-regular PNGs as CSS masks and keep the "Icons by Icons8" credit visible.
- **Do** honor prefers-reduced-motion by removing the write-on, erase and scribble animations.

### Don't:
- **Don't** use red, green or blue for decoration, emphasis or branding.
- **Don't** set numerals in lists, ranks or steps in Permanent Marker; its "1" reads as ")".
- **Don't** put kickers or eyebrow labels above headings.
- **Don't** use zero-blur hard offset shadows.
- **Don't** use gradients anywhere except the board's ruled lines.
- **Don't** imitate brushed metal in CSS with multi-stop gradients or radial highlights.
- **Don't** add neon glows or colored shadows to the dark theme. The one exception is the AI marker's violet glow, which marks the only tool that sends something to the AI.
- **Don't** use emoji or em dashes in UI copy.
- **Don't** use a dark gradient hero, a dashboard screenshot, or a row of icon cards.

## Open Items

**The Aluminium Promise (open by decision).** The direction promises a brushed aluminium frame and tray and real magnets. The build currently ships a flat solid neutral frame and tray (alu, alu-lo) and flat yellow magnet discs, because no image generation was available. The user chose to keep the aluminium promise: photo-quality raster assets for the frame, the tray and the magnets will be added in a later session, each with its provenance recorded. Until then the flat fills are placeholders, not the target. Imitating metal in CSS (multi-stop gradients, radial highlights, faux sheen) is explicitly rejected; the replacement is real raster material or nothing. This was the one item left open of eight in the finish review (7 of 8 resolved). The raster assets will need an after-hours variant (or a dimming treatment) for the dark theme.
