import 'package:flutter/material.dart';

/// A selectable option in the outfit builder.
class BuilderOption {
  const BuilderOption({
    required this.id,
    required this.label,
    required this.icon,
    required this.description,
  });

  final String id;
  final String label;
  final IconData icon;
  final String description;

  static const List<BuilderOption> occasionOptions = [
    BuilderOption(
      id: 'casual',
      label: 'Casual',
      icon: Icons.wb_sunny_outlined,
      description: 'Relaxed everyday comfort',
    ),
    BuilderOption(
      id: 'office',
      label: 'Office',
      icon: Icons.business_center_outlined,
      description: 'Professional work attire',
    ),
    BuilderOption(
      id: 'date',
      label: 'Date',
      icon: Icons.favorite_outline_rounded,
      description: 'Memorable romantic evening',
    ),
    BuilderOption(
      id: 'party',
      label: 'Party',
      icon: Icons.nightlife_rounded,
      description: 'Stand out at social events',
    ),
    BuilderOption(
      id: 'travel',
      label: 'Travel',
      icon: Icons.flight_outlined,
      description: 'Comfortable on-the-go style',
    ),
  ];

  static const List<BuilderOption> moodOptions = [
    BuilderOption(
      id: 'minimal',
      label: 'Minimal',
      icon: Icons.horizontal_rule_rounded,
      description: 'Clean, understated elegance',
    ),
    BuilderOption(
      id: 'bold',
      label: 'Bold',
      icon: Icons.bolt_rounded,
      description: 'Confident, statement looks',
    ),
    BuilderOption(
      id: 'classic',
      label: 'Classic',
      icon: Icons.auto_awesome_rounded,
      description: 'Timeless sophisticated pieces',
    ),
    BuilderOption(
      id: 'eclectic',
      label: 'Eclectic',
      icon: Icons.palette_outlined,
      description: 'Creative, curated mix of styles',
    ),
  ];

  static const List<BuilderOption> fitOptions = [
    BuilderOption(
      id: 'slim',
      label: 'Slim',
      icon: Icons.tune_rounded,
      description: 'Tailored, form-fitting silhouette',
    ),
    BuilderOption(
      id: 'relaxed',
      label: 'Relaxed',
      icon: Icons.weekend_rounded,
      description: 'Comfortable, easy fit',
    ),
    BuilderOption(
      id: 'tailored',
      label: 'Tailored',
      icon: Icons.content_cut_rounded,
      description: 'Structured, custom-like fit',
    ),
  ];

  static const List<BuilderOption> colorPaletteOptions = [
    BuilderOption(
      id: 'monochrome',
      label: 'Monochrome',
      icon: Icons.opacity_rounded,
      description: 'Black, white, and shades of grey',
    ),
    BuilderOption(
      id: 'warm',
      label: 'Warm',
      icon: Icons.whatshot_outlined,
      description: 'Browns, creams, and earth tones',
    ),
    BuilderOption(
      id: 'cool',
      label: 'Cool',
      icon: Icons.ac_unit_rounded,
      description: 'Blues, greys, and cool neutrals',
    ),
  ];
}

/// A processing stage during outfit generation.
class GenerationStage {
  const GenerationStage({
    required this.id,
    required this.label,
    this.duration = const Duration(milliseconds: 800),
  });

  final String id;
  final String label;
  final Duration duration;

  static const List<GenerationStage> mockStages = [
    GenerationStage(id: 'wardrobe', label: 'Analyzing wardrobe items'),
    GenerationStage(
      id: 'occasion',
      label: 'Matching occasion preferences',
      duration: Duration(milliseconds: 1000),
    ),
    GenerationStage(
      id: 'style_dna',
      label: 'Applying Style DNA',
      duration: Duration(milliseconds: 900),
    ),
    GenerationStage(
      id: 'pieces',
      label: 'Selecting complementary pieces',
      duration: Duration(milliseconds: 1100),
    ),
    GenerationStage(
      id: 'recommendations',
      label: 'Generating outfit recommendations',
      duration: Duration(milliseconds: 1200),
    ),
  ];
}

/// A component in a recommended outfit.
class OutfitComponent {
  const OutfitComponent({
    required this.id,
    required this.name,
    required this.category,
    required this.color,
    required this.colorHex,
    this.material,
    required this.reason,
  });

  final String id;
  final String name;
  final String category;
  final String color;
  final String colorHex;
  final String? material;
  final String reason;
}

/// A full outfit recommendation from the builder.
class OutfitRecommendation {
  const OutfitRecommendation({
    required this.title,
    required this.matchScore,
    required this.components,
    required this.reasons,
    required this.colorHarmony,
    required this.bodyFit,
    required this.occasionMatch,
    required this.styleScoreImpact,
    required this.improvementSuggestion,
    required this.selectedOccasion,
    required this.selectedMood,
    required this.selectedColorPalette,
  });

  final String title;
  final double matchScore;
  final List<OutfitComponent> components;
  final List<String> reasons;
  final String colorHarmony;
  final String bodyFit;
  final String occasionMatch;
  final String styleScoreImpact;
  final String improvementSuggestion;
  final String selectedOccasion;
  final String selectedMood;
  final String selectedColorPalette;

  static const OutfitRecommendation mock = OutfitRecommendation(
    title: 'Refined Office Ensemble',
    matchScore: 0.91,
    selectedOccasion: 'Office',
    selectedMood: 'Classic',
    selectedColorPalette: 'Warm',
    components: [
      OutfitComponent(
        id: 'top_1',
        name: 'Navy Textured Blazer',
        category: 'Outerwear',
        color: 'Navy',
        colorHex: '#1A237E',
        material: 'Wool Blend',
        reason: 'Structured silhouette creates a commanding presence',
      ),
      OutfitComponent(
        id: 'top_2',
        name: 'Cream Cotton Oxford',
        category: 'Tops',
        color: 'Cream',
        colorHex: '#FFFDD0',
        material: 'Cotton',
        reason: 'Classic layering piece that brightens the palette',
      ),
      OutfitComponent(
        id: 'bottom_1',
        name: 'Charcoal Tailored Trousers',
        category: 'Bottoms',
        color: 'Charcoal',
        colorHex: '#36454F',
        material: 'Wool',
        reason: 'Clean lines complement the structured blazer',
      ),
      OutfitComponent(
        id: 'shoe_1',
        name: 'Brown Leather Derbies',
        category: 'Footwear',
        color: 'Brown',
        colorHex: '#5D4037',
        material: 'Leather',
        reason: 'Warm earth tones anchor the outfit naturally',
      ),
      OutfitComponent(
        id: 'acc_1',
        name: 'Gold Minimalist Watch',
        category: 'Accessories',
        color: 'Gold',
        colorHex: '#C5A059',
        material: 'Stainless Steel',
        reason: 'Adds a subtle premium accent to the ensemble',
      ),
    ],
    reasons: [
      'The structured blazer and tailored trousers create a cohesive professional profile',
      'Warm color palette complements the office environment while maintaining sophistication',
      'Classic pieces ensure versatility across multiple work settings',
      'Gold accents provide a premium touch without overwhelming the core palette',
    ],
    colorHarmony:
        'Warm analogous palette with cream as the bridge between navy and charcoal. Gold accents add calculated contrast at key focal points.',
    bodyFit:
        'Tailored upper and tapered lower creates a balanced V-silhouette. The blazer shoulder structure offsets the slim trouser profile.',
    occasionMatch:
        'Fully aligned with office dress codes. The combination communicates competence, attention to detail, and refined taste.',
    styleScoreImpact: '+3 Style Score points for consistency across categories',
    improvementSuggestion:
        'Consider a textured pocket square in deep burgundy for client meetings to add a personal signature element.',
  );
}
