# Design System: The Digital Atelier

## 1. Overview & Creative North Star
**The Creative North Star: "The Digital Atelier"**

This design system is not a utility; it is a curated editorial experience. It moves away from the "app-like" density of traditional SaaS and embraces the spaciousness of a high-end fashion lookbook. We prioritize negative space as a luxury commodity.

The system breaks the "template" look through **intentional asymmetry** and **tonal depth**. We do not use grids to box things in; we use them to anchor elements while letting others breathe or overlap. The aesthetic is a fusion of Apple’s precision, Zara’s stark minimalism, and Vogue’s typographic authority.

---

## 2. Colors & Tonal Architecture
Our palette is rooted in the "After Hours" luxury of deep blacks and matte golds. It is designed to make high-resolution fashion photography "pop" while the UI recedes into the background.

### The "No-Line" Rule
**Explicit Instruction:** Designers are prohibited from using 1px solid borders to section content. Boundaries must be defined solely through background color shifts.
- Use `surface-container-low` (#1C1B1B) to define a section against the `background` (#131313).
- Use `surface-container-high` (#2A2A2A) to indicate interactivity or nesting.
- High-contrast lines are "cheap"; tonal transitions are "premium."

### Surface Hierarchy & Nesting
Treat the UI as physical layers of fine paper or frosted glass. 
- **Base Layer:** `surface` (#131313) or `surface-container-lowest` (#0E0E0E).
- **In-Section Cards:** `surface-container` (#201F1F).
- **Floating Overlays:** `surface-container-highest` (#353534) with backdrop-blur.

### The "Glass & Gradient" Rule
To avoid a flat, "dead" dark mode, use Glassmorphism for floating elements (e.g., Tab bars, sticky headers). 
- **Recipe:** `surface-container-low` at 70% opacity + 20px Backdrop Blur.
- **Signature Texture:** Use a subtle linear gradient on primary CTAs moving from `primary` (#E3C373) to `primary-container` (#C6A85B) at a 135-degree angle. This adds a "metallic" weight that flat hex codes lack.

---

## 3. Typography: The Editorial Voice
Typography is our primary tool for brand authority. We use a high-contrast pairing of a sophisticated serif and a functional sans-serif.

| Level | Token | Font Family | Size | Weight | Intent |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Display** | `display-lg` | Noto Serif | 3.5rem | 400 | Editorial Hero / Statements |
| **Headline** | `headline-md` | Noto Serif | 1.75rem | 500 | Section Headers |
| **Title** | `title-lg` | Inter | 1.375rem | 600 | Card Titles / Nav |
| **Body** | `body-lg` | Inter | 1rem | 400 | General Reading |
| **Label** | `label-md` | Inter | 0.75rem | 500 | Metadata / All-Caps Tags |

**Design Note:** For a "Vogue" feel, use `display-lg` with tight letter-spacing and `label-md` with 10% letter-spacing in all-caps for a premium, utilitarian contrast.

---

## 4. Elevation & Depth
We convey hierarchy through **Tonal Layering** rather than traditional structural lines or heavy shadows.

### The Layering Principle
Depth is achieved by "stacking" the surface-container tiers. Place a `surface-container-lowest` card on a `surface-container-low` section. This creates a soft, natural "recessed" or "lifted" look without visual noise.

### Ambient Shadows
When a "floating" effect is required (e.g., a Modal or FAB), shadows must be extra-diffused:
- **Value:** `0px 24px 48px rgba(0, 0, 0, 0.5)`
- **The Tint:** The shadow should not be pure black; it should be a deep tint of the background color to mimic natural ambient light.

### The "Ghost Border" Fallback
If a border is absolutely necessary for accessibility (e.g., an input field), use a **Ghost Border**: 
- **Token:** `outline-variant` (#4C4638) at **20% opacity**. 
- **Forbidden:** 100% opaque, high-contrast borders.

---

## 5. Components

### Buttons
- **Primary:** Background `primary` (#E3C373), Text `on-primary` (#3E2E00). Radius: `full`.
- **Secondary:** Background `surface-container-high`, Text `on-surface`.
- **Tertiary (Editorial):** Text-only with `label-md` styling and a 1px `primary` underline offset by 4px.

### Cards & Lists
- **Rule:** Forbid divider lines. Use vertical white space (`2rem` or `3rem`) to separate content.
- **Radius:** Always use `lg` (2rem) or `md` (1.5rem) for main containers to create a soft, friendly silhouette that contrasts with the sharp typography.

### Input Fields
- **Style:** Minimalist. No background fill. Only a bottom border using `outline-variant` at 40% opacity. 
- **Focus State:** Bottom border transitions to `primary` (#E3C373) with a subtle `primary` outer glow (4px blur).

### Chips (The "Label" Look)
- **Style:** `surface-container-highest` background, `sm` (0.5rem) radius, `label-sm` text. These should look like garment tags.

---

## 6. Do's and Don'ts

### Do
- **Do** use generous white space. If a layout feels "full," it is wrong. Increase padding by 1.5x.
- **Do** overlap elements. Let a photo slightly overlap a `display-lg` heading to create a 3D editorial depth.
- **Do** use `secondary` (#C6C6CB) for secondary text to maintain a soft visual hierarchy.

### Don't
- **Don't** use pure white (#FFFFFF). Use `on-surface` (#E5E2E1) to avoid harsh eye strain on the black background.
- **Don't** use standard "Material Design" blue for links. Use `primary` (gold) or simply underline the text.
- **Don't** use sharp corners. Everything interactive must follow the Roundedness Scale (`md` to `xl`).
- **Don't** use "Drop Shadows" on cards sitting on the background. Use tonal shifts (`surface-container-low`) instead.
