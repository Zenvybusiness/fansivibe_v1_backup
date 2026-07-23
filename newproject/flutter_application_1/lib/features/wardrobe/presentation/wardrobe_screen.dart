import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/presentation/widgets/wardrobe_widgets.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class WardrobeScreen extends StatefulWidget {
  const WardrobeScreen({super.key});

  @override
  State<WardrobeScreen> createState() => _WardrobeScreenState();
}

class _WardrobeScreenState extends State<WardrobeScreen> {
  String _selectedCategory = 'all';
  final List<WardrobeItemData> _localItems = List.from(WardrobeMockData.items);

  void _selectCategory(String categoryId) {
    setState(() {
      _selectedCategory = categoryId;
    });
  }

  List<WardrobeItemData> get _filteredItems {
    if (_selectedCategory == 'all') return _localItems;
    return _localItems
        .where((item) => item.category == _selectedCategory)
        .toList();
  }

  int get _favoritesCount =>
      _localItems.where((item) => item.isFavorite).length;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final filteredItems = _filteredItems;
    final totalItems = _localItems.length;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 20.0;
            final contentMaxWidth = maxWidth > 600 ? 520.0 : double.infinity;
            final crossAxisCount = maxWidth > 600 ? 3 : 2;

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
                        const SizedBox(height: 8),
                        WardrobeDashboardHeader(
                          totalItems: totalItems,
                          styleType: WardrobeMockData.styleType,
                          favoritesCount: _favoritesCount,
                          categoryCount: WardrobeMockData.categories.length - 1,
                        ),
                        const SizedBox(height: 24),
                        WardrobeInsightCard(
                          data: WardrobeInsightData.mock,
                          onActionPressed: () => _handleViewAnalysis(context),
                        ),
                        const SizedBox(height: 24),
                        SizedBox(
                          height: 82,
                          child: ListView.separated(
                            scrollDirection: Axis.horizontal,
                            physics: const BouncingScrollPhysics(),
                            itemCount: WardrobeMockData.categories.length,
                            separatorBuilder: (_, __) =>
                                const SizedBox(width: 10),
                            itemBuilder: (context, index) {
                              final cat = WardrobeMockData.categories[index];
                              final count = cat.id == 'all'
                                  ? totalItems
                                  : _localItems
                                        .where(
                                          (item) => item.category == cat.id,
                                        )
                                        .length;
                              return CategoryTile(
                                name: cat.name,
                                iconName: cat.iconName,
                                count: count,
                                selected: _selectedCategory == cat.id,
                                onTap: () => _selectCategory(cat.id),
                              );
                            },
                          ),
                        ),
                        const SizedBox(height: 24),
                        Row(
                          children: [
                            Expanded(
                              child: Text(
                                _selectedCategory == 'all'
                                    ? 'All Items'
                                    : WardrobeMockData.categories
                                          .firstWhere(
                                            (c) => c.id == _selectedCategory,
                                          )
                                          .name,
                                style: theme.textTheme.titleSmall?.copyWith(
                                  fontWeight: FontWeight.w600,
                                  color: FansivibeColors.textPrimary,
                                ),
                              ),
                            ),
                            Text(
                              '${filteredItems.length} ${filteredItems.length == 1 ? 'item' : 'items'}',
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: FansivibeColors.textSecondary,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),
                        _buildItemGrid(
                          context,
                          items: filteredItems,
                          crossAxisCount: crossAxisCount,
                        ),
                        const SizedBox(height: 24),
                        FansiButton.primary(
                          label: 'Add Item to Wardrobe',
                          icon: Icons.add_rounded,
                          onPressed: () => _handleAddItem(context),
                        ),
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

  Widget _buildItemGrid(
    BuildContext context, {
    required List<WardrobeItemData> items,
    required int crossAxisCount,
  }) {
    final theme = Theme.of(context);
    final width = MediaQuery.of(context).size.width;
    final hp = width > 600 ? 48.0 : 20.0;
    final available = (width > 600 ? 520.0 : width) - hp * 2;
    final spacing = 12.0;
    final childW =
        (available - spacing * (crossAxisCount - 1)) / crossAxisCount;
    final aspect = childW / (childW * 1.4);

    if (items.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 32),
        child: Center(
          child: Column(
            children: [
              Icon(
                Icons.inventory_2_outlined,
                size: 48,
                color: FansivibeColors.textSecondary.withValues(alpha: 0.4),
              ),
              const SizedBox(height: 12),
              Text(
                'No items in this category yet',
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
      );
    }

    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: crossAxisCount,
        crossAxisSpacing: spacing,
        mainAxisSpacing: spacing,
        childAspectRatio: aspect,
      ),
      itemCount: items.length,
      itemBuilder: (context, index) {
        final item = items[index];
        return ClothingItemCard(
          item: item,
          onTap: () => _handleItemTap(context, item),
        );
      },
    );
  }

  void _handleViewAnalysis(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('Opening Wardrobe Analysis...'),
        backgroundColor: FansivibeColors.accentGold,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  void _handleAddItem(BuildContext context) async {
    final result = await context.pushNamed<WardrobeItemData>(
      RouteNames.wardrobeAddCategory,
    );
    if (result != null && context.mounted) {
      setState(() {
        _localItems.add(result);
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('${result.name} added to wardrobe'),
          backgroundColor: FansivibeColors.accentGold,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
      );
    }
  }

  void _handleItemTap(BuildContext context, WardrobeItemData item) {
    context.pushNamed(RouteNames.wardrobeItemDetails, extra: item);
  }
}
