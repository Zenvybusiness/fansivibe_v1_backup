// import 'package:flutter/material.dart';

/// Mock data for personalized greeting.
class GreetingData {
  /// Creates a [GreetingData].
  const GreetingData({
    required this.greeting,
    required this.name,
    required this.dateLabel,
  });

  /// Greeting text (e.g., "Good morning").
  final String greeting;

  /// User's name.
  final String name;

  /// Date label (e.g., "Monday, January 13").
  final String dateLabel;

  /// Mock greeting data.
  static const GreetingData mock = GreetingData(
    greeting: 'Good morning',
    name: 'Alex',
    dateLabel: 'Monday, January 13',
  );
}

/// Mock data for Today's Look card.
class TodaysLookData {
  /// Creates a [TodaysLookData].
  const TodaysLookData({
    required this.title,
    required this.occasion,
    required this.weather,
    required this.description,
    required this.items,
    required this.styleScore,
  });

  /// Look title.
  final String title;

  /// Occasion label.
  final String occasion;

  /// Weather description.
  final String weather;

  /// Look description.
  final String description;

  /// Outfit items.
  final List<OutfitItemData> items;

  /// Style score (0-100).
  final int styleScore;

  /// Mock today's look data.
  static const TodaysLookData mock = TodaysLookData(
    title: 'Modern Minimalist',
    occasion: 'Work • Casual Friday',
    weather: '68°F • Partly Cloudy',
    description:
        'Clean lines meet relaxed sophistication. The unstructured blazer elevates the merino tee while the wool trousers keep it grounded. Perfect for transitioning from desk to drinks.',
    items: [
      OutfitItemData(
        id: '1',
        name: 'Charcoal Unstructured Blazer',
        category: 'outerwear',
        color: 'Charcoal',
      ),
      OutfitItemData(
        id: '2',
        name: 'Merino Wool Crewneck',
        category: 'tops',
        color: 'Off-White',
      ),
      OutfitItemData(
        id: '3',
        name: 'Tapered Wool Trousers',
        category: 'bottoms',
        color: 'Charcoal',
      ),
      OutfitItemData(
        id: '4',
        name: 'Leather Chelsea Boots',
        category: 'footwear',
        color: 'Black',
      ),
      OutfitItemData(
        id: '5',
        name: 'Minimalist Leather Belt',
        category: 'accessories',
        color: 'Black',
      ),
    ],
    styleScore: 87,
  );
}

/// Outfit item data.
class OutfitItemData {
  /// Creates an [OutfitItemData].
  const OutfitItemData({
    required this.id,
    required this.name,
    required this.category,
    required this.color,
  });

  /// Unique identifier.
  final String id;

  /// Item name.
  final String name;

  /// Category (outerwear, tops, bottoms, footwear, accessories).
  final String category;

  /// Color.
  final String color;
}

/// Style score data.
class StyleScoreData {
  /// Creates a [StyleScoreData].
  const StyleScoreData({
    required this.currentScore,
    required this.weeklyChange,
    required this.weeklyTrend,
    required this.breakdown,
  });

  /// Current style score (0-100).
  final int currentScore;

  /// Weekly change.
  final int weeklyChange;

  /// Weekly trend.
  final StyleTrend weeklyTrend;

  /// Score breakdown by category.
  final List<StyleScoreBreakdownItem> breakdown;

  /// Mock style score data.
  static const StyleScoreData mock = StyleScoreData(
    currentScore: 84,
    weeklyChange: 3,
    weeklyTrend: StyleTrend.up,
    breakdown: [
      StyleScoreBreakdownItem(
        category: 'Fit',
        score: 92,
        label: 'Excellent proportions',
      ),
      StyleScoreBreakdownItem(
        category: 'Color',
        score: 85,
        label: 'Good harmony',
      ),
      StyleScoreBreakdownItem(
        category: 'Occasion',
        score: 88,
        label: 'Well matched',
      ),
      StyleScoreBreakdownItem(
        category: 'Creativity',
        score: 72,
        label: 'Room to experiment',
      ),
    ],
  );
}

/// Style score breakdown item.
class StyleScoreBreakdownItem {
  /// Creates a [StyleScoreBreakdownItem].
  const StyleScoreBreakdownItem({
    required this.category,
    required this.score,
    required this.label,
  });

  /// Category name.
  final String category;

  /// Score (0-100).
  final int score;

  /// Descriptive label.
  final String label;
}

/// Style trend enum.
enum StyleTrend {
  /// Trending up.
  up,

  /// Trending down.
  down,

  /// Stable.
  stable,
}

/// Style streak data.
class StyleStreakData {
  /// Creates a [StyleStreakData].
  const StyleStreakData({
    required this.currentStreak,
    required this.longestStreak,
    required this.totalDaysStyled,
    required this.thisWeekCount,
    required this.weeklyGoal,
    required this.recentActivity,
  });

  /// Current streak in days.
  final int currentStreak;

  /// Longest streak in days.
  final int longestStreak;

  /// Total days styled.
  final int totalDaysStyled;

  /// Days styled this week.
  final int thisWeekCount;

  /// Weekly goal.
  final int weeklyGoal;

  /// Recent activity (last 7 days).
  final List<StreakDayData> recentActivity;

  /// Mock streak data.
  static const StyleStreakData mock = StyleStreakData(
    currentStreak: 12,
    longestStreak: 28,
    totalDaysStyled: 156,
    thisWeekCount: 4,
    weeklyGoal: 7,
    recentActivity: [
      StreakDayData(day: 'Mon', styled: true, score: 87),
      StreakDayData(day: 'Tue', styled: true, score: 84),
      StreakDayData(day: 'Wed', styled: true, score: 91),
      StreakDayData(day: 'Thu', styled: true, score: 88),
      StreakDayData(day: 'Fri', styled: false, score: null),
      StreakDayData(day: 'Sat', styled: false, score: null),
      StreakDayData(day: 'Sun', styled: false, score: null),
    ],
  );
}

/// Single day streak data.
class StreakDayData {
  /// Creates a [StreakDayData].
  const StreakDayData({required this.day, required this.styled, this.score});

  /// Day label (Mon, Tue, etc.).
  final String day;

  /// Whether styled on this day.
  final bool styled;

  /// Style score if styled.
  final int? score;
}

/// AI wardrobe insight data.
class AIWardrobeInsightData {
  /// Creates an [AIWardrobeInsightData].
  const AIWardrobeInsightData({
    required this.title,
    required this.insight,
    required this.iconName,
    required this.accentColor,
    required this.actionLabel,
    required this.actionRoute,
  });

  /// Insight title.
  final String title;

  /// Insight description.
  final String insight;

  /// Icon name.
  final String iconName;

  /// Accent color (as int).
  final int accentColor;

  /// Action button label.
  final String actionLabel;

  /// Action route.
  final String actionRoute;

  /// Mock AI wardrobe insight.
  static const AIWardrobeInsightData mock = AIWardrobeInsightData(
    title: 'Wardrobe Gap Detected',
    insight:
        'You have 3 navy blazers but no lightweight spring jackets. Adding a trench or chore coat would unlock 12+ new outfit combinations for transitional weather.',
    iconName: 'lightbulb_outline_rounded',
    accentColor: 0xFFC5A059,
    actionLabel: 'View Recommendations',
    actionRoute: '/wardrobe/gaps',
  );
}

/// Quick action data.
class QuickActionData {
  /// Creates a [QuickActionData].
  const QuickActionData({
    required this.id,
    required this.title,
    required this.subtitle,
    required this.iconName,
    required this.route,
    this.accentColor = 0xFFC5A059,
  });

  /// Unique identifier.
  final String id;

  /// Action title.
  final String title;

  /// Action subtitle.
  final String subtitle;

  /// Icon name.
  final String iconName;

  /// Navigation route.
  final String route;

  /// Accent color.
  final int accentColor;

  /// Mock quick actions.
  static const List<QuickActionData> mockActions = [
    QuickActionData(
      id: 'scan_outfit',
      title: 'Scan My Outfit',
      subtitle: 'Get AI analysis of your current look',
      iconName: 'camera_alt_outlined',
      route: '/scan',
      accentColor: 0xFFC5A059,
    ),
    QuickActionData(
      id: 'build_outfit',
      title: 'Build Outfit',
      subtitle: 'Create a look from your wardrobe',
      iconName: 'checkroom_outlined',
      route: '/outfit/build',
      accentColor: 0xFF8B7D6B,
    ),
    QuickActionData(
      id: 'change_style',
      title: 'Change Style',
      subtitle: 'Adjust today\'s recommendation',
      iconName: 'refresh_rounded',
      route: '/outfit/change',
      accentColor: 0xFF6B8E8E,
    ),
  ];
}
