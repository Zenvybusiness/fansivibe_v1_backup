import 'package:flutter/material.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/utils/score_colors.dart';

/// Loading placeholder for a backend summary slot (M10-C).
///
/// Keeps the slot title visible so surrounding layout stays stable while
/// the summary loads. Never poses a value.
class SummaryLoadingCard extends StatelessWidget {
  const SummaryLoadingCard({required this.title, super.key});

  final String title;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return FansivibeCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w600,
              color: FansivibeColors.textPrimary,
            ),
          ),
          const SizedBox(height: 16),
          const Center(
            child: SizedBox(
              width: 28,
              height: 28,
              child: CircularProgressIndicator(strokeWidth: 3),
            ),
          ),
        ],
      ),
    );
  }
}

/// Error placeholder for a backend summary slot (M10-C).
///
/// Keeps the slot title visible with a truthful message and retry.
/// Never fabricates a score or streak.
class SummaryErrorCard extends StatelessWidget {
  const SummaryErrorCard({
    required this.title,
    required this.message,
    required this.onRetry,
    super.key,
  });

  final String title;
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return FansivibeCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w600,
              color: FansivibeColors.textPrimary,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            message,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: FansivibeColors.textSecondary,
            ),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh_rounded, size: 18),
            label: const Text('Try Again'),
            style: FilledButton.styleFrom(
              shape: RoundedRectangleBorder(
                borderRadius: FansivibeRadius.fullBorder,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Backend-fed style score card (M10-C, STEP 19.16).
///
/// Renders the server-authoritative [LearningSummary.styleScore] in the
/// existing Home slot visual language. No weekly trend chip and no
/// category grid: the backend summary carries neither, and inventing
/// them would fabricate data.
class BackendStyleScoreCard extends StatelessWidget {
  const BackendStyleScoreCard({required this.summary, super.key});

  final LearningSummary summary;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final score = summary.styleScore;
    final scoreColor = scoreColorFromDouble(score / 100);

    return FansivibeCard(
      child: Row(
        children: [
          SizedBox(
            width: 88,
            height: 88,
            child: Stack(
              alignment: Alignment.center,
              children: [
                SizedBox(
                  width: 88,
                  height: 88,
                  child: CircularProgressIndicator(
                    value: score / 100,
                    strokeWidth: 7,
                    backgroundColor: scoreColor.withValues(alpha: 0.1),
                    valueColor: AlwaysStoppedAnimation<Color>(scoreColor),
                    strokeCap: StrokeCap.round,
                  ),
                ),
                Container(
                  width: 62,
                  height: 62,
                  decoration: BoxDecoration(
                    color: scoreColor.withValues(alpha: 0.08),
                    shape: BoxShape.circle,
                  ),
                  alignment: Alignment.center,
                  child: Text(
                    '$score',
                    style: theme.textTheme.headlineMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: scoreColor,
                      fontSize: 26,
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 20),
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
                const SizedBox(height: 2),
                Text(
                  'From your wardrobe and saved looks',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: FansivibeColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Backend-fed style streak card (M10-C, STEP 19.16).
///
/// Renders the server-authoritative [LearningSummary.streak] count in the
/// existing Home slot visual language. No week path and no stat bar: the
/// backend summary carries only the current count, and inventing the
/// rest would fabricate data.
class BackendStyleStreakCard extends StatelessWidget {
  const BackendStyleStreakCard({required this.streak, super.key});

  final int streak;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final fireColor = streak >= 7
        ? const Color(0xFFFF6B35)
        : FansivibeColors.accentGold;

    return FansivibeCard(
      child: Row(
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
                  'Consecutive styled days',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: FansivibeColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
          Flexible(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              decoration: BoxDecoration(
                color: fireColor.withValues(alpha: 0.12),
                borderRadius: FansivibeRadius.fullBorder,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.local_fire_department_rounded,
                    size: 18,
                    color: fireColor,
                  ),
                  const SizedBox(width: 6),
                  Flexible(
                    child: Text(
                      '$streak-day streak',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: fireColor,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
