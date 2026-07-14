import 'package:flutter/material.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

/// The Wardrobe Item Details screen (WARDROBE-004).
class WardrobeItemDetailsScreen extends StatelessWidget {
  const WardrobeItemDetailsScreen({required this.item, super.key});

  final WardrobeItemData item;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final category = _resolveCategory();

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        backgroundColor: FansivibeColors.background,
        elevation: 0,
        leading: IconButton(
          icon: Icon(
            Icons.arrow_back_rounded,
            color: FansivibeColors.textPrimary,
          ),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: Text(
          item.name,
          style: theme.textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
          ),
        ),
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 20.0;
            final contentMaxWidth = maxWidth > 600 ? 600.0 : double.infinity;

            return SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              child: Center(
                child: ConstrainedBox(
                  constraints: BoxConstraints(maxWidth: contentMaxWidth),
                  child: Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: horizontalPadding,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const SizedBox(height: 12),

                        _buildVisualSection(context),
                        const SizedBox(height: 24),

                        _buildInfoCard(context, category),
                        const SizedBox(height: 16),

                        _buildMetadataCard(context),
                        const SizedBox(height: 24),

                        _buildActionsSection(context),
                        const SizedBox(height: 32),
                      ],
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  WardrobeCategory? _resolveCategory() {
    try {
      return WardrobeMockData.categories.firstWhere(
        (c) => c.id == item.category,
      );
    } catch (_) {
      return null;
    }
  }

  Widget _buildVisualSection(BuildContext context) {
    final theme = Theme.of(context);
    final category = _resolveCategory();

    return Container(
      width: double.infinity,
      height: 220,
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.12),
          width: 1,
        ),
      ),
      child: Stack(
        fit: StackFit.expand,
        children: [
          Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  _categoryIcon(category?.iconName),
                  size: 56,
                  color: FansivibeColors.accentGold.withValues(alpha: 0.3),
                ),
                const SizedBox(height: 12),
                Text(
                  item.name,
                  style: theme.textTheme.bodyLarge?.copyWith(
                    color: FansivibeColors.textSecondary.withValues(alpha: 0.7),
                  ),
                ),
              ],
            ),
          ),
          if (item.isFavorite)
            const Positioned(
              top: 12,
              right: 12,
              child: Icon(
                Icons.favorite_rounded,
                size: 24,
                color: FansivibeColors.accentGold,
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildInfoCard(BuildContext context, WardrobeCategory? category) {
    final theme = Theme.of(context);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.2),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.3),
            blurRadius: 20,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: FansivibeColors.accentGold.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Icon(
              _categoryIcon(category?.iconName),
              size: 28,
              color: FansivibeColors.accentGold,
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  category?.name ?? item.category,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: FansivibeColors.accentGold,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  item.name,
                  style: theme.textTheme.headlineMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: FansivibeColors.textPrimary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMetadataCard(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.2),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.3),
            blurRadius: 20,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Details',
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w600,
              color: FansivibeColors.textPrimary,
              fontFamily: 'serif',
              fontSize: 18,
            ),
          ),
          const SizedBox(height: 16),
          _metadataRow(
            theme,
            icon: Icons.palette_rounded,
            label: 'Color',
            value: item.color,
            trailing: Container(
              width: 20,
              height: 20,
              decoration: BoxDecoration(
                color: _colorFromName(item.color),
                shape: BoxShape.circle,
                border: Border.all(
                  color: FansivibeColors.accentGold.withValues(alpha: 0.3),
                  width: 1,
                ),
              ),
            ),
          ),
          if (item.material != null) ...[
            const SizedBox(height: 14),
            _metadataRow(
              theme,
              icon: Icons.texture_rounded,
              label: 'Material',
              value: item.material!,
            ),
          ],
          const SizedBox(height: 14),
          _metadataRow(
            theme,
            icon: Icons.category_rounded,
            label: 'Category',
            value: _resolveCategory()?.name ?? item.category,
          ),
          if (item.isFavorite) ...[
            const SizedBox(height: 14),
            _metadataRow(
              theme,
              icon: Icons.favorite_rounded,
              label: 'Status',
              value: 'Favorite',
              valueColor: FansivibeColors.accentGold,
            ),
          ],
        ],
      ),
    );
  }

  Widget _metadataRow(
    ThemeData theme, {
    required IconData icon,
    required String label,
    required String value,
    Color? valueColor,
    Widget? trailing,
  }) {
    return Row(
      children: [
        Icon(icon, size: 18, color: FansivibeColors.accentGold),
        const SizedBox(width: 12),
        SizedBox(
          width: 80,
          child: Text(
            label,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: FansivibeColors.textSecondary,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Row(
            children: [
              if (trailing != null) ...[trailing, const SizedBox(width: 8)],
              Text(
                value,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: valueColor ?? FansivibeColors.textPrimary,
                  fontWeight: FontWeight.w500,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildActionsSection(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      children: [
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            onPressed: () => _handleEdit(context),
            icon: const Icon(Icons.edit_rounded, size: 18),
            label: Text(
              'Edit Item',
              style: theme.textTheme.bodyMedium?.copyWith(
                fontWeight: FontWeight.w600,
                color: FansivibeColors.background,
              ),
            ),
            style: FilledButton.styleFrom(
              backgroundColor: FansivibeColors.accentGold,
              foregroundColor: FansivibeColors.background,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
              elevation: 4,
              shadowColor: FansivibeColors.accentGold.withValues(alpha: 0.3),
            ),
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () => _handleAddToOutfit(context),
                icon: const Icon(Icons.add_circle_outline_rounded, size: 18),
                label: Text(
                  'Add to Outfit',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: FansivibeColors.accentGold,
                  ),
                ),
                style: OutlinedButton.styleFrom(
                  foregroundColor: FansivibeColors.accentGold,
                  side: BorderSide(
                    color: FansivibeColors.accentGold.withValues(alpha: 0.4),
                  ),
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(16),
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () => _handleDelete(context),
                icon: Icon(
                  Icons.delete_outline_rounded,
                  size: 18,
                  color: Colors.redAccent.withValues(alpha: 0.8),
                ),
                label: Text(
                  'Delete',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: Colors.redAccent,
                  ),
                ),
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.redAccent,
                  side: BorderSide(
                    color: Colors.redAccent.withValues(alpha: 0.4),
                  ),
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(16),
                  ),
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  void _handleEdit(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Editing ${item.name}...'),
        backgroundColor: FansivibeColors.accentGold,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  void _handleDelete(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('${item.name} removed from wardrobe'),
        backgroundColor: FansivibeColors.accentGold,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  void _handleAddToOutfit(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('${item.name} added to outfit'),
        backgroundColor: FansivibeColors.accentGold,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  IconData _categoryIcon(String? iconName) {
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
