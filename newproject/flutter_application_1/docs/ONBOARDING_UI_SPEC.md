# Fansivibe Onboarding — UI Design Specification

## Digital Atelier Design Language

The onboarding is a private fitting session in a luxury atelier. Every visual decision communicates: *this is a premium studio, not a utility app.*

| Principle | Application |
|---|---|
| Warm minimalism | Generous whitespace, no clutter, every element earns its place |
| Editorial hierarchy | Serif for statements, sans-serif for information |
| Tonal layering | Depth through surface colours, not shadows |
| Gold as accent | Only for CTAs, scores, and active states — never decorative |
| Glassmorphism | Subtle backdrop blur for overlays, never full-screen |
| No borders | Containers differentiate by colour, not strokes |

---

## 1. Splash (ONB-001)

### Layout

Full-screen near-black (`#131313`). Centered wordmark. Nothing else.

| Element | Spec |
|---|---|
| Background | `FansivibeColors.surface` |
| Wordmark | "FANSIVIBE" — `labelMediumWithFamily`, 14px, letter-spacing 4, gold |
| Animation | Wordmark fades in over 800ms, letter-spacing loosens 8→4 over 1.2s |
| Duration | 1.8s auto-transition |

### Component Breakdown

- `_SplashLogo` — centered `Text` widget
- `_SplashGlow` — radial gradient behind the logo (gold at 8% opacity, 120×120)

### Animation

1. Screen starts black (200ms)
2. Gold glow pulses in behind logo (400ms ease-out)
3. Logo fades in while letter-spacing animates (800ms ease-out)
4. Hold (400ms)
5. Cross-fade out to Entry (600ms overlap)

### Interaction

- No user interaction required
- If user taps during splash, transition accelerates to Entry immediately

### Error State

- Not applicable (no data loading)

---

## 2. Entry (ONB-002)

### Layout

Scrollable vertical layout with generous spacing. Editorial hero treatment.

| Section | Element | Spec |
|---|---|---|
| Top | Logo | "FANSIVIBE" — `labelMediumWithFamily`, 14px, ls 4, gold, centered |
| Spacer | | `FansivibeSpacing.xxxl` (64px) |
| Hero | Headline | "Your Personal<br>Appearance Intelligence" — serif, 36px, w400, center, leading 1.15 |
| Spacer | | `FansivibeSpacing.md` (16px) |
| Subtitle | Body | 15px, secondary colour, center, leading 1.5 |
| Spacer | | `FansivibeSpacing.xl + 8` (40px) |
| Hero image | Illustration | 280px tall, `surfaceContainerHigh` bg, rounded 28px, abstract geometric face profile with gold glow accent and decorative dots/stars |
| Spacer | | `FansivibeSpacing.xl + 8` (40px) |
| Primary CTA | Button | "Analyze My Style" — `FansiButton.primary` with `auto_awesome_rounded` icon |
| Spacer | | `FansivibeSpacing.sm + 4` (12px) |
| Secondary CTA | Button | "Explore Without Scanning" — `FansiButton.secondary` |
| Spacer | | `FansivibeSpacing.xxl + 8` (56px) |
| Sign In | Text + button | "Already have an account?" 14px secondary + outlined gold "Sign In" button |
| Spacer | | `FansivibeSpacing.xl` (32px) |
| Privacy | Note | Lock icon + "Your photos stay private and secure." 10px muted |
| Bottom | | `FansivibeSpacing.lg` (24px) |

### Colour Usage

- Background: `surface` (`#131313`)
- Cards/Illustration bg: `surfaceContainerHigh` (`#2A2A2A`)
- Primary text: `onSurface` (`#E5E2E1`)
- Secondary text: `secondary` (`#C6C6CB`)
- Gold accent: `primary` (`#E3C373`)
- All text: center-aligned

### Animation

- Content rises from below in sequence (600ms each, 300ms stagger)
- Logo fades in → headline rises → subtitle → illustration fades → CTAs stagger
- Selected CTA pulses (1.0→1.06→1.0) then screen brightness fades

### Interaction

- Tap "Analyze My Style" → set `photoPath: true` → navigate to ONB-003
- Tap "Explore Without Scanning" → set `photoPath: false` → navigate to ONB-003
- Tap "Sign In" → navigate to sign-in flow (outside onboarding)

### Responsive

- ≤600px: horizontal padding 24px, content fills width
- >600px: horizontal padding 48px, content max-width 520px, centered

---

## 3. Style Vibe (ONB-003)

### Layout

Single question with 6 premium visual cards in a 2×3 grid.

| Element | Spec |
|---|---|
| Question | "Which style feels most like you?" — `headlineMediumWithFamily`, 28px serif, center |
| Subtitle | "Choose one that resonates" — `bodyMediumWithFamily`, 14px secondary, center |
| Cards | 6 cards in 2×3 grid, each 44% width × 160px height, `surfaceContainer` bg |
| Card animation | Spring (bounciness 3, speed 12), staggered 80ms per pair |
| Selection | Gold border (2px→4px), glow, translateY -4px |
| Continue CTA | `FansiButton.primary` — "Continue" (disabled until selection) |
| Skip | `FansiButton.tertiary` — "I'm not sure" |

### Card Design

Each card is an editorial mood board — no photos, no emoji, no text except the vibe label at the bottom.

| Vibe | Visual |
|---|---|
| Minimalist | Clean horizontal lines, beige-to-charcoal gradient, asymmetry |
| Bold | Saturated geometric collision, magenta/cobalt colour fields |
| Classic | Symmetrical arch motif, gold-on-cream, structured grid |
| Trendy | Dynamic diagonal sweep, neon-adjacent refined colours |
| Natural | Organic curves, earth tones (olive, terracotta), flowing lines |
| Edgy | Sharp angles, dark field with one bright accent |

### Animation

1. Question fades in (400ms)
2. Cards fly in from below in staggered pairs (80ms delay)
3. Each card lands with spring physics
4. On tap: selected card glows gold, others dim slightly
5. "Continue" fades in (200ms after selection)
6. Exit: selected card lifts, screen fades

### Interaction

- Tap card → select (deselects any previous)
- Tap selected card → deselect
- Tap "Continue" → navigate to ONB-004 (or ONB-005 in the user's list)
- Tap "I'm not sure" → skip selection, navigate forward with null vibe

---

## 4. Camera Permission (ONB-005)

### Layout

Trust-building screen with illustration and three privacy statements.

| Element | Spec |
|---|---|
| Illustration | Floating viewfinder-shaped card, `surfaceContainerHigh`, large camera/phone icon |
| Headline | "One Photo Is All It Takes" — `headlineMediumWithFamily`, 28px serif |
| Body | "AI analyzes your look and suggests improvements. No data is stored without your permission." |
| Trust statements | 3 items: lock+shield icons, 14px body |
| Primary CTA | "Allow Camera" — `FansiButton.primary` |
| Secondary | "Choose from Gallery" — `FansiButton.secondary` |
| Skip | "Skip for now" — `FansiButton.tertiary` |

### Colour

- Lock icon: gold
- Trust statements: `bodyMediumWithFamily`, secondary colour
- Privacy emphasis: regular weight, no scare formatting

### Animation

1. Viewfinder card floats in from above (1.0s float, ease-in-out)
2. Lock icon pulses subtly
3. Trust statements fade in sequentially (200ms stagger)
4. CTA fades in last

### States

- **Normal**: All elements visible, CTAs enabled
- **Permission denied**: Show gallery option more prominently, show Settings deep-link
- **Both denied**: Message "Enable camera access in Settings" + "Continue without scanning"

### Interaction

- "Allow Camera" → OS permission dialog → ONB-006
- "Choose from Gallery" → OS picker → ONB-006
- "Skip for now" → navigate to HOME-001 (light path)

---

## 5. Photo Capture (ONB-006)

### Layout

Full-screen camera with minimal UI overlay.

| Element | Spec |
|---|---|
| Camera preview | Full-screen, fills entire safe area |
| Framing guide | Semi-transparent silhouette outline, white, 40% opacity |
| Shutter button | Large circle (72px), gold accent ring, white fill, center bottom |
| Gallery button | Small thumbnail preview of last photo, bottom-left |
| Skip link | "Skip" text, top-right, small |
| Retake | Replaces "Skip" after capture, top-right |

### Animation

1. Camera preview slides in from top (400ms)
2. Framing guide fades in (600ms)
3. After capture: photo "develops" like Polaroid (center ripple, 600ms)
4. Auto-advance to ONB-007 after 2s preview

### States

- **Ready**: Camera preview active, framing guide visible
- **Captured**: Photo preview with "Looks great!" overlay, retake option
- **Gallery pick**: Photo preview, same state as captured
- **Error**: Camera unavailable → show error message + gallery option

### Interaction

- Tap shutter → capture photo
- Tap gallery → pick from library
- Tap retake → return to camera
- Tap skip → navigate forward without photo (light path)

---

## 6. AI Analysis (ONB-007)

### Layout

Full-screen atmospheric processing state.

| Element | Spec |
|---|---|
| Photo | Circular crop (120×120) of captured photo, center |
| Arc | Gold circular progress arc, 0→300° over 2.5s |
| Particles | Gold particles spiral outward from photo |
| Terms | Atmospheric floating terms: "SILHOUETTE", "HARMONY", "PROPORTION", "PALETTE" |
| Glass layer | Subtle backdrop blur on the lower portion |
| Auto-advance | After 2.5-3.5s, transition to ONB-008 |

### Animation

1. Photo shrinks into circular frame (400ms)
2. Gold particles begin spiraling outward
3. Arc traces from 0° to 300° (2.5s)
4. Terms drift diagonally, fade in/out (3s cycle)
5. At completion: particles coalesce, screen brightness increases
6. ONB-008 materializes from center (700ms)

### States

- **Processing (normal)**: All animations active, 2.5-3.5s
- **Extended (5s+)**: Terms change to "STILL ANALYZING…", arc pulses
- **Error (>8s)**: Show "Analysis paused" with retry button
- **Light path**: Not applicable (no photo to process)

---

## 7. Your Analysis (ONB-008)

### Layout — The Emotional Peak

Scrolled layout with multiple card sections. Each section is a premium editorial card.

#### Section 1: Score Hero

| Element | Spec |
|---|---|
| Score | Large animated number (0→X), serif, 72px, gold if ≥70, green if ≥90 |
| Label | "Style Score" — `labelMediumWithFamily`, secondary, center |
| Silhouette | Small diagram/icon representing detected silhouette type |

#### Section 2: Color Palette

| Element | Spec |
|---|---|
| Title | "Your Colour Palette" — small serif heading |
| Swatches | 4-6 colour circles in a horizontal row, each 44×44 |
| Labels | Small colour name under each swatch |

#### Section 3: AI Insights

| Element | Spec |
|---|---|
| Cards | 2-3 editorial insight cards, `surfaceContainerLow` bg, md radius |
| Each card has | Icon (left), title (`titleLarge`), body (`bodyMedium`), optional detail expand |

#### Section 4: Appearance Intelligence Progress

| Element | Spec |
|---|---|
| Title | "Appearance Intelligence" — label |
| Capabilities | Horizontal scroll row of 7 circle+label items |
| Active | Gold gradient ring, filled icon, "Active" label |
| Locked | Dimmed ring, lock icon, unlock hint text |

#### CTAs

| Element | Spec |
|---|---|
| Primary | "Save My Progress" — `FansiButton.primary` → ONB-009 |
| Secondary | "Retake Photo" — `FansiButton.tertiary` → ONB-006 |

### Animation

1. Score badge flies in from top (spring, 600ms)
2. Score counter animates 0→X (800ms ease-out)
3. Colour swatches expand from center (400ms, 80ms stagger)
4. Insight cards slide up from below (100ms stagger)
5. AI Progress scroll fades in (500ms)
6. Exit: score and palette converge to center → become avatar in ONB-009

### Interaction

- Tap insight card → expand for more detail (subtle height animation)
- Tap locked capability → show tooltip "Available when you [action]"
- Tap "Save My Progress" → ONB-009
- Tap "Retake Photo" → ONB-006

---

## 8. Account Creation (ONB-009)

### Layout

Minimal form with glassmorphism inputs.

| Element | Spec |
|---|---|
| Avatar | Circular ring showing extracted colour palette, center-top |
| Headline | "Save Your Style Journey" — serif, 24px, center |
| Subtitle | "Your Style DNA, score, and analysis will be saved to your account." |
| Email field | Glass-style input, dark bg, gold underline focus |
| Password field | Same style, obscured, optional biometric toggle |
| Name field | Optional, pre-hint "Your name" |
| Primary CTA | "Create Account" — `FansiButton.primary` |
| Social | Google button, Apple button — `FansiButton.secondary` with icons |
| Skip | "Maybe Later — Save Locally" — `FansiButton.tertiary` |

### Colour

- Input bg: `surfaceContainerLow` with slight transparency
- Focus: gold underline, `primary`
- Social buttons: `surfaceContainerHigh` with brand icons

### Animation

1. Colour ring from ONB-008 travels to center-top and settles (500ms)
2. Form fields fade in from below (100ms stagger)
3. Each field's gold underline animates on focus (200ms)
4. "Create Account" button fills with gold gradient on press
5. Exit: avatar ring expands outward, cross-fades to HOME-001 (700ms)

### States

- **Empty**: All fields empty, "Create Account" disabled
- **Filling**: Validation indicators (subtle), button enables when valid
- **Error (email)**: Red message below field "Enter a valid email"
- **Error (network)**: Inline message "Connection issue. Saved locally."
- **Loading**: Button shows subtle shimmer while creating account
- **Success**: Transition to HOME-001

### Interaction

- Type in fields → validation on submit
- Tap "Create Account" → save + navigate to HOME-001
- Tap Google/Apple → OAuth flow → navigate to HOME-001
- Tap "Maybe Later" → save locally → navigate to HOME-001

---

## 9. Personalized Home — First Visit (HOME-001)

### Layout

Standard Home screen layout with onboarding data injected. Sections adapt based on whether user completed photo path or light path.

#### Photo Path Sections (in order):

1. **GreetingHeader** — "Welcome, [Name]" with date
2. **StyleScoreCard** — Score from onboarding, first-view animation (gold shimmer sweep)
3. **StyleDNACard** (new first-visit card) — Archetype label, colour palette, silhouette type
4. **TodaysLookCard** — First AI recommendation contextualized by analysis + vibe
5. **AiCapabilitiesCard** (new) — "Appearance Intelligence" progress: 2 active (gold), 5 locked (dimmed)
6. **QuickActions** — Standard action cards
7. **AIInsightCard** — One insight from the analysis

#### Light Path Sections:

1. **GreetingHeader** — "Welcome to Fansivibe"
2. **StyleScoreCard** — Placeholder: "Take your first analysis"
3. **TodaysLookCard** — Sample look with "Analyze your style" prompt
4. **QuickActionCard** — First action: "Analyze My Style" → ONB-005
5. **AIInsightCard** — "AI is ready when you are"

### Animation (First Visit Only)

- Score card: gentle gold shimmer sweep on appear (1.5s)
- Style DNA card: fades in with content staggered
- AI capabilities: icons light up sequentially from left to right
- A subtle "Welcome" toast appears at top for 3s then fades

---

## Motion Design System

| Transition | Duration | Curve | Use |
|---|---|---|---|
| Cross-fade | 600ms | ease-out | Between screens |
| Shared element | 500ms | ease-in-out | Avatar ring analysis→account |
| Card fly-in | 600ms | cubic-bezier(0.16,1,0.3,1) | Vibe cards, insight cards |
| Score counter | 800ms | ease-out | Score animation |
| Shimmer sweep | 1.5s | linear | Score card celebration |
| Float | 1.0s | ease-in-out | Permission illustration |
| Spring | — | bounciness 3, speed 12 | Card selection physics |
| Gold arc | 2.5s | linear | Processing progress |

### Reduced Motion

When `MediaQuery.reducedMotion` is enabled:
- All spring animations become fade transitions
- Staggered reveals happen simultaneously
- Counter animation jumps to final value
- Processing arc skips to completion in 0.5s

---

## Accessibility

| Requirement | Implementation |
|---|---|
| Dynamic text | All text uses `Text` widget with `textScaleFactor` support |
| Screen readers | `Semantics` widgets on cards, CTAs, icons |
| One-handed use | Primary CTAs at thumb-reachable height |
| Small phones | Scrollable layout, horizontal padding adapts |
| Tablets | Max-width constraint (520px), generous padding |
| Dark mode | Native (dark theme only by design) |
| Light mode | Not currently supported (dark brand identity) |
| Reduced motion | `MediaQuery.reducedMotion` respected |

---

## Component Inventory — Shared Onboarding Widgets

| Widget | File | Purpose |
|---|---|---|
| `GlassContainer` | `widgets/glass_container.dart` | Frosted glass effect container |
| `VibeCard` | `widgets/vibe_card.dart` | Style selection mood board card |
| `AnimatedScoreCounter` | `widgets/animated_score_counter.dart` | Animated number with gold styling |
| `ColorPaletteDisplay` | `widgets/color_palette_display.dart` | Horizontal colour swatch row |
| `AiCapabilityIcon` | `widgets/ai_capability_icon.dart` | Single capability status indicator |
| `AnalysisInsightCard` | `widgets/analysis_insight_card.dart` | Editorial insight card with icon |

---

## Route Map

| Route | Screen | Path |
|---|---|---|
| `splash` | Splash | `/splash` |
| `entry` | Entry | `/entry` |
| `vibeSelect` | Vibe Select | `/onboarding/vibe` |
| `cameraPermission` | Camera Permission | `/onboarding/camera-permission` |
| `photoCapture` | Photo Capture | `/onboarding/photo-capture` |
| `aiAnalysis` | AI Analysis | `/onboarding/analysis` |
| `yourAnalysis` | Your Analysis | `/onboarding/result` |
| `accountCreation` | Account Creation | `/onboarding/account` |
| `home` | Home (existing) | `/home` |
