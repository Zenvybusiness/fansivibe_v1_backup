import 'package:flutter/material.dart';
import 'package:fansivibe/features/discover/data/discover_mock_data.dart';
import 'package:fansivibe/shared/components/fansi_badge.dart';
import 'package:fansivibe/shared/components/fansi_chip.dart';
import 'package:fansivibe/shared/components/fansi_hero_card.dart';
import 'package:fansivibe/shared/components/fansi_image_well.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// A tab button for Discover tabs (For You / Trending).
class DiscoverTabButton extends StatelessWidget {
  const DiscoverTabButton({
    required this.data,
    required this.isSelected,
    required this.onTap,
    this.badge,
    super.key,
  });

  final DiscoverTabData data;
  final bool isSelected;
  final VoidCallback onTap;
  final Widget? badge;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Semantics(
      button: true,
      label: data.label,
      child: InkWell(
        onTap: onTap,
        borderRadius: FansivibeRadius.smdBorder,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
          decoration: BoxDecoration(
            color: isSelected
                ? FansivibeColors.accentGold.withValues(alpha: 0.15)
                : Colors.transparent,
            borderRadius: FansivibeRadius.smdBorder,
            border: Border.all(
              color: isSelected
                  ? FansivibeColors.accentGold.withValues(alpha: 0.4)
                  : FansivibeColors.accentGold.withValues(alpha: 0.08),
              width: 1,
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                data.icon,
                size: 18,
                color: isSelected
                    ? FansivibeColors.accentGold
                    : FansivibeColors.textSecondary,
              ),
              const SizedBox(width: 8),
              Flexible(
                child: Text(
                  data.label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: isSelected
                        ? FansivibeColors.accentGold
                        : FansivibeColors.textSecondary,
                  ),
                ),
              ),
              if (badge != null) ...[
                const SizedBox(width: 6),
                badge!,
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// A horizontal filter chips row for Discover.
class DiscoverFilterChipsRow extends StatelessWidget {
  const DiscoverFilterChipsRow({
    required this.options,
    required this.onOptionChanged,
    this.title,
    super.key,
  });

  final List<FilterOption> options;
  final void Function(FilterOption) onOptionChanged;
  final String? title;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (title != null) ...[
          Text(
            title!,
            style: theme.textTheme.bodySmall?.copyWith(
              fontWeight: FontWeight.w600,
              color: FansivibeColors.textSecondary,
              letterSpacing: 0.5,
            ),
          ),
          const SizedBox(height: 8),
        ],
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: options.map((option) {
              return Padding(
                padding: const EdgeInsets.only(right: 8),
                child: FansiChip(
                  label: option.label,
                  icon: option.icon,
                  selected: option.isSelected,
                  onTap: () => onOptionChanged(option),
                ),
              );
            }).toList(),
          ),
        ),
      ],
    );
  }
}

/// Look card widget for Discover grid.
class LookCard extends StatelessWidget {
  const LookCard({
    required this.data,
    this.onTap,
    this.showMatchBadge = true,
    this.showTrendingBadge = false,
    super.key,
  });

  final DiscoverLookData data;
  final VoidCallback? onTap;
  final bool showMatchBadge;
  final bool showTrendingBadge;

  @override
  Widget build(BuildContext context) {
    final tags = <String>[
      ...data.styleTags.take(2),
      if (data.fitTags.isNotEmpty) data.fitTags.first,
    ];

    return FansiHeroCard(
      onTap: onTap,
      image: Stack(
        fit: StackFit.expand,
        children: [
          FansiImageWell(
            icon: _categoryIcon(data.occasion),
            color: FansivibeColors.accentGold,
          ),
          if (showTrendingBadge)
            Positioned(
              top: FansivibeSpacing.md,
              left: FansivibeSpacing.md,
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: FansivibeSpacing.sm + 2,
                  vertical: 4,
                ),
                decoration: BoxDecoration(
                  color: FansivibeColors.accentGold,
                  borderRadius: FansivibeRadius.fullBorder,
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(
                      Icons.trending_up_rounded,
                      size: 12,
                      color: FansivibeColors.onPrimary,
                    ),
                    const SizedBox(width: 3),
                    Text(
                      'Trending',
                      style: FansivibeTypography.labelSmallWithFamily.copyWith(
                        color: FansivibeColors.onPrimary,
                        fontWeight: FontWeight.w700,
                        fontSize: 9,
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
      title: data.title,
      subtitle: data.occasion,
      tags: tags.take(2).toList(),
      badge: showMatchBadge
          ? FansiBadge(score: data.matchScore, size: BadgeSize.compact)
          : null,
    );
  }

  IconData _categoryIcon(String occasion) {
    switch (occasion.toLowerCase()) {
      case 'work':
      case 'business':
        return Icons.business_center_rounded;
      case 'casual':
      case 'weekend':
        return Icons.wb_sunny_rounded;
      case 'evening':
        return Icons.nightlife_rounded;
      case 'event':
        return Icons.event_rounded;
      case 'travel':
        return Icons.flight_rounded;
      default:
        return Icons.checkroom_rounded;
    }
  }
}
