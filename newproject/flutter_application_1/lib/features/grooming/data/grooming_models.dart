import 'grooming_mock_data.dart';

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
  );

  String? id;
  String? name;
  String? description;
  double matchScore;
  List<String> reasons;
  String? stylingTips;
  String? maintenance;
  String? bestFor;
  String? icon;
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

  String faceShape;
  String beardStyle;
  String beardDensity;
  String beardColor;
  GroomingRecommendation topRecommendation;
  List<GroomingRecommendation> alternatives;
}