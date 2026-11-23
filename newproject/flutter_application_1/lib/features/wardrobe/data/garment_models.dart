/// Garment analysis result — the validated observation snapshot from
/// `POST /v1/analysis/garment` (M11 wardrobe intelligence).
///
/// Every attribute is either observed or null. Null means "not clearly
/// visible" — the UI renders `Not detected` and leaves the field for the
/// user to pick manually. Nothing here is defaulted, guessed, or
/// fabricated: a malformed backend value throws into the caller's error
/// path instead of posing as a measurement.
class GarmentCandidate {
  const GarmentCandidate({
    this.id,
    this.category,
    this.subcategory,
    this.color,
    this.secondaryColors,
    this.pattern,
    this.material,
    this.style,
    this.fit,
    this.sleeveType,
    this.neckline,
    this.length,
    this.condition,
    this.description,
    this.boundingBox,
    this.confidence,
    this.needsReview = true,
    this.isSelected = true,
  });

  final String? id;
  final String? category;
  final String? subcategory;
  final String? color;
  final List<String>? secondaryColors;
  final String? pattern;
  final String? material;
  final String? style;
  final String? fit;
  final String? sleeveType;
  final String? neckline;
  final String? length;
  final String? condition;
  final String? description;
  final Map<String, dynamic>? boundingBox;
  final double? confidence;
  final bool needsReview;
  final bool isSelected;

  GarmentCandidate copyWith({
    String? id,
    String? category,
    String? subcategory,
    String? color,
    List<String>? secondaryColors,
    String? pattern,
    String? material,
    String? style,
    String? fit,
    String? sleeveType,
    String? neckline,
    String? length,
    String? condition,
    String? description,
    Map<String, dynamic>? boundingBox,
    double? confidence,
    bool? needsReview,
    bool? isSelected,
  }) {
    return GarmentCandidate(
      id: id ?? this.id,
      category: category ?? this.category,
      subcategory: subcategory ?? this.subcategory,
      color: color ?? this.color,
      secondaryColors: secondaryColors ?? this.secondaryColors,
      pattern: pattern ?? this.pattern,
      material: material ?? this.material,
      style: style ?? this.style,
      fit: fit ?? this.fit,
      sleeveType: sleeveType ?? this.sleeveType,
      neckline: neckline ?? this.neckline,
      length: length ?? this.length,
      condition: condition ?? this.condition,
      description: description ?? this.description,
      boundingBox: boundingBox ?? this.boundingBox,
      confidence: confidence ?? this.confidence,
      needsReview: needsReview ?? this.needsReview,
      isSelected: isSelected ?? this.isSelected,
    );
  }

  factory GarmentCandidate.fromJson(Map<String, dynamic> json) {
    final rawCat = GarmentAnalysisResult.optString(json['category']);
    if (rawCat != null && !GarmentAnalysisResult.categories.contains(rawCat)) {
      throw FormatException('Unknown garment category: $rawCat');
    }
    double? confidence;
    final rawConfidence = json['confidence'];
    if (rawConfidence != null) {
      if (rawConfidence is! num) {
        throw const FormatException('Invalid garment confidence');
      }
      confidence = rawConfidence.toDouble();
    }
    List<String>? secColors;
    final rawSec = json['secondary_colors'];
    if (rawSec is List) {
      secColors = rawSec.map((e) => e.toString()).toList();
    }
    return GarmentCandidate(
      id: GarmentAnalysisResult.optString(json['id']),
      category: rawCat,
      subcategory: GarmentAnalysisResult.optString(json['subcategory'] ?? json['name']),
      color: GarmentAnalysisResult.optString(json['color']),
      secondaryColors: secColors,
      pattern: GarmentAnalysisResult.optString(json['pattern']),
      material: GarmentAnalysisResult.optString(json['material']),
      style: GarmentAnalysisResult.optString(json['style']),
      fit: GarmentAnalysisResult.optString(json['fit']),
      sleeveType: GarmentAnalysisResult.optString(json['sleeve_type']),
      neckline: GarmentAnalysisResult.optString(json['neckline']),
      length: GarmentAnalysisResult.optString(json['length']),
      condition: GarmentAnalysisResult.optString(json['condition']),
      description: GarmentAnalysisResult.optString(json['description']),
      boundingBox: json['bounding_box'] is Map<String, dynamic>
          ? json['bounding_box'] as Map<String, dynamic>
          : null,
      confidence: confidence,
      needsReview: json['needs_review'] as bool? ?? true,
      isSelected: true,
    );
  }
}

class GarmentAnalysisResult {
  const GarmentAnalysisResult({
    this.category,
    this.subcategory,
    this.color,
    this.pattern,
    this.material,
    this.style,
    this.fit,
    this.confidence,
    this.needsReview = true,
    this.sourceRunId,
    this.candidates = const [],
  });

  /// Canonical wardrobe category code (tops/bottoms/outerwear/footwear/
  /// accessories) or null when not classifiable.
  final String? category;
  final String? subcategory;
  final String? color;
  final String? pattern;
  final String? material;
  final String? style;
  final String? fit;

  /// Analyzer confidence 0..1, or null when the backend omits it.
  /// Never invented — absent stays absent.
  final double? confidence;

  /// True when the user should review/confirm before saving.
  final bool needsReview;

  /// Producing run id (provenance), when the backend attaches it.
  final String? sourceRunId;

  /// Individual detected garment candidates from this extraction.
  final List<GarmentCandidate> candidates;

  /// Canonical wardrobe category codes the backend may return.
  static const Set<String> categories = {
    'tops',
    'bottoms',
    'outerwear',
    'footwear',
    'accessories',
  };

  /// Parses a completed-run `result` map. Throws [FormatException] on a
  /// malformed value (wrong type, out-of-vocabulary category, non-numeric
  /// confidence) so the caller renders an error, never a fake garment.
  factory GarmentAnalysisResult.fromJson(Map<String, dynamic> json) {
    final category = optString(json['category']);
    if (category != null && !categories.contains(category)) {
      throw FormatException('Unknown garment category: $category');
    }
    double? confidence;
    final rawConfidence = json['confidence'];
    if (rawConfidence != null) {
      if (rawConfidence is! num) {
        throw const FormatException('Invalid garment confidence');
      }
      confidence = rawConfidence.toDouble();
    }

    final parsedCandidates = <GarmentCandidate>[];
    final rawCandidates = json['candidates'] ?? json['items'];
    if (rawCandidates is List && rawCandidates.isNotEmpty) {
      for (final item in rawCandidates) {
        if (item is Map<String, dynamic>) {
          parsedCandidates.add(GarmentCandidate.fromJson(item));
        }
      }
    }

    if (parsedCandidates.isEmpty &&
        (category != null ||
            json['subcategory'] != null ||
            json['color'] != null ||
            json['material'] != null)) {
      parsedCandidates.add(
        GarmentCandidate(
          id: 'cand_1',
          category: category,
          subcategory: optString(json['subcategory']),
          color: optString(json['color']),
          pattern: optString(json['pattern']),
          material: optString(json['material']),
          style: optString(json['style']),
          fit: optString(json['fit']),
          sleeveType: optString(json['sleeve_type']),
          neckline: optString(json['neckline']),
          length: optString(json['length']),
          condition: optString(json['condition']),
          description: optString(json['description']),
          confidence: confidence,
          needsReview: json['needs_review'] as bool? ?? true,
          isSelected: true,
        ),
      );
    }

    return GarmentAnalysisResult(
      category: category,
      subcategory: optString(json['subcategory']),
      color: optString(json['color']),
      pattern: optString(json['pattern']),
      material: optString(json['material']),
      style: optString(json['style']),
      fit: optString(json['fit']),
      confidence: confidence,
      needsReview: json['needs_review'] as bool? ?? true,
      sourceRunId: optString(json['sourceRunId']),
      candidates: parsedCandidates,
    );
  }

  /// Observed string or null. Non-string values (numbers, lists, maps)
  /// throw — silently stringifying them would fabricate attributes.
  static String? optString(Object? raw) {
    if (raw == null) return null;
    if (raw is! String) throw const FormatException('Invalid garment attribute');
    final text = raw.trim();
    return text.isEmpty ? null : text;
  }
}
