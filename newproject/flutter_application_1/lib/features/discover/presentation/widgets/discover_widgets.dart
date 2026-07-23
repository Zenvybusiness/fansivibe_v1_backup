import 'package:flutter/material.dart';
import 'package:fansivibe/features/discover/data/discover_mock_data.dart';
import 'package:fansivibe/shared/components/fansi_badge.dart';
import 'package:fansivibe/shared/components/fansi_chip.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

/// A tab button for Discover tabs (For You / Trending).
class DiscoverTabButton extends StatelessWidget {
  const DiscoverTabButton({
    required this.data,
    required this.isSelected,
    required this.onTap,
    super.key,
  });

  final DiscoverTabData data;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Semantics(
      button: true,
      label: data.label,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
          decoration: BoxDecoration(
            color: isSelected
                ? FansivibeColors.accentGold.withValues(alpha: 0.15)
                : Colors.transparent,
            borderRadius: BorderRadius.circular(12),
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
              Text(
                data.label,
                style: theme.textTheme.bodyMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: isSelected
                      ? FansivibeColors.accentGold
                      : FansivibeColors.textSecondary,
                ),
              ),
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
    final theme = Theme.of(context);

    return Semantics(
      button: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: FansivibeRadius.mdBorder,
        child: FansivibeCard(
          padding: EdgeInsets.zero,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                height: 140,
                width: double.infinity,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    Container(
                      decoration: BoxDecoration(
                        color: FansivibeColors.surface,
                        borderRadius: const BorderRadius.vertical(
                          top: Radius.circular(24),
                        ),
                      ),
                      child: Stack(
                        fit: StackFit.expand,
                        children: [
                          Center(
                            child: Icon(
                              _categoryIcon(data.occasion),
                              size: 32,
                              color: FansivibeColors.accentGold.withValues(
                                alpha: 0.25,
                              ),
                            ),
                          ),
                          Positioned(
                            bottom: 0,
                            left: 0,
                            right: 0,
                            child: Container(
                              height: 40,
                              decoration: BoxDecoration(
                                borderRadius: const BorderRadius.vertical(
                                  bottom: Radius.circular(24),
                                ),
                                gradient: LinearGradient(
                                  begin: Alignment.bottomCenter,
                                  end: Alignment.topCenter,
                                  colors: [
                                    FansivibeColors.background,
                                    Colors.transparent,
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (showTrendingBadge)
                      Positioned(
                        top: 6,
                        left: 6,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 6,
                            vertical: 3,
                          ),
                          decoration: BoxDecoration(
                            color: FansivibeColors.accentGold,
                            borderRadius: FansivibeRadius.fullBorder,
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                Icons.trending_up_rounded,
                                size: 10,
                                color: FansivibeColors.onPrimary,
                              ),
                              const SizedBox(width: 3),
                              Text(
                                'Trending',
                                style: theme.textTheme.bodySmall?.copyWith(
                                  color: FansivibeColors.onPrimary,
                                  fontWeight: FontWeight.w700,
                                  fontSize: 9,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    if (showMatchBadge)
                      Positioned(
                        top: 6,
                        right: 6,
                        child: FansiBadge(
                          score: data.matchScore,
                          size: BadgeSize.compact,
                        ),
                      ),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.all(10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      data.title,
                      style: theme.textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.w600,
                        color: FansivibeColors.textPrimary,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 2),
                    Row(
                      children: [
                        Icon(
                          Icons.calendar_today_rounded,
                          size: 10,
                          color: FansivibeColors.textSecondary.withValues(
                            alpha: 0.6,
                          ),
                        ),
                        const SizedBox(width: 3),
                        Flexible(
                          child: Text(
                            data.occasion,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: FansivibeColors.textSecondary,
                              fontSize: 10,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Wrap(
                      spacing: 4,
                      runSpacing: 3,
                      children: [
                        ...data.styleTags
                            .take(2)
                            .map((tag) => _buildTag(context, tag)),
                        if (data.fitTags.isNotEmpty)
                          _buildTag(context, data.fitTags.first, isFit: true),
                      ],
                    ),
                    if (data.wardrobeMatchCount > 0) ...[
                      const SizedBox(height: 6),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 6,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: FansivibeColors.accentGold.withValues(
                            alpha: 0.1,
                          ),
                          borderRadius: FansivibeRadius.fullBorder,
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              Icons.checkroom_rounded,
                              size: 10,
                              color: FansivibeColors.accentGold.withValues(
                                alpha: 0.8,
                              ),
                            ),
                            const SizedBox(width: 3),
                            Text(
                              '${data.wardrobeMatchCount} in wardrobe',
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: FansivibeColors.accentGold.withValues(
                                  alpha: 0.8,
                                ),
                                fontWeight: FontWeight.w600,
                                fontSize: 9,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTag(BuildContext context, String label, {bool isFit = false}) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: isFit
            ? FansivibeColors.accentGold.withValues(alpha: 0.1)
            : FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.smBorder,
        border: Border.all(
          color: isFit
              ? FansivibeColors.accentGold.withValues(alpha: 0.3)
              : FansivibeColors.accentGold.withValues(alpha: 0.1),
        ),
      ),
      child: Text(
        label,
        style: theme.textTheme.bodySmall?.copyWith(
          color: isFit
              ? FansivibeColors.accentGold
              : FansivibeColors.textSecondary,
          fontWeight: FontWeight.w500,
          fontSize: 10,
        ),
      ),
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
