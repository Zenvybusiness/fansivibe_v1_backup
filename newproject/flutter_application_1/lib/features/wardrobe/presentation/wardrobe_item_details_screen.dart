import 'package:flutter/material.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_client.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
/// Converts a [WardrobeItemData] to a [WardrobeEntry] for LearningService sync.
WardrobeEntry _toEntry(WardrobeItemData item) => WardrobeEntry(
  id: item.id,
  name: item.name,
  category: item.category,
  color: item.color,
  material: item.material,
  isFavorite: item.isFavorite,
);

/// Strict backend-UUID gate for wear capture (DEC-012, §10.2).
///
/// Backend wardrobe IDs are server-generated UUIDs; local/mock catalog
/// IDs ("1"–"24") never match. Only a strict match enables capture — no
/// heuristic mapping, no invented UUIDs, no local-ID translation. A UUID
/// the backend no longer owns (deleted/unknown item) still passes this
/// client-side gate and resolves server-side (404 → safe retry message);
/// the server stays authoritative for everything else (422/409).
final RegExp _backendUuidPattern = RegExp(
  r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
  r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$',
);

bool _isBackendUuid(String id) => _backendUuidPattern.hasMatch(id);


/// The Wardrobe Item Details screen (WARDROBE-004).
class WardrobeItemDetailsScreen extends StatefulWidget {
  const WardrobeItemDetailsScreen({
    required this.itemId,
    this.item,
    this.repository,
    super.key,
  });

  final String itemId;
  final WardrobeItemData? item;
  final WardrobeRepository? repository;

  @override
  State<WardrobeItemDetailsScreen> createState() =>
      _WardrobeItemDetailsScreenState();
}

class _WardrobeItemDetailsScreenState
    extends State<WardrobeItemDetailsScreen> {
  late final WardrobeRepository _repository;
  WardrobeItemData? _item;
  bool _isLoading = true;
  bool _isEditing = false;
  bool _isDeleting = false;
  bool _isLoggingWear = false;
  // Idempotency key for the current logical wear action (STEP 17.5).
  // Created on the first tap, retained across explicit user retries of
  // the SAME action so a lost response replays instead of duplicating,
  // cleared on success so the next tap starts a fresh logical action.
  String? _wearIdempotencyKey;
  final _formKey = GlobalKey<FormState>();
  String? _newName;
  String? _newCategory;
  String? _newColor;
  String? _newMaterial;
  bool? _newFavorite;
  String? _errorMessage;
  bool _canEdit = true;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? WardrobeRepositoryImpl();
    _loadItem();
  }

  @override
  void dispose() {
    super.dispose();
  }

  Future<void> _loadItem() async {
    final item = await _repository.getItem(itemId: widget.itemId);
    setState(() {
      _item = item;
      _isLoading = false;
      _isLoggingWear = false;
      _wearIdempotencyKey = null;
      if (item != null) {
        _newName = item.name;
        _newCategory = item.category;
        _newColor = item.color;
        _newMaterial = item.material;
        _newFavorite = item.isFavorite;
      }
    });
  }

  void _toggleEdit() {
    setState(() {
      _isEditing = !_isEditing;
      if (!_isEditing) {
        // Save changes
        _saveChanges();
      }
    });
  }

  Future<void> _saveChanges() async {
    if (!_formKey.currentState!.validate()) {
      setState(() {
        _errorMessage = 'Please fix the validation errors.';
      });
      return;
    }

    setState(() {
      _canEdit = false;
      _errorMessage = null;
    });

    // Build WardrobeItemPatch with only the fields that changed
    final changes = <String, dynamic>{};

    if (_newName != _item?.name) {
      changes['name'] = _newName;
    }
    if (_newCategory != _item?.category) {
      changes['category'] = _newCategory;
    }
    if (_newColor != _item?.color) {
      changes['color'] = _newColor;
    }
    if (_newMaterial != _item?.material) {
      changes['material'] = _newMaterial;
    }
    if (_newFavorite != _item?.isFavorite) {
      changes['isFavorite'] = _newFavorite;
    }

    if (changes.isEmpty) {
      // No changes detected, just close edit mode
      setState(() {
        _isEditing = false;
        _canEdit = true;
      });
      return;
    }

    try {
      final updatedItem = await _repository.updateItem(
        itemId: widget.itemId,
        name: changes['name'] as String?,
        category: changes['category'] as String?,
        color: changes['color'] as String?,
        material: changes['material'] as String?,
        isFavorite: changes['isFavorite'] as bool?,
      );

      if (!mounted) return;

      if (updatedItem != null) {
        // Success: treat as source of truth and sync with LearningService
        setState(() {
          _item = updatedItem;
          _newName = updatedItem.name;
          _newCategory = updatedItem.category;
          _newColor = updatedItem.color;
          _newMaterial = updatedItem.material;
          _newFavorite = updatedItem.isFavorite;
          _isEditing = false;
          _canEdit = true;
        });
        // Synchronize the server-returned item into LearningService so
        // WardrobeScreen's listener updates its grid accordingly.
        LearningService.instance.updateItem(updatedItem.id, _toEntry(updatedItem));
      } else {
        // API failure
        setState(() {
          _errorMessage = 'Failed to update item. Please try again.';
          _canEdit = true;
        });
      }
    } catch (e) {
      // Network/error failure
      if (!mounted) return;
      setState(() {
        _errorMessage = 'Failed to update item. Please check your connection.';
        _canEdit = true;
      });
    }
  }

  Future<void> _deleteItem() async {
    if (_isDeleting) return;

    final itemId = widget.itemId;
    final shouldConfirm = await showDialog<bool?>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Delete Item'),
        content: Text('Are you sure you want to remove "${_item?.name}"?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );

    if (shouldConfirm != true) return;

    setState(() {
      _isDeleting = true;
    });

    try {
      final result = await _repository.deleteItem(itemId: itemId);

      if (!mounted) return;

      if (result == true) {
        // Success: remove from LearningService and close screen
        LearningService.instance.removeItem(itemId);
        if (!mounted) return;
ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Item removed from wardrobe'),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8.0),
        ),
      ),
    );
        if (!mounted) return;
        Navigator.of(context).pop();
      } else {
        // API failure or item already deleted
        setState(() {
          _errorMessage = 'Failed to delete item. Please try again.';
          _isDeleting = false;
        });
        if (!mounted) return;
ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Failed to delete item. Please try again.'),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8.0),
        ),
      ),
    );
      }
    } catch (e) {
      // Network/error failure
      if (!mounted) return;
      setState(() {
        _errorMessage = 'Failed to delete item. Please check your connection.';
        _isDeleting = false;
      });
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Failed to delete item. Please check your connection.'),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8.0),
        ),
      ),
    );
    }
  }

  /// Logs a single wear for the displayed item ("I wore this", STEP 17.5).
  ///
  /// One tap is one logical wear action: exactly one backend UUID is
  /// submitted via the existing `logWear` seam (`wornAt` omitted — server
  /// now stays authoritative; no date picker in this step). The UUID gate
  /// in the actions row guarantees only backend UUIDs reach this point;
  /// local mock IDs never arrive here. Re-taps while pending are ignored
  /// (button disabled + guard); explicit retries after failure reuse the
  /// same idempotency key so a lost response replays instead of
  /// duplicating. Success and failure surface as lightweight snackbars in
  /// the file's existing style — failure never fabricates success and is
  /// never interpreted as "not worn". No auto-logging: callers invoke
  /// this only from the explicit capture action.
  Future<void> _logWear() async {
    final item = _item;
    if (_isLoggingWear || item == null || !_isBackendUuid(item.id)) return;

    setState(() {
      _isLoggingWear = true;
    });

    final key = _wearIdempotencyKey ??= newWearIdempotencyKey();
    WearEventLogResponse? result;
    try {
      result = await _repository.logWear(
        itemIds: [item.id],
        idempotencyKey: key,
      );
    } catch (_) {
      result = null;
    }

    if (!mounted) return;
    setState(() {
      _isLoggingWear = false;
      if (result != null) {
        // Action complete — the next tap starts a fresh logical action.
        _wearIdempotencyKey = null;
      }
    });
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          result == null
              ? "Couldn't log wear. Check your connection and try again."
              : (result.created ? 'Wear logged' : 'Already logged'),
        ),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8.0),
        ),
      ),
    );
  }

  Widget _buildLoadingScreen(BuildContext context) {
    return const Center(child: CircularProgressIndicator());
  }

  Widget _buildMissingItemScreen(BuildContext context) {
    return const Center(
      child: Text('Item not found'),
    );
  }

  Widget _buildEditingForm(BuildContext context, WardrobeItemData item) {
    final theme = Theme.of(context);

    return Form(
      key: _formKey,
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Edit ${item.name}',
              style: theme.textTheme.titleLarge?.copyWith(
                fontWeight: FontWeight.w600,
                color: FansivibeColors.textPrimary,
              ),
            ),
            const SizedBox(height: 24),

            // Name field
            TextFormField(
              initialValue: _newName,
              decoration: InputDecoration(
                labelText: 'Name',
                border: OutlineInputBorder(
                  borderRadius: FansivibeRadius.baseBorder,
                ),
                errorBorder: OutlineInputBorder(
                  borderRadius: FansivibeRadius.baseBorder,
                  borderSide: const BorderSide(color: FansivibeColors.error),
                ),
                focusedErrorBorder: OutlineInputBorder(
                  borderRadius: FansivibeRadius.baseBorder,
                  borderSide: const BorderSide(color: FansivibeColors.error),
                ),
              ),
              validator: (value) {
                if (value == null || value.isEmpty) {
                  return 'Please enter a name';
                }
                return null;
              },
              onChanged: (value) {
                setState(() {
                  _newName = value;
                });
              },
            ),
            const SizedBox(height: 16),

            // Category field
            DropdownButtonFormField<String>(
              value: _newCategory,
              decoration: InputDecoration(
                labelText: 'Category',
                border: OutlineInputBorder(
                  borderRadius: FansivibeRadius.baseBorder,
                ),
              ),
              items: const [
                DropdownMenuItem(value: 'tops', child: Text('Tops')),
                DropdownMenuItem(value: 'bottoms', child: Text('Bottoms')),
                DropdownMenuItem(value: 'outerwear', child: Text('Outerwear')),
                DropdownMenuItem(value: 'footwear', child: Text('Footwear')),
                DropdownMenuItem(value: 'accessories', child: Text('Accessories')),
              ],
              onChanged: (value) {
                setState(() {
                  _newCategory = value;
                });
              },
              validator: (value) {
                if (value == null) {
                  return 'Please select a category';
                }
                return null;
              },
            ),
            const SizedBox(height: 16),

            // Color field
            TextFormField(
              initialValue: _newColor,
              decoration: InputDecoration(
                labelText: 'Color',
                border: OutlineInputBorder(
                  borderRadius: FansivibeRadius.baseBorder,
                ),
              ),
              onChanged: (value) {
                setState(() {
                  _newColor = value;
                });
              },
            ),
            const SizedBox(height: 16),

            // Material field
            TextFormField(
              initialValue: _newMaterial ?? (item.material ?? ''),
              decoration: InputDecoration(
                labelText: 'Material (optional)',
                border: OutlineInputBorder(
                  borderRadius: FansivibeRadius.baseBorder,
                ),
                hintText: 'Leave empty to clear',
              ),
              onChanged: (value) {
                setState(() {
                  _newMaterial = value.isEmpty ? null : value;
                });
              },
            ),
            const SizedBox(height: 16),

            // Favorite toggle
            ListTile(
              title: const Text('Favorite'),
              leading: Icon(
                _newFavorite ?? item.isFavorite
                    ? Icons.favorite_rounded
                    : Icons.favorite_border_rounded,
                color: FansivibeColors.accentGold,
              ),
              onTap: () {
                setState(() {
                  _newFavorite = !(_newFavorite ?? item.isFavorite);
                });
              },
            ),
            const SizedBox(height: 24),

            // Buttons row
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                TextButton(
                  onPressed: () {
                    setState(() {
                      _isEditing = false;
                    });
                  },
                  child: const Text('Cancel'),
                ),
                const SizedBox(width: 8),
                ElevatedButton(
                  onPressed: _saveChanges,
                  child: _isEditing && _canEdit
                      ? const SizedBox(
                          height: 16,
                          width: 16,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            valueColor:
                                AlwaysStoppedAnimation<Color>(FansivibeColors.background),
                          ),
                        )
                      : const Text('Save'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildViewMode(BuildContext context, WardrobeItemData item) {
    final theme = Theme.of(context);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            item.name,
            style: theme.textTheme.titleLarge?.copyWith(
              fontWeight: FontWeight.w600,
              color: FansivibeColors.textPrimary,
            ),
          ),
          const SizedBox(height: 24),

          // Name
          _metadataRow(
            theme,
            icon: Icons.title_rounded,
            label: 'Name',
            value: item.name,
          ),
          const SizedBox(height: 12),

          // Category
          _metadataRow(
            theme,
            icon: Icons.folder_rounded,
            label: 'Category',
            value: item.category,
          ),
          const SizedBox(height: 12),

          // Color with swatch
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
          const SizedBox(height: 12),

          // Material
          _metadataRow(
            theme,
            icon: Icons.texture_rounded,
            label: 'Material',
            value: item.material ?? 'Not specified',
          ),
          const SizedBox(height: 12),

          // Favorite
          _metadataRow(
            theme,
            icon: item.isFavorite ? Icons.favorite_rounded : Icons.favorite_border_rounded,
            label: 'Status',
            value: item.isFavorite ? 'Favorite' : 'Not favorite',
            valueColor: item.isFavorite ? FansivibeColors.accentGold : null,
          ),
          const SizedBox(height: 12),

          // Actions (Wrap, not Row: the capture button below makes three
          // actions, which would overflow narrow screens in a fixed Row.
          // Identical end-aligned layout whenever everything fits.)
          Wrap(
            alignment: WrapAlignment.end,
            spacing: 8,
            runSpacing: 8,
            children: [
              // Wear capture (STEP 17.5, DEC-012 §10.2): rendered only for
              // authoritative backend UUIDs. Local/mock IDs ("1"–"24") hide
              // the action instead of erroring — nothing non-backend is
              // ever submitted, mapped, or invented. The label stays
              // visible while pending (spinner replaces the icon) so the
              // in-flight action remains identifiable; the button is
              // disabled and re-taps are guarded.
              if (_isBackendUuid(item.id))
                OutlinedButton.icon(
                  onPressed: _isLoggingWear ? null : _logWear,
                  icon: _isLoggingWear
                      ? const SizedBox(
                          height: 16,
                          width: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.checkroom_rounded, size: 16),
                  label: const Text('I wore this'),
                ),
              OutlinedButton.icon(
                onPressed: _toggleEdit,
                icon: const Icon(Icons.edit_rounded, size: 16),
                label: const Text('Edit'),
              ),
              OutlinedButton.icon(
                onPressed: _isDeleting ? null : _deleteItem,
                icon: const Icon(Icons.delete_rounded, size: 16),
                label: _isDeleting
                    ? const SizedBox(
                        height: 16,
                        width: 16,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          valueColor:
                              AlwaysStoppedAnimation<Color>(FansivibeColors.background),
                        ),
                      )
                    : const Text('Delete'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildContent(BuildContext context) {
    final theme = Theme.of(context);

    if (_isLoading) {
      return _buildLoadingScreen(context);
    }

    if (_item == null) {
      return _buildMissingItemScreen(context);
    }

    if (_isEditing) {
      return _buildEditingForm(context, _item!);
    }

    return _buildViewMode(context, _item!);
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
              Flexible(
                child: Text(
                  value,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: valueColor ?? FansivibeColors.textPrimary,
                    fontWeight: FontWeight.w500,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  IconData _categoryIcon(String? iconName) {
    if (iconName == null) return Icons.category_rounded;
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: _isEditing
            ? Text('Edit Item')
            : Text(_item?.name ?? 'Wardrobe Item'),
        actions: _isEditing
            ? [
                IconButton(
                  icon: const Icon(Icons.save_rounded),
                  onPressed: _saveChanges,
                ),
              ]
            : [
                IconButton(
                  icon: const Icon(Icons.edit_rounded),
                  onPressed: _toggleEdit,
                ),
              ],
      ),
      body: SafeArea(
        child: _buildContent(context),
      ),
    );
  }
}
