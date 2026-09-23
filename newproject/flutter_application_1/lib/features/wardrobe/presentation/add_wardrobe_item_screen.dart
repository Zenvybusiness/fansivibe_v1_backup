import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:fansivibe/features/wardrobe/data/garment_client.dart';
import 'package:fansivibe/features/wardrobe/data/garment_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/data/local_wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_photo_screen.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

/// Screen for filling in item details when adding a new wardrobe item.
///
/// Optional photo flow (M11): photograph the garment, analyze it against
/// the real garment endpoint, review the suggestion, then confirm. AI
/// output only preselects the existing manual chips — the confirmed chips
/// are the canonical values saved to the backend.
class AddWardrobeItemScreen extends StatefulWidget {
  const AddWardrobeItemScreen({
    required this.category,
    this.repository,
    this.garmentClient,
    this.photoGalleryPick,
    super.key,
  });

  final AddItemCategoryConfig category;

  /// Repository override (tests only). Defaults to the live backend.
  final WardrobeRepository? repository;

  /// Garment client override (tests only). Defaults to the live backend.
  final GarmentClient? garmentClient;

  /// Gallery picker override for the photo screen (tests only).
  final Future<XFile?> Function(ImageSource source)? photoGalleryPick;

  @override
  State<AddWardrobeItemScreen> createState() => _AddWardrobeItemScreenState();
}

/// Photo → analysis pipeline stages (idle → photo → analyzing → result).
enum _PhotoStage { none, selected, analyzing, result }

class _AddWardrobeItemScreenState extends State<AddWardrobeItemScreen> {
  String? _selectedType;
  ColorOption? _selectedColor;
  String? _selectedTextureName;
  String? _errorMessage;
  bool _isSubmitting = false;
  late final WardrobeRepository _repository;
  late final GarmentClient _garmentClient;

  Uint8List? _photoBytes;
  String? _photoFilename;
  _PhotoStage _photoStage = _PhotoStage.none;
  String? _analysisStatus;
  bool _stillAnalyzing = false;
  GarmentAnalysisResult? _garmentResult;
  Map<String, dynamic>? _garmentInputMedia;
  String? _garmentRunId;
  Timer? _stillAnalyzingTimer;

  bool get _isValid => _selectedType != null && _selectedColor != null;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? WardrobeRepositoryImpl();
    _garmentClient = widget.garmentClient ?? GarmentClient();
  }

  @override
  void dispose() {
    _stillAnalyzingTimer?.cancel();
    _garmentClient.dispose();
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

    try {
      // Phase 2.1 guests persist on-device through the local repository
      // (photo imageRefs are always null here: garment analysis is
      // server-side, so local items are imageless — the photo step says
      // so when analysis prompts for sign-in). No prompt, no backend.
      final repository =
          isGuestUser ? LocalWardrobeRepository() : _repository;
      final createdItem = await repository.createItem(
        name: newItem.name,
        category: newItem.category,
        color: newItem.color,
        material: newItem.material,
        imageRef: _buildImageRef(),
      );

      if (!mounted) return;

      if (createdItem != null) {
        // Success: return the server-created item as source of truth
        Navigator.pop<WardrobeItemData>(context, createdItem);
      } else {
        // API failure
        setState(() {
          _errorMessage = 'Failed to add item. Please try again.';
          _isSubmitting = false;
        });
      }
    } catch (e) {
      // Network/error failure
      if (!mounted) return;
      setState(() {
        _errorMessage = 'Failed to add item. Please try again.';
        _isSubmitting = false;
      });
    }
  }

  /// Builds the photo reference for the save payload from the garment
  /// run's persisted input-media (key/mediaType/sizeBytes/contentHash are
  /// the backend's own values — never invented). Null when no analyzed
  /// photo exists, so manual saves stay imageless as before.
  MediaRef? _buildImageRef() {
    final media = _garmentInputMedia;
    final bytes = _photoBytes;
    if (media == null || bytes == null) return null;
    final key = media['key'] as String?;
    final mediaType = media['mediaType'] as String?;
    if (key == null || mediaType == null) return null;
    return MediaRef(
      objectKey: key,
      mediaType: mediaType,
      sizeBytes: media['sizeBytes'] as int?,
      contentHash: media['contentHash'] as String?,
      isGenerated: false,
      uploadedAt: media['uploadedAt'] != null
          ? DateTime.tryParse(media['uploadedAt'] as String)
          : null,
      sourceRunId: _garmentRunId,
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
      _photoStage = _PhotoStage.selected;
      _garmentResult = null;
      _garmentInputMedia = null;
      _garmentRunId = null;
      _analysisStatus = null;
      _stillAnalyzing = false;
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
        _photoStage = _PhotoStage.selected;
        _garmentResult = null;
        _garmentInputMedia = null;
        _garmentRunId = null;
        _analysisStatus = null;
        _stillAnalyzing = false;
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
      _photoStage = _PhotoStage.none;
      _garmentResult = null;
      _garmentInputMedia = null;
      _garmentRunId = null;
      _analysisStatus = null;
      _stillAnalyzing = false;
      _errorMessage = null;
    });
  }

  Future<void> _analyzePhoto() async {
    // Phase 2 guests: garment analysis is account-only — prompt at the
    // button instead of submitting into a 401.
    if (isGuestUser) {
      promptGuestSignIn(
        context,
        action: 'Sign in to analyze clothing. Browsing stays free.',
      );
      return;
    }
    final bytes = _photoBytes;
    if (bytes == null || _photoStage == _PhotoStage.analyzing) return;
    if (bytes.length > GarmentClient.maxImageBytes) {
      setState(() {
        _errorMessage =
            'This photo is larger than 20 MB. Retake it at a lower resolution.';
      });
      return;
    }
    setState(() {
      _photoStage = _PhotoStage.analyzing;
      _analysisStatus = 'Uploading photo…';
      _stillAnalyzing = false;
      _garmentResult = null;
      _errorMessage = null;
    });
    // Cold-model notice (outfit-processing precedent): first inference can
    // take a while — say so instead of stalling silently. Timer-cancelled
    // on dispose so no setState fires after the screen is gone.
    _stillAnalyzingTimer?.cancel();
    _stillAnalyzingTimer = Timer(const Duration(seconds: 20), () {
      if (!mounted || _photoStage != _PhotoStage.analyzing) return;
      setState(() {
        _stillAnalyzing = true;
      });
    });

    final runId = await _garmentClient.submitGarmentAnalysisBytes(
      bytes,
      filename: _photoFilename ?? 'wardrobe_item.jpg',
    );
    if (!mounted) return;
    if (runId == null) {
      setState(() {
        _photoStage = _PhotoStage.selected;
        _analysisStatus = null;
        _errorMessage = 'Could not upload the photo. Please try again.';
      });
      return;
    }
    setState(() => _analysisStatus = 'Analyzing clothing…');
    final run = await _garmentClient.pollGarmentRun(runId: runId);
    if (!mounted) return;
    if (run == null) {
      setState(() {
        _photoStage = _PhotoStage.selected;
        _analysisStatus = null;
        _errorMessage =
            'Analysis is taking longer than expected. '
            'Please try again.';
      });
      return;
    }
    if (run.isFailed) {
      setState(() {
        _photoStage = _PhotoStage.selected;
        _analysisStatus = null;
        _errorMessage = _garmentFailureMessage(run.failureReason);
      });
      return;
    }
    final resultMap = run.result;
    if (resultMap == null) {
      setState(() {
        _photoStage = _PhotoStage.selected;
        _analysisStatus = null;
        _errorMessage = 'The analysis result was unreadable. Please try again.';
      });
      return;
    }
    late final GarmentAnalysisResult result;
    try {
      result = GarmentAnalysisResult.fromJson(resultMap);
    } on FormatException {
      if (!mounted) return;
      setState(() {
        _photoStage = _PhotoStage.selected;
        _analysisStatus = null;
        _errorMessage = 'The analysis result was unreadable. Please try again.';
      });
      return;
    }
    setState(() {
      _photoStage = _PhotoStage.result;
      _analysisStatus = null;
      _stillAnalyzing = false;
      _garmentResult = result;
      _garmentInputMedia = run.inputMedia;
      _garmentRunId = runId;
    });
    _prefillFromGarment(result);
  }

  /// Maps a typed backend failure reason to truthful UI copy. Unknown
  /// reasons stay generic — no invented detail, never a fake suggestion.
  String _garmentFailureMessage(String? reason) {
    switch (reason) {
      case 'no_garment_detected':
        return 'No clothing item was detected in this photo. '
            'Retake it with the garment clearly visible.';
      case 'ambiguous_subject':
        return 'Several garments overlap in this photo. '
            'Photograph one item at a time.';
      case 'low_confidence':
        return 'The photo was too unclear to analyze confidently. '
            'Retake it in better light.';
      case 'analyzer_timeout':
      case 'analyzer_unavailable':
        return 'The analysis service is unavailable right now. '
            'Please try again in a moment.';
      default:
        return 'Garment analysis failed. Please try again.';
    }
  }

  /// Preselects manual chips from the AI suggestion. Only exact
  /// case-insensitive matches against the existing on-screen options —
  /// near-misses stay unselected for the user to pick. Existing user
  /// selections are never overwritten.
  void _prefillFromGarment(GarmentAnalysisResult result) {
    final subcategory = result.subcategory;
    if (_selectedType == null && subcategory != null) {
      final lowered = subcategory.toLowerCase();
      for (final type in widget.category.types) {
        if (type.toLowerCase() == lowered) {
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
    _errorMessage = null;
  }

  String _buildItemName() {
    final texture = _selectedTextureName != null
        ? ' $_selectedTextureName'
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
                        const SizedBox(height: 32),

                        // Error message (shared error treatment)
                        if (_errorMessage != null) ...[
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: FansivibeColors.error.withValues(alpha: 0.1),
                              borderRadius: FansivibeRadius.smdBorder,
                              border: Border.all(
                                color: FansivibeColors.error.withValues(alpha: 0.3),
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

                        // Save button (shared primary action)
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
        children: [
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
        if (_photoStage == _PhotoStage.analyzing) ...[
          Row(
            children: [
              const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2.5),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  _stillAnalyzing
                      ? 'Still analyzing — this can take a little longer '
                          'on the first scan.'
                      : (_analysisStatus ?? 'Analyzing clothing…'),
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: FansivibeColors.textSecondary,
                  ),
                ),
              ),
            ],
          ),
        ] else if (_photoStage == _PhotoStage.result &&
            _garmentResult != null) ...[
          _buildGarmentSummary(theme, _garmentResult!),
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
                child: FansiButton.secondary(
                  label: 'Analyze Again',
                  icon: Icons.refresh_rounded,
                  onPressed: _analyzePhoto,
                ),
              ),
            ],
          ),
        ] else ...[
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
                  onPressed: _analyzePhoto,
                ),
              ),
            ],
          ),
        ],
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
                      fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
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
