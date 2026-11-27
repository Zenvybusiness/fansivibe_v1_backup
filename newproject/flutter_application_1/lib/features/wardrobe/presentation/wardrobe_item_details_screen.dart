import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/media/data/media_client.dart';
import 'package:fansivibe/features/media/domain/image_pipeline.dart';
import 'package:fansivibe/features/media/domain/original_file_manager.dart';
import 'package:fansivibe/features/media/presentation/wardrobe_cache_manager.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_client.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_item_photo.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/local_wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/widgets/wardrobe_widgets.dart';
import 'package:fansivibe/shared/components/fansi_image_well.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

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
    this.mediaClient,
    this.photoGalleryPick,
    this.cacheManager,
    super.key,
  });

  final String itemId;
  final WardrobeItemData? item;
  final WardrobeRepository? repository;
  final MediaClient? mediaClient;
  final Future<XFile?> Function(ImageSource source)? photoGalleryPick;
  final WardrobeCacheManager? cacheManager;

  @override
  State<WardrobeItemDetailsScreen> createState() =>
      _WardrobeItemDetailsScreenState();
}

class _WardrobeItemDetailsScreenState extends State<WardrobeItemDetailsScreen> {
  late WardrobeRepository _repository;
  late final MediaClient _mediaClient;
  late final WardrobeCacheManager _cacheManager;
  WardrobeItemData? _item;
  bool _isLoading = true;
  bool _isEditing = false;
  bool _isSaving = false;
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
  String? _newFit;
  bool? _newFavorite;
  Uint8List? _pendingPhotoBytes;
  bool _pendingPhotoRemoved = false;

  @override
  void initState() {
    super.initState();
    _mediaClient = widget.mediaClient ?? MediaClient();
    _cacheManager = widget.cacheManager ?? WardrobeCacheManager.instance;
    // Signed-out screens read/edit/delete through the local repository —
    // same screen, zero API calls. Injected fakes without savedLocally keep
    // exercising the authenticated backend path (per guest_mode.dart contract).
    if (isGuestUser ||
        (!AuthSession.isAuthenticated && widget.repository == null)) {
      _repository = LocalWardrobeRepository();
    } else {
      _repository = widget.repository ?? WardrobeRepositoryImpl();
    }
    _loadItem();
    // The data source is session-derived: re-resolve it when the
    // session flips under this mounted route.
    AuthSession.authVersion.addListener(_onAuthChanged);
  }

  void _onAuthChanged() {
    if (!mounted) return;
    if (isGuestUser ||
        (!AuthSession.isAuthenticated && widget.repository == null)) {
      _repository = LocalWardrobeRepository();
    } else {
      _repository = widget.repository ?? WardrobeRepositoryImpl();
    }
    _loadItem();
  }

  @override
  void dispose() {
    AuthSession.authVersion.removeListener(_onAuthChanged);
    if (widget.mediaClient == null) {
      _mediaClient.dispose();
    }
    super.dispose();
  }

  bool _hasPhoto(WardrobeItemData item) =>
      (item.imageBytes != null && item.imageBytes!.isNotEmpty) ||
      (item.imageUrl != null && item.imageUrl!.isNotEmpty) ||
      item.imageRef != null ||
      (item.localOriginalPath != null && item.localOriginalPath!.isNotEmpty);

  void _syncDraftFields(WardrobeItemData item) {
    _newName = item.name;
    _newCategory = item.category;
    _newColor = item.color;
    _newMaterial = item.material;
    _newFit = item.fit;
    _newFavorite = item.isFavorite;
    _pendingPhotoBytes = null;
    _pendingPhotoRemoved = false;
  }

  Future<void> _loadItem() async {
    final item = await _repository.getItem(itemId: widget.itemId);
    if (!mounted) return;
    setState(() {
      // Backend rows carry metadata only: rehydrate the photo from the
      // on-device mirror by id (imageless rows pass through).
      final resolved = item == null ? null : attachLocalPhoto(item);
      _item = resolved;
      _isLoading = false;
      _isLoggingWear = false;
      _wearIdempotencyKey = null;
      if (resolved != null) {
        _syncDraftFields(resolved);
      }
    });
  }

  void _toggleEdit() {
    if (_isSaving) return;
    if (!_isEditing) {
      final current = _item;
      if (current != null) {
        _syncDraftFields(current);
      }
      setState(() {
        _isEditing = true;
      });
    } else {
      _saveChanges();
    }
  }

  void _showErrorSnackBar(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8.0)),
      ),
    );
  }

  void _invalidateItemCache(WardrobeItemData item) {
    final keys = <String?>{
      item.imageRef?.contentHash,
      item.imageRef?.objectKey,
      item.id,
    };
    for (final key in keys) {
      if (key != null && key.isNotEmpty) {
        _cacheManager.invalidate(key);
      }
    }
  }

  Future<void> _pickReplacementPhoto() async {
    if (_isSaving) return;
    final picker =
        widget.photoGalleryPick ??
        (source) => ImagePicker().pickImage(source: source);
    try {
      final picked = await picker(ImageSource.gallery);
      if (picked == null || !mounted) return;
      final bytes = await picked.readAsBytes();
      if (!mounted) return;
      if (bytes.isEmpty) {
        _showErrorSnackBar('Selected image is empty. Please choose another.');
        return;
      }
      setState(() {
        _pendingPhotoBytes = bytes;
        _pendingPhotoRemoved = false;
      });
    } catch (_) {
      _showErrorSnackBar('Could not load selected image. Please try again.');
    }
  }

  void _removePhotoDraft() {
    if (_isSaving) return;
    setState(() {
      _pendingPhotoBytes = null;
      _pendingPhotoRemoved = true;
    });
  }

  Future<void> _saveChanges() async {
    if (_isSaving) return;
    if (!(_formKey.currentState?.validate() ?? false)) {
      return;
    }

    final current = _item;
    if (current == null) return;

    final nameChanged = _newName != current.name;
    final categoryChanged = _newCategory != current.category;
    final colorChanged = _newColor != current.color;
    final materialChanged = _newMaterial != current.material;
    final clearMaterial = materialChanged && _newMaterial == null;
    final fitChanged = _newFit != current.fit;
    final clearFit = fitChanged && _newFit == null;
    final favoriteChanged = _newFavorite != current.isFavorite;
    final photoReplaced =
        _pendingPhotoBytes != null && _pendingPhotoBytes!.isNotEmpty;
    final photoRemoved = _pendingPhotoRemoved && !photoReplaced;

    if (!nameChanged &&
        !categoryChanged &&
        !colorChanged &&
        !materialChanged &&
        !fitChanged &&
        !favoriteChanged &&
        !photoReplaced &&
        !photoRemoved) {
      setState(() {
        _isEditing = false;
      });
      return;
    }

    setState(() {
      _isSaving = true;
    });

    Uint8List? preparedPhotoBytes;
    String? newLocalOriginalPath;
    MediaRef? newImageRef;

    try {
      if (photoReplaced) {
        preparedPhotoBytes = await prepareWardrobePhoto(_pendingPhotoBytes);
        if (!mounted) return;

        final uploadBytes = _pendingPhotoBytes!;
        if (AuthSession.isAuthenticated && !isGuestUser) {
          final detectedMime = detectImageMimeType(uploadBytes);
          if (uploadBytes.length > 2 * 1024 * 1024 ||
              (detectedMime != 'image/jpeg' && detectedMime != 'image/webp')) {
            setState(() {
              _isSaving = false;
            });
            _showErrorSnackBar(
              'Please choose a JPEG or WebP image under 2 MB.',
            );
            return;
          }

          final clientSha = sha256Hex(uploadBytes);
          final dims = await getImageDimensions(uploadBytes);
          final idempotencyKey =
              'edit_${widget.itemId}_${clientSha.substring(0, 16)}_${DateTime.now().millisecondsSinceEpoch}';

          final authRes = await _mediaClient.authorizeUpload(
            clientSizeBytes: uploadBytes.length,
            clientSha256: clientSha,
            idempotencyKey: idempotencyKey,
            mimeType: detectedMime!,
            clientDeclaredWidth: dims?.$1,
            clientDeclaredHeight: dims?.$2,
          );
          if (authRes == null) {
            if (!mounted) return;
            setState(() {
              _isSaving = false;
            });
            _showErrorSnackBar(
              'Failed to upload replacement photo. Please try again.',
            );
            return;
          }

          final uploaded = await _mediaClient.uploadBytesDirect(
            presignedPutUrl: authRes.presignedPutUrl,
            bytes: uploadBytes,
            contentType: detectedMime,
          );
          if (!uploaded) {
            if (!mounted) return;
            setState(() {
              _isSaving = false;
            });
            _showErrorSnackBar(
              'Failed to upload replacement photo. Please try again.',
            );
            return;
          }

          final pubRes = await _mediaClient.completeUpload(
            uploadId: authRes.uploadId,
          );
          if (pubRes == null || pubRes.status != 'published') {
            if (!mounted) return;
            setState(() {
              _isSaving = false;
            });
            _showErrorSnackBar(
              'Failed to publish replacement photo. Please try again.',
            );
            return;
          }

          newImageRef = MediaRef(
            objectKey: pubRes.canonicalKey,
            mediaType: pubRes.mediaType,
            uploadId: pubRes.uploadId,
            width: pubRes.width,
            height: pubRes.height,
            sizeBytes: pubRes.sizeBytes,
            contentHash: pubRes.sha256,
            sourceRunId: current.sourceRunId ?? current.imageRef?.sourceRunId,
            candidateId: current.candidateId ?? current.imageRef?.candidateId,
            extractionConfidence:
                current.extractionConfidence ??
                current.imageRef?.extractionConfidence,
          );
        }

        if (preparedPhotoBytes != null && preparedPhotoBytes.isNotEmpty) {
          newLocalOriginalPath = await OriginalFileManager.instance
              .saveOriginal(idOrHash: '', bytes: preparedPhotoBytes);
        }
      }

      final updatedItem = await _repository.updateItemDetails(
        itemId: widget.itemId,
        name: nameChanged ? _newName : null,
        category: categoryChanged ? _newCategory : null,
        color: colorChanged ? _newColor : null,
        material: (materialChanged && !clearMaterial) ? _newMaterial : null,
        clearMaterial: clearMaterial,
        isFavorite: favoriteChanged ? _newFavorite : null,
        fit: (fitChanged && !clearFit) ? _newFit : null,
        clearFit: clearFit,
        imageRef: newImageRef,
        clearImageRef: photoRemoved,
        imageBytes: preparedPhotoBytes,
      );

      if (!mounted) return;

      if (updatedItem != null) {
        if (photoReplaced || photoRemoved) {
          _invalidateItemCache(current);
        }

        final effectiveUpdated = updatedItem.copyWith(
          imageBytes: photoRemoved
              ? null
              : (preparedPhotoBytes ??
                    updatedItem.imageBytes ??
                    current.imageBytes),
          clearImageBytes: photoRemoved,
          localOriginalPath: photoRemoved
              ? null
              : (newLocalOriginalPath ??
                    updatedItem.localOriginalPath ??
                    current.localOriginalPath),
          clearLocalOriginalPath: photoRemoved,
          imageRef: photoRemoved
              ? null
              : (updatedItem.imageRef ?? newImageRef ?? current.imageRef),
          clearImageRef: photoRemoved,
          imageUrl: photoRemoved
              ? null
              : (photoReplaced
                    ? (updatedItem.imageUrl ??
                          updatedItem.imageRef?.downloadUrl ??
                          updatedItem.imageRef?.url)
                    : (updatedItem.imageUrl ?? current.imageUrl)),
          clearImageUrl: photoRemoved,
          fitConfidence: updatedItem.fitConfidence ?? current.fitConfidence,
          sourceRunId: updatedItem.sourceRunId ?? current.sourceRunId,
          candidateId: updatedItem.candidateId ?? current.candidateId,
          extractionConfidence:
              updatedItem.extractionConfidence ?? current.extractionConfidence,
          createdAt: updatedItem.createdAt ?? current.createdAt,
          updatedAt: updatedItem.updatedAt ?? current.updatedAt,
        );

        setState(() {
          _item = effectiveUpdated;
          _syncDraftFields(effectiveUpdated);
          _isEditing = false;
          _isSaving = false;
        });

        LearningService.instance.updateItem(
          effectiveUpdated.id,
          wardrobeEntryFromItem(effectiveUpdated, clearImage: photoRemoved),
        );
      } else {
        setState(() {
          _isSaving = false;
        });
        _showErrorSnackBar('Failed to save changes. Please try again.');
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isSaving = false;
      });
      _showErrorSnackBar(
        'Failed to save changes. Please check your connection and try again.',
      );
    }
  }

  Future<void> _deleteItem() async {
    // Phase 2.1 guests delete on-device through the local repository —
    // no prompt, no backend call.
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
    // Phase 2 guests: wear logging is account-only — prompt at the
    // button instead of posting into a 401.
    if (isGuestUser) {
      promptGuestSignIn(
        context,
        action: 'Sign in to log wears. Browsing stays free.',
      );
      return;
    }
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
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8.0)),
      ),
    );
  }

  Widget _buildLoadingScreen(BuildContext context) {
    return const Center(child: CircularProgressIndicator());
  }

  Widget _buildMissingItemScreen(BuildContext context) {
    return const Center(child: Text('Item not found'));
  }

  Widget _buildPhotoEditorPreview(WardrobeItemData item) {
    if (_pendingPhotoRemoved) {
      return FansiImageWell(
        icon: wardrobeIconFor(item.category),
        color: wardrobeSwatchFor(item.color),
        iconSize: 40,
        showLabel: false,
      );
    }
    if (_pendingPhotoBytes != null && _pendingPhotoBytes!.isNotEmpty) {
      return Image.memory(
        _pendingPhotoBytes!,
        fit: BoxFit.cover,
        gaplessPlayback: true,
        errorBuilder: (_, __, ___) => FansiImageWell(
          icon: wardrobeIconFor(item.category),
          color: wardrobeSwatchFor(item.color),
          iconSize: 40,
          showLabel: false,
        ),
      );
    }
    if (_hasPhoto(item)) {
      return WardrobeItemImage(item: item, iconSize: 48);
    }
    return FansiImageWell(
      icon: wardrobeIconFor(item.category),
      color: wardrobeSwatchFor(item.color),
      iconSize: 40,
      showLabel: false,
    );
  }

  Widget _buildEditingForm(BuildContext context, WardrobeItemData item) {
    final theme = Theme.of(context);
    final hasActivePhoto =
        !_pendingPhotoRemoved &&
        (_pendingPhotoBytes != null || _hasPhoto(item));
    final fitOptions = <String>[
      ...AddItemConfig.fitOptions,
      if (_newFit != null &&
          _newFit!.isNotEmpty &&
          !AddItemConfig.fitOptions.contains(_newFit))
        _newFit!,
    ];

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
            const SizedBox(height: 16),

            // Photo management section
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: SizedBox(
                height: 180,
                width: double.infinity,
                child: _buildPhotoEditorPreview(item),
              ),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                OutlinedButton.icon(
                  onPressed: _isSaving ? null : _pickReplacementPhoto,
                  icon: const Icon(Icons.photo_camera_outlined, size: 16),
                  label: Text(hasActivePhoto ? 'Replace Photo' : 'Add Photo'),
                ),
                if (hasActivePhoto)
                  OutlinedButton.icon(
                    onPressed: _isSaving ? null : _removePhotoDraft,
                    icon: const Icon(Icons.delete_outline_rounded, size: 16),
                    label: const Text('Remove Photo'),
                  ),
              ],
            ),
            const SizedBox(height: 20),

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
              initialValue: _newCategory,
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
                DropdownMenuItem(
                  value: 'accessories',
                  child: Text('Accessories'),
                ),
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

            // Fit field
            DropdownButtonFormField<String?>(
              initialValue: _newFit,
              decoration: InputDecoration(
                labelText: 'Fit (optional)',
                border: OutlineInputBorder(
                  borderRadius: FansivibeRadius.baseBorder,
                ),
              ),
              items: [
                const DropdownMenuItem<String?>(
                  value: null,
                  child: Text('Not specified'),
                ),
                ...fitOptions.map(
                  (f) => DropdownMenuItem<String?>(value: f, child: Text(f)),
                ),
              ],
              onChanged: (value) {
                setState(() {
                  _newFit = value;
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
                  onPressed: _isSaving
                      ? null
                      : () {
                          setState(() {
                            _syncDraftFields(item);
                            _isEditing = false;
                          });
                        },
                  child: const Text('Cancel'),
                ),
                const SizedBox(width: 8),
                ElevatedButton(
                  onPressed: _isSaving ? null : _saveChanges,
                  child: _isSaving
                      ? const SizedBox(
                          height: 16,
                          width: 16,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            valueColor: AlwaysStoppedAnimation<Color>(
                              FansivibeColors.background,
                            ),
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
          // Item photo (bounded hero, same slot as the wardrobe card) —
          // only when the item has a photo, so manual entries keep their
          // exact existing layout. Undecodable bytes fall back safely.
          if (_hasPhoto(item)) ...[
            const SizedBox(height: 16),
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: SizedBox(
                height: 220,
                width: double.infinity,
                child: WardrobeItemImage(item: item, iconSize: 48),
              ),
            ),
          ],
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

          if (item.fit != null && item.fit!.isNotEmpty) ...[
            _metadataRow(
              theme,
              icon: Icons.straighten_rounded,
              label: 'Fit',
              value: item.fit!,
            ),
            const SizedBox(height: 12),
          ],

          // Favorite
          _metadataRow(
            theme,
            icon: item.isFavorite
                ? Icons.favorite_rounded
                : Icons.favorite_border_rounded,
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
                          valueColor: AlwaysStoppedAnimation<Color>(
                            FansivibeColors.background,
                          ),
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
                  onPressed: _isSaving ? null : _saveChanges,
                ),
              ]
            : [
                IconButton(
                  icon: const Icon(Icons.edit_rounded),
                  onPressed: _toggleEdit,
                ),
              ],
      ),
      body: SafeArea(child: _buildContent(context)),
    );
  }
}
