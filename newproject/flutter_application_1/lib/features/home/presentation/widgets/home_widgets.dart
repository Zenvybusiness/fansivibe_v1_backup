import 'package:flutter/material.dart';
import 'package:fansivibe/features/home/data/home_mock_data.dart';
import 'package:fansivibe/shared/components/fansi_badge.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/components/fansi_chip.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/components/section_title.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/utils/icon_utils.dart';
import 'package:fansivibe/shared/utils/score_colors.dart';

typedef HomeCard = FansivibeCard;
typedef HomeSectionTitle = SectionTitle;

/// A stat display widget for the Home feature.
class HomeStatItem extends StatelessWidget {
  /// Creates a [HomeStatItem].
  const HomeStatItem({
    required this.label,
    required this.value,
    this.valueStyle,
    this.icon,
    this.trend,
    super.key,
  });

  /// Stat label.
  final String label;

  /// Stat value.
  final String value;

  /// Custom value style.
  final TextStyle? valueStyle;

  /// Optional leading icon.
  final IconData? icon;

  /// Optional trend indicator.
  final StyleTrend? trend;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    Color trendColor;
    IconData trendIcon;

    switch (trend) {
      case StyleTrend.up:
        trendColor = const Color(0xFF4CAF50);
        trendIcon = Icons.trending_up_rounded;
        break;
      case StyleTrend.down:
        trendColor = const Color(0xFFF44336);
        trendIcon = Icons.trending_down_rounded;
        break;
      case StyleTrend.stable:
      case null:
        trendColor = FansivibeColors.textSecondary;
        trendIcon = Icons.trending_flat_rounded;
        break;
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            if (icon != null) ...[
              Icon(icon, size: 18, color: FansivibeColors.accentGold),
              const SizedBox(width: 8),
            ],
            Text(
              label,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: FansivibeColors.textSecondary,
              ),
            ),
            if (trend != null) ...[
              const SizedBox(width: 8),
              Icon(trendIcon, size: 14, color: trendColor),
            ],
          ],
        ),
        const SizedBox(height: 4),
        Text(
          value,
          style:
              valueStyle ??
              theme.textTheme.headlineMedium?.copyWith(
                fontWeight: FontWeight.bold,
                color: FansivibeColors.textPrimary,
                fontFamily: 'sans-serif',
              ),
        ),
      ],
    );
  }
}

/// A progress indicator widget for the Home feature.
class HomeProgressRing extends StatelessWidget {
  /// Creates a [HomeProgressRing].
  const HomeProgressRing({
    required this.progress,
    required this.label,
    this.size = 80,
    this.strokeWidth = 8,
    this.progressColor,
    this.backgroundColor,
    super.key,
  });

  /// Progress value (0.0 to 1.0).
  final double progress;

  /// Center label.
  final String label;

  /// Size of the ring.
  final double size;

  /// Stroke width.
  final double strokeWidth;

  /// Progress color.
  final Color? progressColor;

  /// Background color.
  final Color? backgroundColor;

  @override
  Widget build(BuildContext context) {
    final color = progressColor ?? FansivibeColors.accentGold;
    final bgColor =
        backgroundColor ?? FansivibeColors.accentGold.withValues(alpha: 0.15);

    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          SizedBox(
            width: size,
            height: size,
            child: CircularProgressIndicator(
              value: progress,
              strokeWidth: strokeWidth,
              backgroundColor: bgColor,
              valueColor: AlwaysStoppedAnimation<Color>(color),
              strokeCap: StrokeCap.round,
            ),
          ),
          SizedBox(
            width: size,
            height: size,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  '${(progress * 100).round()}%',
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: FansivibeColors.textPrimary,
                    fontFamily: 'sans-serif',
                    fontSize: size * 0.25,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2),
                Text(
                  label,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: FansivibeColors.textSecondary,
                    fontSize: size * 0.09,
                  ),
                  overflow: TextOverflow.ellipsis,
                  maxLines: 1,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// A streak day indicator widget.
class StreakDayIndicator extends StatelessWidget {
  /// Creates a [StreakDayIndicator].
  const StreakDayIndicator({
    required this.day,
    required this.styled,
    this.score,
    this.isToday = false,
    super.key,
  });

  /// Day label.
  final String day;

  /// Whether styled on this day.
  final bool styled;

  /// Style score (optional).
  final int? score;

  /// Whether this is today.
  final bool isToday;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: styled
                ? FansivibeColors.accentGold.withValues(alpha: 0.2)
                : FansivibeColors.surface,
            border: Border.all(
              color: isToday
                  ? FansivibeColors.accentGold
                  : (styled
                        ? FansivibeColors.accentGold.withValues(alpha: 0.4)
                        : FansivibeColors.accentGold.withValues(alpha: 0.1)),
              width: isToday ? 2.5 : 1,
            ),
            boxShadow: styled
                ? [
                    BoxShadow(
                      color: FansivibeColors.accentGold.withValues(alpha: 0.3),
                      blurRadius: 12,
                      offset: const Offset(0, 4),
                    ),
                  ]
                : null,
          ),
          child: Center(
            child: styled
                ? Icon(
                    Icons.check_rounded,
                    size: 20,
                    color: FansivibeColors.accentGold,
                  )
                : Icon(
                    Icons.close_rounded,
                    size: 16,
                    color: FansivibeColors.textSecondary.withValues(alpha: 0.5),
                  ),
          ),
        ),
        const SizedBox(height: 6),
        Text(
          day,
          style: theme.textTheme.bodyMedium?.copyWith(
            color: isToday
                ? FansivibeColors.accentGold
                : FansivibeColors.textSecondary,
            fontWeight: isToday ? FontWeight.w600 : FontWeight.normal,
          ),
        ),
        if (score != null && styled) ...[
          const SizedBox(height: 2),
          Text(
            '$score',
            style: theme.textTheme.bodySmall?.copyWith(
              color: FansivibeColors.accentGold,
              fontWeight: FontWeight.w600,
              fontFamily: 'sans-serif',
              fontSize: 10,
            ),
          ),
        ],
      ],
    );
  }
}

IconData outfitCategoryIcon(String category) {
  switch (category.toLowerCase()) {
    case 'outerwear':
      return Icons.checkroom_rounded;
    case 'tops':
      return Icons.person_rounded;
    case 'bottoms':
      return Icons.accessibility_rounded;
    case 'footwear':
      return Icons.directions_walk_rounded;
    case 'accessories':
      return Icons.diamond_rounded;
    default:
      return Icons.category_rounded;
  }
}

/// An AI insight card widget.
class AIInsightCard extends StatelessWidget {
  /// Creates an [AIInsightCard].
  const AIInsightCard({required this.data, this.onActionPressed, super.key});

  /// Insight data.
  final AIWardrobeInsightData data;

  /// Action callback.
  final VoidCallback? onActionPressed;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final accentColor = Color(data.accentColor);

    return FansivibeCard(
      borderColor: accentColor.withValues(alpha: 0.3),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: accentColor.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  _getIconData(data.iconName),
                  color: accentColor,
                  size: 22,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      data.title,
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                        color: FansivibeColors.textPrimary,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'AI Insight',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: accentColor,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Text(
            data.insight,
            style: theme.textTheme.bodyLarge?.copyWith(
              color: FansivibeColors.textPrimary,
              height: 1.5,
            ),
          ),
          if (onActionPressed != null) ...[
            const SizedBox(height: 16),
            FansiButton.secondary(
              label: data.actionLabel,
              icon: Icons.arrow_forward_rounded,
              onPressed: onActionPressed,
              expanded: false,
            ),
          ],
        ],
      ),
    );
  }

  IconData _getIconData(String iconName) => iconFromName(iconName);
}

/// Quick action card widget.
class QuickActionCard extends StatelessWidget {
  /// Creates a [QuickActionCard].
  const QuickActionCard({required this.data, this.onTap, super.key});

  /// Action data.
  final QuickActionData data;

  /// Tap callback.
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final accentColor = Color(data.accentColor);

    return Semantics(
      button: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: FansivibeCard(
          padding: const EdgeInsets.all(20),
          borderColor: accentColor.withValues(alpha: 0.2),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: accentColor.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(
                  _getIconData(data.iconName),
                  color: accentColor,
                  size: 24,
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      data.title,
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                        color: FansivibeColors.textPrimary,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      data.subtitle,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: FansivibeColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              Icon(
                Icons.chevron_right_rounded,
                color: FansivibeColors.textSecondary,
                size: 24,
              ),
            ],
          ),
        ),
      ),
    );
  }

  IconData _getIconData(String iconName) {
    switch (iconName) {
      case 'camera_alt_outlined':
        return Icons.camera_alt_outlined;
      case 'checkroom_outlined':
        return Icons.checkroom_outlined;
      case 'refresh_rounded':
        return Icons.refresh_rounded;
      case 'auto_awesome_outlined':
        return Icons.auto_awesome_outlined;
      case 'event_outlined':
        return Icons.event_outlined;
      default:
        return Icons.category_rounded;
    }
  }
}

/// Greeting header widget.
class GreetingHeader extends StatelessWidget {
  /// Creates a [GreetingHeader].
  const GreetingHeader({required this.data, super.key});

  /// Greeting data.
  final GreetingData data;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '${data.greeting}, ${data.name}',
          style: theme.textTheme.displayLarge?.copyWith(
            fontWeight: FontWeight.bold,
            color: FansivibeColors.textPrimary,
            fontSize: 28,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          data.dateLabel,
          style: theme.textTheme.bodyLarge?.copyWith(
            color: FansivibeColors.textSecondary,
          ),
        ),
      ],
    );
  }
}

/// Today's Look card widget.
class TodaysLookCard extends StatelessWidget {
  /// Creates a [TodaysLookCard].
  const TodaysLookCard({
    required this.data,
    this.onTryThisLook,
    this.onChangeStyle,
    super.key,
  });

  /// Today's look data.
  final TodaysLookData data;

  /// Callback for "Try This Look" action.
  final VoidCallback? onTryThisLook;

  /// Callback for "Change Style" action.
  final VoidCallback? onChangeStyle;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return FansivibeCard(
      padding: EdgeInsets.zero,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header with title and style score
          Padding(
            padding: const EdgeInsets.all(20),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 10,
                              vertical: 4,
                            ),
                            decoration: BoxDecoration(
                              color: FansivibeColors.accentGold.withValues(
                                alpha: 0.15,
                              ),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Text(
                              'TODAY\'S LOOK',
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: FansivibeColors.accentGold,
                                fontWeight: FontWeight.w700,
                                letterSpacing: 0.5,
                              ),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              data.title,
                              style: theme.textTheme.titleLarge?.copyWith(
                                fontWeight: FontWeight.w600,
                                color: FansivibeColors.textPrimary,
                              ),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        data.occasion,
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: FansivibeColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                _buildStyleScoreBadge(context),
              ],
            ),
          ),

          // Outfit image placeholder
          Container(
            height: 220,
            width: double.infinity,
            decoration: BoxDecoration(
              color: FansivibeColors.surface,
              borderRadius: BorderRadius.zero,
            ),
            child: Stack(
              fit: StackFit.expand,
              children: [
                // Placeholder for outfit image
                Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Semantics(
                        image: true,
                        label: 'Outfit image placeholder',
                        child: Icon(
                          Icons.checkroom_rounded,
                          size: 64,
                          color: FansivibeColors.accentGold.withValues(
                            alpha: 0.4,
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      Text(
                        'Outfit Image',
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: FansivibeColors.textSecondary,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        data.weather,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: FansivibeColors.textSecondary.withValues(
                            alpha: 0.7,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                // Gradient overlay at bottom
                Positioned(
                  bottom: 0,
                  left: 0,
                  right: 0,
                  child: Container(
                    height: 80,
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.bottomCenter,
                        end: Alignment.topCenter,
                        colors: [
                          FansivibeColors.background.withValues(alpha: 0.9),
                          Colors.transparent,
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),

          // Description
          Padding(
            padding: const EdgeInsets.all(20),
            child: Text(
              data.description,
              style: theme.textTheme.bodyLarge?.copyWith(
                color: FansivibeColors.textPrimary,
                height: 1.5,
              ),
            ),
          ),

          // Outfit items
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: Wrap(
              spacing: 10,
              runSpacing: 10,
              children: data.items
                  .map(
                    (item) => FansiChip(
                      label: item.name,
                      icon: outfitCategoryIcon(item.category),
                    ),
                  )
                  .toList(),
            ),
          ),

          const SizedBox(height: 20),

          // Action buttons
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
            child: LayoutBuilder(
              builder: (context, constraints) {
                final isNarrow = constraints.maxWidth < 320;
                if (isNarrow) {
                  return Column(
                    children: [
                      FansiButton.primary(
                        label: 'Try This Look',
                        icon: Icons.check_circle_outline_rounded,
                        onPressed: onTryThisLook,
                      ),
                      const SizedBox(height: 12),
                      FansiButton.secondary(
                        label: 'Change Style',
                        icon: Icons.refresh_rounded,
                        onPressed: onChangeStyle,
                      ),
                    ],
                  );
                }
                return Row(
                  children: [
                    Expanded(
                      child: FansiButton.primary(
                        label: 'Try This Look',
                        icon: Icons.check_circle_outline_rounded,
                        onPressed: onTryThisLook,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: FansiButton.secondary(
                        label: 'Change Style',
                        icon: Icons.refresh_rounded,
                        onPressed: onChangeStyle,
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStyleScoreBadge(BuildContext context) {
    return FansiBadge(score: data.styleScore);
  }
}

/// Style Score card widget.
class StyleScoreCard extends StatelessWidget {
  /// Creates a [StyleScoreCard].
  const StyleScoreCard({required this.data, super.key});

  /// Style score data.
  final StyleScoreData data;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    final trendColor = data.weeklyTrend == StyleTrend.up
        ? const Color(0xFF4CAF50)
        : data.weeklyTrend == StyleTrend.down
        ? const Color(0xFFF44336)
        : FansivibeColors.textSecondary;
    final trendIcon = data.weeklyTrend == StyleTrend.up
        ? Icons.trending_up_rounded
        : data.weeklyTrend == StyleTrend.down
        ? Icons.trending_down_rounded
        : Icons.trending_flat_rounded;

    return FansivibeCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Style Score',
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                        color: FansivibeColors.textPrimary,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Your weekly style performance',
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: FansivibeColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    '${data.currentScore}',
                    style: theme.textTheme.displayLarge?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: FansivibeColors.textPrimary,
                      fontFamily: 'sans-serif',
                      fontSize: 36,
                    ),
                  ),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(trendIcon, size: 16, color: trendColor),
                      const SizedBox(width: 4),
                      Text(
                        '${data.weeklyChange >= 0 ? '+' : ''}${data.weeklyChange} vs last week',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: trendColor,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 24),
          Row(
            children: data.breakdown
                .map(
                  (item) => Expanded(child: _buildBreakdownItem(context, item)),
                )
                .toList(),
          ),
        ],
      ),
    );
  }

  Widget _buildBreakdownItem(
    BuildContext context,
    StyleScoreBreakdownItem item,
  ) {
    final theme = Theme.of(context);
    final scoreColor = scoreColorFromDouble(item.score / 100);

    return Padding(
      padding: const EdgeInsets.only(right: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  item.category,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: FansivibeColors.textSecondary,
                    fontWeight: FontWeight.w500,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Text(
                '${item.score}',
                style: theme.textTheme.bodySmall?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: scoreColor,
                  fontFamily: 'sans-serif',
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: item.score / 100,
              minHeight: 6,
              backgroundColor: FansivibeColors.accentGold.withValues(
                alpha: 0.1,
              ),
              valueColor: AlwaysStoppedAnimation<Color>(scoreColor),
              borderRadius: BorderRadius.circular(4),
            ),
          ),
          const SizedBox(height: 4),
          Text(
            item.label,
            style: theme.textTheme.bodySmall?.copyWith(
              color: FansivibeColors.textSecondary,
              fontSize: 11,
            ),
          ),
        ],
      ),
    );
  }
}

/// Style Streak card widget.
class StyleStreakCard extends StatelessWidget {
  /// Creates a [StyleStreakCard].
  const StyleStreakCard({required this.data, super.key});

  /// Streak data.
  final StyleStreakData data;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final progress = data.thisWeekCount / data.weeklyGoal;

    return FansivibeCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Style Streak',
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                        color: FansivibeColors.textPrimary,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Keep your daily style momentum',
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: FansivibeColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              HomeProgressRing(
                progress: progress.clamp(0.0, 1.0),
                label: '${data.thisWeekCount}/${data.weeklyGoal}',
                size: 70,
                strokeWidth: 6,
              ),
            ],
          ),
          const SizedBox(height: 24),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _buildStatColumn(
                context,
                'Current',
                '${data.currentStreak}d',
                Icons.local_fire_department_rounded,
              ),
              _buildStatColumn(
                context,
                'Longest',
                '${data.longestStreak}d',
                Icons.emoji_events_rounded,
              ),
              _buildStatColumn(
                context,
                'Total',
                '${data.totalDaysStyled}d',
                Icons.calendar_today_rounded,
              ),
            ],
          ),
          const SizedBox(height: 24),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: data.recentActivity
                .map(
                  (day) => StreakDayIndicator(
                    day: day.day,
                    styled: day.styled,
                    score: day.styled ? day.score : null,
                    isToday: day.day == _getTodayLabel(),
                  ),
                )
                .toList(),
          ),
        ],
      ),
    );
  }

  Widget _buildStatColumn(
    BuildContext context,
    String label,
    String value,
    IconData icon,
  ) {
    final theme = Theme.of(context);

    return Column(
      children: [
        Icon(icon, color: FansivibeColors.accentGold, size: 22),
        const SizedBox(height: 8),
        Text(
          value,
          style: theme.textTheme.titleLarge?.copyWith(
            fontWeight: FontWeight.bold,
            color: FansivibeColors.textPrimary,
            fontFamily: 'sans-serif',
          ),
        ),
        const SizedBox(height: 2),
        Text(
          label,
          style: theme.textTheme.bodySmall?.copyWith(
            color: FansivibeColors.textSecondary,
          ),
        ),
      ],
    );
  }

  String _getTodayLabel() {
    const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    return days[DateTime.now().weekday - 1];
  }
}
