// Style Journey historical progress DTOs for SJ1/SJ2.
//
// Wire shapes mirror `backend/app/api/schemas/learning.py`
// (`StyleJourneyHistoryResponse`, `WeeklyProgressItem`,
// `StyleJourneyComparisonSchema`) verbatim. Nothing here fabricates
// missing historical weeks or computes scores/rankings locally.

import 'package:fansivibe/features/learning/data/learning_summary_models.dart';

/// Failure reasons for Style Journey history reads.
enum StyleJourneyFailure {
  unauthorized,
  networkError,
  rateLimited,
  serviceUnavailable,
  serverError,
}

/// Typed result wrapper for `GET /v1/learning/journey/history`.
class StyleJourneyHistoryResult {
  const StyleJourneyHistoryResult.success(StyleJourneyHistory this.history)
    : failure = null;

  const StyleJourneyHistoryResult.failure(StyleJourneyFailure this.failure)
    : history = null;

  final StyleJourneyHistory? history;
  final StyleJourneyFailure? failure;

  bool get isSuccess => history != null;
  bool get isFailure => failure != null;
}

/// One week of personal Style Journey progress (live current week or
/// immutable historical snapshot).
class WeeklyProgressItem {
  const WeeklyProgressItem({
    required this.weekStart,
    required this.weekEnd,
    required this.timezone,
    required this.styleScore,
    required this.breakdown,
    required this.styledDaysCount,
    required this.signalsCount,
    required this.isCurrent,
    required this.personalRank,
    required this.recordedAt,
    required this.aggregationPolicy,
  });

  /// Monday start date of the ISO week in [timezone] (calendar date).
  final DateTime weekStart;

  /// Sunday end date of the ISO week in [timezone] (calendar date).
  final DateTime weekEnd;

  /// IANA timezone name used for week boundaries (e.g. `Asia/Karachi`, `UTC`).
  final String timezone;

  /// Style score for this week (60..100).
  final int styleScore;

  /// Score component breakdown.
  final LearningSummaryBreakdown breakdown;

  /// Distinct styled days recorded within this week (0..7).
  final int styledDaysCount;

  /// Total learning signals recorded within this week (>= 0).
  final int signalsCount;

  /// True for the live current week; false for historical snapshots.
  final bool isCurrent;

  /// 1-based personal competition rank among the user's own weeks.
  final int personalRank;

  /// UTC timestamp when the immutable snapshot was recorded, if persisted.
  final DateTime? recordedAt;

  /// Aggregation policy identifier (e.g. `end_of_week_score_v1`).
  final String aggregationPolicy;

  /// Short start date label for chart axes (e.g. `Nov 16`).
  String get shortStartLabel => _formatShortDate(weekStart);

  /// Clear date range label for weekly cards (e.g. `Nov 16 – 22` or
  /// `Nov 30 – Dec 6`).
  String get shortRangeLabel {
    final startMonth = _monthNames[weekStart.month - 1];
    final endMonth = _monthNames[weekEnd.month - 1];
    if (weekStart.month == weekEnd.month && weekStart.year == weekEnd.year) {
      return '$startMonth ${weekStart.day}–${weekEnd.day}';
    }
    return '$startMonth ${weekStart.day} – $endMonth ${weekEnd.day}';
  }

  factory WeeklyProgressItem.fromJson(Map<String, dynamic> json) {
    final recordedAtRaw = json['recordedAt'];
    return WeeklyProgressItem(
      weekStart: _parseIsoDate(json['weekStart'] as String),
      weekEnd: _parseIsoDate(json['weekEnd'] as String),
      timezone: json['timezone'] as String,
      styleScore: json['styleScore'] as int,
      breakdown: LearningSummaryBreakdown.fromJson(
        json['breakdown'] as Map<String, dynamic>,
      ),
      styledDaysCount: json['styledDaysCount'] as int,
      signalsCount: json['signalsCount'] as int,
      isCurrent: json['isCurrent'] as bool,
      personalRank: json['personalRank'] as int,
      recordedAt: recordedAtRaw is String
          ? DateTime.parse(recordedAtRaw)
          : null,
      aggregationPolicy: json['aggregationPolicy'] as String,
    );
  }

  Map<String, dynamic> toJson() => {
    'weekStart': _formatIsoDate(weekStart),
    'weekEnd': _formatIsoDate(weekEnd),
    'timezone': timezone,
    'styleScore': styleScore,
    'breakdown': breakdown.toJson(),
    'styledDaysCount': styledDaysCount,
    'signalsCount': signalsCount,
    'isCurrent': isCurrent,
    'personalRank': personalRank,
    'recordedAt': recordedAt?.toUtc().toIso8601String(),
    'aggregationPolicy': aggregationPolicy,
  };
}

/// Personal-only weekly comparison metrics (never cross-user).
class StyleJourneyComparison {
  const StyleJourneyComparison({
    required this.scoreDelta,
    required this.trend,
    required this.currentWeekRank,
    required this.totalRankedWeeks,
    required this.isTiedWithBest,
  });

  /// Score difference vs. previous week; null when previous week is absent.
  final int? scoreDelta;

  /// `'up'`, `'down'`, `'flat'`, or null when previous week is absent.
  final String? trend;

  /// Current week's 1-based personal rank across recorded weeks + current.
  final int currentWeekRank;

  /// Total number of ranked weeks (current + recorded historical weeks).
  final int totalRankedWeeks;

  /// True when current week's score ties [StyleJourneyHistory.bestHistoricalWeek].
  final bool isTiedWithBest;

  factory StyleJourneyComparison.fromJson(Map<String, dynamic> json) {
    return StyleJourneyComparison(
      scoreDelta: json['scoreDelta'] as int?,
      trend: json['trend'] as String?,
      currentWeekRank: json['currentWeekRank'] as int,
      totalRankedWeeks: json['totalRankedWeeks'] as int,
      isTiedWithBest: json['isTiedWithBest'] as bool,
    );
  }

  Map<String, dynamic> toJson() => {
    'scoreDelta': scoreDelta,
    'trend': trend,
    'currentWeekRank': currentWeekRank,
    'totalRankedWeeks': totalRankedWeeks,
    'isTiedWithBest': isTiedWithBest,
  };
}

/// Complete SJ1 Style Journey history response (`GET /v1/learning/journey/history`).
class StyleJourneyHistory {
  const StyleJourneyHistory({
    required this.timezone,
    required this.aggregationPolicy,
    required this.currentWeek,
    required this.previousWeek,
    required this.bestHistoricalWeek,
    required this.comparison,
    required this.weeks,
    required this.hasHistory,
  });

  final String timezone;
  final String aggregationPolicy;
  final WeeklyProgressItem currentWeek;
  final WeeklyProgressItem? previousWeek;
  final WeeklyProgressItem? bestHistoricalWeek;
  final StyleJourneyComparison comparison;

  /// Weeks returned by the backend (newest-first, up to `limit`).
  final List<WeeklyProgressItem> weeks;

  /// True when at least one historical snapshot exists prior to current week.
  final bool hasHistory;

  /// Recorded weeks ordered chronologically (oldest-first) for chart display.
  /// Never fabricates missing weeks.
  List<WeeklyProgressItem> get chronologicalWeeks {
    final sorted = List<WeeklyProgressItem>.from(weeks)
      ..sort((a, b) => a.weekStart.compareTo(b.weekStart));
    return sorted;
  }

  factory StyleJourneyHistory.fromJson(Map<String, dynamic> json) {
    final prevRaw = json['previousWeek'];
    final bestRaw = json['bestHistoricalWeek'];
    return StyleJourneyHistory(
      timezone: json['timezone'] as String,
      aggregationPolicy: json['aggregationPolicy'] as String,
      currentWeek: WeeklyProgressItem.fromJson(
        json['currentWeek'] as Map<String, dynamic>,
      ),
      previousWeek: prevRaw is Map<String, dynamic>
          ? WeeklyProgressItem.fromJson(prevRaw)
          : null,
      bestHistoricalWeek: bestRaw is Map<String, dynamic>
          ? WeeklyProgressItem.fromJson(bestRaw)
          : null,
      comparison: StyleJourneyComparison.fromJson(
        json['comparison'] as Map<String, dynamic>,
      ),
      weeks: (json['weeks'] as List)
          .map(
            (item) => WeeklyProgressItem.fromJson(item as Map<String, dynamic>),
          )
          .toList(),
      hasHistory: json['hasHistory'] as bool,
    );
  }

  Map<String, dynamic> toJson() => {
    'timezone': timezone,
    'aggregationPolicy': aggregationPolicy,
    'currentWeek': currentWeek.toJson(),
    'previousWeek': previousWeek?.toJson(),
    'bestHistoricalWeek': bestHistoricalWeek?.toJson(),
    'comparison': comparison.toJson(),
    'weeks': weeks.map((w) => w.toJson()).toList(),
    'hasHistory': hasHistory,
  };
}

DateTime _parseIsoDate(String raw) {
  final parts = raw.split('-');
  if (parts.length != 3) {
    throw FormatException('Invalid ISO date: $raw');
  }
  return DateTime.utc(
    int.parse(parts[0]),
    int.parse(parts[1]),
    int.parse(parts[2]),
  );
}

String _formatIsoDate(DateTime date) {
  final y = date.year.toString().padLeft(4, '0');
  final m = date.month.toString().padLeft(2, '0');
  final d = date.day.toString().padLeft(2, '0');
  return '$y-$m-$d';
}

const List<String> _monthNames = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

String _formatShortDate(DateTime date) {
  return '${_monthNames[date.month - 1]} ${date.day}';
}
