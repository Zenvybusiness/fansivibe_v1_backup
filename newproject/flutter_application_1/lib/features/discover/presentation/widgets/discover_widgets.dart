import 'package:flutter/material.dart';
import 'package:fansivibe/features/discover/data/discover_mock_data.dart';
import 'package:fansivibe/shared/components/fansi_badge.dart';
import 'package:fansivibe/shared/components/fansi_chip.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

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

    return FansivibeCard(
      onTap: onTap,
      padding: EdgeInsets.zero,
      child: LayoutBuilder(
        builder: (context, constraints) {
          final imageHeight = constraints.maxWidth * 4 / 3;
          final contentHeight = constraints.maxHeight - imageHeight;

          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                height: imageHeight,
                width: double.infinity,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    Container(
                      decoration: BoxDecoration(
                        color: FansivibeColors.surface,
                        borderRadius: const BorderRadius.vertical(
                          top: Radius.circular(16),
                        ),
                      ),
                      child: Stack(
                        fit: StackFit.expand,
                        children: [
                          Center(
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Semantics(
                                  image: true,
                                  label: 'Look image placeholder',
                                  child: Icon(
                                    Icons.checkroom_rounded,
                                    size: 40,
                                    color: FansivibeColors.accentGold
                                        .withValues(alpha: 0.3),
                                  ),
                                ),
                                const SizedBox(height: 6),
                                Text(
                                  'Look Image',
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: FansivibeColors.textSecondary
                                        .withValues(alpha: 0.7),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Positioned(
                            bottom: 0,
                            left: 0,
                            right: 0,
                            child: Container(
                              height: 50,
                              decoration: BoxDecoration(
                                borderRadius: const BorderRadius.vertical(
                                  top: Radius.circular(0),
                                  bottom: Radius.circular(16),
                                ),
                                gradient: LinearGradient(
                                  begin: Alignment.bottomCenter,
                                  end: Alignment.topCenter,
                                  colors: [
                                    FansivibeColors.background.withValues(
                                      alpha: 0.9,
                                    ),
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
                        top: 8,
                        left: 8,
                        child: FansiChip(
                          label: 'Trending',
                          icon: Icons.trending_up_rounded,
                          selected: true,
                        ),
                      ),
                    if (showMatchBadge)
                      Positioned(
                        top: 8,
                        right: 8,
                        child: FansiBadge(
                          score: data.matchScore,
                          size: BadgeSize.compact,
                        ),
                      ),
                  ],
                ),
              ),

              SizedBox(
                height: contentHeight,
                child: Padding(
                  padding: const EdgeInsets.all(10),
                  child: SingleChildScrollView(
                    physics: const NeverScrollableScrollPhysics(),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          data.title,
                          style: theme.textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w600,
                            color: FansivibeColors.textPrimary,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 3),
                        Text(
                          data.occasion,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: FansivibeColors.textSecondary,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 6),

                        Wrap(
                          spacing: 5,
                          runSpacing: 3,
                          children: [
                            ...data.styleTags
                                .take(2)
                                .map((tag) => _buildTag(context, tag)),
                            if (data.fitTags.isNotEmpty)
                              _buildTag(
                                context,
                                data.fitTags.first,
                                isFit: true,
                              ),
                          ],
                        ),
                        const SizedBox(height: 6),

                        if (data.wardrobeMatchCount > 0)
                          Row(
                            children: [
                              Icon(
                                Icons.checkroom_rounded,
                                size: 11,
                                color: FansivibeColors.accentGold.withValues(
                                  alpha: 0.8,
                                ),
                              ),
                              const SizedBox(width: 3),
                              Flexible(
                                child: Text(
                                  '${data.wardrobeMatchCount} items in your wardrobe',
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: FansivibeColors.accentGold
                                        .withValues(alpha: 0.8),
                                    fontWeight: FontWeight.w500,
                                    fontSize: 10,
                                  ),
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                            ],
                          ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          );
        },
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
            : FansivibeColors.surface,
        borderRadius: BorderRadius.circular(6),
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
          fontSize: 10,
        ),
      ),
    );
  }
}
