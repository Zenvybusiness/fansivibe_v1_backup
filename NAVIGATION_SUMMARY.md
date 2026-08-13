# Fansivibe Navigation Analysis - Complete

## Key Findings

### Route Configuration
- 42 GoRoute definitions in app_router.dart
- 5 main branches under StatefulShellRoute.indexedStack
- Bottom Navigation Bar: Home, Discover, Stylist, Wardrobe, Profile
- Initial route: /entry (after splash)

### Onboarding Flow (8 screens)
1. Splash (3s) → Entry
2. Entry: CTA "Analyze My Style" or "Explore Without Scanning" + "Sign In"
3. VibeSelect: 6 style choices (Minimalist, Bold, Classic, Trendy, Natural, Edgy)
4. CameraPermission: Allow camera / Gallery / Skip
5. PhotoCapture: Take photo / Retake / Skip
6. AiAnalysis: AI processing animation (3s)
7. YourAnalysis: Style score, palette, insights
8. AccountCreation: Email/password/social sign-in

### Authentication
- Onboarding-first (no traditional login)
- Account creation → /home with onboarding_complete extra
- "Save Locally" bypasses full account

### Home Screen States (3 conditions)
- onboardingData != null + hasAnalysis + hasSavedWardrobeItem → FirstTimeLightPathHomeScreen
- onboardingData != null + hasAnalysis → FirstTimeHomeScreen
- onboardingData != null → FirstTimeLightPathHomeScreen
- Otherwise → Regular HomeScreen

### Vertical Slices
- **Hairstyle**: 5 screens (FaceScan → Processing → Result → Details)
- **Grooming**: 4 screens (Input → Processing → Result → Details)
- **Out Scan**: 3 screens (Scan → Processing → Analysis)
- **Discover**: Filtered look browsing + LookDetails
- **Wardrobe**: Item management + details

### State Management
- UserSession: hasSavedWardrobeItem flag (no persistence)
- LearningService: Singleton, wardrobe + saved looks
- Hairstyle/Grooming Services: AI analysis + save
- OnboardingData: vibe, analysis, displayName flags

### Design System
- FansiHeroCard: 65% image / 35% content (flex ratio enforced)
- FansiInsightCard: 20% visual / 80% content
- FansiButton: 3 variants (primary/gold, secondary, tertiary)
- Dark theme with custom colors/typography/spacing/radius

### Navigation Patterns
- GoRouter with nested StatefulShellRoute
- Route extras: vibe, photoPath, onboarding_complete, display_name
- context.pushNamed() for new flows, context.replaceNamed() for final steps
- Light path for first-time users based on choices
- Bottom nav persists across all branches
- State gating via onboardingData flags + UserSession