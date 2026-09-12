import 'package:flutter/material.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_builder_mock_data.dart'
    hide OutfitComponent, OutfitRecommendation;
import 'package:fansivibe/features/outfit_builder/data/outfit_models.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/components/fansi_insight_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/utils/score_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

class OptionChip extends StatelessWidget {
  const OptionChip({
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
          borderRadius: FansivibeRadius.smdBorder,
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

class OptionSection extends StatelessWidget {
  const OptionSection({
    required this.title,
    required this.subtitle,
    required this.options,
    required this.selectedId,
    required this.onSelected,
    super.key,
  });

  final String title;
  final String subtitle;
  final List<BuilderOption> options;
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
            child: OptionChip(
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

class ScoreCircle extends StatelessWidget {
  const ScoreCircle({required this.score, required this.label, super.key});

  final double score;
  final String label;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scoreColor = _scoreColor(score);
    final percentage = (score * 100).round();

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: 100,
          height: 100,
          child: Stack(
            fit: StackFit.expand,
            children: [
              CircularProgressIndicator(
                value: score,
                strokeWidth: 6,
                backgroundColor: FansivibeColors.surface,
                valueColor: AlwaysStoppedAnimation<Color>(scoreColor),
              ),
              Center(
                child: Text(
                  '$percentage%',
                  style: theme.textTheme.displayLarge?.copyWith(
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                    color: scoreColor,
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        Text(
          label,
          style: theme.textTheme.bodyMedium?.copyWith(
            color: FansivibeColors.textSecondary,
          ),
        ),
      ],
    );
  }

  Color _scoreColor(double s) => scoreColorFromDouble(s);
}

class MetricCard extends StatelessWidget {
  const MetricCard({
    required this.icon,
    required this.title,
    required this.description,
    this.accentColor,
    super.key,
  });

  final IconData icon;
  final String title;
  final String description;
  final Color? accentColor;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: FansiInsightCard(
        icon: icon,
        title: title,
        body: description,
        accentColor: accentColor ?? FansivibeColors.accentGold,
      ),
    );
  }
}

class OutfitComponentCard extends StatelessWidget {
  const OutfitComponentCard({
    required this.component,
    required this.onReplace,
    super.key,
  });

  final OutfitComponent component;
  final VoidCallback onReplace;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    // No colorHex on the wire (no server source): neutral accent tint.
    const tint = FansivibeColors.accentGold;

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.smdBorder,
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: tint.withValues(alpha: 0.2),
              borderRadius: FansivibeRadius.smdBorder,
              border: Border.all(color: tint.withValues(alpha: 0.3)),
            ),
            child: Center(
              child: Icon(
                _categoryIcon(component.category),
                size: 20,
                color: tint,
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  component.name,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w500,
                    color: FansivibeColors.textPrimary,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2),
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        '${component.category} \u2022 ${component.color}',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: FansivibeColors.textSecondary,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    if (component.material != null) ...[
                      const SizedBox(width: 4),
                      Flexible(
                        child: Text(
                          component.material!,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: FansivibeColors.textSecondary.withValues(
                              alpha: 0.7,
                            ),
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  component.reason,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: FansivibeColors.accentGold.withValues(alpha: 0.8),
                    fontStyle: FontStyle.italic,
                    fontSize: 11,
                  ),
                  overflow: TextOverflow.ellipsis,
                  maxLines: 2,
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Flexible(
            child: FansiButton.secondary(
              label: 'Replace',
              onPressed: onReplace,
              expanded: false,
            ),
          ),
        ],
      ),
    );
  }

  IconData _categoryIcon(String category) {
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
}
