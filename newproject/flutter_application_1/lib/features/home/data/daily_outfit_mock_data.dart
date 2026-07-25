class AiInsightData {
  const AiInsightData({
    required this.title,
    required this.description,
    required this.iconName,
  });

  final String title;
  final String description;
  final String iconName;
}

class AlternativeLookData {
  const AlternativeLookData({
    required this.id,
    required this.name,
    required this.matchScore,
    required this.styleName,
  });

  final String id;
  final String name;
  final int matchScore;
  final String styleName;
}

class DailyOutfitData {
  const DailyOutfitData({
    required this.title,
    required this.occasion,
    required this.weather,
    required this.description,
    required this.matchScore,
    required this.styleScore,
    required this.components,
    required this.reasons,
    required this.styleDna,
    required this.wardrobeContext,
    this.aiSelectionReason,
    this.confidenceBoost,
    this.aiInsights = const [],
    this.alternatives = const [],
    this.dailyStyleTip,
  });

  final String title;
  final String occasion;
  final String weather;
  final String description;
  final int matchScore;
  final int styleScore;
  final List<DailyOutfitComponent> components;
  final List<String> reasons;
  final StyleDnaContext styleDna;
  final WardrobeContext wardrobeContext;
  final String? aiSelectionReason;
  final String? confidenceBoost;
  final List<AiInsightData> aiInsights;
  final List<AlternativeLookData> alternatives;
  final String? dailyStyleTip;

  static const DailyOutfitData mock = DailyOutfitData(
    title: 'Modern Minimalist',
    occasion: 'Casual Friday',
    weather: '68\u00B0F \u2022 Partly Cloudy',
    description:
        'Clean lines meet relaxed sophistication. The unstructured blazer '
        'elevates the merino tee while the wool trousers keep it grounded.',
    matchScore: 91,
    styleScore: 87,
    components: [
      DailyOutfitComponent(
        id: 'comp_1',
        name: 'Charcoal Unstructured Blazer',
        category: 'Outerwear',
        color: 'Charcoal',
        material: 'Wool Blend',
        colorHex: '#36454F',
      ),
      DailyOutfitComponent(
        id: 'comp_2',
        name: 'Merino Wool Crewneck',
        category: 'Tops',
        color: 'Off-White',
        material: 'Merino Wool',
        colorHex: '#FAF9F6',
      ),
      DailyOutfitComponent(
        id: 'comp_3',
        name: 'Tapered Wool Trousers',
        category: 'Bottoms',
        color: 'Charcoal',
        material: 'Wool',
        colorHex: '#36454F',
      ),
      DailyOutfitComponent(
        id: 'comp_4',
        name: 'Leather Chelsea Boots',
        category: 'Footwear',
        color: 'Black',
        material: 'Leather',
        colorHex: '#1A1A1A',
      ),
      DailyOutfitComponent(
        id: 'comp_5',
        name: 'Minimalist Leather Belt',
        category: 'Accessories',
        color: 'Black',
        material: 'Leather',
        colorHex: '#1A1A1A',
      ),
    ],
    reasons: [
      'The monochrome palette creates a cohesive, elongated silhouette that '
          'projects confidence and attention to detail',
      'Unstructured blazer provides structure without stiffness, perfect for '
          'the casual office dress code',
      'Merino wool crewneck layers seamlessly, adding texture without bulk '
          'under the blazer',
      'Chelsea boots bridge the gap between formal and casual, making this '
          'look versatile from day to evening',
    ],
    styleDna: StyleDnaContext(
      styleType: 'Modern Minimalist',
      bodyType: 'Athletic',
      skinTone: 'Medium',
      faceShape: 'Oval',
    ),
    wardrobeContext: WardrobeContext(
      totalItems: 42,
      matchingItems: 8,
      insight:
          'You own 6 of these pieces. Adding a charcoal unstructured blazer '
          'would unlock 4 new outfit combinations.',
    ),
    aiSelectionReason:
        'Perfect for today\'s partly cloudy weather and your Modern Classic aesthetic.',
    confidenceBoost: 'You\'ll feel polished and effortlessly confident.',
    aiInsights: [
      AiInsightData(
        title: 'Color Harmony',
        description:
            'The charcoal-and-cream palette creates a sophisticated monochrome '
            'that complements your warm skin tone.',
        iconName: 'palette_outlined',
      ),
      AiInsightData(
        title: 'Body Proportions',
        description:
            'The tapered trousers and structured blazer create a balanced '
            'silhouette that elongates your frame naturally.',
        iconName: 'accessibility_new_rounded',
      ),
      AiInsightData(
        title: 'Style Compatibility',
        description:
            'This Modern Minimalist look aligns perfectly with your '
            'Refined Minimalist Style DNA.',
        iconName: 'auto_awesome_rounded',
      ),
      AiInsightData(
        title: 'Occasion Suitability',
        description:
            'Smart casual with enough polish for meetings and enough '
            'comfort for after-work plans.',
        iconName: 'event_outlined',
      ),
    ],
    alternatives: [
      AlternativeLookData(
        id: 'alt_1',
        name: 'Relaxed Refined',
        matchScore: 88,
        styleName: 'Smart Casual',
      ),
      AlternativeLookData(
        id: 'alt_2',
        name: 'Urban Edge',
        matchScore: 84,
        styleName: 'Contemporary',
      ),
      AlternativeLookData(
        id: 'alt_3',
        name: 'Classic Heritage',
        matchScore: 82,
        styleName: 'Traditional',
      ),
    ],
    dailyStyleTip:
        'A textured leather belt in warm brown adds depth to monochrome '
        'outfits without breaking the clean silhouette.',
  );
}

class DailyOutfitComponent {
  const DailyOutfitComponent({
    required this.id,
    required this.name,
    required this.category,
    required this.color,
    this.material,
    this.colorHex,
  });

  final String id;
  final String name;
  final String category;
  final String color;
  final String? material;
  final String? colorHex;
}

class StyleDnaContext {
  const StyleDnaContext({
    required this.styleType,
    required this.bodyType,
    required this.skinTone,
    required this.faceShape,
  });

  final String styleType;
  final String bodyType;
  final String skinTone;
  final String faceShape;
}

class WardrobeContext {
  const WardrobeContext({
    required this.totalItems,
    required this.matchingItems,
    required this.insight,
  });

  final int totalItems;
  final int matchingItems;
  final String insight;
}

class DailyOutfitComponentCategory {
  const DailyOutfitComponentCategory._();

  static const String outerwear = 'Outerwear';
  static const String tops = 'Tops';
  static const String bottoms = 'Bottoms';
  static const String footwear = 'Footwear';
  static const String accessories = 'Accessories';
}
