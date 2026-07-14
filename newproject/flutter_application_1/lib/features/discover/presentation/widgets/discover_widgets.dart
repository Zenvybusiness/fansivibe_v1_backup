import 'package:flutter/material.dart';
import 'package:fansivibe/features/discover/data/discover_mock_data.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

/// A premium card widget for the Discover feature.
class DiscoverCard extends StatelessWidget {
  /// Creates a [DiscoverCard].
  const DiscoverCard({
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.margin = EdgeInsets.zero,
    this.onTap,
    this.borderColor,
    super.key,
  });

  /// The child widget.
  final Widget child;

  /// Internal padding.
  final EdgeInsetsGeometry padding;

  /// External margin.
  final EdgeInsetsGeometry margin;

  /// Optional tap callback.
  final VoidCallback? onTap;

  /// Optional border color.
  final Color? borderColor;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final effectiveBorderColor =
        borderColor ?? FansivibeColors.accentGold.withValues(alpha: 0.15);

    Widget card = Container(
      margin: margin,
      padding: padding,
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: effectiveBorderColor, width: 1),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.25),
            blurRadius: 16,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: child,
    );

    if (onTap != null) {
      return Semantics(
        button: true,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(16),
          child: card,
        ),
      );
    }

    return card;
  }
}

/// A section title widget for the Discover feature.
class DiscoverSectionTitle extends StatelessWidget {
  /// Creates a [DiscoverSectionTitle].
  const DiscoverSectionTitle({
    required this.title,
    this.subtitle,
    this.actionLabel,
    this.onActionPressed,
    super.key,
  });

  /// Section title.
  final String title;

  /// Optional subtitle.
  final String? subtitle;

  /// Optional action label.
  final String? actionLabel;

  /// Optional action callback.
  final VoidCallback? onActionPressed;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: theme.textTheme.headlineMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: FansivibeColors.textPrimary,
                  ),
                ),
                if (subtitle != null) ...[
                  const SizedBox(height: 4),
                  Text(
                    subtitle!,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: FansivibeColors.textSecondary,
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (actionLabel != null && onActionPressed != null)
            TextButton(
              onPressed: onActionPressed,
              style: TextButton.styleFrom(
                foregroundColor: FansivibeColors.accentGold,
                padding: EdgeInsets.zero,
                minimumSize: const Size(0, 32),
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
              child: Text(
                actionLabel!,
                style: theme.textTheme.bodyMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.accentGold,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// A tab button for Discover tabs (For You / Trending).
class DiscoverTabButton extends StatelessWidget {
  /// Creates a [DiscoverTabButton].
  const DiscoverTabButton({
    required this.data,
    required this.isSelected,
    required this.onTap,
    super.key,
  });

  /// Tab data.
  final DiscoverTabData data;

  /// Whether this tab is selected.
  final bool isSelected;

  /// Tap callback.
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

/// A filter chip for Discover filters (Occasion, Style, Fit).
class DiscoverFilterChip extends StatelessWidget {
  /// Creates a [DiscoverFilterChip].
  const DiscoverFilterChip({
    required this.option,
    required this.onTap,
    super.key,
  });

  /// Filter option data.
  final FilterOption option;

  /// Tap callback.
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isSelected = option.isSelected;

    return Semantics(
      button: true,
      label: option.label,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(10),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: isSelected
                ? FansivibeColors.accentGold.withValues(alpha: 0.15)
                : FansivibeColors.surface,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: isSelected
                  ? FansivibeColors.accentGold
                  : FansivibeColors.accentGold.withValues(alpha: 0.1),
              width: isSelected ? 1.5 : 1,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                option.icon,
                size: 16,
                color: isSelected
                    ? FansivibeColors.accentGold
                    : FansivibeColors.textSecondary,
              ),
              const SizedBox(width: 6),
              Text(
                option.label,
                style: theme.textTheme.bodySmall?.copyWith(
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
  /// Creates a [DiscoverFilterChipsRow].
  const DiscoverFilterChipsRow({
    required this.options,
    required this.onOptionChanged,
    this.title,
    super.key,
  });

  /// Filter options.
  final List<FilterOption> options;

  /// Callback when an option changes.
  final void Function(FilterOption) onOptionChanged;

  /// Optional section title.
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
                child: DiscoverFilterChip(
                  option: option,
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

/// Match percentage badge widget.
class MatchPercentageBadge extends StatelessWidget {
  /// Creates a [MatchPercentageBadge].
  const MatchPercentageBadge({
    required this.percentage,
    this.size = 48,
    this.showLabel = true,
    super.key,
  });

  /// Match percentage (0-100).
  final int percentage;

  /// Badge size.
  final double size;

  /// Whether to show the "Match" label.
  final bool showLabel;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    Color scoreColor;

    if (percentage >= 90) {
      scoreColor = const Color(0xFF4CAF50);
    } else if (percentage >= 80) {
      scoreColor = FansivibeColors.accentGold;
    } else if (percentage >= 70) {
      scoreColor = const Color(0xFFFF9800);
    } else {
      scoreColor = const Color(0xFFF44336);
    }

    return Semantics(
      label: 'Match $percentage%',
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: size,
            height: size,
            child: Stack(
              fit: StackFit.expand,
              children: [
                CircularProgressIndicator(
                  value: percentage / 100,
                  strokeWidth: 4,
                  backgroundColor: scoreColor.withValues(alpha: 0.15),
                  valueColor: AlwaysStoppedAnimation<Color>(scoreColor),
                  strokeCap: StrokeCap.round,
                ),
                Center(
                  child: Text(
                    '$percentage%',
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: FansivibeColors.textPrimary,
                      fontFamily: 'sans-serif',
                      fontSize: size * 0.22,
                    ),
                  ),
                ),
              ],
            ),
          ),
          if (showLabel) ...[
            const SizedBox(height: 4),
            Text(
              'Match',
              style: theme.textTheme.bodySmall?.copyWith(
                color: FansivibeColors.textSecondary,
                fontSize: 10,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Trending badge widget.
class TrendingBadge extends StatelessWidget {
  /// Creates a [TrendingBadge].
  const TrendingBadge({this.label = 'Trending', super.key});

  /// Badge label.
  final String label;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: FansivibeColors.accentGold.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.3),
          width: 1,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.trending_up_rounded,
            size: 12,
            color: FansivibeColors.accentGold,
          ),
          const SizedBox(width: 4),
          Text(
            label,
            style: theme.textTheme.bodySmall?.copyWith(
              fontWeight: FontWeight.w700,
              color: FansivibeColors.accentGold,
              fontSize: 10,
              letterSpacing: 0.5,
            ),
          ),
        ],
      ),
    );
  }
}

/// Look card widget for Discover grid.
class LookCard extends StatelessWidget {
  /// Creates a [LookCard].
  const LookCard({
    required this.data,
    this.onTap,
    this.showMatchBadge = true,
    this.showTrendingBadge = false,
    super.key,
  });

  /// Look data.
  final DiscoverLookData data;

  /// Tap callback.
  final VoidCallback? onTap;

  /// Whether to show match percentage badge.
  final bool showMatchBadge;

  /// Whether to show trending badge.
  final bool showTrendingBadge;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return DiscoverCard(
      onTap: onTap,
      padding: EdgeInsets.zero,
      child: LayoutBuilder(
        builder: (context, constraints) {
          // Calculate available height for content
          final imageHeight = constraints.maxWidth * 4 / 3; // 3:4 aspect ratio
          final contentHeight = constraints.maxHeight - imageHeight;

          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Image area with badges
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
                          // Placeholder for look image
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
                          // Gradient overlay
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
                    // Trending badge
                    if (showTrendingBadge)
                      Positioned(top: 8, left: 8, child: TrendingBadge()),
                    // Match badge
                    if (showMatchBadge)
                      Positioned(
                        top: 8,
                        right: 8,
                        child: MatchPercentageBadge(
                          percentage: data.matchScore,
                          size: 36,
                          showLabel: false,
                        ),
                      ),
                  ],
                ),
              ),

              // Content - constrained to available height
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
                        // Title and occasion
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

                        // Style and fit tags
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

                        // Wardrobe match indicator
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
