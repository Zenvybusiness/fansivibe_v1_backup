import 'package:flutter/material.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/utils/icon_utils.dart';

class WardrobeDashboardHeader extends StatelessWidget {
  const WardrobeDashboardHeader({
    required this.totalItems,
    required this.styleType,
    required this.favoritesCount,
    required this.categoryCount,
    super.key,
  });

  final int totalItems;
  final String styleType;
  final int favoritesCount;
  final int categoryCount;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: FansivibeColors.accentGold.withValues(alpha: 0.12),
                borderRadius: FansivibeRadius.smBorder,
              ),
              child: const Icon(
                Icons.checkroom_rounded,
                color: FansivibeColors.accentGold,
                size: 22,
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'My Wardrobe',
                    style: theme.textTheme.headlineMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: FansivibeColors.textPrimary,
                      fontSize: 24,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Row(
                    children: [
                      Text(
                        '$totalItems items',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: FansivibeColors.textSecondary,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: FansivibeColors.accentGold.withValues(
                            alpha: 0.1,
                          ),
                          borderRadius: FansivibeRadius.fullBorder,
                        ),
                        child: Text(
                          styleType,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: FansivibeColors.accentGold,
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        Row(
          children: [
            _buildStatTile(context, '$totalItems', 'Total items'),
            const SizedBox(width: 10),
            _buildStatTile(context, '$categoryCount', 'Categories'),
            const SizedBox(width: 10),
            _buildStatTile(
              context,
              '$favoritesCount',
              'Favorites',
              valueColor: FansivibeColors.accentGold,
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildStatTile(
    BuildContext context,
    String value,
    String label, {
    Color? valueColor,
  }) {
    final theme = Theme.of(context);

    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(
          color: FansivibeColors.surfaceContainerLow,
          borderRadius: FansivibeRadius.smBorder,
        ),
        child: Column(
          children: [
            Text(
              value,
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.bold,
                color: valueColor ?? FansivibeColors.textPrimary,
                fontFamily: 'sans-serif',
              ),
            ),
            const SizedBox(height: 2),
            Text(
              label,
              style: theme.textTheme.bodySmall?.copyWith(
                color: FansivibeColors.textSecondary,
                fontSize: 11,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class CategoryTile extends StatelessWidget {
  const CategoryTile({
    required this.name,
    required this.iconName,
    required this.count,
    required this.selected,
    required this.onTap,
    super.key,
  });

  final String name;
  final String iconName;
  final int count;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Semantics(
      button: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: FansivibeRadius.smBorder,
        child: Container(
          width: 72,
          padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 4),
          decoration: BoxDecoration(
            color: selected
                ? FansivibeColors.accentGold.withValues(alpha: 0.1)
                : FansivibeColors.surface,
            borderRadius: FansivibeRadius.smBorder,
            border: Border.all(
              color: selected
                  ? FansivibeColors.accentGold.withValues(alpha: 0.45)
                  : FansivibeColors.accentGold.withValues(alpha: 0.08),
              width: selected ? 1.5 : 1,
            ),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                iconFromName(iconName),
                size: 22,
                color: selected
                    ? FansivibeColors.accentGold
                    : FansivibeColors.textSecondary,
              ),
              const SizedBox(height: 6),
              Text(
                name == 'All Items' ? 'All' : name,
                style: theme.textTheme.bodySmall?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: selected
                      ? FansivibeColors.accentGold
                      : FansivibeColors.textSecondary,
                  fontSize: 10,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 2),
              Text(
                '$count',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: selected
                      ? FansivibeColors.accentGold
                      : FansivibeColors.textSecondary.withValues(alpha: 0.7),
                  fontSize: 10,
                  fontFamily: 'sans-serif',
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

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

    return FansivibeCard(
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
                  iconFromName(data.iconName),
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
            FansiButton.secondary(
              label: data.actionLabel,
              icon: Icons.arrow_forward_rounded,
              onPressed: onActionPressed,
              expanded: false,
            ),
          ],
        ],
      ),
    );
  }
}

class ClothingItemCard extends StatelessWidget {
  const ClothingItemCard({required this.item, this.onTap, super.key});

  final WardrobeItemData item;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final swatch = _colorFromName(item.color);

    return InkWell(
      onTap: onTap,
      borderRadius: FansivibeRadius.mdBorder,
      child: Container(
        decoration: BoxDecoration(
          color: FansivibeColors.surface,
          borderRadius: FansivibeRadius.mdBorder,
          border: Border.all(
            color: FansivibeColors.accentGold.withValues(alpha: 0.1),
          ),
        ),
        child: Column(
          children: [
            Expanded(
              flex: 3,
              child: Container(
                decoration: BoxDecoration(
                  color: swatch.withValues(alpha: 0.15),
                  borderRadius: const BorderRadius.vertical(
                    top: Radius.circular(24),
                  ),
                ),
                child: Stack(
                  children: [
                    Center(
                      child: Icon(
                        _categoryIcon(item.category),
                        size: 32,
                        color: swatch.withValues(alpha: 0.5),
                      ),
                    ),
                    if (item.isFavorite)
                      Positioned(
                        top: 6,
                        right: 6,
                        child: Container(
                          width: 24,
                          height: 24,
                          decoration: BoxDecoration(
                            color: FansivibeColors.surface.withValues(
                              alpha: 0.7,
                            ),
                            shape: BoxShape.circle,
                          ),
                          child: const Icon(
                            Icons.favorite_rounded,
                            size: 14,
                            color: FansivibeColors.accentGold,
                          ),
                        ),
                      ),
                    Positioned(
                      bottom: 6,
                      left: 6,
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 6,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: FansivibeColors.surface.withValues(alpha: 0.7),
                          borderRadius: FansivibeRadius.fullBorder,
                        ),
                        child: Text(
                          item.material ?? '',
                          style: theme.textTheme.bodySmall?.copyWith(
                            fontSize: 8,
                            color: FansivibeColors.textSecondary,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            Expanded(
              flex: 2,
              child: Padding(
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
                    const SizedBox(height: 4),
                    Row(
                      children: [
                        Container(
                          width: 10,
                          height: 10,
                          decoration: BoxDecoration(
                            color: swatch,
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: FansivibeColors.accentGold.withValues(
                                alpha: 0.2,
                              ),
                              width: 0.5,
                            ),
                          ),
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
        return const Color(0xFF444444);
      case 'black':
        return Colors.black;
      case 'white':
      case 'off-white':
        return const Color(0xFFE5E5E5);
      case 'cream':
        return const Color(0xFFFDF5E6);
      case 'navy':
        return const Color(0xFF1A237E);
      case 'indigo':
        return const Color(0xFF3F51B5);
      case 'blush':
        return const Color(0xFFDEBCCD);
      case 'beige':
        return const Color(0xFFE8D5B7);
      case 'khaki':
        return const Color(0xFFC3B091);
      case 'stone':
        return const Color(0xFFA0A0A0);
      case 'tan':
        return const Color(0xFFD2B48C);
      case 'light wash':
        return const Color(0xFFB5D2E0);
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

// Retained for backward compatibility.
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
