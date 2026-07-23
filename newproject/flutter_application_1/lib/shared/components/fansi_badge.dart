import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// A small score / status badge used for match percentages, style scores, etc.
///
/// Colour is derived from [score]:
/// - >= 90 → `success` (green)
/// - >= 70 → `primary` (gold)
/// - >= 50 → `warning` (orange)
/// - < 50  → `error` (red)
class FansiBadge extends StatelessWidget {
  const FansiBadge({
    required this.score,
    this.size = BadgeSize.medium,
    super.key,
  });

  final int score;
  final BadgeSize size;

  @override
  Widget build(BuildContext context) {
    final color = _scoreColor;
    final isCompact = size == BadgeSize.compact;

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: isCompact ? 8 : 12,
        vertical: isCompact ? 3 : 6,
      ),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(
          isCompact ? FansivibeRadius.sm : FansivibeRadius.md,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.star_rounded, size: isCompact ? 12 : 16, color: color),
          const SizedBox(width: 4),
          Text(
            '$score%',
            style:
                (isCompact
                        ? FansivibeTypography.labelSmallWithFamily
                        : FansivibeTypography.labelMediumWithFamily)
                    .copyWith(fontWeight: FontWeight.bold, color: color),
          ),
        ],
      ),
    );
  }

  Color get _scoreColor {
    if (score >= 90) return FansivibeColors.success;
    if (score >= 70) return FansivibeColors.primary;
    if (score >= 50) return FansivibeColors.warning;
    return FansivibeColors.error;
  }
}

enum BadgeSize { compact, medium }
