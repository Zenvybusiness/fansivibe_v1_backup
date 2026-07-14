import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/utils/score_colors.dart';
import 'package:fansivibe/features/grooming/data/grooming_mock_data.dart';

class GroomingOptionChip extends StatelessWidget {
  const GroomingOptionChip({
    required this.label,
    required this.icon,
    required this.description,
    required this.isSelected,
    required this.onTap,
    super.key,
  });

  final String label;
  final IconData icon;
  final String description;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final selectedColor = FansivibeColors.accentGold;

    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: isSelected
              ? selectedColor.withValues(alpha: 0.1)
              : FansivibeColors.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: isSelected
                ? selectedColor.withValues(alpha: 0.6)
                : FansivibeColors.textSecondary.withValues(alpha: 0.15),
            width: isSelected ? 1.5 : 1,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  icon,
                  size: 20,
                  color: isSelected
                      ? selectedColor
                      : FansivibeColors.textSecondary,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    label,
                    style: theme.textTheme.bodyLarge?.copyWith(
                      fontWeight: isSelected
                          ? FontWeight.w600
                          : FontWeight.w500,
                      color: isSelected
                          ? FansivibeColors.textPrimary
                          : FansivibeColors.textSecondary,
                    ),
                  ),
                ),
                if (isSelected)
                  Icon(
                    Icons.check_circle_rounded,
                    size: 18,
                    color: selectedColor,
                  ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              description,
              style: theme.textTheme.bodySmall?.copyWith(
                color: FansivibeColors.textSecondary.withValues(alpha: 0.7),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class GroomingOptionSection extends StatelessWidget {
  const GroomingOptionSection({
    required this.title,
    required this.subtitle,
    required this.options,
    required this.selectedId,
    required this.onSelected,
    super.key,
  });

  final String title;
  final String subtitle;
  final List<GroomingOption> options;
  final String? selectedId;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: theme.textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
            fontSize: 20,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          subtitle,
          style: theme.textTheme.bodyMedium?.copyWith(
            color: FansivibeColors.textSecondary,
          ),
        ),
        const SizedBox(height: 12),
        ...options.map(
          (option) => Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: GroomingOptionChip(
              label: option.label,
              icon: option.icon,
              description: option.description,
              isSelected: selectedId == option.id,
              onTap: () => onSelected(option.id),
            ),
          ),
        ),
      ],
    );
  }
}

class GroomingStageIndicator extends StatelessWidget {
  const GroomingStageIndicator({
    required this.stage,
    required this.isActive,
    required this.isComplete,
    super.key,
  });

  final GroomingProcessingStage stage;
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

class GroomingRecommendationCard extends StatelessWidget {
  const GroomingRecommendationCard({
    required this.recommendation,
    required this.onTap,
    this.isCompact = false,
    super.key,
  });

  final GroomingRecommendation recommendation;
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

  Color _scoreColor(double s) => scoreColorFromDouble(s);
}
