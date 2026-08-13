# Core User Journey Target

## Overview

This document defines the TARGET user journey for Fansivibe without implementation details. It represents the desired first-time and returning-user experience aligned with the product principles A through H. No screens, routing, backend, or database was modified.

The target defines two paths and a returning user journey:

- **PATH A:** New user who wants personalized analysis (via camera scan)
- **PATH B:** New/returning user who wants to explore without scanning
- **RETURNING USER JOURNEY:** Continuity of state and personalized content

---

## Product Principles (Reference)

A. First useful value should arrive quickly.
B. Don't ask the user for information the system can reasonably infer.
C. Account creation should preserve/protect value rather than unnecessarily block value.
D. The first successful recommendation should feel like an achievement.
E. Home should reflect what Fansivibe already knows about the user.
F. Saved actions should become part of user memory.
G. Capability progression should reflect what Fansivibe understands about the user.
H. Returning users should see continuity rather than starting over.

---

## PATH A — New User Who Wants Personalized Analysis

### Target Flow

The user opens the app with the intent of getting personalized style analysis. The journey is streamlined to deliver first useful value in the fewest steps possible, respecting principle A.

#### Step 1: Entry Point
- User lands at the entry point with two clear options:
  - **"Scan My Style"** — initiates camera-based analysis
  - **"Explore Without Scanning"** — enters browsable experience immediately

#### Step 2: Direction (Optional, not blocking)
- If user chooses "Scan My Style," they may optionally select a style vibe direction
- Selecting a vibe is **not required** before scanning — the AI can infer direction from the photo
- If user skips vibe selection, the system defaults to "Open to Everything" and tunes recommendations after the first scan

#### Step 3: Capture Photo
- Camera interface with minimal guidance (frame alignment hint)
- **One photo only** — no retakes encouraged to reduce friction
- Photo is captured and immediately sent for analysis

#### Step 4: First Meaningful Value (Arrives Quickly)
- **Within 3-5 seconds** of photo capture, the user sees their first insight:
  - Face shape identification (e.g., "Your face shape is oval")
  - Simple color palette observation (e.g., "Warm undertones detected")
- This arrives **before** any account creation prompt — principle C (account creation preserves value, doesn't block it)

#### Step 5: Low-Friction Account Option
- After the first insight appears, the user is offered:
  - **"Continue Without Account"** — saves analysis locally on device; user can resume later
  - **"Save to Account"** — creates account or signs in; analysis syncs to profile
- The "Continue Without Account" option is the **default** and requires no form filling
- Principle C is satisfied: value is preserved even without account creation

#### Step 6: Personalized Home
- User arrives at Home screen that already reflects what Fansivibe knows:
  - Display: "Welcome back" (or "Welcome" if first visit)
  - First insight is shown prominently (e.g., "Your face shape is oval — structured necklaces complement this")
  - First recommendation is displayed (e.g., "Try these necklines for your face shape")
  - This feels like the reward/destination after the first interaction — principle E

#### Step 7: Capability Unlock (Progression)
- As the user interacts more, capabilities unlock progressively:
  - "Tap to see color analysis for your palette"
  - "Tap to add grooming profile"
  - Progression reflects what Fansivibe understands about the user, not generic XP — principle G

#### Step 8: Saved Actions Become Memory
- When the user saves a look or recommendation, it appears in their profile
- Saved looks are visible on return, creating continuity — principle F
- The Home screen references saved looks: "Based on your saved Modern Minimalist look..."

---

## PATH B — New/Returning User Who Wants to Explore Without Scanning

### Target Flow

The user opens the app not intending to scan but wanting to browse, get inspiration, or explore features.

#### Step 1: Entry Point
- User taps **"Explore Without Scanning"** on the entry screen
- Or user opens the app and lands directly in the Home explorer experience

#### Step 2: Vibe Direction (Optional)
- User may optionally select a style vibe (6 options: Minimalist, Bold, Classic, Trendy, Natural, Edgy)
- Selection is saved to profile but **does not block** access to any feature
- If skipped, user sees "Open to Everything" content

#### Step 3: Immediate Browse Access
- User is taken directly to Home with personalized content based on selected vibe (or default)
- No camera permission request, no photo capture, no processing wait
- Principle A satisfied: useful value arrives instantly

#### Step 4: Explore Feature Tiles
- Home shows feature tiles appropriate for a non-scanning user:
  - "Hairstyle Studio" — browse hairstyle catalog by face shape or vibe
  - "Style Tips" — curated tips for the selected vibe
  - "Discover Looks" — curated looks collection
  - "Wardrobe" — manage digital wardrobe (if items exist)

#### Step 5: Try a Feature Without Scanning
- User taps "Hairstyle Studio" → sees styles categorized by face shape
- User taps "Style Tips" → sees tips tailored to their vibe (or default)
- No photo required for these features — they work from vibe selection alone

#### Step 6: Scan When Ready
- At any point, user can initiate scan via "Scan My Style" CTA on Home
- If user has previously selected a vibe, it's pre-selected
- If not, scan proceeds with "Open to Everything" default

#### Step 7: Home as Discovery Hub
- Home evolves based on what the user explores:
  - New tiles appear based on vibe interactions
  - "Based on your Bold vibe, here are..." recommendations
  - No analysis required for basic personalization

---

## RETURNING USER JOURNEY

### Continuity Without Re-entry

When a returning user opens the app, they should see continuity rather than starting over — principle H.

#### Step 1: App Launch Recognition
- The app recognizes the returning user (via onboarding_data in router state, or local session)
- No re-introduction needed; no re-prompting for basic preferences

#### Step 2: Home Reflects Previous State
- Home screen shows:
  - "Welcome back, [Name]" if display name is known
  - First insight from previous session displayed prominently
  - Reference to last saved look or recommendation
  - Style score progression shown (if previously analyzed)

#### Step 3: Capabilities at Current Level
- Capabilities shown at the user's current unlocked level
- New capabilities are introduced as: "You've unlocked Color Analysis — try it with your next scan"
- Not all capabilities shown as active/inactive based on mock state — principle G

#### Step 4: Quick Re-Scan Option
- Prominent CTA: "Refresh Your Style DNA" 
- Quick one-photo re-scan (no vibe selection required if previously set)
- Results build on previous analysis, not start from scratch

#### Step 5: Seamless Continuation
- If user previously saved looks, they appear in Profile → Saved Looks
- If user previously analyzed hair/grooming, references appear in Home
- The app "remembers" what it knows and only asks for new information — principle B

---

## Journey Comparison: Current vs. Target

| Step | Current Flow | Target Flow | Principle |
|------|-------------|-------------|-----------|
| **Entry** | Splash → Entry with 2 CTA + account gate | Entry with 2 CTA; vibe optional, not blocking | A, C |
| **First Value** | After 8 screen transitions & ~10s | Within 3-5s of photo capture (or instantly for explore) | A |
| **Account Creation** | Required before saving; "Maybe Later" loses data | "Continue Without Account" defaults; saves locally; syncs if account created later | C |
| **Home Arrival** | Conditional on onboardingData/mock data | Reflects user's actual insights, vibe, saved looks | E |
| **Vibe Selection** | Required before scanning (6 options) | Optional; can be selected after scan or skipped | B |
| **Returning User** | Fragile; depends on router state; starts over if lost | Recognized; home reflects previous state; capabilities at current level | H |
| **Saved Looks** | Mock data; no persistence | Real persistence; appears in Home and Profile; creates continuity | F |
| **Capability Grid** | Mock active/inactive state | Progressive unlock based on user's actual interactions | G |
| **First Recommendation** | Listed among other insights | Prominently displayed as achievement after first scan | D |

---

## Key Target Behaviors (No Implementation Details)

### 1. Progressive Understanding
- The AI collects what it can from scans and asks the user only for information it cannot reasonably infer
- Early steps require minimal user input; later steps introduce more detailed preferences
- The system infers: face shape, skin tone, style direction from photo; asks user only for: explicit preferences, saved looks titles

### 2. Account Friction is Minimal
- Account creation never blocks value
- "Continue Without Account" is the default path
- All analysis results are saved locally by default; sync to account is opt-in
- Social sign-in (Google/Apple) is available as a faster account-creation path

### 3. Home is the Reward
- The personalized Home screen feels like a destination, not a starting point
- First meaningful insight appears before account friction where technically possible
- Home reflects what Fansivibe already knows about the user at all times

### 4. Capability Progression is Real
- Capabilities unlock based on what Fansivibe understands about the user
- Not generic XP/levels, but genuine capability progression:
  - "You have face analysis — try hairstyle profiling"
  - "You've saved 3 looks — unlock wardrobe intelligence"
  - Progression is visible in Home and Profile

### 5. Returning User Continuity
- On app launch, the user is recognized and their state is restored
- Home reflects previous analysis, saved looks, vibe direction
- New features are introduced progressively: "You've been using Hairstyle Studio — try Grooming Profile next"
- No setup form; the app asks only for new information

---

## Missing Pieps to Enable the Target Journey

The following exist in the REAL repository and can support the target journey (from the audit):

**Backend APIs:** All necessary endpoints exist (`GET /v1/users/me`, `POST /v1/analysis/hairstyle`, `POST /v1/analysis/grooming`, `POST /v1/looks/saved`, `GET /v1/analysis/runs`)

**Frontend Models:** `OnboardingResult`, `StyleVibe`, `AiCapability`, `HairstyleAnalysisResult`, `GroomingAnalysisResult`, `ProfileData`, `StyleDnaData`

**Shared Components:** Button variants, error views, loading views, hero cards, image wells, badges

**Routing:** GoRouter configuration with all routes properly defined

**What's Missing (to be addressed separately):**
- Local persistence layer for analysis results between launches
- Router state management for `onboarding_data` across sessions
- Frontend services connecting mock data to backend APIs
- Capability unlock logic based on actual user interactions