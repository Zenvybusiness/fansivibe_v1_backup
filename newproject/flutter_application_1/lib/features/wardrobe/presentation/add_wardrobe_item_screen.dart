import 'package:flutter/material.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

/// Screen for filling in item details when adding a new wardrobe item.
class AddWardrobeItemScreen extends StatefulWidget {
  const AddWardrobeItemScreen({required this.category, super.key});

  final AddItemCategoryConfig category;

  @override
  State<AddWardrobeItemScreen> createState() => _AddWardrobeItemScreenState();
}

class _AddWardrobeItemScreenState extends State<AddWardrobeItemScreen> {
  String? _selectedType;
  ColorOption? _selectedColor;
  TextureOption? _selectedTexture;
  String? _errorMessage;

  bool get _isValid => _selectedType != null && _selectedColor != null;

  void _saveItem() {
    if (!_isValid) {
      setState(() {
        _errorMessage = 'Please select a type and color.';
      });
      return;
    }

    final newItem = WardrobeItemData(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      name: _buildItemName(),
      category: widget.category.wardrobeCategoryId,
      color: _selectedColor!.name,
      material: _selectedTexture?.name,
    );

    Navigator.pop<WardrobeItemData>(context, newItem);
  }

  String _buildItemName() {
    final texture = _selectedTexture != null
        ? '${_selectedTexture!.name} '
        : '';
    final type = _selectedType ?? 'Item';
    return '$texture$type'.trim();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: Text('Add ${widget.category.name}'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 20.0;
            final contentMaxWidth = maxWidth > 600 ? 520.0 : double.infinity;

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

                        // Category indicator
                        _buildCategoryIndicator(theme),
                        const SizedBox(height: 28),

                        // Type selection
                        _SectionLabel(label: 'Type'),
                        const SizedBox(height: 12),
                        _buildChipRow(
                          items: widget.category.types,
                          selectedItem: _selectedType,
                          onSelected: (value) {
                            setState(() {
                              _selectedType = value;
                              _errorMessage = null;
                            });
                          },
                        ),
                        const SizedBox(height: 28),

                        // Color selection
                        _SectionLabel(label: 'Color'),
                        const SizedBox(height: 12),
                        _buildColorChipRow(theme),
                        const SizedBox(height: 28),

                        // Texture selection
                        _SectionLabel(label: 'Texture (optional)'),
                        const SizedBox(height: 12),
                        _buildChipRow(
                          items: AddItemConfig.textures
                              .map((t) => t.name)
                              .toList(),
                          selectedItem: _selectedTexture?.name,
                          onSelected: (value) {
                            setState(() {
                              _selectedTexture = value != null
                                  ? TextureOption(name: value)
                                  : null;
                              _errorMessage = null;
                            });
                          },
                        ),
                        const SizedBox(height: 32),

                        // Error message
                        if (_errorMessage != null) ...[
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: Colors.red.withValues(alpha: 0.1),
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(
                                color: Colors.red.withValues(alpha: 0.3),
                              ),
                            ),
                            child: Row(
                              children: [
                                const Icon(
                                  Icons.error_outline_rounded,
                                  color: Colors.redAccent,
                                  size: 18,
                                ),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    _errorMessage!,
                                    style: theme.textTheme.bodyMedium?.copyWith(
                                      color: Colors.redAccent,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 16),
                        ],

                        // Save button
                        SizedBox(
                          width: double.infinity,
                          child: FilledButton.icon(
                            onPressed: _saveItem,
                            icon: const Icon(Icons.save_rounded, size: 18),
                            label: Text(
                              'Save Item',
                              style: theme.textTheme.bodyMedium?.copyWith(
                                fontWeight: FontWeight.w600,
                                color: FansivibeColors.background,
                              ),
                            ),
                            style: FilledButton.styleFrom(
                              backgroundColor: FansivibeColors.accentGold,
                              foregroundColor: FansivibeColors.background,
                              padding: const EdgeInsets.symmetric(
                                vertical: 14,
                                horizontal: 16,
                              ),
                              minimumSize: const Size(0, 48),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(16),
                              ),
                              elevation: 4,
                              shadowColor: FansivibeColors.accentGold
                                  .withValues(alpha: 0.3),
                            ),
                          ),
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

  Widget _buildCategoryIndicator(ThemeData theme) {
    return Row(
      children: [
        Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: FansivibeColors.accentGold.withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(
            _categoryIcon(widget.category.iconName),
            size: 20,
            color: FansivibeColors.accentGold,
          ),
        ),
        const SizedBox(width: 12),
        Text(
          widget.category.name,
          style: theme.textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
          ),
        ),
      ],
    );
  }

  Widget _buildChipRow({
    required List<String> items,
    required String? selectedItem,
    required ValueChanged<String?> onSelected,
  }) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: items.map((item) {
        final isSelected = item == selectedItem;
        return GestureDetector(
          onTap: () => onSelected(isSelected ? null : item),
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
            child: Text(
              item,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: isSelected
                    ? FansivibeColors.accentGold
                    : FansivibeColors.textSecondary,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
              ),
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _buildColorChipRow(ThemeData theme) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: AddItemConfig.colors.map((color) {
        final isSelected = color == _selectedColor;
        return GestureDetector(
          onTap: () {
            setState(() {
              _selectedColor = isSelected ? null : color;
              _errorMessage = null;
            });
          },
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
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
                Container(
                  width: 16,
                  height: 16,
                  decoration: BoxDecoration(
                    color: Color(color.colorValue),
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: color.colorValue == 0xFFFFFFFF
                          ? FansivibeColors.accentGold.withValues(alpha: 0.3)
                          : Colors.transparent,
                      width: 1,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  color.name,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: isSelected
                        ? FansivibeColors.accentGold
                        : FansivibeColors.textSecondary,
                    fontWeight: isSelected
                        ? FontWeight.w600
                        : FontWeight.normal,
                  ),
                ),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }

  IconData _categoryIcon(String iconName) {
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

class _SectionLabel extends StatelessWidget {
  const _SectionLabel({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Text(
      label,
      style: theme.textTheme.titleMedium?.copyWith(
        fontWeight: FontWeight.w600,
        color: FansivibeColors.textPrimary,
        fontFamily: 'serif',
        fontSize: 18,
      ),
    );
  }
}
