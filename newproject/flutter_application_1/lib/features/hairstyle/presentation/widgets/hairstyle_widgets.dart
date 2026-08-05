import 'package:flutter/material.dart';
import 'package:fansivibe/shared/components/fansi_badge.dart';
import 'package:fansivibe/shared/components/fansi_hero_card.dart';
import 'package:fansivibe/shared/components/fansi_image_well.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

class FacePreviewPlaceholder extends StatelessWidget {
  const FacePreviewPlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      height: 320,
      width: double.infinity,
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: FansivibeRadius.baseBorder,
      ),
      child: Stack(
        fit: StackFit.expand,
        children: [
          Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 140,
                  height: 180,
                  decoration: BoxDecoration(
                    shape: BoxShape.rectangle,
                    borderRadius: FansivibeRadius.fullBorder,
                    border: Border.all(
                      color: FansivibeColors.accentGold.withValues(alpha: 0.5),
                      width: 2,
                    ),
                  ),
                  child: Icon(
                    Icons.face_rounded,
                    size: 80,
                    color: FansivibeColors.accentGold.withValues(alpha: 0.3),
                  ),
                ),
                const SizedBox(height: 16),
                Text(
                  'Position your face within the oval guide',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: FansivibeColors.textSecondary.withValues(alpha: 0.7),
                  ),
                ),
              ],
            ),
          ),
          Positioned(
            top: 12,
            right: 12,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: FansivibeColors.accentGold.withValues(alpha: 0.2),
                borderRadius: FansivibeRadius.smBorder,
                border: Border.all(
                  color: FansivibeColors.accentGold.withValues(alpha: 0.4),
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    width: 8,
                    height: 8,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      valueColor: AlwaysStoppedAnimation<Color>(
                        FansivibeColors.accentGold,
                      ),
                    ),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    'Face Detection Active',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: FansivibeColors.accentGold,
                      fontWeight: FontWeight.w600,
                      fontSize: 11,
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

class HairstyleCheckIndicator extends StatelessWidget {
  const HairstyleCheckIndicator({
    required this.label,
    required this.isPassing,
    super.key,
  });

  final String label;
  final bool isPassing;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = isPassing
        ? FansivibeColors.success
        : FansivibeColors.textSecondary.withValues(alpha: 0.5);

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(
          isPassing
              ? Icons.check_circle_rounded
              : Icons.hourglass_empty_rounded,
          size: 14,
          color: color,
        ),
        const SizedBox(width: 6),
        Flexible(
          child: Text(
            label,
            style: theme.textTheme.bodySmall?.copyWith(
              color: color,
              fontWeight: isPassing ? FontWeight.w500 : FontWeight.normal,
            ),
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );
  }
}

class HairstyleStageIndicator extends StatelessWidget {
  const HairstyleStageIndicator({
    required this.stage,
    required this.isActive,
    required this.isComplete,
    super.key,
  });

  final HairstyleProcessingStage stage;
  final bool isActive;
  final bool isComplete;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final Color iconColor;
    final Widget icon;

    if (isComplete) {
      iconColor = FansivibeColors.success;
      icon = Icon(Icons.check_circle_rounded, size: 22, color: iconColor);
    } else if (isActive) {
      iconColor = FansivibeColors.accentGold;
      icon = SizedBox(
        width: 22,
        height: 22,
        child: CircularProgressIndicator(
          strokeWidth: 2.5,
          valueColor: AlwaysStoppedAnimation<Color>(iconColor),
        ),
      );
    } else {
      iconColor = FansivibeColors.textSecondary.withValues(alpha: 0.3);
      icon = Icon(
        Icons.radio_button_unchecked_rounded,
        size: 22,
        color: iconColor,
      );
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          icon,
          const SizedBox(width: 14),
          Expanded(
            child: Text(
              stage.label,
              style: theme.textTheme.bodyLarge?.copyWith(
                color: isComplete
                    ? FansivibeColors.textPrimary
                    : isActive
                    ? FansivibeColors.textPrimary
                    : FansivibeColors.textSecondary.withValues(alpha: 0.4),
                fontWeight: isActive ? FontWeight.w600 : FontWeight.normal,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}

class HairstyleCard extends StatelessWidget {
  const HairstyleCard({
    required this.recommendation,
    required this.onTap,
    this.isCompact = false,
    super.key,
  });

  final HairstyleRecommendation recommendation;
  final VoidCallback onTap;
  final bool isCompact;

  @override
  Widget build(BuildContext context) {
    final percentage = (recommendation.matchScore * 100).round();

    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: SizedBox(
        height: 240,
        child: FansiHeroCard(
          onTap: onTap,
          eyebrow: isCompact ? null : 'TOP RECOMMENDATION',
          image: FansiImageWell(
            icon: recommendation.icon,
            color: FansivibeColors.accentGold,
            iconSize: 44,
          ),
          badge: FansiBadge(score: percentage),
          title: recommendation.name,
          subtitle: isCompact ? null : recommendation.bestFor,
        ),
      ),
    );
  }
}
