/// Garment analysis result — the validated observation snapshot from
/// `POST /v1/analysis/garment` (M11 wardrobe intelligence).
///
/// Every attribute is either observed or null. Null means "not clearly
/// visible" — the UI renders `Not detected` and leaves the field for the
/// user to pick manually. Nothing here is defaulted, guessed, or
/// fabricated: a malformed backend value throws into the caller's error
/// path instead of posing as a measurement.
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
    final category = _optString(json['category']);
    if (category != null && !categories.contains(category)) {
      throw FormatException('Unknown garment category: $category');
    }
    double? confidence;
    final rawConfidence = json['confidence'];
    if (rawConfidence != null) {
      if (rawConfidence is! num) {
        throw FormatException('Invalid garment confidence');
      }
      confidence = rawConfidence.toDouble();
    }
    return GarmentAnalysisResult(
      category: category,
      subcategory: _optString(json['subcategory']),
      color: _optString(json['color']),
      pattern: _optString(json['pattern']),
      material: _optString(json['material']),
      style: _optString(json['style']),
      fit: _optString(json['fit']),
      confidence: confidence,
      needsReview: json['needs_review'] as bool? ?? true,
      sourceRunId: _optString(json['sourceRunId']),
    );
  }

  /// Observed string or null. Non-string values (numbers, lists, maps)
  /// throw — silently stringifying them would fabricate attributes.
  static String? _optString(Object? raw) {
    if (raw == null) return null;
    if (raw is! String) throw FormatException('Invalid garment attribute');
    final text = raw.trim();
    return text.isEmpty ? null : text;
  }
}
