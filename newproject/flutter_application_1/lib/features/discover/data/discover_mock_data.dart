import 'package:flutter/material.dart';

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
    this.matchScoreDetails,
    this.recommendationReasons,
    this.ensembleComponents,
    this.wardrobeAlternatives,
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

  /// Detailed match score breakdown by category.
  final MatchScoreDetails? matchScoreDetails;

  /// Personalized recommendation reasons.
  final List<RecommendationReason>? recommendationReasons;

  /// Ensemble components (outfit pieces).
  final List<EnsembleComponent>? ensembleComponents;

  /// Wardrobe alternatives for each component.
  final List<WardrobeAlternative>? wardrobeAlternatives;

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
      matchScoreDetails: MatchScoreDetails(
        overall: 94,
        fit: 92,
        colorHarmony: 95,
        occasion: 96,
        creativity: 88,
      ),
      recommendationReasons: [
        RecommendationReason(
          title: 'Matches your Style DNA',
          description:
              'Your Style DNA prefers minimalist, modern aesthetics with elevated casual pieces.',
          icon: Icons.auto_awesome_rounded,
        ),
        RecommendationReason(
          title: 'Perfect for your upcoming events',
          description:
              'You have 3 Casual Friday events this month where this look would excel.',
          icon: Icons.event_outlined,
        ),
        RecommendationReason(
          title: 'Wardrobe synergy',
          description:
              'You own 3 items that pair perfectly with this ensemble (blazer, trousers, boots).',
          icon: Icons.checkroom_rounded,
        ),
      ],
      ensembleComponents: [
        EnsembleComponent(
          category: 'Outerwear',
          name: 'Charcoal Unstructured Blazer',
          color: 'Charcoal',
          material: 'Wool blend',
          fit: 'Relaxed Fit',
          imageUrl: 'assets/images/items/blazer_charcoal.jpg',
          isOwned: true,
        ),
        EnsembleComponent(
          category: 'Top',
          name: 'Merino Wool Crewneck Tee',
          color: 'Oatmeal',
          material: 'Merino wool',
          fit: 'Regular Fit',
          imageUrl: 'assets/images/items/tee_oatmeal.jpg',
          isOwned: true,
        ),
        EnsembleComponent(
          category: 'Bottoms',
          name: 'Tapered Wool Trousers',
          color: 'Charcoal',
          material: 'Wool',
          fit: 'Tailored',
          imageUrl: 'assets/images/items/trousers_charcoal.jpg',
          isOwned: false,
        ),
        EnsembleComponent(
          category: 'Footwear',
          name: 'Leather Chelsea Boots',
          color: 'Black',
          material: 'Full-grain leather',
          fit: 'Standard',
          imageUrl: 'assets/images/items/boots_black.jpg',
          isOwned: true,
        ),
      ],
      wardrobeAlternatives: [
        WardrobeAlternative(
          componentCategory: 'Outerwear',
          alternatives: [
            WardrobeItem(
              id: 'alt_1',
              name: 'Navy Unstructured Blazer',
              color: 'Navy',
              imageUrl: 'assets/images/items/blazer_navy.jpg',
              isOwned: true,
              matchScore: 88,
            ),
            WardrobeItem(
              id: 'alt_2',
              name: 'Grey Hopsack Blazer',
              color: 'Grey',
              imageUrl: 'assets/images/items/blazer_grey.jpg',
              isOwned: false,
              matchScore: 91,
            ),
          ],
        ),
        WardrobeAlternative(
          componentCategory: 'Bottoms',
          alternatives: [
            WardrobeItem(
              id: 'alt_3',
              name: 'Charcoal Flannel Trousers',
              color: 'Charcoal',
              imageUrl: 'assets/images/items/trousers_flannel.jpg',
              isOwned: true,
              matchScore: 93,
            ),
          ],
        ),
      ],
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
      matchScoreDetails: MatchScoreDetails(
        overall: 89,
        fit: 87,
        colorHarmony: 90,
        occasion: 92,
        creativity: 85,
      ),
      recommendationReasons: [
        RecommendationReason(
          title: 'Matches your Style DNA',
          description:
              'Your Style DNA shows preference for technical, functional pieces with contemporary styling.',
          icon: Icons.auto_awesome_rounded,
        ),
        RecommendationReason(
          title: 'Weather-appropriate',
          description:
              'Rain forecast for your area this week - water-resistant shell is practical.',
          icon: Icons.water_drop_rounded,
        ),
        RecommendationReason(
          title: 'Wardrobe synergy',
          description:
              'You own 2 items that work with this look (merino base, technical sneakers).',
          icon: Icons.checkroom_rounded,
        ),
      ],
      ensembleComponents: [
        EnsembleComponent(
          category: 'Outerwear',
          name: 'Water-Resistant Technical Shell',
          color: 'Slate Grey',
          material: 'Gore-Tex Pro',
          fit: 'Regular Fit',
          imageUrl: 'assets/images/items/shell_slate.jpg',
          isOwned: false,
        ),
        EnsembleComponent(
          category: 'Top',
          name: 'Merino Base Layer',
          color: 'Black',
          material: 'Merino wool',
          fit: 'Slim Fit',
          imageUrl: 'assets/images/items/base_black.jpg',
          isOwned: true,
        ),
        EnsembleComponent(
          category: 'Bottoms',
          name: 'Technical Cargo Trousers',
          color: 'Slate Grey',
          material: 'Nylon blend',
          fit: 'Regular Fit',
          imageUrl: 'assets/images/items/cargo_slate.jpg',
          isOwned: false,
        ),
        EnsembleComponent(
          category: 'Footwear',
          name: 'Technical Running Sneakers',
          color: 'Black',
          material: 'Mesh/Synthetic',
          fit: 'Standard',
          imageUrl: 'assets/images/items/sneakers_tech.jpg',
          isOwned: true,
        ),
      ],
      wardrobeAlternatives: [
        WardrobeAlternative(
          componentCategory: 'Outerwear',
          alternatives: [
            WardrobeItem(
              id: 'alt_4',
              name: 'Olive Field Jacket',
              color: 'Olive',
              imageUrl: 'assets/images/items/jacket_olive.jpg',
              isOwned: true,
              matchScore: 85,
            ),
          ],
        ),
      ],
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
      matchScoreDetails: MatchScoreDetails(
        overall: 91,
        fit: 94,
        colorHarmony: 93,
        occasion: 95,
        creativity: 78,
      ),
      recommendationReasons: [
        RecommendationReason(
          title: 'Perfect for upcoming dinner event',
          description:
              'Matches your "Evening Event" calendar entry for Friday.',
          icon: Icons.calendar_today_rounded,
        ),
        RecommendationReason(
          title: 'Excellent wardrobe match',
          description:
              'You own 4 items that complete this look (suit, shirt, tie, shoes).',
          icon: Icons.checkroom_rounded,
        ),
        RecommendationReason(
          title: 'Classic style alignment',
          description:
              'Your Style DNA shows strong preference for classic, timeless pieces.',
          icon: Icons.auto_awesome_rounded,
        ),
      ],
      ensembleComponents: [
        EnsembleComponent(
          category: 'Suit',
          name: 'Midnight Navy Wool Suit',
          color: 'Midnight Navy',
          material: 'Super 120s Wool',
          fit: 'Slim Fit',
          imageUrl: 'assets/images/items/suit_navy.jpg',
          isOwned: true,
        ),
        EnsembleComponent(
          category: 'Shirt',
          name: 'Crisp White Poplin Shirt',
          color: 'White',
          material: 'Cotton Poplin',
          fit: 'Regular Fit',
          imageUrl: 'assets/images/items/shirt_white.jpg',
          isOwned: true,
        ),
        EnsembleComponent(
          category: 'Tie',
          name: 'Navy Knit Tie',
          color: 'Navy',
          material: 'Silk Knit',
          fit: 'Standard',
          imageUrl: 'assets/images/items/tie_navy.jpg',
          isOwned: true,
        ),
        EnsembleComponent(
          category: 'Footwear',
          name: 'Black Oxford Shoes',
          color: 'Black',
          material: 'Calfskin Leather',
          fit: 'Standard',
          imageUrl: 'assets/images/items/oxfords_black.jpg',
          isOwned: true,
        ),
      ],
      wardrobeAlternatives: [
        WardrobeAlternative(
          componentCategory: 'Suit',
          alternatives: [
            WardrobeItem(
              id: 'alt_5',
              name: 'Charcoal Wool Suit',
              color: 'Charcoal',
              imageUrl: 'assets/images/items/suit_charcoal.jpg',
              isOwned: true,
              matchScore: 89,
            ),
            WardrobeItem(
              id: 'alt_6',
              name: 'Black Tuxedo',
              color: 'Black',
              imageUrl: 'assets/images/items/tuxedo_black.jpg',
              isOwned: false,
              matchScore: 94,
            ),
          ],
        ),
      ],
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
      matchScoreDetails: MatchScoreDetails(
        overall: 87,
        fit: 85,
        colorHarmony: 88,
        occasion: 89,
        creativity: 95,
      ),
      recommendationReasons: [
        RecommendationReason(
          title: 'Trending in your creative circle',
          description:
              'Pattern mixing is trending among creative professionals this season.',
          icon: Icons.trending_up_rounded,
        ),
        RecommendationReason(
          title: 'Matches your artistic Style DNA',
          description:
              'Your Style DNA shows affinity for bold, artistic expression.',
          icon: Icons.auto_awesome_rounded,
        ),
        RecommendationReason(
          title: 'Partial wardrobe match',
          description: 'You own the rollneck and boots (2 items).',
          icon: Icons.checkroom_rounded,
        ),
      ],
      ensembleComponents: [
        EnsembleComponent(
          category: 'Outerwear',
          name: 'Houndstooth Wool Blazer',
          color: 'Brown/Cream',
          material: 'Wool',
          fit: 'Relaxed Fit',
          imageUrl: 'assets/images/items/blazer_houndstooth.jpg',
          isOwned: false,
        ),
        EnsembleComponent(
          category: 'Top',
          name: 'Cream Merino Rollneck',
          color: 'Cream',
          material: 'Merino Wool',
          fit: 'Slim Fit',
          imageUrl: 'assets/images/items/rollneck_cream.jpg',
          isOwned: true,
        ),
        EnsembleComponent(
          category: 'Bottoms',
          name: 'Wide-Leg Wool Trousers',
          color: 'Brown',
          material: 'Wool',
          fit: 'Wide Leg',
          imageUrl: 'assets/images/items/trousers_wide_brown.jpg',
          isOwned: false,
        ),
        EnsembleComponent(
          category: 'Footwear',
          name: 'Brown Leather Loafers',
          color: 'Brown',
          material: 'Leather',
          fit: 'Standard',
          imageUrl: 'assets/images/items/loafers_brown.jpg',
          isOwned: true,
        ),
      ],
      wardrobeAlternatives: [
        WardrobeAlternative(
          componentCategory: 'Outerwear',
          alternatives: [
            WardrobeItem(
              id: 'alt_7',
              name: 'Glen Check Blazer',
              color: 'Grey/Black',
              imageUrl: 'assets/images/items/blazer_glencheck.jpg',
              isOwned: true,
              matchScore: 86,
            ),
            WardrobeItem(
              id: 'alt_8',
              name: 'Prince of Wales Blazer',
              color: 'Navy/Grey',
              imageUrl: 'assets/images/items/blazer_pow.jpg',
              isOwned: false,
              matchScore: 90,
            ),
          ],
        ),
      ],
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
      matchScoreDetails: MatchScoreDetails(
        overall: 85,
        fit: 88,
        colorHarmony: 82,
        occasion: 90,
        creativity: 75,
      ),
      recommendationReasons: [
        RecommendationReason(
          title: 'Weekend staple in your rotation',
          description:
              'Heritage style aligns with your casual weekend preferences.',
          icon: Icons.weekend_rounded,
        ),
        RecommendationReason(
          title: 'Strong wardrobe match',
          description: 'You own 3 items (chore jacket, denim, boots).',
          icon: Icons.checkroom_rounded,
        ),
        RecommendationReason(
          title: 'Seasonal appropriateness',
          description: 'Heavyweight cotton perfect for current temperatures.',
          icon: Icons.thermostat_rounded,
        ),
      ],
      ensembleComponents: [
        EnsembleComponent(
          category: 'Outerwear',
          name: 'Heavyweight Cotton Chore Jacket',
          color: 'Olive',
          material: 'Cotton Canvas',
          fit: 'Regular Fit',
          imageUrl: 'assets/images/items/jacket_olive_canvas.jpg',
          isOwned: true,
        ),
        EnsembleComponent(
          category: 'Top',
          name: 'Striped Cotton Tee',
          color: 'White/Navy',
          material: 'Cotton',
          fit: 'Regular Fit',
          imageUrl: 'assets/images/items/tee_striped.jpg',
          isOwned: false,
        ),
        EnsembleComponent(
          category: 'Bottoms',
          name: 'Selvedge Denim Jeans',
          color: 'Indigo',
          material: 'Selvedge Denim',
          fit: 'Straight Leg',
          imageUrl: 'assets/images/items/jeans_indigo.jpg',
          isOwned: true,
        ),
        EnsembleComponent(
          category: 'Footwear',
          name: 'Leather Service Boots',
          color: 'Brown',
          material: 'Full-grain Leather',
          fit: 'Standard',
          imageUrl: 'assets/images/items/boots_brown.jpg',
          isOwned: true,
        ),
      ],
      wardrobeAlternatives: [
        WardrobeAlternative(
          componentCategory: 'Top',
          alternatives: [
            WardrobeItem(
              id: 'alt_9',
              name: 'Solid White Tee',
              color: 'White',
              imageUrl: 'assets/images/items/tee_white.jpg',
              isOwned: true,
              matchScore: 88,
            ),
            WardrobeItem(
              id: 'alt_10',
              name: 'Grey Henley',
              color: 'Grey',
              imageUrl: 'assets/images/items/henley_grey.jpg',
              isOwned: true,
              matchScore: 85,
            ),
          ],
        ),
      ],
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
      matchScoreDetails: MatchScoreDetails(
        overall: 88,
        fit: 86,
        colorHarmony: 92,
        occasion: 91,
        creativity: 82,
      ),
      recommendationReasons: [
        RecommendationReason(
          title: 'Upcoming summer event match',
          description:
              'Perfect for your "Summer Party" calendar event next month.',
          icon: Icons.event_outlined,
        ),
        RecommendationReason(
          title: 'Color harmony with your palette',
          description: 'Sand tone complements your warm skin tone beautifully.',
          icon: Icons.palette_outlined,
        ),
        RecommendationReason(
          title: 'Breathable fabric for warm weather',
          description: 'Linen blend keeps you cool at daytime outdoor events.',
          icon: Icons.wb_sunny_outlined,
        ),
      ],
      ensembleComponents: [
        EnsembleComponent(
          category: 'Suit',
          name: 'Sand Linen-Blend Suit',
          color: 'Warm Sand',
          material: 'Linen/Wool Blend',
          fit: 'Relaxed Fit',
          imageUrl: 'assets/images/items/suit_sand.jpg',
          isOwned: false,
        ),
        EnsembleComponent(
          category: 'Shirt',
          name: 'White Linen Shirt',
          color: 'White',
          material: 'Linen',
          fit: 'Relaxed Fit',
          imageUrl: 'assets/images/items/shirt_linen_white.jpg',
          isOwned: true,
        ),
        EnsembleComponent(
          category: 'Footwear',
          name: 'Tan Suede Loafers',
          color: 'Tan',
          material: 'Suede',
          fit: 'Standard',
          imageUrl: 'assets/images/items/loafers_tan.jpg',
          isOwned: false,
        ),
      ],
      wardrobeAlternatives: [
        WardrobeAlternative(
          componentCategory: 'Suit',
          alternatives: [
            WardrobeItem(
              id: 'alt_11',
              name: 'Light Grey Linen Suit',
              color: 'Light Grey',
              imageUrl: 'assets/images/items/suit_lightgrey.jpg',
              isOwned: false,
              matchScore: 85,
            ),
            WardrobeItem(
              id: 'alt_12',
              name: 'Cream Cotton Suit',
              color: 'Cream',
              imageUrl: 'assets/images/items/suit_cream.jpg',
              isOwned: true,
              matchScore: 90,
            ),
          ],
        ),
      ],
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
    FilterOption(id: 'all', label: 'All Occasions', icon: Icons.event_outlined),
    FilterOption(id: 'work', label: 'Work', icon: Icons.work_outline_rounded),
    FilterOption(id: 'casual', label: 'Casual', icon: Icons.weekend_rounded),
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
    FilterOption(id: 'all', label: 'All Styles', icon: Icons.style_outlined),
    FilterOption(
      id: 'minimalist',
      label: 'Minimalist',
      icon: Icons.remove_rounded,
    ),
    FilterOption(id: 'classic', label: 'Classic', icon: Icons.diamond_outlined),
    FilterOption(
      id: 'contemporary',
      label: 'Contemporary',
      icon: Icons.auto_awesome_outlined,
    ),
    FilterOption(id: 'rugged', label: 'Rugged', icon: Icons.terrain_outlined),
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
    FilterOption(id: 'preppy', label: 'Preppy', icon: Icons.school_outlined),
    FilterOption(id: 'bohemian', label: 'Bohemian', icon: Icons.spa_outlined),
  ];
}

/// Fit filter options.
class FitFilters {
  /// All fit filter options.
  static const List<FilterOption> options = [
    FilterOption(id: 'all', label: 'All Fits', icon: Icons.straighten_outlined),
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

/// Detailed match score breakdown.
class MatchScoreDetails {
  const MatchScoreDetails({
    required this.overall,
    required this.fit,
    required this.colorHarmony,
    required this.occasion,
    required this.creativity,
  });

  final int overall;
  final int fit;
  final int colorHarmony;
  final int occasion;
  final int creativity;
}

/// A recommendation reason.
class RecommendationReason {
  const RecommendationReason({
    required this.title,
    required this.description,
    required this.icon,
  });

  final String title;
  final String description;
  final IconData icon;
}

/// A component of an outfit ensemble.
class EnsembleComponent {
  const EnsembleComponent({
    required this.category,
    required this.name,
    required this.color,
    required this.material,
    required this.fit,
    required this.imageUrl,
    required this.isOwned,
  });

  final String category;
  final String name;
  final String color;
  final String material;
  final String fit;
  final String imageUrl;
  final bool isOwned;
}

/// Alternatives for a component category.
class WardrobeAlternative {
  const WardrobeAlternative({
    required this.componentCategory,
    required this.alternatives,
  });

  final String componentCategory;
  final List<WardrobeItem> alternatives;
}

/// A wardrobe item that can substitute.
class WardrobeItem {
  const WardrobeItem({
    required this.id,
    required this.name,
    required this.color,
    required this.imageUrl,
    required this.isOwned,
    required this.matchScore,
  });

  final String id;
  final String name;
  final String color;
  final String imageUrl;
  final bool isOwned;
  final int matchScore;
}
