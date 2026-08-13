# Fansivibe Flutter Application - Complete Navigation/User Journey Analysis

## Overview
This document provides a thorough analysis of the complete navigation flow, screens/routes, and user journey in the Fansivibe Flutter application. The app uses `go_router` for navigation with a modular feature-based architecture.

---

## 1. Main Screens/Routes (GoRouter Configuration)

### App Router Structure (`lib/app/router/app_router.dart`)
The app uses a `StatefulShellRoute.indexedStack` pattern with a bottom navigation bar and 5 main branches:

| Route Path | Route Name | Description |
|---|---|---|
| `/splash` | `splash` | Initial splash screen |
| `/entry` | `entry` | Entry point after splash |
| `/onboarding/vibe` | `vibeSelect` | Style vibe selection |
| `/onboarding/camera-permission` | `cameraPermission` | Camera permission request |
| `/onboarding/photo-capture` | `photoCapture` | Photo capture screen |
| `/onboarding/analysis` | `aiAnalysis` | AI analysis in progress |
| `/onboarding/result` | `yourAnalysis` | Analysis results |
| `/onboarding/account` | `accountCreation` | Account creation |
| `/assistant` | `assistant` | AI assistant screen |
| `/home` | `home` | Main home screen |
| `/home/daily-outfit` | `dailyOutfit` | Daily outfit screen |
| `/discover` | `discover` | Discover looks screen |
| `/discover/look-details` | `lookDetails` | Look details screen |
| `/stylist` | `stylist` | Stylist feature with nested routes |
| `/stylist/scan-outfit` | `scanOutfit` | Outfit scan flow |
| `/stylist/scan-outfit/processing` | `scanProcessing` | Processing screen |
| `/stylist/scan-outfit/processing/analysis` | `scanAnalysis` | Analysis results |
| `/stylist/scan-outfit/build-outfit` | `buildOutfit` | Build outfit flow |
| `/stylist/scan-outfit/build-outfit/generation` | `outfitGeneration` | Outfit generation |
| `/stylist/scan-outfit/build-outfit/generation/recommendation` | `outfitRecommendation` | Recommendation screen |
| `/stylist/hairstyle` | `hairstyle` | Hairstyle vertical slice |
| `/stylist/hairstyle/processing` | `hairstyleProcessing` | Face processing |
| `/stylist/hairstyle/processing/result` | `hairstyleResult` | Hairstyle results |
| `/stylist/hairstyle/processing/result/details` | `hairstyleDetails` | Hairstyle details |
| `/stylist/hairstyle/processing/result/details/recommendation` | (implicit) | Recommendation detail |
| `/stylist/grooming` | `grooming` | Grooming vertical slice |
| `/stylist/grooming/processing` | `groomingProcessing` | Grooming processing |
| `/stylist/grooming/processing/result` | `groomingResult` | Grooming results |
| `/stylist/grooming/processing/result/details` | `groomingDetails` | Grooming details |
| `/stylist/events` | `events` | Events list |
| `/stylist/events/add` | `eventAdd` | Add event |
| `/stylist/events/details` | `eventDetails` | Event details |
| `/wardrobe` | `wardrobe` | Wardrobe screen |
| `/wardrobe/add-category` | `wardrobeAddCategory` | Add wardrobe category |
| `/wardrobe/add-item` | `wardrobeAddItem` | Add wardrobe item |
| `/wardrobe/item-details` | `wardrobeItemDetails` | Wardrobe item details |
| `/profile` | `profile` | Profile screen |
| `/profile/preferences` | `profilePreferences` | Preferences |
| `/profile/saved-looks` | `profileSavedLooks` | Saved looks |
| `/profile/subscription` | `profileSubscription` | Subscription |
| `/profile/support` | `profileSupport` | Support |
| `/profile/settings` | `profileSettings` | Settings |

### Bottom Navigation Bar (5 destinations)
1. **Home** - Home screen
2. **Discover** - Discover looks
3. **Stylist** - Hairstyle + Grooming
4. **Wardrobe** - Wardrobe management
5. **Profile** - Profile & settings

---

## 2. Onboarding Flow

### Entry Points
1. **Splash Screen** (`splash_screen.dart`) - Shows on app launch
   - Animates, then navigates to `/entry`

2. **Entry Screen** (`entry_screen.dart`) - First user interaction
   - Two CTA options:
     - **Analyze My Style** → pushes to `/onboarding/vibe` (vibe select)
     - **Explore Without Scanning** → pushes to `/onboarding/vibe` (vibe select, no photo path)
   - **Sign In** → navigates to `/home`

3. **Vibe Select Screen** (`vibe_select_screen.dart`) - Style vibe choice
   - 6 style vibes: Minimalist, Bold, Classic, Trendy, Natural, Edgy
   - **Continue** (with selection):
     - If photo path: pushes to `/onboarding/camera-permission`
     - If no photo path: navigates to `/home` with vibe extra
   - **Skip** → navigates to `/home` (with or without vibe)

4. **Camera Permission Screen** (`camera_permission_screen.dart`) - Camera access
   - Options: Allow Camera → `/onboarding/photo-camera`, Choose from Gallery → `/onboarding/photo-capture`, Skip → `/home`

5. **Photo Capture Screen** (`photo_capture_screen.dart`) - Take/capture photo
   - Capture photo → after 2 sec delay → `/onboarding/analysis`
   - Retake → re-capture
   - Skip → `/home`

6. **AI Analysis Screen** (`ai_analysis_screen.dart`) - Analysis in progress
   - Particle animation + arc progress
   - After completion → replaces route to `/onboarding/result`

7. **Your Analysis Screen** (`your_analysis_screen.dart`) - Analysis results
   - Style score, color palette, AI insights
   - **Save My Progress** → `/onboarding/account`
   - **Retake Photo** → `/onboarding/photo-capture` or pops back

8. **Account Creation Screen** (`account_creation_screen.dart`) - Create account
   - Email, password, name fields
   - **Create Account** → navigates to `/home` with `onboarding_complete` extra
   - **Google/Apple Sign In** → navigates to `/home` with `onboarding_complete` extra
   - **Maybe Later** → navigates to `/home` with `saved_locally` extra

---

## 3. Authentication/Login Flow

### Onboarding-Driven Authentication
The app uses an onboarding-first approach rather than traditional login:

1. **Splash → Entry** - Initial screen
2. **Entry → Vibe Select** - User chooses style direction
3. **Vibe Select → Camera Permission** - Photo capture decision
4. **Camera Permission → Photo Capture** - Take/gallery photo
5. **Photo Capture → AI Analysis** - Process image
6. **AI Analysis → Your Analysis** - Show results
7. **Your Analysis → Account Creation** - Save progress

### Key Flow Variations
- **Skip onboarding**: User can skip at Entry or Camera Permission → goes directly to `/home`
- **Already have account**: Entry screen has "Already have a Fansivibe account? Sign In" → goes to `/home`
- **Save Locally**: Account creation has "Maybe Later — Save Locally" → goes to `/home` without full onboarding

### Profile Screen Access
- Profile accessible from bottom nav bar
- Profile menu has: Preferences, Saved Looks, Subscription, Support, Settings, Sign Out
- Account creation completes onboarding and navigates user to home

---

## 4. Home Screen Architecture

### Home Screen (`home_screen.dart`)
The home screen has three states based on `onboardingData`:

| Condition | Screen Rendered |
|---|---|
| `onboardingData != null && hasAnalysis && UserSession.hasSavedWardrobeItem` | `FirstTimeLightPathHomeScreen` |
| `onboardingData != null && hasAnalysis` | `FirstTimeHomeScreen` |
| `onboardingData != null` | `FirstTimeLightPathHomeScreen` |
| Otherwise | Regular `HomeScreen` |

### First Time Home Screen (`first_time_home_screen.dart`)
- Welcome screen for new users
- Features: Style Score, Style DNA, Capability Grid, Quick Tools, AI Quote
- **Try This Look** → `/daily-outfit`
- **Explore Hairstyles** → `/hairstyle`

### First Time Light Path Home Screen (`first_time_light_path_home_screen.dart`)
- For users who chose a vibe but haven't scanned a photo
- Acknowledges their style direction choice
- Offers: Analyze My Style → `/camera-permission`, Explore looks → `/discover`

### Home Screen Quick Actions
- **Scan Outfit** → `/scan-outfit`
- **Build Outfit** → `/build-outfit`
- **Change Style** → `/build-outfit`
- **Style Tips** → `/discover`
- **Event Styling** → `/events`

### Home Screen Components
- `FansiHeroCard` (65% image / 35% content rule)
- `FansiInsightCard` (20% visual / 80% content rule)
- `FansiCard` - base card component
- `SectionTitle` - section headers
- `QuickActionCard` - actionable cards
- `StyleScoreCard` - circular progress + breakdown grid
- `StyleStreakCard` - daily streak tracking
- `AIInsightCard` - AI insight displays

---

## 5. Scan Screen Flow

### Outfit Scan Flow
1. **From Home** → `/scan-outfit` (OutfitScanScreen)
   - Camera interface with preview
   - Check: Lighting, Framing, Posture
   - **Capture** → `/scan-processing` with image path

2. **Outfit Processing** (`outfit_processing_screen.dart`)
   - Processes captured image
   - Shows processing stages
   - **View Results** → `/scan-analysis`

3. **Outfit Analysis** (`outfit_analysis_screen.dart`)
   - Full analysis results
   - Alternative outfits, recommendations

### Hairstyle Scan Flow
1. **From Home or Discover** → `/hairstyle` (FaceScanScreen)
   - Face scan checks (eye detection, face shape, etc.)
   - **Scan Face** → `/hairstyle-processing`

2. **Face Processing** (`face_processing_screen.dart`)
   - AI analysis service
   - Progress stages display
   - **View Results** → `/hairstyle-result`

3. **Hairstyle Results** (`hairstyle_result_screen.dart`)
   - Style profile (face shape, skin tone, style DNA)
   - Top recommendation with % match
   - Alternative hairstyles
   - **Save Style** → saves to profile
   - **Try Another** → back to `/hairstyle`

4. **Hairstyle Details** (`hairstyle_details_screen.dart`)
   - Detailed recommendation info
   - Styling tips, maintenance, best for
   - **Try This Style** → saves style

### Grooming Scan Flow
1. **From Stylist** → `/grooming` (GroomingInputScreen)
   - Face shape selection
   - Beard style, density, color selection
   - **Analyze Style** → `/grooming-processing`

2. **Grooming Processing** (`groving_processing_screen.dart` - inferred from route)
   - AI grooming analysis
   - Shows progress stages

3. **Grooming Results** (`grooming_result_screen.dart`)
   - Feature profile (face shape, beard style, density, color)
   - Score/percentage match
   - Primary beard recommendation
   - Eyewear recommendations
   - Why it works section
   - Specifications (beard length, cheek line, eyewear frame)
   - Alternatives
   - **Save Look** → saves to profile
   - **Try Another** → back to `/grooming`

---

## 6. Hairstyle Vertical Slice

### Files and Flow
| File | Role |
|---|---|
| `lib/features/hairstyle/data/hairstyle_models.dart` | Data models (HairstyleAnalysisResult, HairstyleRecommendation) |
| `lib/features/hairstyle/data/hairstyle_mock_data.dart` | Mock data for testing |
| `lib/features/hairstyle/data/hairstyle_client.dart` | Client/API layer |
| `lib/features/hairstyle/domain/hairstyle_service.dart` | Business logic + learning service |
| `lib/features/hairstyle/presentation/face_scan_screen.dart` | Camera-based face scan |
| `lib/features/hairstyle/presentation/face_processing_screen.dart` | AI analysis processing |
| `lib/features/hairstyle/presentation/hairstyle_result_screen.dart` | Results with recommendations |
| `lib/features/hairstyle/presentation/hairstyle_details_screen.dart` | Detailed recommendation view |
| `lib/features/hairstyle/presentation/widgets/hairstyle_widgets.dart` | Supporting widgets |

### Hairstyle Flow
```
Home/Discover → /hairstyle (FaceScanScreen)
    ↓ Scan Face
    ↓ /hairstyle-processing (FaceProcessingScreen)
    ↓ AI Analysis
    ↓ /hairstyle-result (HairstyleResultScreen)
    ↓ View details
    ↓ /hairstyle-details (HairstyleDetailsScreen)
```

### Key Widgets (`hairstyle_widgets.dart`) - Need to check

---

## 7. Grooming Vertical Slice

### Files and Flow
| File | Role |
|---|---|
| `lib/features/grooming/data/grooming_models.dart` | Data models (GroomingAnalysisResult, GroomingRecommendation) |
| `lib/features/grooming/data/grooming_mock_data.dart` | Mock data |
| `lib/features/grooming/data/grooming_client.dart` | Client layer |
| `lib/features/grooming/data/grooming_service.dart` | Business logic |
| `lib/features/grooming/presentation/grooming_input_screen.dart` | Feature input (face shape, beard style, etc.) |
| `lib/features/grooming/presentation/grooming_result_screen.dart` | Results screen |
| `lib/features/grooming/presentation/grooming_details_screen.dart` | Detailed recommendations |
| `lib/features/grooming/presentation/widgets/grooming_widgets.dart` | Supporting widgets |

### Grooming Flow
```
Stylist → /grooming (GroomingInputScreen)
    ↓ Select features (face shape, beard style, density, color)
    ↓ /grooming-processing (processing screen)
    ↓ AI Analysis
    ↓ /grooming-result (GroomingResultScreen)
    ↓ View details
    ↓ /grooming-details (GroomingDetailsScreen)
```

### Grooming Input Screen
- Face Shape options
- Beard Style options
- Beard Density options
- Beard Color options
- **Analyze Style** → triggers processing

### Grooming Result Screen Sections
- Feature Profile (face shape, beard style, density, color)
- Score section with match percentage
- Primary Beard Recommendation
- Eyewear Suggestion
- Why It Works (reasons)
- Grooming Specifications (beard length, cheek line, eyewear frame)
- Alternatives
- Actions (Save Look, Try Another)

---

## 8. Saved Looks / Profile Flow

### Profile Screen (`profile_screen.dart`)
Main profile with:
- Profile Hero Card
- Achievement Bar
- Style DNA Card
- **Saved Looks** section with "View All"
- Account menu (Preferences, Saved Looks, Subscription, Support, Settings, Sign Out)

### Saved Looks Screen (`saved_looks_screen.dart`)
- Lists all saved looks
- Each look: FansiHeroCard with title, date, items
- **Back** button in app bar

### Discover → Look Details → Save
```
DiscoverScreen → look tap → /look-details (LookDetailsScreen)
    ↓ Save Look button
    ↓ LearningService.instance.addSavedLook(look.title)
    ↓ Profile → Saved Looks updated
```

### Look Details Screen (`look_details_screen.dart`)
- Hero section with look image
- Match Score breakdown (Fit, Color Harmony, Occasion, Creativity)
- Reasons for recommendation
- Style & Fit tags
- Ensemble components
- Wardrobe alternatives
- **Save Look** → saves to profile
- **Share** → share dialog

### Saved Look Data Structure
- Each saved look has: title, date, score, items (category names)
- Displayed in SavedLooksScreen as FansiHeroCard

---

## 9. State Management/Services

### User Session (`lib/shared/utils/user_session.dart`)
- Simple global flag: `UserSession.hasSavedWardrobeItem`
- No persistence - resets on app restart
- Used to gate first-visit home screen flows

### Learning Service (`lib/features/learning/domain/learning_service.dart`)
- Singleton pattern: `LearningService.instance`
- Manages wardrobe items: `addItem()`, `load()`, listeners
- Saves learned looks: `addSavedLook()`
- Wardrobe data source for WardrobeScreen

### Hairstyle Service (`lib/features/hairstyle/domain/hairstyle_service.dart`)
- Runs AI analysis: `runAnalysis()`
- Manages stages: `completedStageCount`, `totalStages`
- Handles errors: `analysisError`
- Saves recommendations: `saveLook()`
- Attaches learning: `attachLearning(LearningService.instance)`

### Grooming Service (`lib/features/grooming/data/grooming_service.dart`)
- Similar pattern to hairstyle service
- Runs grooming analysis
- Saves grooming looks: `saveGroomingLook()`
- Analysis results: `GroomingAnalysisResult`

### Onboarding Data (`lib/features/onboarding/data/onboarding_data.dart`)
- `StyleVibe` enum (6 styles)
- `OnboardingResult` - vibe + analysis + display name
- `AiCapability` - 7 capabilities with active status
- `allCapabilities` list - tracks which capabilities are active

### Mock Data
- `home_mock_data.dart`, `daily_outfit_mock_data.dart`
- `hairstyle_mock_data.dart`, `grooming_mock_data.dart`
- `wardrobe_mock_data.dart`, `discover_mock_data.dart`
- `profile_mock_data.dart`, `profile_mocks.dart`

---

## 10. Shared/Reusable Components

### Card Family (Digital Atelier Design System)

#### FansiHeroCard (65% image / 35% content rule)
- Enforced via `Expanded` flex ratios
- Image area always 65% (default), content 35%
- Used for: Today's Look, Outfit Recommendations, Saved Looks, Discover Stories, Hairstyle Recommendations
- Rules: Image is hero, content concise and ellipsized, additional info on detail page

#### FansiInsightCard (20% visual / 80% content rule)
- Horizontal split with 20% flex for visual, 80% for content
- Used for: AI Insights, Style DNA, Progress, Tips, Analytics
- Rules: Content is focus, visual is compact medallion, additional info on detail page

#### FansiCard
- Base card component with surface container styling
- Used as base for other card types

#### FansiBadge
- Small badge widget for scores, labels, tags
- Colors: accent gold, success, secondary

### Button Variants
- **FansiButton.primary** - Gold background, main CTA
- **FansiButton.secondary** - Surface container high, alternatives
- **FansiButton.tertiary** - Text only, editorial links

### Other Reusable Components
- `FansiButton` - three variants (primary/secondary/tertiary)
- `FansiImageWell` - image well widget
- `FansiChip` - filter/chip widget
- `SectionTitle` - section headers with underline
- `GreetingHeader` - time-based greeting
- `TodaysLookCard` - today's look display
- `StyleScoreCard` - style performance card
- `StyleStreakCard` - daily streak tracking
- `AIInsightCard` - AI insight displays
- `HomeStatItem` - stat displays
- `HomeProgressRing` - progress indicator
- `StreakDayIndicator` - streak day dots
- `QuickActionCard` - quick action cards on home
- `GreetingHeader` - welcome message
- `CategoryTile` - wardrobe category tiles
- `ClothingItemCard` - wardrobe item cards
- `LookCard` - discover look cards
- `LookTag` - style/fit tags
- `ReasonRow` - recommendation reasons
- `ComponentRow` - ensemble components
- `AlternativeSection` - wardrobe alternatives
- `_FilterSheet` - filter modal in Discover

### Theme Constants
- `fansivibe_colors.dart` - color palette
- `fansivibe_typography.dart` - text styles
- `fansivibe_radius.dart` - border radii
- `fansivibe_spacing.dart` - spacing tokens
- `fansivibe_shadows.dart` - shadow definitions

---

## Complete User Journey Maps

### New User Journey (Full Onboarding)
```
Splash (3s) → Entry (welcome/CTA)
    ├── Analyze My Style → Vibe Select → Camera Permission → Photo Capture
    │       ↓ (capture photo) ↓
    │       AI Analysis (3s) ↓ Your Analysis
    │       ↓ Save Progress ↓ Account Creation
    │       └──────────────────→ Home (onboarding complete)
    │
    └── Explore Without Scanning → Vibe Select (no photo)
            ↓
        Home (with chosen vibe, light path)
```

### Returning User Journey
```
Splash → Entry → (Sign In) → Home
```
- If onboarding complete + has wardrobe item → FirstTimeLightPathHomeScreen
- If onboarding complete + no wardrobe → FirstTimeHomeScreen
- Otherwise → Regular HomeScreen

### From Home Screen
```
Home → Quick Actions:
  ↓ Scan Outfit → OutfitScanScreen → Processing → Analysis
  ↓ Build Outfit → BuildOutfitScreen → Generation → Recommendation
  ↓ Hairstyle Studio → HairstyleScreen → Processing → Result → Details
  ↓ Style Tips → DiscoverScreen → LookDetails
  ↓ Event Styling → EventsScreen → EventDetails

Home → Profile → Saved Looks → View saved looks
Home → Profile → Preferences → Account settings
Home → Discover → Filter → LookDetails → Save Look
```

### From Discover
```
DiscoverScreen → Filter → LookCard tap → LookDetailsScreen
    ↓ Save Look → Profile → Saved Looks updated
    ↓ Share → Share dialog
```

### From Stylist
```
Stylist → Hairstyle → FaceScan → Processing → Result → Details → Save
Stylist → Grooming → Input → Processing → Result → Details → Save
Stylist → Events → EventList → Add Event → EventDetails
Stylist → Scan Outfit → OutfitScanScreen → Processing → Analysis
Stylist → Build Outfit → BuildOutfitScreen → Generation → Recommendation
```

---

## Key Navigation Patterns

1. **GoRouter with StatefulShellRoute** - Bottom nav persists across branches
2. **Nested Routes** - Features like stylist have nested child routes
3. **Route extras** - Vibe, photoPath, onboarding_complete, display_name passed between screens
4. **Replace vs Push** - `context.replaceNamed()` for final steps, `context.pushNamed()` for new flows
5. **Light path handling** - First-time users get specialized home screens based on their choices
6. **State gating** - `UserSession.hasSavedWardrobeItem`, `onboardingData` flags control screen flow