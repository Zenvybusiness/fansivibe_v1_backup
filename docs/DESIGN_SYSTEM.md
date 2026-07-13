# Fansivibe Design System

## Brand Feel

Fansivibe is:

- premium
- modern
- intelligent
- warm
- confident
- personal

The UI must not feel childish, noisy, or like a generic AI chatbot.

## Visual Direction

The approved screen designs use a dark luxury visual direction.

Core visual language:

- near-black backgrounds
- dark charcoal surfaces
- warm gold accents
- soft off-white primary text
- muted secondary text
- rounded cards
- editorial serif headings
- clean sans-serif supporting text

The actual color and typography tokens must be verified from implemented
theme values.

## Theme Rule

All reusable visual values belong in the design system.

Suggested structure:

shared/theme/
├── fansivibe_colors.dart
├── fansivibe_typography.dart
├── fansivibe_spacing.dart
├── fansivibe_radius.dart
├── fansivibe_shadows.dart
└── fansivibe_theme.dart

Do not repeatedly hardcode visual values inside screens.

## Components

Create reusable components only after a pattern is actually reused.

Possible shared components:

- FansiButton
- FansiCard
- FansiChip
- FansiBadge
- FansiSectionTitle
- FansiLoadingView
- FansiErrorView

Feature-specific components remain inside their feature.

## Layout

UI must:

- support common mobile widths
- respect safe areas
- handle keyboard visibility
- prevent text overflow
- support long content
- use scrolling where appropriate
- consider text scaling

Do not design for one fixed device size.

## Consistency

Before creating a new visual pattern, inspect existing:

- colors
- typography
- spacing
- radius
- cards
- buttons
- chips
- navigation

Reuse established patterns.

Avoid:

- random gradients
- excessive shadows
- inconsistent radius
- arbitrary spacing
- different button styles on every screen

## AI Results

AI result screens should use structured visual sections.

Examples:

- score
- explanation
- metrics
- reasons
- recommendations
- alternatives

AI-generated text must not determine the widget hierarchy.

## Product Language

User-facing language should be constructive and respectful.

Prefer:

"This fit may create a more balanced silhouette."

Avoid:

"This looks bad on you."

Recommendations are guidance, not absolute judgments.