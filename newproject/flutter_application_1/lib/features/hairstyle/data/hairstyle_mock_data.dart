import 'package:flutter/material.dart';

class FaceScanCheck {
  const FaceScanCheck({
    required this.id,
    required this.label,
    required this.isPassing,
    this.message,
  });

  final String id;
  final String label;
  final bool isPassing;
  final String? message;

  static const List<FaceScanCheck> mockChecks = [
    FaceScanCheck(id: 'lighting', label: 'Lighting', isPassing: true),
    FaceScanCheck(id: 'distance', label: 'Distance', isPassing: true),
    FaceScanCheck(
      id: 'alignment',
      label: 'Alignment',
      isPassing: false,
      message: 'Center your face in the frame',
    ),
  ];
}

class HairstyleProcessingStage {
  const HairstyleProcessingStage({
    required this.id,
    required this.label,
    this.duration = const Duration(milliseconds: 800),
  });

  final String id;
  final String label;
  final Duration duration;

  static const List<HairstyleProcessingStage> mockStages = [
    HairstyleProcessingStage(id: 'detecting', label: 'Detecting face features'),
    HairstyleProcessingStage(
      id: 'shape',
      label: 'Analyzing face shape',
      duration: Duration(milliseconds: 1200),
    ),
    HairstyleProcessingStage(
      id: 'tone',
      label: 'Analyzing skin tone',
      duration: Duration(milliseconds: 1000),
    ),
    HairstyleProcessingStage(
      id: 'style_dna',
      label: 'Applying Style DNA',
      duration: Duration(milliseconds: 900),
    ),
    HairstyleProcessingStage(
      id: 'recommendations',
      label: 'Ranking hairstyle recommendations',
      duration: Duration(milliseconds: 1100),
    ),
  ];
}

class HairstyleRecommendation {
  const HairstyleRecommendation({
    required this.id,
    required this.name,
    required this.description,
    required this.matchScore,
    required this.reasons,
    required this.stylingTips,
    required this.maintenance,
    required this.bestFor,
    this.icon = Icons.face_rounded,
  });

  final String id;
  final String name;
  final String description;
  final double matchScore;
  final List<String> reasons;
  final String stylingTips;
  final String maintenance;
  final String bestFor;
  final IconData icon;
}

class HairstyleAnalysisResult {
  const HairstyleAnalysisResult({
    required this.faceShape,
    required this.skinTone,
    required this.styleDna,
    required this.topRecommendation,
    required this.alternatives,
  });

  final String faceShape;
  final String skinTone;
  final String styleDna;
  final HairstyleRecommendation topRecommendation;
  final List<HairstyleRecommendation> alternatives;

  static const HairstyleAnalysisResult mock = HairstyleAnalysisResult(
    faceShape: 'Oval',
    skinTone: 'Warm Medium',
    styleDna: 'Modern Classic \u2022 Minimalist \u2022 Structured',
    topRecommendation: HairstyleRecommendation(
      id: 'textured_quiff',
      name: 'Textured Quiff',
      description:
          'A modern take on the classic quiff with added texture and '
          'movement. The volume on top complements oval face shapes by '
          'adding vertical dimension while the textured finish keeps it '
          'effortless and contemporary.',
      matchScore: 0.94,
      reasons: [
        'Oval face shapes benefit from volume on top, which the quiff provides naturally',
        'Textured finish softens the structured silhouette for a modern, approachable look',
        'Works exceptionally well with warm medium skin tones and adds contrast',
        'Aligns with your Modern Classic Style DNA for a cohesive appearance',
      ],
      stylingTips:
          'Apply a volumizing mousse to damp hair, blow-dry upward using a '
          'round brush, then finish with a light-hold matte clay. Use fingers '
          'to create separation and texture.',
      maintenance: 'Medium \u2022 Trim every 4-5 weeks',
      bestFor: 'Oval, Heart, and Rectangle face shapes',
    ),
    alternatives: [
      HairstyleRecommendation(
        id: 'classic_pompadour',
        name: 'Classic Pompadour',
        description:
            'A timeless pompadour with swept-back volume and clean sides. '
            'Offers a more polished, formal alternative while maintaining '
            'the vertical emphasis that suits your face shape.',
        matchScore: 0.87,
        reasons: [
          'Provides elegant volume that elongates and balances facial features',
          'Clean sides keep the silhouette sharp and intentional',
          'Pairs naturally with structured, tailored wardrobe pieces',
        ],
        stylingTips:
            'Use a strong-hold pomade on towel-dried hair, blow-dry back '
            'and up, then comb into place. Finish with a light hairspray '
            'for all-day hold.',
        maintenance: 'High \u2022 Trim every 3-4 weeks',
        bestFor: 'Oval, Round, and Square face shapes',
      ),
      HairstyleRecommendation(
        id: 'side_part',
        name: 'Side Part',
        description:
            'A refined side part with medium length on top and tapered '
            'sides. A versatile, professional option that works across '
            'settings while maintaining a clean, structured appearance.',
        matchScore: 0.82,
        reasons: [
          'Creates asymmetry that adds visual interest to symmetrical face shapes',
          'Tapered sides prevent the silhouette from feeling too wide',
          'Easy to transition from professional to casual settings',
        ],
        stylingTips:
            'Apply a styling cream to damp hair, create a deep side part, '
            'and blow-dry in place. Finish with a light-hold wax for '
            'natural movement.',
        maintenance: 'Low \u2022 Trim every 5-6 weeks',
        bestFor: 'Oval, Square, and Diamond face shapes',
      ),
      HairstyleRecommendation(
        id: 'brushed_up_undercut',
        name: 'Brushed Up Undercut',
        description:
            'A contemporary undercut with brushed-up length on top. '
            'Provides maximum contrast between the longer top and faded '
            'sides for a bold, fashion-forward statement.',
        matchScore: 0.78,
        reasons: [
          'High contrast silhouette makes a strong style statement',
          'Undercut keeps the look clean and low-maintenance on the sides',
          'Brushed-up top adds height that complements oval face proportions',
        ],
        stylingTips:
            'Apply a sea salt spray for texture, blow-dry forward and up, '
            'then use a matte paste to shape. Keep the sides faded every '
            '2-3 weeks.',
        maintenance: 'Medium \u2022 Trim every 3-4 weeks',
        bestFor: 'Oval, Heart, and Diamond face shapes',
      ),
    ],
  );
}
