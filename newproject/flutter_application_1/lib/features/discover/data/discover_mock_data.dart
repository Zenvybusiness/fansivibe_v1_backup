// import 'package:flutter/material.dart';

/// Mock data for Discover look cards.
class DiscoverLookData {
  /// Creates a [DiscoverLookData].
  const DiscoverLookData({
    required this.id,
    required this.imageUrl,
    required this.title,
    required this.description,
    required this.occasion,
    required this.styleTags,
    required this.fitTags,
    required this.matchScore,
    this.isTrending = false,
    this.wardrobeMatchCount = 0,
  });

  /// Unique identifier.
  final String id;

  /// Image URL or asset path.
  final String imageUrl;

  /// Look title.
  final String title;

  /// Look description.
  final String description;

  /// Occasion tag.
  final String occasion;

  /// Style tags.
  final List<String> styleTags;

  /// Fit tags.
  final List<String> fitTags;

  /// Match score percentage (0-100).
  final int matchScore;

  /// Whether this look is trending.
  final bool isTrending;

  /// Number of wardrobe items that match.
  final int wardrobeMatchCount;

  /// Mock data for "For You" personalized looks.
  static const List<DiscoverLookData> forYouMock = [
    DiscoverLookData(
      id: 'fy_1',
      imageUrl: 'assets/images/looks/foryou_1.jpg',
      title: 'Modern Minimalist',
      description:
          'Clean lines meet relaxed sophistication. The unstructured blazer elevates the merino tee while wool trousers keep it grounded.',
      occasion: 'Work • Casual Friday',
      styleTags: ['Minimalist', 'Modern', 'Elevated Casual'],
      fitTags: ['Relaxed Fit', 'Tailored'],
      matchScore: 94,
      wardrobeMatchCount: 3,
    ),
    DiscoverLookData(
      id: 'fy_2',
      imageUrl: 'assets/images/looks/foryou_2.jpg',
      title: 'Urban Explorer',
      description:
          'Technical fabrics meet city style. The water-resistant shell layers over a merino base for unpredictable weather.',
      occasion: 'Weekend • Urban',
      styleTags: ['Techwear', 'Functional', 'Contemporary'],
      fitTags: ['Regular Fit', 'Layered'],
      matchScore: 89,
      wardrobeMatchCount: 2,
    ),
    DiscoverLookData(
      id: 'fy_3',
      imageUrl: 'assets/images/looks/foryou_3.jpg',
      title: 'Evening Refined',
      description:
          'A midnight navy suit with subtle texture. Crisp white shirt and tonal knit tie for understated elegance.',
      occasion: 'Evening Event • Dinner',
      styleTags: ['Classic', 'Refined', 'Timeless'],
      fitTags: ['Slim Fit', 'Structured'],
      matchScore: 91,
      wardrobeMatchCount: 4,
    ),
    DiscoverLookData(
      id: 'fy_4',
      imageUrl: 'assets/images/looks/foryou_4.jpg',
      title: 'Creative Director',
      description:
          'Pattern mixing done right. Houndstooth blazer over a tonal rollneck with wide-leg wool trousers.',
      occasion: 'Creative Work • Gallery Opening',
      styleTags: ['Artistic', 'Bold', 'Pattern Mix'],
      fitTags: ['Relaxed Fit', 'Wide Leg'],
      matchScore: 87,
      isTrending: true,
      wardrobeMatchCount: 2,
    ),
    DiscoverLookData(
      id: 'fy_5',
      imageUrl: 'assets/images/looks/foryou_5.jpg',
      title: 'Weekend Casual',
      description:
          'Heavyweight cotton chore jacket over a striped tee. Selvedge denim and leather boots complete the look.',
      occasion: 'Weekend • Casual',
      styleTags: ['Rugged', 'Heritage', 'Effortless'],
      fitTags: ['Regular Fit', 'Straight Leg'],
      matchScore: 85,
      wardrobeMatchCount: 3,
    ),
    DiscoverLookData(
      id: 'fy_6',
      imageUrl: 'assets/images/looks/foryou_6.jpg',
      title: 'Summer Soirée',
      description:
          'Linen-blend suit in warm sand tone. Open-collar shirt and loafers for breezy elegance.',
      occasion: 'Summer Party • Daytime',
      styleTags: ['Resort', 'Relaxed Luxury', 'Breathable'],
      fitTags: ['Relaxed Fit', 'Unstructured'],
      matchScore: 88,
      wardrobeMatchCount: 1,
    ),
  ];

  /// Mock data for "Trending" looks.
  static const List<DiscoverLookData> trendingMock = [
    DiscoverLookData(
      id: 'tr_1',
      imageUrl: 'assets/images/looks/trending_1.jpg',
      title: 'Quiet Luxury',
      description:
          'Monochromatic camel ensemble. Cashmere coat, silk blend trousers, tonal knit. Whisper-quiet confidence.',
      occasion: 'Work • Elevated Daily',
      styleTags: ['Quiet Luxury', 'Monochrome', 'Investment Pieces'],
      fitTags: ['Tailored', 'Drapey'],
      matchScore: 92,
      isTrending: true,
      wardrobeMatchCount: 1,
    ),
    DiscoverLookData(
      id: 'tr_2',
      imageUrl: 'assets/images/looks/trending_2.jpg',
      title: 'New Prep',
      description:
          'Navy blazer, oxford shirt, chinos, loafers. The classics updated with relaxed proportions.',
      occasion: 'Weekend • Smart Casual',
      styleTags: ['New Prep', 'Classic Revival', 'Polished'],
      fitTags: ['Relaxed Fit', 'Straight Leg'],
      matchScore: 86,
      isTrending: true,
      wardrobeMatchCount: 4,
    ),
    DiscoverLookData(
      id: 'tr_3',
      imageUrl: 'assets/images/looks/trending_3.jpg',
      title: 'Earth Tones',
      description:
          'Olive field jacket, cream knit, rust trousers. Nature\'s palette in perfect harmony.',
      occasion: 'Outdoor • Autumn',
      styleTags: ['Earth Tones', 'Nature-Inspired', 'Textural'],
      fitTags: ['Oversized', 'Relaxed Fit'],
      matchScore: 83,
      isTrending: true,
      wardrobeMatchCount: 2,
    ),
    DiscoverLookData(
      id: 'tr_4',
      imageUrl: 'assets/images/looks/trending_4.jpg',
      title: 'Double Denim Done Right',
      description:
          'Indigo jacket over black jeans. Contrast wash makes it intentional, not accidental.',
      occasion: 'Casual • Creative',
      styleTags: ['Denim on Denim', 'Edgy', 'High Contrast'],
      fitTags: ['Regular Fit', 'Slim Straight'],
      matchScore: 81,
      isTrending: true,
      wardrobeMatchCount: 3,
    ),
    DiscoverLookData(
      id: 'tr_5',
      imageUrl: 'assets/images/looks/trending_5.jpg',
      title: 'Statement Outerwear',
      description:
          'Checked wool coat steals the show. All-black underneath lets the pattern breathe.',
      occasion: 'Winter • Evening',
      styleTags: ['Statement Piece', 'Pattern Play', 'Dramatic'],
      fitTags: ['Oversized', 'Layered'],
      matchScore: 79,
      isTrending: true,
      wardrobeMatchCount: 1,
    ),
    DiscoverLookData(
      id: 'tr_6',
      imageUrl: 'assets/images/looks/trending_6.jpg',
      title: 'Athleisure Elevated',
      description:
          'Technical wool joggers, merino hoodie, minimal sneakers. Gym-to-gallery ready.',
      occasion: 'Travel • Daily',
      styleTags: ['Athleisure', 'Technical', 'Minimal'],
      fitTags: ['Tapered', 'Athletic Fit'],
      matchScore: 84,
      isTrending: true,
      wardrobeMatchCount: 2,
    ),
  ];
}

/// Filter option data model.
class FilterOption {
  /// Creates a [FilterOption].
  const FilterOption({
    required this.id,
    required this.label,
    required this.icon,
    this.isSelected = false,
  });

  /// Unique identifier.
  final String id;

  /// Display label.
  final String label;

  /// Icon data.
  final IconData icon;

  /// Whether this filter is currently selected.
  final bool isSelected;

  /// Copy with new values.
  FilterOption copyWith({
    String? id,
    String? label,
    IconData? icon,
    bool? isSelected,
  }) {
    return FilterOption(
      id: id ?? this.id,
      label: label ?? this.label,
      icon: icon ?? this.icon,
      isSelected: isSelected ?? this.isSelected,
    );
  }
}

/// Occasion filter options.
class OccasionFilters {
  /// All occasion filter options.
  static const List<FilterOption> options = [
    FilterOption(
      id: 'all',
      label: 'All Occasions',
      icon: Icons.event_outlined,
    ),
    FilterOption(
      id: 'work',
      label: 'Work',
      icon: Icons.work_outline_rounded,
    ),
    FilterOption(
      id: 'casual',
      label: 'Casual',
      icon: Icons.weekend_rounded,
    ),
    FilterOption(
      id: 'evening',
      label: 'Evening',
      icon: Icons.nightlife_outlined,
    ),
    FilterOption(
      id: 'weekend',
      label: 'Weekend',
      icon: Icons.beach_access_outlined,
    ),
    FilterOption(
      id: 'event',
      label: 'Special Event',
      icon: Icons.celebration_outlined,
    ),
    FilterOption(
      id: 'travel',
      label: 'Travel',
      icon: Icons.flight_takeoff_rounded,
    ),
  ];
}

/// Style filter options.
class StyleFilters {
  /// All style filter options.
  static const List<FilterOption> options = [
    FilterOption(
      id: 'all',
      label: 'All Styles',
      icon: Icons.style_outlined,
    ),
    FilterOption(
      id: 'minimalist',
      label: 'Minimalist',
      icon: Icons.remove_rounded,
    ),
    FilterOption(
      id: 'classic',
      label: 'Classic',
      icon: Icons.diamond_outlined,
    ),
    FilterOption(
      id: 'contemporary',
      label: 'Contemporary',
      icon: Icons.auto_awesome_outlined,
    ),
    FilterOption(
      id: 'rugged',
      label: 'Rugged',
      icon: Icons.terrain_outlined,
    ),
    FilterOption(
      id: 'artistic',
      label: 'Artistic',
      icon: Icons.palette_outlined,
    ),
    FilterOption(
      id: 'techwear',
      label: 'Techwear',
      icon: Icons.memory_outlined,
    ),
    FilterOption(
      id: 'preppy',
      label: 'Preppy',
      icon: Icons.school_outlined,
    ),
    FilterOption(
      id: 'bohemian',
      label: 'Bohemian',
      icon: Icons.spa_outlined,
    ),
  ];
}

/// Fit filter options.
class FitFilters {
  /// All fit filter options.
  static const List<FilterOption> options = [
    FilterOption(
      id: 'all',
      label: 'All Fits',
      icon: Icons.straighten_outlined,
    ),
    FilterOption(
      id: 'slim',
      label: 'Slim Fit',
      icon: Icons.person_outline_rounded,
    ),
    FilterOption(
      id: 'regular',
      label: 'Regular Fit',
      icon: Icons.person_rounded,
    ),
    FilterOption(
      id: 'relaxed',
      label: 'Relaxed Fit',
      icon: Icons.accessibility_new_rounded,
    ),
    FilterOption(
      id: 'oversized',
      label: 'Oversized',
      icon: Icons.crop_free_rounded,
    ),
    FilterOption(
      id: 'tailored',
      label: 'Tailored',
      icon: Icons.content_cut_rounded,
    ),
    FilterOption(
      id: 'athletic',
      label: 'Athletic Fit',
      icon: Icons.fitness_center_rounded,
    ),
  ];
}

/// Discover tab types.
enum DiscoverTab {
  /// For You personalized tab.
  forYou,

  /// Trending tab.
  trending,
}

/// Discover tab data.
class DiscoverTabData {
  /// Creates a [DiscoverTabData].
  const DiscoverTabData({
    required this.tab,
    required this.label,
    required this.icon,
  });

  /// Tab enum value.
  final DiscoverTab tab;

  /// Display label.
  final String label;

  /// Tab icon.
  final IconData icon;

  /// All tabs.
  static const List<DiscoverTabData> all = [
    DiscoverTabData(
      tab: DiscoverTab.forYou,
      label: 'For You',
      icon: Icons.person_outline_rounded,
    ),
    DiscoverTabData(
      tab: DiscoverTab.trending,
      label: 'Trending',
      icon: Icons.trending_up_rounded,
    ),
  ];
}