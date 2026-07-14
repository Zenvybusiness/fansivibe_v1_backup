import 'package:flutter/material.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/presentation/add_wardrobe_item_screen.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

/// Screen for selecting a clothing category when adding a new wardrobe item.
class AddWardrobeCategoryScreen extends StatelessWidget {
  const AddWardrobeCategoryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Add Item'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 20.0;
            final contentMaxWidth = maxWidth > 600 ? 520.0 : double.infinity;
            final crossAxisCount = maxWidth > 600 ? 4 : 2;

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
                        Text(
                          'Select a Category',
                          style: theme.textTheme.bodyLarge?.copyWith(
                            color: FansivibeColors.textSecondary,
                          ),
                        ),
                        const SizedBox(height: 24),
                        GridView.builder(
                          shrinkWrap: true,
                          physics: const NeverScrollableScrollPhysics(),
                          gridDelegate:
                              SliverGridDelegateWithFixedCrossAxisCount(
                                crossAxisCount: crossAxisCount,
                                crossAxisSpacing: 12,
                                mainAxisSpacing: 12,
                                childAspectRatio: 0.85,
                              ),
                          itemCount: AddItemConfig.categories.length,
                          itemBuilder: (context, index) {
                            final category = AddItemConfig.categories[index];
                            return _CategoryCard(
                              category: category,
                              onTap: () =>
                                  _onCategorySelected(context, category),
                            );
                          },
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

  void _onCategorySelected(
    BuildContext context,
    AddItemCategoryConfig category,
  ) async {
    final result = await Navigator.push<WardrobeItemData>(
      context,
      MaterialPageRoute(
        builder: (_) => AddWardrobeItemScreen(category: category),
      ),
    );
    if (result != null && context.mounted) {
      Navigator.pop(context, result);
    }
  }
}

class _CategoryCard extends StatelessWidget {
  const _CategoryCard({required this.category, required this.onTap});

  final AddItemCategoryConfig category;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(20),
      child: Container(
        decoration: BoxDecoration(
          color: FansivibeColors.surface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: FansivibeColors.accentGold.withValues(alpha: 0.2),
            width: 1,
          ),
        ),
        child: FittedBox(
          fit: BoxFit.scaleDown,
          child: SizedBox(
            width: 120,
            height: 140,
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  _iconForCategory(category.iconName),
                  size: 32,
                  color: FansivibeColors.accentGold,
                ),
                const SizedBox(height: 10),
                Text(
                  category.name,
                  style: theme.textTheme.bodyLarge?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: FansivibeColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '${category.types.length} types',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: FansivibeColors.textSecondary,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  IconData _iconForCategory(String iconName) {
    switch (iconName) {
      case 'person_rounded':
        return Icons.person_rounded;
      case 'accessibility_rounded':
        return Icons.accessibility_rounded;
      case 'directions_walk_rounded':
        return Icons.directions_walk_rounded;
      case 'checkroom_rounded':
        return Icons.checkroom_rounded;
      default:
        return Icons.category_rounded;
    }
  }
}
