import 'dart:math';

import 'package:flutter/material.dart';

class AnalysisRun {
  const AnalysisRun({
    required this.runId,
    required this.runType,
    required this.status,
    this.createdAt,
    this.completedAt,
    this.result,
    this.error,
  });

  final String runId;
  final String runType;
  final String status;
  final DateTime? createdAt;
  final DateTime? completedAt;
  final Map<String, dynamic>? result;
  final Map<String, dynamic>? error;

  bool get isCompleted => status == 'completed';

  bool get isFailed => status == 'failed';

  factory AnalysisRun.fromJson(Map<String, dynamic> json) => AnalysisRun(
    runId: json['run_id'] as String? ?? '',
    runType: json['run_type'] as String? ?? '',
    status: json['status'] as String? ?? 'pending',
    createdAt:
        json['created_at'] != null ? DateTime.tryParse(json['created_at'] as String) : null,
    completedAt:
        json['completed_at'] != null ? DateTime.tryParse(json['completed_at'] as String) : null,
    result: json['result'] as Map<String, dynamic>?,
    error: json['error'] as Map<String, dynamic>?,
  );
}

class GroomingRun {
  const GroomingRun({
    required this.runId,
    required this.runType,
    required this.status,
    this.createdAt,
    this.completedAt,
    this.result,
    this.error,
  });

  final String runId;
  final String runType;
  final String status;
  final DateTime? createdAt;
  final DateTime? completedAt;
  final Map<String, dynamic>? result;
  final Map<String, dynamic>? error;

  bool get isCompleted => status == 'completed';

  bool get isFailed => status == 'failed';

  factory GroomingRun.fromJson(Map<String, dynamic> json) => GroomingRun(
    runId: json['run_id'] as String? ?? '',
    runType: json['run_type'] as String? ?? '',
    status: json['status'] as String? ?? 'pending',
    createdAt:
        json['created_at'] != null ? DateTime.tryParse(json['created_at'] as String) : null,
    completedAt:
        json['completed_at'] != null ? DateTime.tryParse(json['completed_at'] as String) : null,
    result: json['result'] as Map<String, dynamic>?,
    error: json['error'] as Map<String, dynamic>?,
  );
}

class GroomingRecommendation {
  const GroomingRecommendation({
    required this.id,
    required this.name,
    required this.description,
    required this.matchScore,
    required this.reasons,
    required this.stylingTips,
    required this.maintenance,
    required this.bestFor,
    this.icon,
    this.beardLength,
    this.cheekLine,
    this.eyewearFrame,
    this.eyewearRecommendation,
  });

  factory GroomingRecommendation.fromBackend(Map<String, dynamic> json) => GroomingRecommendation(
    id: json['id'] as String? ?? '',
    name: json['name'] as String? ?? '',
    description: json['description'] as String? ?? '',
    matchScore: (json['matchScore'] as num? ?? 0).toDouble(),
    reasons: (json['reasons'] as List<dynamic>? ?? [])
        .map((e) => e as String)
        .toList(),
    stylingTips: json['stylingTips'] as String? ?? '',
    maintenance: json['maintenance'] as String? ?? '',
    bestFor: json['bestFor'] as String? ?? '',
    icon: json['icon'] as String?,
    beardLength: json['beardLength'] as String?,
    cheekLine: json['cheekLine'] as String?,
    eyewearFrame: json['eyewearFrame'] as String?,
    eyewearRecommendation: json['eyewearRecommendation'] as String?,
  );

  GroomingRecommendation.toMock(GroomingRecommendation mock) : this(
    id: mock.id,
    name: mock.name,
    description: mock.description,
    matchScore: mock.matchScore,
    reasons: List<String>.from(mock.reasons),
    stylingTips: mock.stylingTips,
    maintenance: mock.maintenance,
    bestFor: mock.bestFor,
    icon: mock.icon,
    beardLength: mock.beardLength,
    cheekLine: mock.cheekLine,
    eyewearFrame: mock.eyewearFrame,
    eyewearRecommendation: mock.eyewearRecommendation,
  );

  factory GroomingRecommendation.fromMock(GroomingRecommendation mock) => GroomingRecommendation(
    id: mock.id,
    name: mock.name,
    description: mock.description,
    matchScore: mock.matchScore,
    reasons: List<String>.from(mock.reasons),
    stylingTips: mock.stylingTips,
    maintenance: mock.maintenance,
    bestFor: mock.bestFor,
    icon: mock.icon,
    beardLength: mock.beardLength,
    cheekLine: mock.cheekLine,
    eyewearFrame: mock.eyewearFrame,
    eyewearRecommendation: mock.eyewearRecommendation,
  );

  final String id;
  final String name;
  final String description;
  final double matchScore;
  final List<String> reasons;
  final String stylingTips;
  final String maintenance;
  final String bestFor;
  final String? icon;
  final String? beardLength;
  final String? cheekLine;
  final String? eyewearFrame;
  final String? eyewearRecommendation;
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

factory GroomingAnalysisResult.fromRunResult(GroomingRun? run) => run == null
    ? GroomingAnalysisResult.mock
    : GroomingAnalysisResult(
        faceShape: run!.result?['appearance']?['faceShape'] as String? ?? '',
        beardStyle: _beardStyleFromRun(run.result),
        beardDensity: '',
        beardColor: '',
        topRecommendation: GroomingRecommendation.fromBackend(
          run.result?['recommendations']?['top'] as Map<String, dynamic>,
        ),
        alternatives: (run.result?['recommendations'] as List<dynamic>?)
            ?.map((e) => GroomingRecommendation.fromBackend(e as Map<String, dynamic>))
            .toList() as List<GroomingRecommendation>,
      );

  factory GroomingAnalysisResult.fromBackend(Map<String, dynamic> json) => GroomingAnalysisResult(
    faceShape: json['appearance']['faceShape'] as String? ?? '',
    beardStyle: json['topRecommendation']['id'] as String? ?? '',
    beardDensity: '',
    beardColor: '',
    topRecommendation: GroomingRecommendation.fromBackend(
      json['recommendations']['top'] as Map<String, dynamic>,
    ),
    alternatives: (json['recommendations']['alternatives'] as List<dynamic>? ?? [])
        .map((e) => GroomingRecommendation.fromBackend(e as Map<String, dynamic>))
        .toList(),
  );

  factory GroomingAnalysisResult.fromMock(GroomingAnalysisResult mock) => GroomingAnalysisResult(
    faceShape: mock.faceShape,
    beardStyle: mock.topRecommendation.id,
    beardDensity: '',
    beardColor: '',
    topRecommendation: mock.topRecommendation,
    alternatives: List.from(mock.alternatives),
  );

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
      stylingTips:
          'Keep the goatee edges clean and defined. Trim the beard line '
          'at the jaw to maintain contrast. Use a beard oil daily to '
          'keep hairs soft and manageable. Brush downward for a polished '
          'look.',
      maintenance: 'Medium • Trim every 3-4 days',
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
        stylingTips:
            'Use a beard trimmer with a guard to maintain consistent 3mm '
            'length. Define the neckline just above the Adam\'s apple for '
            'a clean transition.',
        maintenance: 'Low • Trim every 2-3 days',
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
        stylingTips:
            'Use a beard balm to keep hairs in place and reduce flyaways. '
            'Shape the neckline and cheek line every few days for a clean '
            'silhouette.',
        maintenance: 'Medium • Trim every 4-5 days',
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
        stylingTips:
            'Use moustache wax to shape and hold. Trim the upper lip line '
            'cleanly. Keep the rest of the face clean-shaven for maximum '
            'contrast.',
        maintenance: 'Medium • Trim every 2-3 days',
        bestFor: 'Oval, Heart, and Diamond face shapes',
      ),
    ],
  );

  final String faceShape;
  final String beardStyle;
  final String beardDensity;
  final String beardColor;
  final GroomingRecommendation topRecommendation;
  final List<GroomingRecommendation> alternatives;

  static String _beardStyleFromRun(Map<String, dynamic>? recommendations) {
    if (recommendations == null || recommendations is! Map<String, dynamic>) return '';
    final top = recommendations['top'];
    if (top == null) return '';
    return top['id'] as String? ?? '';
  }
}