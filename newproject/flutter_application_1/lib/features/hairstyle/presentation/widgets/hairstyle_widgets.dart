import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';

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
        borderRadius: BorderRadius.circular(20),
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
                    borderRadius: BorderRadius.circular(90),
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
                borderRadius: BorderRadius.circular(8),
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
        ? const Color(0xFF4CAF50)
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
      iconColor = const Color(0xFF4CAF50);
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
    final theme = Theme.of(context);
    final scoreColor = _scoreColor(recommendation.matchScore);
    final percentage = (recommendation.matchScore * 100).round();

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Container(
        margin: const EdgeInsets.only(bottom: 14),
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: FansivibeColors.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: FansivibeColors.accentGold.withValues(alpha: 0.15),
            width: 1,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: FansivibeColors.accentGold.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(
                    recommendation.icon,
                    size: 24,
                    color: FansivibeColors.accentGold,
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        recommendation.name,
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w600,
                          color: FansivibeColors.textPrimary,
                        ),
                      ),
                      if (!isCompact) ...[
                        const SizedBox(height: 2),
                        Text(
                          recommendation.bestFor,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: FansivibeColors.textSecondary,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: scoreColor.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(
                      color: scoreColor.withValues(alpha: 0.3),
                    ),
                  ),
                  child: Text(
                    '$percentage%',
                    style: theme.textTheme.bodySmall?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: scoreColor,
                    ),
                  ),
                ),
              ],
            ),
            if (!isCompact) ...[
              const SizedBox(height: 12),
              Text(
                recommendation.description,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: FansivibeColors.textPrimary,
                  height: 1.5,
                ),
              ),
              const SizedBox(height: 10),
              ...recommendation.reasons
                  .take(2)
                  .map(
                    (reason) => Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '\u2022',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: FansivibeColors.accentGold,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          const SizedBox(width: 6),
                          Expanded(
                            child: Text(
                              reason,
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: FansivibeColors.textSecondary,
                                height: 1.4,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Icon(
                    Icons.content_cut_rounded,
                    size: 12,
                    color: FansivibeColors.accentGold.withValues(alpha: 0.7),
                  ),
                  const SizedBox(width: 4),
                  Flexible(
                    child: Text(
                      recommendation.maintenance,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: FansivibeColors.accentGold.withValues(
                          alpha: 0.7,
                        ),
                        fontSize: 11,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  Color _scoreColor(double s) {
    if (s >= 0.9) return const Color(0xFF4CAF50);
    if (s >= 0.7) return FansivibeColors.accentGold;
    if (s >= 0.5) return const Color(0xFFFF9800);
    return const Color(0xFFF44336);
  }
}
