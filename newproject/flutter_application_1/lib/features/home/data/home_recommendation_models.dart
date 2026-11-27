/// Source classification for every Home recommendation item.
enum HomeRecommendationSourceType {
  /// Derived from the user's Digital Wardrobe via `GET /v1/looks/today`.
  wardrobeDerived('wardrobe_derived'),

  /// Personalized catalog recommendations via `GET /v1/discovery/for-you`.
  backendPersonalized('backend_personalized'),

  /// Curated catalog looks via `GET /v1/looks`.
  backendCurated('backend_curated'),

  /// Trend intelligence via `GET /v1/trending`.
  backendTrending('backend_trending'),

  /// Static bundled editorial fallback (never presented as personalized AI).
  editorialCurated('editorial_curated'),

  /// Static initial/demo look for first-time or guest onboarding.
  demoFixture('demo_fixture');

  const HomeRecommendationSourceType(this.code);
  final String code;
}

/// Transparent provenance attached to every Home recommendation.
class HomeRecommendationProvenance {
  const HomeRecommendationProvenance({
    required this.recommendationId,
    required this.sourceType,
    this.associatedPreferences = const [],
    this.selectedVibe,
    this.occasion,
    this.imageRef,
    required this.contentKind,
    required this.isPersonalized,
    this.isStale = false,
  });

  final String recommendationId;
  final HomeRecommendationSourceType sourceType;
  final List<String> associatedPreferences;
  final String? selectedVibe;
  final String? occasion;
  final String? imageRef;

  /// One of: `'personalized'`, `'curated'`, `'trending'`, `'demo'`.
  final String contentKind;
  final bool isPersonalized;
  final bool isStale;

  String get badgeLabel {
    switch (sourceType) {
      case HomeRecommendationSourceType.wardrobeDerived:
        if (selectedVibe != null && selectedVibe!.isNotEmpty) {
          return 'PERSONALIZED • ${selectedVibe!.toUpperCase()}';
        }
        return 'PERSONALIZED • WARDROBE';
      case HomeRecommendationSourceType.backendPersonalized:
        return 'PERSONALIZED • FOR YOU';
      case HomeRecommendationSourceType.backendCurated:
        return 'CURATED • CATALOG';
      case HomeRecommendationSourceType.backendTrending:
        return isStale ? 'TRENDING • CACHED' : 'TRENDING • LIVE';
      case HomeRecommendationSourceType.editorialCurated:
        if (selectedVibe != null && selectedVibe!.isNotEmpty) {
          return 'CURATED • ${selectedVibe!.toUpperCase()}';
        }
        return 'EDITORIAL • FALLBACK';
      case HomeRecommendationSourceType.demoFixture:
        return 'DEMO • INITIAL LOOK';
    }
  }
}

/// One item in the Home Curated Looks / For You section with full provenance.
class HomeCuratedLookItem {
  const HomeCuratedLookItem({
    required this.id,
    required this.title,
    required this.category,
    required this.imageRef,
    required this.height,
    required this.provenance,
  });

  final String id;
  final String title;
  final String category;
  final String imageRef;
  final double height;
  final HomeRecommendationProvenance provenance;
}

/// One item in the Home Trending Now section with full provenance.
class HomeTrendingItem {
  const HomeTrendingItem({
    required this.id,
    required this.title,
    required this.subtitle,
    required this.imageRef,
    required this.provenance,
  });

  final String id;
  final String title;
  final String subtitle;
  final String imageRef;
  final HomeRecommendationProvenance provenance;
}

