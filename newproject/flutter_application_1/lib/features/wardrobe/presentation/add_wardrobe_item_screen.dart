import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/media/data/media_client.dart';
import 'package:fansivibe/features/media/domain/image_pipeline.dart';
import 'package:fansivibe/features/media/domain/original_file_manager.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/features/wardrobe/data/garment_client.dart';
import 'package:fansivibe/features/wardrobe/data/garment_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_item_photo.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/wardrobe/data/local_wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_extraction_screen.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_photo_screen.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

/// Screen for filling in item details when adding a new wardrobe item.
///
/// Supports manual entry, prefill from Outfit Scan (`initialGarmentResult`),
/// and AI garment extraction by delegating to [WardrobeExtractionScreen].
class AddWardrobeItemScreen extends StatefulWidget {
  const AddWardrobeItemScreen({
    required this.category,
    this.initialGarmentResult,
    this.repository,
    this.garmentClient,
    this.mediaClient,
    this.photoGalleryPick,
    super.key,
  });

  final AddItemCategoryConfig category;

  /// Prefilled garment observation from Outfit Scan (Stage 1D Batch 3A).
  final GarmentAnalysisResult? initialGarmentResult;

  /// Repository override (tests only). Defaults to the live backend.
  final WardrobeRepository? repository;

  /// Garment client override (tests only). Defaults to the live backend.
  final GarmentClient? garmentClient;

  /// Media client override (tests only). Defaults to the live backend.
  final MediaClient? mediaClient;

  /// Gallery picker override for the photo screen (tests only).
  final Future<XFile?> Function(ImageSource source)? photoGalleryPick;

  @override
  State<AddWardrobeItemScreen> createState() => _AddWardrobeItemScreenState();
}

class _AddWardrobeItemScreenState extends State<AddWardrobeItemScreen> {
  String? _selectedType;
  ColorOption? _selectedColor;
  String? _selectedTextureName;
  String? _selectedFit;
  String? _errorMessage;
  bool _isSubmitting = false;
  WardrobeItemData? _savedItem;
  List<WardrobeItemData> _savedItems = const [];
  late final WardrobeRepository _repository;
  late final MediaClient _mediaClient;

  Uint8List? _photoBytes;
  String? _photoFilename;
  GarmentAnalysisResult? _garmentResult;

  bool get _isValid => _selectedType != null && _selectedColor != null;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? WardrobeRepositoryImpl();
    _mediaClient = widget.mediaClient ?? MediaClient();
    if (widget.initialGarmentResult != null) {
      _garmentResult = widget.initialGarmentResult;
      _prefillFromGarment(widget.initialGarmentResult!);
    }
  }

  @override
  void dispose() {
    if (widget.mediaClient == null) {
      _mediaClient.dispose();
    }
    super.dispose();
  }

  Future<void> _saveItem() async {
    if (!_isValid) {
      setState(() {
        _errorMessage = 'Please select a type and color.';
      });
      return;
    }

    setState(() {
      _isSubmitting = true;
      _errorMessage = null;
    });
    final newItem = WardrobeItemData(
      id: '',
      name: _buildItemName(),
      category: widget.category.wardrobeCategoryId,
      color: _selectedColor!.name,
      material: _selectedTextureName,
    );

    final photoBytes = await prepareWardrobePhoto(_photoBytes);
    if (!mounted) return;

    // Option B: Preserved local original in app storage
    String? localOriginalPath;
    if (photoBytes != null && photoBytes.isNotEmpty) {
      localOriginalPath = await OriginalFileManager.instance.saveOriginal(
        idOrHash: '',
        bytes: photoBytes,
      );
    }

    MediaRef? cloudMediaRef;

    // Authenticated upload pipeline (Gate 6.1 / Gate 8.1: only authenticated sessions upload)
    final uploadBytes = _photoBytes ?? photoBytes;
    if (AuthSession.isAuthenticated &&
        !isGuestUser &&
        uploadBytes != null &&
        uploadBytes.isNotEmpty) {
      try {
        final detectedMime = detectImageMimeType(uploadBytes) ?? 'image/jpeg';
        if (uploadBytes.length <= 2 * 1024 * 1024 &&
            (detectedMime == 'image/jpeg' || detectedMime == 'image/webp')) {
          final clientSha = sha256Hex(uploadBytes);
          final dims = await getImageDimensions(uploadBytes);
          final idempotencyKey =
              'add_${clientSha.substring(0, 16)}_${DateTime.now().millisecondsSinceEpoch}';

          final authRes = await _mediaClient.authorizeUpload(
            clientSizeBytes: uploadBytes.length,
            clientSha256: clientSha,
            idempotencyKey: idempotencyKey,
            mimeType: detectedMime,
            clientDeclaredWidth: dims?.$1,
            clientDeclaredHeight: dims?.$2,
          );

          if (authRes != null) {
            final uploaded = await _mediaClient.uploadBytesDirect(
              presignedPutUrl: authRes.presignedPutUrl,
              bytes: uploadBytes,
              contentType: detectedMime,
            );

            if (uploaded) {
              final pubRes = await _mediaClient.completeUpload(
                uploadId: authRes.uploadId,
              );
              if (pubRes != null && pubRes.status == 'published') {
                cloudMediaRef = MediaRef(
                  objectKey: pubRes.canonicalKey,
                  mediaType: pubRes.mediaType,
                  uploadId: pubRes.uploadId,
                  width: pubRes.width,
                  height: pubRes.height,
                  sizeBytes: pubRes.sizeBytes,
                  contentHash: pubRes.sha256,
                );
              }
            }
          }
        }
      } catch (_) {
        // Upload failure does not crash the save; local original is preserved
      }
    }

    try {
      // Phase 2.1 guests persist on-device through the local repository.
      // No prompt, no backend.
      final repository = isGuestUser ? LocalWardrobeRepository() : _repository;
      final createdItem = await repository.createItem(
        name: newItem.name,
        category: newItem.category,
        color: newItem.color,
        material: newItem.material,
        imageRef: cloudMediaRef,
        // C-02-F: persist fit observation when present; never copy general
        // Outfit Scan detection confidence into fitConfidence.
        fit: _selectedFit ?? _garmentResult?.fit,
      );

      if (!mounted) return;

      if (createdItem != null) {
        final savedItem = createdItem.copyWith(
          imageBytes: photoBytes,
          localOriginalPath: localOriginalPath,
        );
        if (photoBytes != null) {
          LearningService.instance.updateItem(
            savedItem.id,
            wardrobeEntryFromItem(savedItem),
          );
        }
        setState(() {
          _isSubmitting = false;
          _savedItem = savedItem;
          _savedItems = [savedItem];
        });
      } else {
        // API failure
        setState(() {
          _errorMessage = 'Failed to add item. Please try again.';
          _isSubmitting = false;
        });
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = 'Failed to add item. Please try again.';
        _isSubmitting = false;
      });
    }
  }

  /// Server UUID usable as a C-03 preferred item (C-04 Scan → Save →
  /// Build). Guest-local (`local-*`) and empty ids are never buildable —
  /// the builder is account-only and the backend accepts UUIDs.
  String? _buildableItemId(WardrobeItemData item) {
    final id = item.id;
    if (id.isEmpty || id.startsWith('local-')) return null;
    return id;
  }

  /// C-04: opens the existing Outfit Builder carrying the saved wardrobe
  /// UUID as the C-03 preferred item. Navigation args only — the builder
  /// still derives through the existing repository/client.
  void _buildWithThisItem(String itemId) {
    context.pushNamed(
      RouteNames.buildOutfit,
      extra: <String, String>{'preferredItemId': itemId},
    );
  }

  /// Post-save actions: confirmation plus Done (existing pop contract)
  /// and, for server-saved items only, Build with this item.
  Widget _buildSavedActions(ThemeData theme, WardrobeItemData item) {
    final buildableId = _buildableItemId(item);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Icon(
              Icons.check_circle_rounded,
              size: 20,
              color: FansivibeColors.success,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                _savedItems.length > 1
                    ? 'Saved ${_savedItems.length} items to your wardrobe.'
                    : 'Saved ${item.name} to your wardrobe.',
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: FansivibeColors.textPrimary,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        if (buildableId != null) ...[
          SizedBox(
            width: double.infinity,
            child: FansiButton.primary(
              label: 'Build with this item',
              icon: Icons.checkroom_rounded,
              onPressed: () => _buildWithThisItem(buildableId),
            ),
          ),
          const SizedBox(height: 12),
        ],
        SizedBox(
          width: double.infinity,
          child: FansiButton.secondary(
            label: 'Done',
            onPressed: () => Navigator.pop<WardrobeItemData>(context, item),
          ),
        ),
      ],
    );
  }

  Future<void> _takePhoto() async {
    final photo = await Navigator.of(context).push<WardrobePhoto>(
      MaterialPageRoute(
        builder: (_) => WardrobePhotoScreen(pickImage: widget.photoGalleryPick),
      ),
    );
    if (photo == null || !mounted) return;
    setState(() {
      _photoBytes = photo.bytes;
      _photoFilename = photo.filename;
      _errorMessage = null;
    });
  }

  /// Explicit gallery path — never invoked by Take Photo.
  Future<void> _pickFromGallery() async {
    try {
      final file = await ImagePicker().pickImage(
        source: ImageSource.gallery,
        maxWidth: 1024,
        maxHeight: 1024,
      );
      if (file == null || !mounted) return;
      final bytes = await file.readAsBytes();
      if (!mounted) return;
      setState(() {
        _photoBytes = bytes;
        _photoFilename = file.name.isNotEmpty ? file.name : 'wardrobe_item.jpg';
        _errorMessage = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = 'Could not open the gallery.';
      });
    }
  }

  void _retakePhoto() {
    setState(() {
      _photoBytes = null;
      _photoFilename = null;
      _errorMessage = null;
    });
  }

  /// Delegates AI garment extraction, crop review, metadata editing,
  /// candidate selection, save idempotency, and asset cleanup to the unified
  /// [WardrobeExtractionScreen].
  Future<void> _launchUnifiedExtraction() async {
    final bytes = _photoBytes;
    if (bytes == null) return;
    final savedItems = await Navigator.of(context).push<List<WardrobeItemData>>(
      MaterialPageRoute(
        builder: (_) => WardrobeExtractionScreen(
          initialImageBytes: bytes,
          initialFilename: _photoFilename ?? 'wardrobe_item.jpg',
          garmentClient: widget.garmentClient,
          mediaClient: widget.mediaClient,
          repository: widget.repository,
          pickImage: widget.photoGalleryPick,
        ),
      ),
    );
    if (!mounted) return;
    if (savedItems != null && savedItems.isNotEmpty) {
      setState(() {
        _photoBytes = null;
        _photoFilename = null;
        _savedItems = savedItems;
        _savedItem = savedItems.first;
        _errorMessage = null;
      });
    }
  }

  /// Preselects manual chips from the AI suggestion. Only exact
  /// case-insensitive matches against the existing on-screen options —
  /// near-misses stay unselected for the user to pick. Existing user
  /// selections are never overwritten.
  void _prefillFromGarment(GarmentAnalysisResult result) {
    final subcategory = result.subcategory;
    if (_selectedType == null && subcategory != null) {
      final lowered = subcategory
          .toLowerCase()
          .replaceAll('_', '-')
          .replaceAll(' ', '-');
      for (final type in widget.category.types) {
        final typeLowered = type
            .toLowerCase()
            .replaceAll('_', '-')
            .replaceAll(' ', '-');
        if (typeLowered == lowered ||
            typeLowered.replaceAll('-', '') == lowered.replaceAll('-', '')) {
          _selectedType = type;
          break;
        }
      }
    }
    if (_selectedColor == null && result.color != null) {
      final lowered = result.color!.toLowerCase();
      for (final option in AddItemConfig.colors) {
        if (option.name.toLowerCase() == lowered) {
          _selectedColor = option;
          break;
        }
      }
    }
    if (_selectedTextureName == null && result.material != null) {
      final lowered = result.material!.toLowerCase();
      for (final texture in AddItemConfig.textures) {
        if (texture.name.toLowerCase() == lowered) {
          _selectedTextureName = texture.name;
          break;
        }
      }
    }
    if (_selectedFit == null && result.fit != null) {
      final lowered = result.fit!.toLowerCase().trim();
      for (final fitOption in AddItemConfig.fitOptions) {
        if (fitOption.toLowerCase() == lowered) {
          _selectedFit = fitOption;
          break;
        }
      }
      _selectedFit ??= result.fit;
    }
    _errorMessage = null;
  }

  String _buildItemName() {
    final texture = _selectedTextureName != null
        ? '$_selectedTextureName '
        : '';
    final type = _selectedType ?? 'Item';
    return '$texture$type'.trim();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final textStyle = theme.textTheme.bodyMedium;

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

                        // Photo (optional): capture → preview → analyze →
                        // review. AI output only preselects the chips below.
                        _SectionLabel(label: 'Photo (optional)'),
                        const SizedBox(height: 12),
                        _buildPhotoSection(theme),
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
                          selectedItem: _selectedTextureName,
                          onSelected: (value) {
                            setState(() {
                              _selectedTextureName = value;
                              _errorMessage = null;
                            });
                          },
                        ),
                        const SizedBox(height: 28),

                        // Fit selection (optional)
                        _SectionLabel(label: 'Fit (optional)'),
                        const SizedBox(height: 12),
                        _buildChipRow(
                          items: {
                            ...AddItemConfig.fitOptions,
                            if (_selectedFit != null) _selectedFit!,
                          }.toList(),
                          selectedItem: _selectedFit,
                          onSelected: (value) {
                            setState(() {
                              _selectedFit = _selectedFit == value
                                  ? null
                                  : value;
                              _errorMessage = null;
                            });
                          },
                        ),
                        const SizedBox(height: 32),

                        // Error message (shared error treatment)
                        if (_errorMessage != null) ...[
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: FansivibeColors.error.withValues(
                                alpha: 0.1,
                              ),
                              borderRadius: FansivibeRadius.smdBorder,
                              border: Border.all(
                                color: FansivibeColors.error.withValues(
                                  alpha: 0.3,
                                ),
                              ),
                            ),
                            child: Row(
                              children: [
                                const Icon(
                                  Icons.error_outline_rounded,
                                  color: FansivibeColors.error,
                                  size: 18,
                                ),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    _errorMessage!,
                                    style: textStyle!.copyWith(
                                      color: FansivibeColors.error,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 16),
                        ],

                        // Save button (shared primary action), or the
                        // post-save actions once the item exists (C-04).
                        if (_savedItem != null)
                          _buildSavedActions(theme, _savedItem!)
                        else
                          SizedBox(
                            width: double.infinity,
                            child: _isSubmitting
                                ? const Center(
                                    child: SizedBox(
                                      width: 24,
                                      height: 24,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 3,
                                        valueColor:
                                            AlwaysStoppedAnimation<Color>(
                                              FansivibeColors.primary,
                                            ),
                                      ),
                                    ),
                                  )
                                : FansiButton.primary(
                                    label: 'Save Item',
                                    icon: Icons.save_rounded,
                                    // Keep enabled so tapping with no
                                    // selection surfaces the validation
                                    // message (see _saveItem).
                                    onPressed: _saveItem,
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

  Widget _buildPhotoSection(ThemeData theme) {
    final bytes = _photoBytes;
    if (bytes == null) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_garmentResult != null) ...[
            _buildGarmentSummary(theme, _garmentResult!),
            const SizedBox(height: 16),
          ],
          SizedBox(
            width: double.infinity,
            child: FansiButton.primary(
              label: 'Take Photo',
              icon: Icons.photo_camera_rounded,
              onPressed: _takePhoto,
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FansiButton.secondary(
              label: 'Choose from Gallery',
              icon: Icons.photo_library_outlined,
              onPressed: _pickFromGallery,
            ),
          ),
        ],
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: Image.memory(
            bytes,
            height: 220,
            width: double.infinity,
            fit: BoxFit.cover,
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: FansiButton.secondary(
                label: 'Retake',
                icon: Icons.refresh_rounded,
                onPressed: _retakePhoto,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: FansiButton.primary(
                label: 'Analyze Item',
                icon: Icons.auto_awesome_outlined,
                onPressed: _launchUnifiedExtraction,
              ),
            ),
          ],
        ),
      ],
    );
  }

  /// Renders the real backend garment observation. Null attributes show
  /// `Not detected` — never a placeholder value.
  Widget _buildGarmentSummary(ThemeData theme, GarmentAnalysisResult result) {
    final rows = <String, String?>{
      'Category': result.category,
      'Subcategory': result.subcategory,
      'Color': result.color,
      'Pattern': result.pattern,
      'Material': result.material,
      'Style': result.style,
      'Fit': result.fit,
    };
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: FansivibeColors.accentGold.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.35),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            result.needsReview
                ? 'AI suggestion — review and edit below'
                : 'AI suggestion — confirmed below, edit if needed',
            style: theme.textTheme.bodySmall?.copyWith(
              color: FansivibeColors.accentGold,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          for (final entry in rows.entries)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 108,
                    child: Text(
                      entry.key,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: FansivibeColors.textSecondary,
                      ),
                    ),
                  ),
                  Expanded(
                    child: Text(
                      entry.value ?? 'Not detected',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: entry.value == null
                            ? FansivibeColors.textSecondary
                            : FansivibeColors.textPrimary,
                        fontStyle: entry.value == null
                            ? FontStyle.italic
                            : FontStyle.normal,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          if (result.confidence != null)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                // ponytail: verbatim backend confidence, no invented
                // precision or progress-bar theater.
                'Confidence: ${(result.confidence! * 100).round()}%',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
              ),
            ),
        ],
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
            borderRadius: FansivibeRadius.smdBorder,
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
              borderRadius: FansivibeRadius.smdBorder,
              border: Border.all(
                color: isSelected
                    ? FansivibeColors.accentGold
                    : FansivibeColors.accentGold.withValues(alpha: 0.15),
                width: isSelected ? 1.5 : 1,
              ),
            ),
            child: Text(
              item,
              style: Theme.of(context).textTheme.bodyMedium!.copyWith(
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
              borderRadius: FansivibeRadius.smdBorder,
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
                  style: theme.textTheme.bodyMedium!.copyWith(
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
    return Text(
      label,
      style: FansivibeTypography.titleLargeWithFamily.copyWith(
        fontWeight: FontWeight.w600,
        color: FansivibeColors.textPrimary,
        fontSize: 18,
      ),
    );
  }
}
