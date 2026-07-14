import 'package:flutter/material.dart';
import 'package:fansivibe/features/discover/data/discover_mock_data.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

/// A detail card used in LookDetailsScreen sections.
class LookDetailCard extends StatelessWidget {
  const LookDetailCard({
    required this.title,
    this.subtitle,
    required this.child,
    super.key,
  });

  final String title;
  final String? subtitle;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
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
          Text(
            title,
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w600,
              color: FansivibeColors.textPrimary,
            ),
          ),
          if (subtitle != null) ...[
            const SizedBox(height: 2),
            Text(
              subtitle!,
              style: theme.textTheme.bodySmall?.copyWith(
                color: FansivibeColors.textSecondary,
              ),
            ),
          ],
          const SizedBox(height: 14),
          child,
        ],
      ),
    );
  }
}

/// A row showing a score category label and its percentage bar.
class ScoreCategoryRow extends StatelessWidget {
  const ScoreCategoryRow({required this.label, required this.score, super.key});

  final String label;
  final int score;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    Color scoreColor;
    if (score >= 90) {
      scoreColor = const Color(0xFF4CAF50);
    } else if (score >= 80) {
      scoreColor = FansivibeColors.accentGold;
    } else if (score >= 70) {
      scoreColor = const Color(0xFFFF9800);
    } else {
      scoreColor = const Color(0xFFF44336);
    }

    return Row(
      children: [
        SizedBox(
          width: 100,
          child: Text(
            label,
            style: theme.textTheme.bodyMedium?.copyWith(
              fontWeight: FontWeight.w500,
              color: FansivibeColors.textPrimary,
            ),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: score / 100,
              minHeight: 8,
              backgroundColor: scoreColor.withValues(alpha: 0.15),
              valueColor: AlwaysStoppedAnimation<Color>(scoreColor),
            ),
          ),
        ),
        const SizedBox(width: 12),
        SizedBox(
          width: 36,
          child: Text(
            '$score%',
            style: theme.textTheme.bodySmall?.copyWith(
              fontWeight: FontWeight.w600,
              color: scoreColor,
            ),
            textAlign: TextAlign.right,
          ),
        ),
      ],
    );
  }
}

/// A recommendation reason row with icon and text.
class ReasonRow extends StatelessWidget {
  const ReasonRow({required this.reason, super.key});

  final RecommendationReason reason;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: FansivibeColors.accentGold.withValues(alpha: 0.1),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(reason.icon, size: 18, color: FansivibeColors.accentGold),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                reason.title,
                style: theme.textTheme.bodyMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.textPrimary,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                reason.description,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// A tag chip for style/fit display.
class LookTag extends StatelessWidget {
  const LookTag({required this.label, this.isFit = false, super.key});

  final String label;
  final bool isFit;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: isFit
            ? FansivibeColors.accentGold.withValues(alpha: 0.1)
            : FansivibeColors.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: isFit
              ? FansivibeColors.accentGold.withValues(alpha: 0.3)
              : FansivibeColors.accentGold.withValues(alpha: 0.15),
          width: 1,
        ),
      ),
      child: Text(
        label,
        style: theme.textTheme.bodySmall?.copyWith(
          color: isFit
              ? FansivibeColors.accentGold
              : FansivibeColors.textSecondary,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }
}

/// A row showing an ensemble component.
class ComponentRow extends StatelessWidget {
  const ComponentRow({required this.component, super.key});

  final EnsembleComponent component;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Row(
      children: [
        Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            color: FansivibeColors.accentGold.withValues(alpha: 0.1),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(
            Icons.checkroom_outlined,
            size: 22,
            color: FansivibeColors.accentGold,
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
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.textPrimary,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                '${component.color} · ${component.material} · ${component.fit}',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
        const SizedBox(width: 8),
        if (component.isOwned)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: const Color(0xFF4CAF50).withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Text(
              'Owned',
              style: theme.textTheme.bodySmall?.copyWith(
                color: const Color(0xFF4CAF50),
                fontWeight: FontWeight.w600,
                fontSize: 10,
              ),
            ),
          )
        else
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: FansivibeColors.accentGold.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Text(
              component.category,
              style: theme.textTheme.bodySmall?.copyWith(
                color: FansivibeColors.accentGold,
                fontWeight: FontWeight.w500,
                fontSize: 10,
              ),
            ),
          ),
      ],
    );
  }
}

/// A wardrobe alternatives section for a component category.
class AlternativeSection extends StatelessWidget {
  const AlternativeSection({required this.alternative, super.key});

  final WardrobeAlternative alternative;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Replace ${alternative.componentCategory}',
          style: theme.textTheme.bodyMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
          ),
        ),
        const SizedBox(height: 8),
        ...alternative.alternatives.map(
          (item) => Padding(
            padding: EdgeInsets.only(
              bottom: item == alternative.alternatives.last ? 0 : 8,
            ),
            child: _buildAlternativeItem(context, item),
          ),
        ),
      ],
    );
  }

  Widget _buildAlternativeItem(BuildContext context, WardrobeItem item) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: FansivibeColors.background,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.1),
          width: 1,
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: FansivibeColors.accentGold.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(
              Icons.checkroom_outlined,
              size: 18,
              color: FansivibeColors.accentGold.withValues(alpha: 0.6),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.name,
                  style: theme.textTheme.bodySmall?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: FansivibeColors.textPrimary,
                  ),
                ),
                Text(
                  item.color,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: FansivibeColors.textSecondary,
                    fontSize: 11,
                  ),
                ),
              ],
            ),
          ),
          if (item.isOwned)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
              decoration: BoxDecoration(
                color: const Color(0xFF4CAF50).withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                'Owned',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: const Color(0xFF4CAF50),
                  fontWeight: FontWeight.w600,
                  fontSize: 9,
                ),
              ),
            ),
          const SizedBox(width: 8),
          Text(
            '${item.matchScore}%',
            style: theme.textTheme.bodySmall?.copyWith(
              fontWeight: FontWeight.w700,
              color: FansivibeColors.accentGold,
            ),
          ),
        ],
      ),
    );
  }
}
