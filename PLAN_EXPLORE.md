# Exploration Plan: Fansivibe Codebase Analysis

## Task
Explore the REAL Fansivibe codebase at `/home/tony/fansivibe_02/fansivibe_v1_backup` and provide comprehensive details on 10 specified components.

## Components to Analyze

### 1. EntryScreen
- File: `lib/features/onboarding/presentation/screens/entry_screen.dart`
- Stateful widget with animation controllers
- Build method: Layout with wordmark, mirror, headline, value statement, CTA buttons, account gate
- Mock data: None (pure UI with animation)
- Key: Uses TickerProviderStateMixin for animations, navigation to vibe select or home

### 2. HomeScreen
- File: `lib/features/home/presentation/home_screen.dart`
- StatelessWidget with onboardingData parameter
- Build method: Conditional rendering based on first-visit status
- Uses mock data from `home_mock_data.dart` and `daily_outfit_mock_data.dart`
- Key: Gating logic with `_isFirstVisit`, `_hasAnalysis`, `UserSession.hasSavedWardrobeItem`

### 3. FirstTimeHomeScreen
- File: `lib/features/home/presentation/first_time_home_screen.dart`
- StatefulWidget with displayName parameter
- Build method: Animated sections with header, hero spread, look editorial, capability grid, tools, AI quote
- Mock data: Static mock values (_mockScore=82, _mockDna='Refined Minimalist', _mockPalette)
- Key: AnimationController with 6 animations, styled content for first-time users

### 4. FirstTimeLightPathHomeScreen
- File: `lib/features/home/presentation/first_time_light_path_home_screen.dart`
- StatefulWidget with vibeName parameter
- Build method: Similar structure to FirstTimeHomeScreen but for light path (no scan)
- Mock data: None (uses onboarding_data.dart StyleVibe and AnalysisResult)
- Key: Distinguishes between vibe directions, analysis pending UI, one-photo unlock flow

### 5. AccountCreationScreen
- File: `lib/features/onboarding/presentation/screens/account_creation_screen.dart`
- StatefulWidget with email, password, name controllers
- Build method: Form with avatar section, animated form, CTA, social login
- Mock data: None (user input driven)
- Key: Creates account with onboarding data extras, social sign-in options

### 6. user_session.dart
- File: `lib/shared/utils/user_session.dart`
- Simple class with static flag `hasSavedWardrobeItem`
- No persistence - in-memory only
- Key: Cross-feature signal for first-visit flow gating

### 7. onboarding_data.dart
- File: `lib/features/onboarding/data/onboarding_data.dart`
- Models: StyleVibe enum, AnalysisResult, PaletteSwatch, AiCapability, OnboardingResult
- Mock data: `allCapabilities` list with 7 capabilities
- Key: Single source of truth for vibe gradients, analysis results, capabilities

### 8. app_router.dart
- File: `lib/app/router/app_router.dart`
- GoRouter configuration with 5 branched navigation shells
- Routes: splash, entry, onboarding, home, discover, stylist, wardrobe, profile
- Key: StatefulShellRoute with indexedStack for bottom navigation structure

### 9. HairstyleResultScreen
- File: `lib/features/hairstyle/presentation/hairstyle_result_screen.dart`
- StatelessWidget with result and service parameters
- Build method: Header, style profile, top recommendation, alternatives, actions
- Mock data: Falls back to `HairstyleAnalysisResult.mock` when result is null
- Key: Service injection for saving, HairstyleCard widgets for recommendations

### 10. GroomingResultScreen
- File: `lib/features/grooming/presentation/grooming_result_screen.dart`
- StatelessWidget with faceShape, beardStyle, beardDensity, beardColor parameters
- Build method: Header, feature profile, score section, beard recommendation, eyewear, why it works, specifications, alternatives, actions
- Mock data: Falls back to `GroomingAnalysisResult.mock` when result is null
- Key: Detailed grooming specs, save look functionality, service injection

### 11. SavedLooksScreen
- File: `lib/features/profile/presentation/saved_looks_screen.dart`
- StatelessWidget using ProfileMockData.savedLooks
- Build method: List of _SavedLookCard using FansiHeroCard
- Mock data: 4 saved looks from profile_mock_data.dart
- Key: Hero card pattern with badge, title, subtitle, footer with items

### 12. ProfileScreen
- File: `lib/features/profile/presentation/profile_screen.dart`
- StatelessWidget using ProfileData.mock
- Build method: Profile hero card, achievement bar, style DNA, saved looks row, menu actions
- Mock data: ProfileData.mock with sample user data (Alex)
- Key: Profile overview with menu-driven navigation

## Key Patterns Observed

1. **Mock Data Usage**: Most screens fall back to mock data when no result/service is provided
2. **Animation Patterns**: AnimatedBuilder with CurvedAnimation is consistent across screens
3. **Card Design**: 65% visual / 35% content card proportion maintained
4. **GoRouter Navigation**: All navigation via GoRouter with named routes
5. **UserSession**: Simple in-memory flags for first-visit gating
6. **Service Injection**: HairstyleResultScreen and GroomingResultScreen accept optional services