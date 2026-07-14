import 'package:flutter/material.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

/// A premium card widget for the Wardrobe feature.
class WardrobeCard extends StatelessWidget {
  const WardrobeCard({
    required this.child,
    this.padding = const EdgeInsets.all(20),
    this.margin = EdgeInsets.zero,
    this.onTap,
    this.borderColor,
    super.key,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final EdgeInsetsGeometry margin;
  final VoidCallback? onTap;
  final Color? borderColor;

  @override
  Widget build(BuildContext context) {
    final effectiveBorderColor =
        borderColor ?? FansivibeColors.accentGold.withValues(alpha: 0.2);

    Widget card = Container(
      margin: margin,
      padding: padding,
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: effectiveBorderColor, width: 1),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.3),
            blurRadius: 20,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: child,
    );

    if (onTap != null) {
      return InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: card,
      );
    }

    return card;
  }
}

/// Wardrobe header with title, item count, and style type.
class WardrobeHeader extends StatelessWidget {
  const WardrobeHeader({
    required this.totalItems,
    required this.styleType,
    super.key,
  });

  final int totalItems;
  final String styleType;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'My Wardrobe',
          style: theme.textTheme.displayLarge?.copyWith(
            fontWeight: FontWeight.bold,
            color: FansivibeColors.textPrimary,
            fontSize: 28,
          ),
        ),
        const SizedBox(height: 4),
        Row(
          children: [
            Icon(
              Icons.checkroom_rounded,
              size: 16,
              color: FansivibeColors.accentGold,
            ),
            const SizedBox(width: 6),
            Text(
              '$totalItems items',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: FansivibeColors.textSecondary,
              ),
            ),
            const SizedBox(width: 16),
            Icon(
              Icons.style_rounded,
              size: 16,
              color: FansivibeColors.accentGold,
            ),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                styleType,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

/// AI Wardrobe Insight card.
class WardrobeInsightCard extends StatelessWidget {
  const WardrobeInsightCard({
    required this.data,
    this.onActionPressed,
    super.key,
  });

  final WardrobeInsightData data;
  final VoidCallback? onActionPressed;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final accentColor = Color(data.accentColor);

    return WardrobeCard(
      borderColor: accentColor.withValues(alpha: 0.3),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: accentColor.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  _getIconData(data.iconName),
                  color: accentColor,
                  size: 22,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      data.title,
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                        color: FansivibeColors.textPrimary,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'AI Insight',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: accentColor,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Text(
            data.insight,
            style: theme.textTheme.bodyLarge?.copyWith(
              color: FansivibeColors.textPrimary,
              height: 1.5,
            ),
          ),
          if (onActionPressed != null) ...[
            const SizedBox(height: 16),
            _WardrobeActionButton(
              label: data.actionLabel,
              icon: Icons.arrow_forward_rounded,
              onPressed: onActionPressed,
              accentColor: accentColor,
            ),
          ],
        ],
      ),
    );
  }

  IconData _getIconData(String iconName) {
    switch (iconName) {
      case 'lightbulb_outline_rounded':
        return Icons.lightbulb_outline_rounded;
      case 'trending_up_rounded':
        return Icons.trending_up_rounded;
      case 'insights_rounded':
        return Icons.insights_rounded;
      case 'psychology_rounded':
        return Icons.psychology_rounded;
      case 'auto_awesome_rounded':
        return Icons.auto_awesome_rounded;
      default:
        return Icons.lightbulb_outline_rounded;
    }
  }
}

/// Secondary outline action button for Wardrobe.
class _WardrobeActionButton extends StatelessWidget {
  const _WardrobeActionButton({
    required this.label,
    required this.icon,
    this.onPressed,
    this.accentColor,
  });

  final String label;
  final IconData icon;
  final VoidCallback? onPressed;
  final Color? accentColor;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = accentColor ?? FansivibeColors.accentGold;

    return FilledButton.icon(
      onPressed: onPressed,
      icon: Icon(icon, size: 18),
      label: Text(
        label,
        style: theme.textTheme.bodyMedium?.copyWith(
          fontWeight: FontWeight.w600,
          color: color,
        ),
        overflow: TextOverflow.ellipsis,
      ),
      style: FilledButton.styleFrom(
        backgroundColor: color.withValues(alpha: 0.15),
        foregroundColor: color,
        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 16),
        minimumSize: const Size(0, 44),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
    );
  }
}

/// Category filter chip for the wardrobe.
class CategoryFilterChip extends StatelessWidget {
  const CategoryFilterChip({
    required this.category,
    required this.isSelected,
    required this.onTap,
    super.key,
  });

  final WardrobeCategory category;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: isSelected
              ? FansivibeColors.accentGold.withValues(alpha: 0.2)
              : FansivibeColors.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: isSelected
                ? FansivibeColors.accentGold
                : FansivibeColors.accentGold.withValues(alpha: 0.15),
            width: isSelected ? 1.5 : 1,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              _getIconData(category.iconName),
              size: 16,
              color: isSelected
                  ? FansivibeColors.accentGold
                  : FansivibeColors.textSecondary,
            ),
            const SizedBox(width: 8),
            Text(
              category.name,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: isSelected
                    ? FansivibeColors.accentGold
                    : FansivibeColors.textSecondary,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
              ),
            ),
          ],
        ),
      ),
    );
  }

  IconData _getIconData(String iconName) {
    switch (iconName) {
      case 'checkroom_rounded':
        return Icons.checkroom_rounded;
      case 'person_rounded':
        return Icons.person_rounded;
      case 'accessibility_rounded':
        return Icons.accessibility_rounded;
      case 'directions_walk_rounded':
        return Icons.directions_walk_rounded;
      case 'diamond_rounded':
        return Icons.diamond_rounded;
      default:
        return Icons.category_rounded;
    }
  }
}

/// A single clothing item card for the grid.
class ClothingItemCard extends StatelessWidget {
  const ClothingItemCard({required this.item, this.onTap, super.key});

  final WardrobeItemData item;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Container(
        decoration: BoxDecoration(
          color: FansivibeColors.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: FansivibeColors.accentGold.withValues(alpha: 0.12),
            width: 1,
          ),
        ),
        child: Stack(
          children: [
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Container(
                    decoration: BoxDecoration(
                      color: FansivibeColors.surface,
                      borderRadius: const BorderRadius.vertical(
                        top: Radius.circular(16),
                      ),
                    ),
                    child: Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            _categoryIcon(item.category),
                            size: 28,
                            color: FansivibeColors.accentGold.withValues(
                              alpha: 0.5,
                            ),
                          ),
                          const SizedBox(height: 6),
                          Text(
                            item.material ?? '',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: FansivibeColors.textSecondary.withValues(
                                alpha: 0.6,
                              ),
                              fontSize: 10,
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(10, 8, 10, 10),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item.name,
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: FansivibeColors.textPrimary,
                          fontWeight: FontWeight.w500,
                          fontSize: 12,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 2),
                      Row(
                        children: [
                          Icon(
                            Icons.circle_rounded,
                            size: 8,
                            color: _colorFromName(item.color),
                          ),
                          const SizedBox(width: 4),
                          Expanded(
                            child: Text(
                              item.color,
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: FansivibeColors.textSecondary,
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
              ],
            ),
            if (item.isFavorite)
              const Positioned(
                top: 8,
                right: 8,
                child: Icon(
                  Icons.favorite_rounded,
                  size: 16,
                  color: FansivibeColors.accentGold,
                ),
              ),
          ],
        ),
      ),
    );
  }

  IconData _categoryIcon(String category) {
    switch (category) {
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

  Color _colorFromName(String colorName) {
    switch (colorName.toLowerCase()) {
      case 'charcoal':
      case 'black':
        return Colors.black;
      case 'white':
      case 'cream':
      case 'off-white':
        return const Color(0xFFE5E5E5);
      case 'navy':
      case 'indigo':
        return const Color(0xFF1A237E);
      case 'blush':
      case 'beige':
      case 'khaki':
      case 'stone':
      case 'tan':
      case 'light wash':
        return const Color(0xFFD7CCC8);
      case 'light blue':
        return const Color(0xFF81D4FA);
      case 'burgundy':
        return const Color(0xFF880E4F);
      case 'brown':
        return const Color(0xFF795548);
      case 'silver':
        return const Color(0xFFBDBDBD);
      default:
        return FansivibeColors.textSecondary;
    }
  }
}

/// Section title for wardrobe sections.
class WardrobeSectionTitle extends StatelessWidget {
  const WardrobeSectionTitle({required this.title, this.subtitle, super.key});

  final String title;
  final String? subtitle;

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
    );
  }
}

/// Full-width primary action button for Wardrobe.
class WardrobeActionButton extends StatelessWidget {
  const WardrobeActionButton({
    required this.label,
    required this.icon,
    this.onPressed,
    super.key,
  });

  final String label;
  final IconData icon;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SizedBox(
      width: double.infinity,
      child: FilledButton.icon(
        onPressed: onPressed,
        icon: Icon(icon, size: 18),
        label: Text(
          label,
          style: theme.textTheme.bodyMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.background,
          ),
          overflow: TextOverflow.ellipsis,
        ),
        style: FilledButton.styleFrom(
          backgroundColor: FansivibeColors.accentGold,
          foregroundColor: FansivibeColors.background,
          padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 16),
          minimumSize: const Size(0, 48),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          elevation: 4,
          shadowColor: FansivibeColors.accentGold.withValues(alpha: 0.3),
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
      ),
    );
  }
}
