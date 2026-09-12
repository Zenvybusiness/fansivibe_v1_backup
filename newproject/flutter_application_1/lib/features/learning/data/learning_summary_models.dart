// Learning summary DTOs for the M10 read (#34, STEP 19.16, DEC-021).
//
// Wire shapes follow the frozen contract exactly: `LearningSummary` carries
// only `styleScore`, `breakdown`, `streak`, `recentSignals`; `breakdown` is
// the frozen object (`base`, `wardrobePoints`, `savedPoints`, `total`) and
// `recentSignals` holds server-owned label strings only. Parsing is
// strict — wrong types throw into the client's null path rather than
// posing garbage as summary data. Nothing here computes scores or
// streaks: the backend is the sole source of truth.

/// Score component contributions (DEC-021 frozen object).
class LearningSummaryBreakdown {
  const LearningSummaryBreakdown({
    required this.base,
    required this.wardrobePoints,
    required this.savedPoints,
    required this.total,
  });

  /// Fixed base contribution (always 60).
  final int base;

  /// Capped wardrobe contribution (0..20).
  final int wardrobePoints;

  /// Capped saved-look contribution (0..20).
  final int savedPoints;

  /// Total, always equal to the enclosing style score (60..100).
  final int total;

  LearningSummaryBreakdown copyWith({
    int? base,
    int? wardrobePoints,
    int? savedPoints,
    int? total,
  }) => LearningSummaryBreakdown(
    base: base ?? this.base,
    wardrobePoints: wardrobePoints ?? this.wardrobePoints,
    savedPoints: savedPoints ?? this.savedPoints,
    total: total ?? this.total,
  );

  factory LearningSummaryBreakdown.fromJson(Map<String, dynamic> json) =>
      LearningSummaryBreakdown(
        base: json['base'] as int,
        wardrobePoints: json['wardrobePoints'] as int,
        savedPoints: json['savedPoints'] as int,
        total: json['total'] as int,
      );

  Map<String, dynamic> toJson() => {
    'base': base,
    'wardrobePoints': wardrobePoints,
    'savedPoints': savedPoints,
    'total': total,
  };
}

/// Derived M10 learning summary (#34).
class LearningSummary {
  const LearningSummary({
    required this.styleScore,
    required this.breakdown,
    required this.streak,
    required this.recentSignals,
  });

  /// Derived style score (60..100).
  final int styleScore;

  /// Frozen score breakdown object.
  final LearningSummaryBreakdown breakdown;

  /// Current consecutive styled days (>= 0).
  final int streak;

  /// Server-owned signal label strings, newest first (may be empty).
  final List<String> recentSignals;

  LearningSummary copyWith({
    int? styleScore,
    LearningSummaryBreakdown? breakdown,
    int? streak,
    List<String>? recentSignals,
  }) => LearningSummary(
    styleScore: styleScore ?? this.styleScore,
    breakdown: breakdown ?? this.breakdown,
    streak: streak ?? this.streak,
    recentSignals: recentSignals ?? this.recentSignals,
  );

  factory LearningSummary.fromJson(Map<String, dynamic> json) =>
      LearningSummary(
        styleScore: json['styleScore'] as int,
        breakdown: LearningSummaryBreakdown.fromJson(
          json['breakdown'] as Map<String, dynamic>,
        ),
        streak: json['streak'] as int,
        recentSignals: (json['recentSignals'] as List)
            .map((item) => item as String)
            .toList(),
      );

  Map<String, dynamic> toJson() => {
    'styleScore': styleScore,
    'breakdown': breakdown.toJson(),
    'streak': streak,
    'recentSignals': recentSignals,
  };
}
