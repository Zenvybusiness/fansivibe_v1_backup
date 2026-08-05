import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// Insight card — content-forward card family for AI surfaces.
///
/// Horizontal split of **20% visual / 80% content** (enforced with `Expanded`
/// flex on the leading visual column).
///
/// Used for: AI Insights, Style DNA, Progress, Tips, Analytics.
///
/// Rules:
/// - Content is the focus; the leading visual is a compact medallion.
/// - Content stays concise and ellipsized. Additional information belongs on
///   a detail page, not in a taller card.
/// - Tonal surface, `md` corner radius, no borders, no divider lines,
///   no drop shadows.
class FansiInsightCard extends StatelessWidget {
  const FansiInsightCard({
    required this.icon,
    required this.title,
    required this.body,
    this.eyebrow,
    this.accentColor = FansivibeColors.primary,
    this.actionLabel,
    this.onActionPressed,
    this.onTap,
    super.key,
  });

  /// Leading visual icon.
  final IconData icon;

  /// Insight title.
  final String title;

  /// Insight body text.
  final String body;

  /// Small label under the title (e.g. "AI Insight").
  final String? eyebrow;

  /// Accent colour for the icon medallion and eyebrow.
  final Color accentColor;

  /// Optional trailing action label.
  final String? actionLabel;

  /// Action callback for [actionLabel].
  final VoidCallback? onActionPressed;

  /// Whole-card tap.
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: onTap != null,
      child: ClipRRect(
        borderRadius: FansivibeRadius.mdBorder,
        child: Material(
          color: FansivibeColors.surfaceContainer,
          child: InkWell(
            onTap: onTap,
            child: LayoutBuilder(
              builder: (context, constraints) {
                final isBounded = constraints.maxHeight.isFinite;
                return Padding(
                  padding: const EdgeInsets.all(FansivibeSpacing.md),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        flex: 20,
                        child: Center(child: _buildMedallion(context)),
                      ),
                      const SizedBox(width: FansivibeSpacing.md),
                      Expanded(
                        flex: 80,
                        child: _buildContent(context, bounded: isBounded),
                      ),
                    ],
                  ),
                );
              },
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildMedallion(BuildContext context) {
    return Container(
      width: 44,
      height: 44,
      decoration: BoxDecoration(
        color: accentColor.withValues(alpha: 0.15),
        borderRadius: FansivibeRadius.smdBorder,
      ),
      child: Icon(icon, size: 22, color: accentColor),
    );
  }

  Widget _buildContent(BuildContext context, {required bool bounded}) {
    return Column(
      mainAxisSize: bounded ? MainAxisSize.max : MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _bounded(
          bounded,
          Text(
            title,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: FansivibeTypography.titleLargeWithFamily.copyWith(
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        if (eyebrow != null) ...[
          const SizedBox(height: 2),
          Text(
            eyebrow!,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: FansivibeTypography.labelSmallWithFamily.copyWith(
              color: accentColor,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
        const SizedBox(height: FansivibeSpacing.sm),
        _bounded(
          bounded,
          Text(
            body,
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.onSurface,
              height: 1.5,
            ),
          ),
        ),
        if (actionLabel != null && onActionPressed != null) ...[
          const SizedBox(height: FansivibeSpacing.sm + 2),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              onPressed: onActionPressed,
              style: TextButton.styleFrom(
                foregroundColor: FansivibeColors.primary,
                padding: EdgeInsets.zero,
                minimumSize: const Size(0, 32),
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Flexible(
                    child: Text(
                      actionLabel!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: FansivibeTypography.labelMediumWithFamily.copyWith(
                        color: FansivibeColors.primary,
                      ),
                    ),
                  ),
                  const SizedBox(width: 4),
                  const Icon(Icons.arrow_forward_rounded, size: 14),
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }

  Widget _bounded(bool bounded, Text text) {
    return bounded ? Flexible(child: text) : text;
  }
}
