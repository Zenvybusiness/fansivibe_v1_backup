import 'package:flutter/material.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

/// Backend-fed style summary section for Profile (M10-C, STEP 19.16).
///
/// Renders the server-authoritative streak, frozen score breakdown, and
/// recent signal labels verbatim. Labels are truthful only — no
/// interpretations ("balanced", "neglected", …), no AI explanations, no
/// unsupported claims. Data-only: loading/error states live with the
/// caller, which shares the screen's summary future.
class StyleSummarySection extends StatelessWidget {
  const StyleSummarySection({required this.summary, super.key});

  final LearningSummary summary;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return FansivibeCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Style Summary',
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w600,
              color: FansivibeColors.textPrimary,
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Icon(
                Icons.local_fire_department_rounded,
                size: 18,
                color: FansivibeColors.accentGold,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  '${summary.streak}-day streak',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: FansivibeColors.textPrimary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            'Consecutive styled days',
            style: theme.textTheme.bodySmall?.copyWith(
              color: FansivibeColors.textSecondary,
            ),
          ),
          const SizedBox(height: 16),
          Text(
            'Score breakdown',
            style: theme.textTheme.bodySmall?.copyWith(
              color: FansivibeColors.textSecondary,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          _buildBreakdownRow(context, 'Base', '${summary.breakdown.base}'),
          _buildBreakdownRow(
            context,
            'Wardrobe',
            '+${summary.breakdown.wardrobePoints}',
          ),
          _buildBreakdownRow(
            context,
            'Saved looks',
            '+${summary.breakdown.savedPoints}',
          ),
          const SizedBox(height: 8),
          _buildBreakdownRow(
            context,
            'Total',
            '${summary.breakdown.total}',
            isTotal: true,
          ),
          const SizedBox(height: 16),
          Text(
            'Recent activity',
            style: theme.textTheme.bodySmall?.copyWith(
              color: FansivibeColors.textSecondary,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          if (summary.recentSignals.isEmpty)
            Text(
              'No recent activity yet.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: FansivibeColors.textSecondary,
              ),
            )
          else
            ...summary.recentSignals.map(
              (label) => Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Container(
                        width: 6,
                        height: 6,
                        decoration: const BoxDecoration(
                          color: FansivibeColors.accentGold,
                          shape: BoxShape.circle,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        label,
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: FansivibeColors.textPrimary,
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

  Widget _buildBreakdownRow(
    BuildContext context,
    String label,
    String value, {
    bool isTotal = false,
  }) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: FansivibeColors.textSecondary,
                fontWeight: isTotal ? FontWeight.w600 : FontWeight.normal,
              ),
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: FansivibeColors.surfaceContainerLow,
              borderRadius: FansivibeRadius.smBorder,
            ),
            child: Text(
              value,
              style: theme.textTheme.bodySmall?.copyWith(
                fontWeight: FontWeight.bold,
                color: FansivibeColors.textPrimary,
                fontFamily: 'sans-serif',
              ),
            ),
          ),
        ],
      ),
    );
  }
}
