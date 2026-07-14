import 'package:flutter/material.dart';

class GroomingOption {
  const GroomingOption({
    required this.id,
    required this.label,
    required this.icon,
    required this.description,
  });

  final String id;
  final String label;
  final IconData icon;
  final String description;

  static const List<GroomingOption> faceShapeOptions = [
    GroomingOption(
      id: 'oval',
      label: 'Oval',
      icon: Icons.circle_outlined,
      description: 'Balanced, slightly longer than wide',
    ),
    GroomingOption(
      id: 'round',
      label: 'Round',
      icon: Icons.circle_rounded,
      description: 'Full cheeks, rounded chin',
    ),
    GroomingOption(
      id: 'square',
      label: 'Square',
      icon: Icons.square_outlined,
      description: 'Strong jawline, equal proportions',
    ),
    GroomingOption(
      id: 'heart',
      label: 'Heart',
      icon: Icons.favorite_outline_rounded,
      description: 'Wider forehead, narrow chin',
    ),
    GroomingOption(
      id: 'diamond',
      label: 'Diamond',
      icon: Icons.diamond_outlined,
      description: 'High cheekbones, narrow jaw',
    ),
    GroomingOption(
      id: 'rectangle',
      label: 'Rectangle',
      icon: Icons.rectangle_outlined,
      description: 'Angular, longer than wide',
    ),
  ];

  static const List<GroomingOption> beardStyleOptions = [
    GroomingOption(
      id: 'full_beard',
      label: 'Full Beard',
      icon: Icons.face_rounded,
      description: 'Complete coverage from sideburns to neck',
    ),
    GroomingOption(
      id: 'goatee',
      label: 'Goatee',
      icon: Icons.face_3_rounded,
      description: 'Chin hair with disconnected moustache',
    ),
    GroomingOption(
      id: 'stubble',
      label: 'Stubble',
      icon: Icons.face_4_rounded,
      description: 'Short, low-maintenance growth',
    ),
    GroomingOption(
      id: 'circle_beard',
      label: 'Circle Beard',
      icon: Icons.face_5_rounded,
      description: 'Connected moustache and goatee',
    ),
    GroomingOption(
      id: 'van_dyke',
      label: 'Van Dyke',
      icon: Icons.face_6_rounded,
      description: 'Pointed goatee with moustache',
    ),
    GroomingOption(
      id: 'moustache',
      label: 'Moustache',
      icon: Icons.face_2_rounded,
      description: 'Upper lip hair only',
    ),
  ];

  static const List<GroomingOption> densityOptions = [
    GroomingOption(
      id: 'sparse',
      label: 'Light',
      icon: Icons.blur_on_rounded,
      description: 'Thin, less coverage',
    ),
    GroomingOption(
      id: 'medium',
      label: 'Medium',
      icon: Icons.blur_circular_rounded,
      description: 'Average density and coverage',
    ),
    GroomingOption(
      id: 'dense',
      label: 'Dense',
      icon: Icons.blur_off_rounded,
      description: 'Full, thick growth',
    ),
  ];

  static const List<GroomingOption> colorOptions = [
    GroomingOption(
      id: 'dark_brown',
      label: 'Dark Brown',
      icon: Icons.format_bold_rounded,
      description: 'Rich deep brown tones',
    ),
    GroomingOption(
      id: 'black',
      label: 'Black',
      icon: Icons.dark_mode_rounded,
      description: 'Deep black pigmentation',
    ),
    GroomingOption(
      id: 'light_brown',
      label: 'Light Brown',
      icon: Icons.format_italic_rounded,
      description: 'Warm lighter brown shades',
    ),
    GroomingOption(
      id: 'auburn',
      label: 'Red / Auburn',
      icon: Icons.whatshot_outlined,
      description: 'Warm red undertones',
    ),
    GroomingOption(
      id: 'blonde',
      label: 'Blonde',
      icon: Icons.wb_sunny_outlined,
      description: 'Light golden tones',
    ),
    GroomingOption(
      id: 'grey',
      label: 'Grey',
      icon: Icons.ac_unit_rounded,
      description: 'Silver and grey tones',
    ),
  ];
}

class GroomingProcessingStage {
  const GroomingProcessingStage({
    required this.id,
    required this.label,
    this.duration = const Duration(milliseconds: 800),
  });

  final String id;
  final String label;
  final Duration duration;

  static const List<GroomingProcessingStage> mockStages = [
    GroomingProcessingStage(id: 'face', label: 'Analyzing face shape'),
    GroomingProcessingStage(
      id: 'features',
      label: 'Evaluating facial features',
      duration: Duration(milliseconds: 1000),
    ),
    GroomingProcessingStage(
      id: 'beard',
      label: 'Matching beard styles',
      duration: Duration(milliseconds: 1100),
    ),
    GroomingProcessingStage(
      id: 'eyewear',
      label: 'Selecting eyewear options',
      duration: Duration(milliseconds: 900),
    ),
    GroomingProcessingStage(
      id: 'recommendations',
      label: 'Ranking grooming recommendations',
      duration: Duration(milliseconds: 1200),
    ),
  ];
}

class GroomingRecommendation {
  const GroomingRecommendation({
    required this.id,
    required this.name,
    required this.description,
    required this.matchScore,
    required this.reasons,
    required this.beardLength,
    required this.cheekLine,
    required this.eyewearFrame,
    required this.eyewearRecommendation,
    required this.stylingTips,
    required this.maintenance,
    required this.bestFor,
    this.icon = Icons.spa_outlined,
  });

  final String id;
  final String name;
  final String description;
  final double matchScore;
  final List<String> reasons;
  final String beardLength;
  final String cheekLine;
  final String eyewearFrame;
  final String eyewearRecommendation;
  final String stylingTips;
  final String maintenance;
  final String bestFor;
  final IconData icon;
}

class GroomingAnalysisResult {
  const GroomingAnalysisResult({
    required this.faceShape,
    required this.beardStyle,
    required this.beardDensity,
    required this.beardColor,
    required this.topRecommendation,
    required this.alternatives,
  });

  final String faceShape;
  final String beardStyle;
  final String beardDensity;
  final String beardColor;
  final GroomingRecommendation topRecommendation;
  final List<GroomingRecommendation> alternatives;

  static const GroomingAnalysisResult mock = GroomingAnalysisResult(
    faceShape: 'Oval',
    beardStyle: 'Full Beard',
    beardDensity: 'Medium',
    beardColor: 'Dark Brown',
    topRecommendation: GroomingRecommendation(
      id: 'structured_goatee',
      name: 'Structured Goatee',
      description:
          'A refined goatee that frames the chin and mouth area, '
          'complementing oval face shapes by adding definition to the '
          'lower third. The structured lines create a clean, intentional '
          'look that pairs well with both professional and casual styles.',
      matchScore: 0.92,
      reasons: [
        'Oval faces benefit from chin definition, which a structured goatee provides naturally',
        'Medium density creates balanced visual weight without overwhelming facial proportions',
        'Dark brown color adds contrast against the skin for a well-defined appearance',
        'Complements rectangular eyewear frames for a cohesive facial aesthetic',
      ],
      beardLength: 'Medium - Long (10-15mm)',
      cheekLine: 'Natural cheek line mid-cheek',
      eyewearFrame: 'Rectangular',
      eyewearRecommendation:
          'Rectangular or wayfarer frames in dark acetate. '
          'The angular lines of rectangular frames create a complementary '
          'contrast with the rounded oval face shape, while dark acetate '
          'pairs well with the dark brown beard coloring. Avoid round frames '
          'that may overemphasize the oval face silhouette.',
      stylingTips:
          'Keep the goatee edges clean and defined. Trim the beard line '
          'at the jaw to maintain contrast. Use a beard oil daily to '
          'keep hairs soft and manageable. Brush downward for a polished '
          'look.',
      maintenance: 'Medium \u2022 Trim every 3-4 days',
      bestFor: 'Oval, Rectangular, and Diamond face shapes',
    ),
    alternatives: [
      GroomingRecommendation(
        id: 'classic_stubble',
        name: 'Classic Stubble',
        description:
            'A uniform short stubble that provides a rugged yet polished '
            'appearance. Low maintenance and versatile, stubble works well '
            'with medium density growth patterns.',
        matchScore: 0.85,
        reasons: [
          'Adds visual weight to the lower face without hiding facial structure',
          'Short length keeps the look professional and office-appropriate',
          'Pairs naturally with round or aviator eyewear frames',
        ],
        beardLength: 'Short (3-5mm)',
        cheekLine: 'Natural full cheek',
        eyewearFrame: 'Aviator',
        eyewearRecommendation:
            'Aviator or round frames in gold or silver. The soft curves '
            'of aviator frames balance the clean lines of stubble, creating '
            'a harmonious look.',
        stylingTips:
            'Use a beard trimmer with a guard to maintain consistent 3mm '
            'length. Define the neckline just above the Adam\'s apple for '
            'a clean transition.',
        maintenance: 'Low \u2022 Trim every 2-3 days',
        bestFor: 'Oval, Square, and Heart face shapes',
      ),
      GroomingRecommendation(
        id: 'full_beard_short',
        name: 'Cropped Full Beard',
        description:
            'A full beard kept at a short, even length for a groomed and '
            'masculine appearance. Provides balanced coverage that works well '
            'with medium to dense growth patterns.',
        matchScore: 0.79,
        reasons: [
          'Full coverage creates a balanced frame for the face',
          'Short length prevents the beard from appearing unkempt',
          'Medium density provides enough volume for a full look without being heavy',
        ],
        beardLength: 'Short - Medium (5-10mm)',
        cheekLine: 'Curved cheek line at mid-cheek',
        eyewearFrame: 'Wayfarer',
        eyewearRecommendation:
            'Wayfarer or square frames in tortoiseshell. The bold lines of '
            'wayfarer frames balance the full bearded look and add structure '
            'to the upper face.',
        stylingTips:
            'Use a beard balm to keep hairs in place and reduce flyaways. '
            'Shape the neckline and cheek line every few days for a clean '
            'silhouette.',
        maintenance: 'Medium \u2022 Trim every 4-5 days',
        bestFor: 'Round, Square, and Rectangular face shapes',
      ),
      GroomingRecommendation(
        id: 'sleek_moustache',
        name: 'Sleek Moustache',
        description:
            'A well-groomed moustache that draws attention to the upper lip '
            'area. Ideal for those who prefer minimal facial hair coverage '
            'while still making a style statement.',
        matchScore: 0.72,
        reasons: [
          'Focuses attention on the central face for a distinctive look',
          'Minimal grooming required while maintaining a polished appearance',
          'Pairs well with bold geometric eyewear for a fashion-forward aesthetic',
        ],
        beardLength: 'Medium (8-12mm)',
        cheekLine: 'Clean shaven',
        eyewearFrame: 'Geometric',
        eyewearRecommendation:
            'Geometric or cat-eye frames in metal. The precise lines of '
            'geometric frames echo the intentional styling of a sleek '
            'moustache for a coordinated appearance.',
        stylingTips:
            'Use moustache wax to shape and hold. Trim the upper lip line '
            'cleanly. Keep the rest of the face clean-shaven for maximum '
            'contrast.',
        maintenance: 'Medium \u2022 Trim every 2-3 days',
        bestFor: 'Oval, Heart, and Diamond face shapes',
      ),
    ],
  );
}
