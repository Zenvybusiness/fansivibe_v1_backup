import 'package:flutter/material.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                'My Wardrobe',
                style: FansivibeTypography.headlineMediumWithFamily,
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(
                horizontal: FansivibeSpacing.md,
                vertical: FansivibeSpacing.sm,
              ),
              decoration: BoxDecoration(
                color: FansivibeColors.primary.withValues(alpha: 0.12),
                borderRadius: FansivibeRadius.fullBorder,
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.favorite_rounded,
                    size: 14,
                    color: FansivibeColors.primary,
                  ),
                  const SizedBox(width: 6),
                  Text(
                    '$favoritesCount',
                    style: FansivibeTypography.labelMediumWithFamily.copyWith(
                      color: FansivibeColors.primary,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: FansivibeSpacing.xs + 2),
        Row(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
              decoration: BoxDecoration(
                color: FansivibeColors.primary.withValues(alpha: 0.12),
                borderRadius: FansivibeRadius.fullBorder,
              ),
              child: Text(
                styleType,
                style: FansivibeTypography.labelSmallWithFamily.copyWith(
                  color: FansivibeColors.primary,
                  fontWeight: FontWeight.w600,
                  fontSize: 10,
                ),
              ),
            ),
            const SizedBox(width: FansivibeSpacing.sm),
            Text(
              '$totalItems items',
              style: FansivibeTypography.labelSmallWithFamily.copyWith(
                color: FansivibeColors.secondary.withValues(alpha: 0.6),
              ),
            ),
            const Spacer(),
            SizedBox(
              height: 30,
              child: _buildGlassmorphicButton(
                icon: Icons.tune_rounded,
                onTap: () {},
              ),
            ),
            const SizedBox(width: FansivibeSpacing.xs),
            SizedBox(
              height: 30,
              child: _buildGlassmorphicButton(
                icon: Icons.sort_rounded,
                onTap: () {},
              ),
            ),
          ],
        ),
        const SizedBox(height: FansivibeSpacing.xs + 2),
        _buildSearchBar(),
      ],
    );
  }

  Widget _buildSearchBar() {
    return Container(
      height: 34,
      padding: const EdgeInsets.symmetric(horizontal: FansivibeSpacing.md),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.fullBorder,
      ),
      child: Row(
        children: [
          Icon(
            Icons.search_rounded,
            size: 14,
            color: FansivibeColors.secondary.withValues(alpha: 0.6),
          ),
          const SizedBox(width: FansivibeSpacing.sm),
          Expanded(
            child: Text(
              'Search your wardrobe...',
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.secondary.withValues(alpha: 0.5),
                fontSize: 12,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildGlassmorphicButton({
    required IconData icon,
    required VoidCallback onTap,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: FansivibeRadius.fullBorder,
        child: Container(
          width: 30,
          decoration: BoxDecoration(
            color: FansivibeColors.surfaceContainerLow.withValues(alpha: 0.6),
            borderRadius: FansivibeRadius.fullBorder,
          ),
          child: Icon(icon, size: 14, color: FansivibeColors.secondary),
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
    return Semantics(
      button: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: FansivibeRadius.fullBorder,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOutCubic,
          padding: const EdgeInsets.symmetric(
            horizontal: FansivibeSpacing.lg,
            vertical: FansivibeSpacing.sm + 2,
          ),
          decoration: BoxDecoration(
            color: selected
                ? FansivibeColors.primary.withValues(alpha: 0.15)
                : FansivibeColors.surfaceContainerLow,
            borderRadius: FansivibeRadius.fullBorder,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                iconFromName(iconName),
                size: 16,
                color: selected
                    ? FansivibeColors.primary
                    : FansivibeColors.secondary,
              ),
              const SizedBox(width: FansivibeSpacing.sm),
              Text(
                name == 'All Items' ? 'All' : name,
                style: FansivibeTypography.labelSmallWithFamily.copyWith(
                  fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
                  color: selected
                      ? FansivibeColors.primary
                      : FansivibeColors.secondary,
                ),
              ),
              const SizedBox(width: FansivibeSpacing.xs),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: selected
                      ? FansivibeColors.primary.withValues(alpha: 0.2)
                      : FansivibeColors.surfaceContainerHighest,
                  borderRadius: FansivibeRadius.fullBorder,
                ),
                child: Text(
                  '$count',
                  style: FansivibeTypography.labelSmallWithFamily.copyWith(
                    fontSize: 9,
                    fontWeight: FontWeight.w600,
                    color: selected
                        ? FansivibeColors.primary
                        : FansivibeColors.secondary.withValues(alpha: 0.7),
                  ),
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
    final accentColor = Color(data.accentColor);

    return Container(
      padding: const EdgeInsets.all(FansivibeSpacing.md),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainer,
        borderRadius: FansivibeRadius.mdBorder,
      ),
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
                      style: FansivibeTypography.titleLargeWithFamily,
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'AI Insight',
                      style: FansivibeTypography.labelSmallWithFamily.copyWith(
                        color: accentColor,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: FansivibeSpacing.sm + 4),
          Text(
            data.insight,
            style: FansivibeTypography.bodyLargeWithFamily.copyWith(
              color: FansivibeColors.onSurface,
              height: 1.5,
            ),
          ),
          if (onActionPressed != null) ...[
            const SizedBox(height: FansivibeSpacing.sm + 4),
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

class ClothingItemCard extends StatefulWidget {
  const ClothingItemCard({required this.item, this.onTap, super.key});

  final WardrobeItemData item;
  final VoidCallback? onTap;

  @override
  State<ClothingItemCard> createState() => _ClothingItemCardState();
}

class _ClothingItemCardState extends State<ClothingItemCard>
    with SingleTickerProviderStateMixin {
  late AnimationController _animController;
  late Animation<double> _scaleAnim;

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(
      duration: const Duration(milliseconds: 200),
      vsync: this,
    );
    _scaleAnim = Tween<double>(begin: 1.0, end: 0.97).animate(
      CurvedAnimation(parent: _animController, curve: Curves.easeOutCubic),
    );
  }

  @override
  void dispose() {
    _animController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final item = widget.item;
    final swatch = _colorFromName(item.color);

    return AnimatedBuilder(
      animation: _scaleAnim,
      builder: (context, child) {
        return Transform.scale(scale: _scaleAnim.value, child: child);
      },
      child: GestureDetector(
        onTapDown: (_) => _animController.forward(),
        onTapUp: (_) {
          _animController.reverse();
          widget.onTap?.call();
        },
        onTapCancel: () => _animController.reverse(),
        child: Container(
          decoration: BoxDecoration(
            color: FansivibeColors.surfaceContainer,
            borderRadius: FansivibeRadius.mdBorder,
          ),
          clipBehavior: Clip.antiAlias,
          child: Column(
            children: [
              Expanded(
                flex: 65,
                child: Stack(
                  children: [
                    Container(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          colors: [
                            swatch.withValues(alpha: 0.25),
                            swatch.withValues(alpha: 0.40),
                          ],
                        ),
                      ),
                      child: Center(
                        child: Icon(
                          _categoryIcon(item.category),
                          size: 40,
                          color: swatch.withValues(alpha: 0.5),
                        ),
                      ),
                    ),
                    Positioned.fill(
                      child: IgnorePointer(
                        child: Container(
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              begin: Alignment.topCenter,
                              end: Alignment.bottomCenter,
                              colors: [
                                Colors.transparent,
                                FansivibeColors.surfaceContainer.withValues(
                                  alpha: 0.6,
                                ),
                              ],
                              stops: const [0.5, 1.0],
                            ),
                          ),
                        ),
                      ),
                    ),
                    if (item.isFavorite)
                      Positioned(
                        top: FansivibeSpacing.sm,
                        right: FansivibeSpacing.sm,
                        child: Container(
                          width: 28,
                          height: 28,
                          decoration: BoxDecoration(
                            color: FansivibeColors.surfaceContainerLow
                                .withValues(alpha: 0.8),
                            shape: BoxShape.circle,
                          ),
                          child: Icon(
                            Icons.favorite_rounded,
                            size: 14,
                            color: FansivibeColors.primary,
                          ),
                        ),
                      ),
                    if (item.material != null)
                      Positioned(
                        bottom: FansivibeSpacing.sm,
                        left: FansivibeSpacing.sm,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: FansivibeSpacing.sm,
                            vertical: 3,
                          ),
                          decoration: BoxDecoration(
                            color: FansivibeColors.surfaceContainerLow
                                .withValues(alpha: 0.8),
                            borderRadius: FansivibeRadius.fullBorder,
                          ),
                          child: Text(
                            item.material!,
                            style: FansivibeTypography.labelSmallWithFamily
                                .copyWith(
                                  fontSize: 9,
                                  color: FansivibeColors.secondary,
                                ),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              Expanded(
                flex: 35,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(
                    FansivibeSpacing.sm + 2,
                    FansivibeSpacing.sm,
                    FansivibeSpacing.sm + 2,
                    FansivibeSpacing.sm + 2,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item.name,
                        style: FansivibeTypography.labelMediumWithFamily
                            .copyWith(
                              color: FansivibeColors.onSurface,
                              fontSize: 11,
                            ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const Spacer(),
                      Row(
                        children: [
                          Container(
                            width: 8,
                            height: 8,
                            decoration: BoxDecoration(
                              color: swatch,
                              shape: BoxShape.circle,
                            ),
                          ),
                          const SizedBox(width: FansivibeSpacing.xs),
                          Expanded(
                            child: Text(
                              item.color,
                              style: FansivibeTypography.labelSmallWithFamily
                                  .copyWith(
                                    fontSize: 9,
                                    color: FansivibeColors.secondary,
                                  ),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: FansivibeSpacing.xs),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.end,
                        children: [
                          _miniIcon(Icons.favorite_outline_rounded),
                          const SizedBox(width: FansivibeSpacing.xs),
                          _miniIcon(Icons.edit_rounded),
                          const SizedBox(width: FansivibeSpacing.xs),
                          _miniIcon(Icons.more_horiz_rounded),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _miniIcon(IconData icon) {
    return Icon(
      icon,
      size: 14,
      color: FansivibeColors.secondary.withValues(alpha: 0.5),
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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'My Wardrobe',
          style: FansivibeTypography.headlineMediumWithFamily,
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
              style: FansivibeTypography.bodyMediumWithFamily,
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
                style: FansivibeTypography.bodyMediumWithFamily,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ],
    );
  }
}
