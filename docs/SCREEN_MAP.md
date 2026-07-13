# Fansivibe Screen Map

## Main Navigation

MainShell
├── HOME-001 Home
├── DISCOVER-001 Discover
├── STYLIST-001 Stylist
├── WARDROBE-001 Wardrobe
└── PROFILE-001 Profile

## Home

HOME-001 HomeScreen

Actions:

Try This Look → HOME-002
Change Style → OUTFIT-001
Scan My Outfit → SCAN-001

HOME-002 DailyOutfitScreen

Actions:

Wear This
Change Style → OUTFIT-001
Replace Component
Save Outfit
Review Closet → WARDROBE-001

## Discover

DISCOVER-001 DiscoverScreen

Actions:

Select Look → DISCOVER-002

DISCOVER-002 LookDetailsScreen

Contains:

- Match Score
- Recommendation Reasons
- Ensemble Components
- Wardrobe Alternatives

## Stylist

STYLIST-001 StylistScreen

Actions:

Scan Outfit → SCAN-001
Build Outfit → OUTFIT-001
Hairstyle → HAIR-001
Beard / Glasses → GROOM-001
Add Event → EVENT-002

## Outfit Scan

SCAN-001 OutfitScanScreen
→ SCAN-002 OutfitProcessingScreen
→ SCAN-003 OutfitAnalysisScreen

## Outfit Builder

OUTFIT-001 BuildOutfitScreen
→ OUTFIT-002 OutfitGenerationScreen
→ OUTFIT-003 OutfitRecommendationScreen

## Hairstyle

HAIR-001 FaceScanScreen
→ HAIR-002 FaceProcessingScreen
→ HAIR-003 HairstyleResultScreen
→ HAIR-004 HairstyleDetailsScreen

## Grooming

GROOM-001 GroomingInputScreen
→ GROOM-002 GroomingProcessingScreen
→ GROOM-003 GroomingResultScreen
→ GROOM-004 GroomingDetailsScreen

## Wardrobe

WARDROBE-001 WardrobeScreen

Add Item
→ WARDROBE-002 AddWardrobeCategoryScreen
→ WARDROBE-003 AddWardrobeItemScreen

Select Item
→ WARDROBE-004 WardrobeItemDetailsScreen

## Events

EVENT-001 EventListScreen

Add Event
→ EVENT-002 AddEventScreen
→ EVENT-003 EventDetailsScreen

Generate Outfit
→ OUTFIT-001

## Profile

PROFILE-001 ProfileScreen

Possible destinations:

PROFILE-002 PreferencesScreen
PROFILE-003 SavedLooksScreen
PROFILE-004 SubscriptionScreen
PROFILE-005 SupportScreen
PROFILE-006 SettingsScreen

## Rule

Screen IDs exist for documentation only.

Navigation implementation must use the approved application router.

Update this file when a screen or navigation relationship changes.