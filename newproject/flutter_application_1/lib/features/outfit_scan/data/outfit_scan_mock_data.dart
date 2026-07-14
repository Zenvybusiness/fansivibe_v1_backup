/// A detected clothing item in the outfit analysis.
class DetectedClothingItem {
  const DetectedClothingItem({
    required this.name,
    required this.category,
    required this.color,
    this.material,
  });

  final String name;
  final String category;
  final String color;
  final String? material;
}

/// A single section in the structured outfit analysis.
class AnalysisSection {
  const AnalysisSection({
    required this.id,
    required this.label,
    required this.description,
    this.score,
    this.detail,
  });

  final String id;
  final String label;
  final String description;
  final double? score;
  final String? detail;
}

/// A processing stage shown during outfit scan processing.
class ProcessingStage {
  const ProcessingStage({
    required this.id,
    required this.label,
    this.duration = const Duration(milliseconds: 800),
  });

  final String id;
  final String label;
  final Duration duration;

  static const List<ProcessingStage> mockStages = [
    ProcessingStage(id: 'detecting', label: 'Detecting clothing items'),
    ProcessingStage(
      id: 'proportions',
      label: 'Analyzing proportions',
      duration: Duration(milliseconds: 1200),
    ),
    ProcessingStage(
      id: 'colors',
      label: 'Analyzing colors',
      duration: Duration(milliseconds: 1000),
    ),
    ProcessingStage(
      id: 'style_dna',
      label: 'Applying Style DNA',
      duration: Duration(milliseconds: 900),
    ),
    ProcessingStage(
      id: 'recommendations',
      label: 'Generating recommendations',
      duration: Duration(milliseconds: 1100),
    ),
  ];
}

/// Structured outfit analysis result data.
class OutfitAnalysisData {
  const OutfitAnalysisData({
    required this.title,
    required this.sections,
    required this.detectedItems,
  });

  final String title;
  final List<AnalysisSection> sections;
  final List<DetectedClothingItem> detectedItems;

  static const OutfitAnalysisData mock = OutfitAnalysisData(
    title: 'Modern Minimalist Look',
    sections: [
      AnalysisSection(
        id: 'silhouette',
        label: 'Silhouette & Proportions',
        description:
            'Clean, balanced A-line silhouette. The structured shoulders '
            'create visual width that complements the tapered lower half. '
            'Proportions are well-maintained with a 1:1.618 upper-to-lower '
            'ratio.',
        score: 0.88,
        detail: 'Excellent proportion balance',
      ),
      AnalysisSection(
        id: 'balance',
        label: 'Balance',
        description:
            'Visual weight is evenly distributed. The darker upper '
            'anchors the look while lighter lower elements keep it from '
            'feeling heavy. Accessories are used sparingly and effectively.',
        score: 0.85,
        detail: 'Good visual equilibrium',
      ),
      AnalysisSection(
        id: 'fit',
        label: 'Fit',
        description:
            'Strong fit across all pieces. The blazer is tailored through '
            'the waist without pulling. Trousers have a clean break at the '
            'shoe. Sleeve lengths end precisely at the wrist bone.',
        score: 0.92,
        detail: 'Excellent fit across all items',
      ),
      AnalysisSection(
        id: 'volume',
        label: 'Volume',
        description:
            'Controlled volume distribution. The structured upper is '
            'balanced by the slim lower half. No excessive fabric pooling. '
            'The overall volume profile suits a lean-to-athletic build.',
        score: 0.82,
        detail: 'Balanced volume distribution',
      ),
      AnalysisSection(
        id: 'color_harmony',
        label: 'Color Harmony',
        description:
            'Monochromatic palette with intentional contrast. The '
            'charcoal-on-charcoal base is elevated by off-white accents. '
            'Gold accessories add warmth without competing with the core '
            'palette. The color temperature is consistent throughout.',
        score: 0.86,
        detail: 'Cohesive monochromatic scheme',
      ),
      AnalysisSection(
        id: 'structure',
        label: 'Structure & Form',
        description:
            'Architectural approach to layering. Each piece has a distinct '
            'role in creating the overall form. The blazer provides the '
            'primary structure while the knit acts as a soft transitional '
            'layer. Form follows function without sacrificing aesthetics.',
        score: 0.84,
        detail: 'Well-defined structural hierarchy',
      ),
    ],
    detectedItems: [
      DetectedClothingItem(
        name: 'Charcoal Unstructured Blazer',
        category: 'Outerwear',
        color: 'Charcoal',
        material: 'Wool Blend',
      ),
      DetectedClothingItem(
        name: 'Off-White Merino Crewneck',
        category: 'Tops',
        color: 'Off-White',
        material: 'Merino Wool',
      ),
      DetectedClothingItem(
        name: 'Tapered Wool Trousers',
        category: 'Bottoms',
        color: 'Charcoal',
        material: 'Wool',
      ),
      DetectedClothingItem(
        name: 'Leather Chelsea Boots',
        category: 'Footwear',
        color: 'Black',
        material: 'Leather',
      ),
      DetectedClothingItem(
        name: 'Minimalist Belt',
        category: 'Accessories',
        color: 'Black',
        material: 'Leather',
      ),
    ],
  );
}
