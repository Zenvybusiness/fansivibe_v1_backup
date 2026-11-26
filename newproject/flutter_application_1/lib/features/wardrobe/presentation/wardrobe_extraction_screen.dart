import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/media/data/media_client.dart';
import 'package:fansivibe/features/media/domain/image_pipeline.dart';
import 'package:fansivibe/features/wardrobe/data/garment_client.dart';
import 'package:fansivibe/features/wardrobe/data/garment_models.dart';
import 'package:fansivibe/features/wardrobe/data/local_wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_item_photo.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_photo_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

enum ExtractionUiStage { idle, extracting, selection, saving, error }

/// End-to-end screen for extracting clothing items from an image,
/// selecting which candidates to save, and persisting them to the wardrobe.
class WardrobeExtractionScreen extends StatefulWidget {
  const WardrobeExtractionScreen({
    this.initialImageBytes,
    this.initialFilename,
    this.garmentClient,
    this.mediaClient,
    this.repository,
    this.pickImage,
    this.takePhoto,
    super.key,
  });

  final Uint8List? initialImageBytes;
  final String? initialFilename;
  final GarmentClient? garmentClient;
  final MediaClient? mediaClient;
  final WardrobeRepository? repository;
  final Future<XFile?> Function(ImageSource source)? pickImage;
  final Future<XFile?> Function()? takePhoto;

  @override
  State<WardrobeExtractionScreen> createState() =>
      _WardrobeExtractionScreenState();
}

class _WardrobeExtractionScreenState extends State<WardrobeExtractionScreen> {
  late final GarmentClient _garmentClient;
  late final MediaClient _mediaClient;
  late final WardrobeRepository _repository;

  Uint8List? _imageBytes;
  String? _filename;
  ExtractionUiStage _stage = ExtractionUiStage.idle;
  String? _statusMessage;
  String? _errorMessage;
  bool _stillAnalyzing = false;
  Timer? _stillAnalyzingTimer;

  List<GarmentCandidate> _candidates = [];
  String? _idempotencyKey;
  String? _currentRunId;
  String? _saveIdempotencyKey;
  String? _partialExtractionNotice;
  bool _isSaving = false;
  bool _assetsCleaned = false;

  @override
  void initState() {
    super.initState();
    _garmentClient = widget.garmentClient ?? GarmentClient();
    _mediaClient = widget.mediaClient ?? MediaClient();
    _repository =
        widget.repository ??
        (isGuestUser || !AuthSession.isAuthenticated
            ? LocalWardrobeRepository()
            : WardrobeRepositoryImpl());

    if (widget.initialImageBytes != null &&
        widget.initialImageBytes!.isNotEmpty) {
      _imageBytes = widget.initialImageBytes;
      _filename = widget.initialFilename ?? 'wardrobe_item.jpg';
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _startExtraction();
      });
    }
  }

  @override
  void dispose() {
    _stillAnalyzingTimer?.cancel();
    _cleanupCurrentRunAssets();
    _garmentClient.dispose();
    _mediaClient.dispose();
    super.dispose();
  }

  void _cleanupCurrentRunAssets() {
    final runId = _currentRunId;
    if (runId == null || _assetsCleaned) return;
    if (isGuestUser || !AuthSession.isAuthenticated) return;
    _assetsCleaned = true;
    unawaited(_garmentClient.cleanupExtractionAssets(runId: runId));
  }

  Future<void> _captureWithCamera() async {
    if (widget.takePhoto != null) {
      final file = await widget.takePhoto!();
      if (file == null || !mounted) return;
      final bytes = await file.readAsBytes();
      _handleSelectedImage(bytes, file.name);
      return;
    }

    final result = await Navigator.of(context).push<WardrobePhoto>(
      MaterialPageRoute(
        builder: (_) => WardrobePhotoScreen(
          pickImage: widget.pickImage,
          takePhoto: widget.takePhoto,
        ),
      ),
    );

    if (result != null && mounted) {
      _handleSelectedImage(result.bytes, result.filename);
    }
  }

  Future<void> _pickFromGallery() async {
    try {
      final picker =
          widget.pickImage ??
          ((source) => ImagePicker().pickImage(
            source: source,
            maxWidth: 1920,
            maxHeight: 1920,
          ));

      final file = await picker(ImageSource.gallery);
      if (file == null || !mounted) return;
      final bytes = await file.readAsBytes();
      _handleSelectedImage(
        bytes,
        file.name.isNotEmpty ? file.name : 'wardrobe_item.jpg',
      );
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _stage = ExtractionUiStage.error;
        _errorMessage =
            'Could not open photo gallery. Please check permissions.';
      });
    }
  }

  void _handleSelectedImage(Uint8List bytes, String filename) {
    if (bytes.isEmpty) {
      setState(() {
        _stage = ExtractionUiStage.error;
        _errorMessage =
            'The selected image is empty. Please choose another image.';
      });
      return;
    }

    if (bytes.length > GarmentClient.maxImageBytes) {
      setState(() {
        _stage = ExtractionUiStage.error;
        _errorMessage =
            'Image exceeds 20 MB size limit. Please select a smaller photo.';
      });
      return;
    }

    final mime = detectImageMimeType(bytes);
    if (mime == null ||
        (mime != 'image/jpeg' && mime != 'image/png' && mime != 'image/webp')) {
      setState(() {
        _stage = ExtractionUiStage.error;
        _errorMessage =
            'Unsupported image format. Please select a JPEG, PNG, or WebP photo.';
      });
      return;
    }

    setState(() {
      _imageBytes = bytes;
      _filename = filename;
      _errorMessage = null;
      _partialExtractionNotice = null;
      _currentRunId = null;
      _saveIdempotencyKey = null;
      _assetsCleaned = false;
    });

    _startExtraction();
  }

  Future<void> _startExtraction() async {
    final bytes = _imageBytes;
    if (bytes == null) return;

    setState(() {
      _stage = ExtractionUiStage.extracting;
      _statusMessage = 'Uploading photo…';
      _stillAnalyzing = false;
      _errorMessage = null;
      _partialExtractionNotice = null;
      _saveIdempotencyKey = null;
      _assetsCleaned = false;
    });

    _stillAnalyzingTimer?.cancel();
    _stillAnalyzingTimer = Timer(const Duration(seconds: 15), () {
      if (!mounted || _stage != ExtractionUiStage.extracting) return;
      setState(() {
        _stillAnalyzing = true;
      });
    });

    if (isGuestUser) {
      await _extractEphemeral(bytes);
      return;
    }

    final key = _idempotencyKey ??= newGarmentIdempotencyKey();
    final runId = await _garmentClient.submitGarmentAnalysisBytes(
      bytes,
      filename: _filename ?? 'wardrobe_item.jpg',
      idempotencyKey: key,
    );

    if (!mounted) return;
    if (runId == null) {
      setState(() {
        _stage = ExtractionUiStage.error;
        _errorMessage =
            _garmentClient.lastSubmitError ??
            'Could not upload photo for analysis. Please check your connection.';
      });
      return;
    }

    _currentRunId = runId;
    setState(() => _statusMessage = 'Extracting garments with AI…');
    final run = await _garmentClient.pollGarmentRun(runId: runId);

    if (!mounted) return;
    if (run == null) {
      setState(() {
        _stage = ExtractionUiStage.error;
        _errorMessage = 'Garment analysis timed out. Please try again.';
      });
      return;
    }

    if (run.isFailed) {
      setState(() {
        _stage = ExtractionUiStage.error;
        _errorMessage = _failureMessage(run.failureReason);
      });
      return;
    }

    final resultMap = run.result;
    if (resultMap == null) {
      setState(() {
        _stage = ExtractionUiStage.error;
        _errorMessage = 'The analysis result was empty. Please try again.';
      });
      return;
    }

    _handleAnalysisResult(resultMap, runId: runId);
  }

  Future<void> _extractEphemeral(Uint8List bytes) async {
    final outcome = await _garmentClient.submitGarmentEphemeralBytes(
      bytes,
      filename: _filename ?? 'wardrobe_item.jpg',
    );

    if (!mounted) return;
    final snapshot = outcome.snapshot;
    if (snapshot == null) {
      setState(() {
        _stage = ExtractionUiStage.error;
        _errorMessage = _failureMessage(outcome.failureReason);
      });
      return;
    }

    _handleAnalysisResult(snapshot);
  }

  void _handleAnalysisResult(Map<String, dynamic> resultData, {String? runId}) {
    late final GarmentAnalysisResult result;
    try {
      result = GarmentAnalysisResult.fromJson(resultData);
    } catch (_) {
      setState(() {
        _stage = ExtractionUiStage.error;
        _errorMessage = 'Unable to parse garment details. Please try again.';
      });
      return;
    }

    final candidates = List<GarmentCandidate>.from(result.candidates);
    if (candidates.isEmpty) {
      setState(() {
        _stage = ExtractionUiStage.error;
        _errorMessage =
            'No clothing item was clearly detected in this photo. Please retake with the item centered and in good lighting.';
      });
      return;
    }

    String? partialNotice;
    if (result.partialFailures.isNotEmpty) {
      partialNotice =
          '${result.partialFailures.length} detected region(s) could not be extracted cleanly; review the available garments below.';
    }

    setState(() {
      _stage = ExtractionUiStage.selection;
      _candidates = candidates;
      _partialExtractionNotice = partialNotice;
      _stillAnalyzing = false;
      _statusMessage = null;
      _idempotencyKey = null;
      if (runId != null) {
        _currentRunId = runId;
      }
    });

    if (runId != null && !isGuestUser) {
      _loadCandidateCrops(runId, candidates);
    }
  }

  Future<void> _loadCandidateCrops(
    String runId,
    List<GarmentCandidate> candidates,
  ) async {
    for (var i = 0; i < candidates.length; i++) {
      final c = candidates[i];
      if (!c.hasCrop || c.id == null) continue;
      final cropBytes = await _garmentClient.fetchCandidateCropBytes(
        runId: runId,
        candidateId: c.id!,
      );
      if (!mounted || cropBytes == null) continue;
      setState(() {
        final idx = _candidates.indexWhere((item) => item.id == c.id);
        if (idx != -1) {
          _candidates[idx] = _candidates[idx].copyWith(cropBytes: cropBytes);
        }
      });
    }
  }

  String _failureMessage(String? reason) {
    switch (reason) {
      case 'no_garment_detected':
        return 'No clothing item was detected in this photo. '
            'Please take a photo where the garment is clearly visible.';
      case 'ambiguous_subject':
        return 'Multiple overlapping garments were difficult to distinguish. '
            'Please photograph one item clearly.';
      case 'low_confidence':
        return 'The photo was too unclear or dimly lit to analyze confidently. '
            'Please retake with better lighting.';
      case 'invalid_image':
        return 'The selected image is invalid or corrupted. Please choose a valid JPEG, PNG, or WebP photo.';
      case 'oversized_image':
        return 'The image dimensions or file size exceed supported limits. Please choose a smaller photo.';
      case 'unsupported_format':
        return 'Unsupported image format. Please select a JPEG, PNG, or WebP photo.';
      case 'analyzer_timeout':
        return 'The analysis service took too long to reply. Please try again.';
      case 'analyzer_unavailable':
        return 'AI extraction service is currently unavailable. Please check your setup.';
      case 'invalid_analyzer_response':
        return 'The AI service returned an unreadable response. Please try again.';
      default:
        return 'Garment extraction failed. Please try again.';
    }
  }

  void _toggleCandidateSelection(int index) {
    setState(() {
      final current = _candidates[index];
      if (current.isSaved) return;
      _candidates[index] = current.copyWith(isSelected: !current.isSelected);
      _saveIdempotencyKey = null;
    });
  }

  void _inspectCandidate(int index) {
    final candidate = _candidates[index];
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: FansivibeColors.surfaceContainerLow,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => _CandidateInspectSheet(
        candidate: candidate,
        fallbackPhotoBytes: _imageBytes,
        onToggleSelected: () {
          Navigator.of(ctx).pop();
          _toggleCandidateSelection(index);
        },
        onEdit: () {
          Navigator.of(ctx).pop();
          _editCandidate(index);
        },
      ),
    );
  }

  void _editCandidate(int index) async {
    final candidate = _candidates[index];
    final categoryConfig = AddItemConfig.categoryConfigFor(candidate.category);

    final updated = await showModalBottomSheet<GarmentCandidate>(
      context: context,
      isScrollControlled: true,
      backgroundColor: FansivibeColors.surfaceContainerLow,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => _CandidateEditSheet(
        candidate: candidate,
        categoryConfig: categoryConfig,
      ),
    );

    if (updated != null && mounted) {
      setState(() {
        _candidates[index] = updated;
        _saveIdempotencyKey = null;
      });
    }
  }

  Future<void> _saveSelectedGarments() async {
    if (_isSaving) return;
    final selectedCandidates = _candidates
        .where((c) => c.isSelected && !c.isSaved)
        .toList();
    if (selectedCandidates.isEmpty) return;

    _isSaving = true;
    setState(() {
      _stage = ExtractionUiStage.saving;
      _statusMessage =
          'Saving ${selectedCandidates.length} item(s) to wardrobe…';
      _errorMessage = null;
    });

    final useServerSavePipeline =
        AuthSession.isAuthenticated &&
        !isGuestUser &&
        _currentRunId != null &&
        _repository is WardrobeRepositoryImpl;

    if (useServerSavePipeline) {
      await _saveViaExtractionEndpoint(selectedCandidates);
      return;
    }

    await _saveViaRepositoryLoop(selectedCandidates);
  }

  Future<void> _saveViaExtractionEndpoint(
    List<GarmentCandidate> selectedCandidates,
  ) async {
    final runId = _currentRunId!;
    var saveKey = _saveIdempotencyKey ??= newGarmentIdempotencyKey();
    var result = await _garmentClient.saveExtractedGarments(
      runId: runId,
      candidates: selectedCandidates,
      idempotencyKey: saveKey,
    );

    if (result != null && result.isConflict) {
      saveKey = _saveIdempotencyKey = newGarmentIdempotencyKey();
      result = await _garmentClient.saveExtractedGarments(
        runId: runId,
        candidates: selectedCandidates,
        idempotencyKey: saveKey,
      );
    }

    _isSaving = false;
    if (!mounted) return;

    if (result == null) {
      setState(() {
        _stage = ExtractionUiStage.selection;
        _errorMessage = 'Failed to save items to wardrobe. Please try again.';
      });
      return;
    }

    if (result.errorMessage != null && !result.hasSavedItems) {
      setState(() {
        _stage = ExtractionUiStage.selection;
        _errorMessage = result!.errorMessage;
      });
      return;
    }

    final savedUiItems = <WardrobeItemData>[];
    for (var i = 0; i < result.savedItems.length; i++) {
      final dto = result.savedItems[i];
      var uiItem = mapItemDtoToUi(dto);
      final matchingCand = i < selectedCandidates.length
          ? selectedCandidates[i]
          : null;
      final localBytes = matchingCand?.cropBytes;
      if (localBytes != null && localBytes.isNotEmpty) {
        final prepared = await prepareWardrobePhoto(localBytes);
        uiItem = uiItem.copyWith(imageBytes: prepared ?? localBytes);
        LearningService.instance.updateItem(
          uiItem.id,
          wardrobeEntryFromItem(uiItem),
        );
      }
      savedUiItems.add(uiItem);
    }

    if (result.cleanedUpAssets) {
      _assetsCleaned = true;
    }

    if (!mounted) return;
    if (result.failedItems.isEmpty && savedUiItems.isNotEmpty) {
      _saveIdempotencyKey = null;
      _assetsCleaned = true;
      Navigator.of(context).pop<List<WardrobeItemData>>(savedUiItems);
      return;
    }

    final failedIds = result.failedItems.map((f) => f.candidateId).toSet();
    final failedNames = result.failedItems.map((f) => f.name).join(', ');
    setState(() {
      _stage = ExtractionUiStage.selection;
      _saveIdempotencyKey = null;
      _candidates = _candidates.map((c) {
        final wasSelected = selectedCandidates.contains(c);
        if (wasSelected && !failedIds.contains(c.id)) {
          return c.copyWith(isSelected: false, isSaved: true);
        }
        return c;
      }).toList();
      _errorMessage = savedUiItems.isNotEmpty
          ? 'Saved ${savedUiItems.length} item(s). Failed to save: $failedNames. You can retry saving remaining items.'
          : 'Failed to save: $failedNames. Please edit details and try again.';
    });
  }

  Future<void> _saveViaRepositoryLoop(
    List<GarmentCandidate> selectedCandidates,
  ) async {
    final photoBytes = _imageBytes;
    MediaRef? cloudMediaRef;

    // Authenticated legacy media upload fallback when using direct repository
    if (AuthSession.isAuthenticated &&
        !isGuestUser &&
        photoBytes != null &&
        photoBytes.isNotEmpty) {
      try {
        final detectedMime = detectImageMimeType(photoBytes) ?? 'image/jpeg';
        if (photoBytes.length <= 2 * 1024 * 1024 &&
            (detectedMime == 'image/jpeg' || detectedMime == 'image/webp')) {
          final clientSha = sha256Hex(photoBytes);
          final dims = await getImageDimensions(photoBytes);
          final idempotencyKey =
              'ext_${clientSha.substring(0, 16)}_${DateTime.now().millisecondsSinceEpoch}';

          final authRes = await _mediaClient.authorizeUpload(
            clientSizeBytes: photoBytes.length,
            clientSha256: clientSha,
            idempotencyKey: idempotencyKey,
            mimeType: detectedMime,
            clientDeclaredWidth: dims?.$1,
            clientDeclaredHeight: dims?.$2,
          );

          if (authRes != null) {
            final uploaded = await _mediaClient.uploadBytesDirect(
              presignedPutUrl: authRes.presignedPutUrl,
              bytes: photoBytes,
              contentType: detectedMime,
            );

            if (uploaded) {
              final pubRes = await _mediaClient.completeUpload(
                uploadId: authRes.uploadId,
              );
              if (pubRes != null &&
                  (pubRes.status == 'ready' || pubRes.status == 'published')) {
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
        // Upload failure does not crash the save; continues
      }
    }

    final savedItems = <WardrobeItemData>[];
    final savedCandidates = <GarmentCandidate>[];
    final failedCandidates = <GarmentCandidate>[];

    for (final candidate in selectedCandidates) {
      final categoryCode = candidate.category ?? 'tops';
      final colorCode = candidate.color ?? 'Black';
      final name =
          candidate.subcategory ??
          '${candidate.color ?? ''} ${candidate.category ?? 'Item'}'.trim();

      try {
        final created = await _repository.createItem(
          name: name,
          category: categoryCode,
          color: colorCode,
          material: candidate.material,
          imageRef: cloudMediaRef,
          fit: candidate.fit,
          fitConfidence: candidate.confidence,
        );

        if (created != null) {
          final bytesToAttach = candidate.cropBytes ?? photoBytes;
          final attached = created.copyWith(imageBytes: bytesToAttach);
          if (bytesToAttach != null) {
            LearningService.instance.updateItem(
              attached.id,
              wardrobeEntryFromItem(attached),
            );
          }
          savedItems.add(attached);
          savedCandidates.add(candidate);
        } else {
          failedCandidates.add(candidate);
        }
      } catch (_) {
        failedCandidates.add(candidate);
      }
    }

    _isSaving = false;
    if (!mounted) return;

    if (failedCandidates.isEmpty && savedItems.isNotEmpty) {
      _cleanupCurrentRunAssets();
      Navigator.of(context).pop<List<WardrobeItemData>>(savedItems);
    } else if (savedItems.isNotEmpty && failedCandidates.isNotEmpty) {
      setState(() {
        _stage = ExtractionUiStage.selection;
        // Deselect saved candidates to prevent duplicate saves on retry
        _candidates = _candidates.map((c) {
          if (savedCandidates.contains(c)) {
            return c.copyWith(isSelected: false, isSaved: true);
          }
          return c;
        }).toList();
        final failedNames = failedCandidates
            .map((c) => c.subcategory ?? c.category ?? 'Item')
            .join(', ');
        _errorMessage =
            'Saved ${savedItems.length} item(s). Failed to save: $failedNames. You can retry saving remaining items.';
      });
    } else {
      setState(() {
        _stage = ExtractionUiStage.selection;
        _errorMessage = 'Failed to save items to wardrobe. Please try again.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Add via AI Extraction'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final isWide = maxWidth > 600;
            final contentMaxWidth = isWide ? 540.0 : double.infinity;
            final horizontalPadding = isWide ? 48.0 : 20.0;

            return Center(
              child: ConstrainedBox(
                constraints: BoxConstraints(maxWidth: contentMaxWidth),
                child: Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal: horizontalPadding,
                    vertical: FansivibeSpacing.md,
                  ),
                  child: _buildStageContent(theme),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildStageContent(ThemeData theme) {
    switch (_stage) {
      case ExtractionUiStage.idle:
        return _buildIdlePickerView(theme);
      case ExtractionUiStage.extracting:
      case ExtractionUiStage.saving:
        return _buildProgressView(theme);
      case ExtractionUiStage.error:
        return _buildErrorView(theme);
      case ExtractionUiStage.selection:
        return _buildCandidateSelectionView(theme);
    }
  }

  Widget _buildIdlePickerView(ThemeData theme) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(
          Icons.auto_awesome_rounded,
          size: 64,
          color: FansivibeColors.accentGold,
        ),
        const SizedBox(height: FansivibeSpacing.lg),
        Text(
          'Extract Garments with AI',
          style: theme.textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.bold,
            color: FansivibeColors.textPrimary,
          ),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: FansivibeSpacing.sm),
        Text(
          'Capture or upload a photo of your clothing. Our vision model identifies garments, colors, materials, and categories automatically.',
          style: theme.textTheme.bodyMedium?.copyWith(
            color: FansivibeColors.textSecondary,
          ),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: FansivibeSpacing.xl),
        SizedBox(
          width: double.infinity,
          child: FansiButton.primary(
            label: 'Take Photo',
            icon: Icons.camera_alt_rounded,
            onPressed: _captureWithCamera,
          ),
        ),
        const SizedBox(height: FansivibeSpacing.sm),
        SizedBox(
          width: double.infinity,
          child: FansiButton.secondary(
            label: 'Choose from Gallery',
            icon: Icons.photo_library_rounded,
            onPressed: _pickFromGallery,
          ),
        ),
      ],
    );
  }

  Widget _buildProgressView(ThemeData theme) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (_imageBytes != null) ...[
          ClipRRect(
            borderRadius: FansivibeRadius.baseBorder,
            child: SizedBox(
              width: 140,
              height: 140,
              child: Image.memory(_imageBytes!, fit: BoxFit.cover),
            ),
          ),
          const SizedBox(height: FansivibeSpacing.xl),
        ],
        const CircularProgressIndicator(color: FansivibeColors.accentGold),
        const SizedBox(height: FansivibeSpacing.lg),
        Text(
          _statusMessage ?? 'Processing…',
          style: theme.textTheme.titleMedium?.copyWith(
            color: FansivibeColors.textPrimary,
            fontWeight: FontWeight.w600,
          ),
        ),
        if (_stillAnalyzing) ...[
          const SizedBox(height: FansivibeSpacing.sm),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Text(
              'Running local vision model on your hardware. This may take a few moments…',
              style: theme.textTheme.bodySmall?.copyWith(
                color: FansivibeColors.textSecondary,
              ),
              textAlign: TextAlign.center,
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildErrorView(ThemeData theme) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const Icon(
          Icons.error_outline_rounded,
          size: 56,
          color: FansivibeColors.error,
        ),
        const SizedBox(height: FansivibeSpacing.md),
        Text(
          'Analysis Issue',
          style: theme.textTheme.titleLarge?.copyWith(
            color: FansivibeColors.textPrimary,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: FansivibeSpacing.sm),
        Text(
          _errorMessage ?? 'An error occurred during extraction.',
          style: theme.textTheme.bodyMedium?.copyWith(
            color: FansivibeColors.textSecondary,
          ),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: FansivibeSpacing.xl),
        if (_imageBytes != null) ...[
          SizedBox(
            width: double.infinity,
            child: FansiButton.primary(
              label: 'Retry Analysis',
              icon: Icons.refresh_rounded,
              onPressed: () {
                _startExtraction();
              },
            ),
          ),
          const SizedBox(height: FansivibeSpacing.sm),
        ],
        SizedBox(
          width: double.infinity,
          child: _imageBytes != null
              ? FansiButton.secondary(
                  label: 'Try Another Photo',
                  icon: Icons.photo_library_outlined,
                  onPressed: () {
                    _cleanupCurrentRunAssets();
                    setState(() {
                      _stage = ExtractionUiStage.idle;
                      _imageBytes = null;
                      _errorMessage = null;
                      _partialExtractionNotice = null;
                      _currentRunId = null;
                      _saveIdempotencyKey = null;
                    });
                  },
                )
              : FansiButton.primary(
                  label: 'Try Another Photo',
                  icon: Icons.refresh_rounded,
                  onPressed: () {
                    _cleanupCurrentRunAssets();
                    setState(() {
                      _stage = ExtractionUiStage.idle;
                      _imageBytes = null;
                      _errorMessage = null;
                      _partialExtractionNotice = null;
                      _currentRunId = null;
                      _saveIdempotencyKey = null;
                    });
                  },
                ),
        ),
      ],
    );
  }

  Widget _buildCandidateSelectionView(ThemeData theme) {
    final selectedCount = _candidates
        .where((c) => c.isSelected && !c.isSaved)
        .length;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            if (_imageBytes != null)
              ClipRRect(
                borderRadius: FansivibeRadius.smBorder,
                child: SizedBox(
                  width: 52,
                  height: 52,
                  child: Image.memory(_imageBytes!, fit: BoxFit.cover),
                ),
              ),
            const SizedBox(width: FansivibeSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Extracted Garments (${_candidates.length})',
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: FansivibeColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'Inspect items and select which ones to save to your wardrobe.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: FansivibeColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: FansivibeSpacing.md),
        if (_partialExtractionNotice != null) ...[
          Container(
            padding: const EdgeInsets.all(FansivibeSpacing.sm),
            decoration: BoxDecoration(
              color: FansivibeColors.accentGold.withValues(alpha: 0.12),
              borderRadius: FansivibeRadius.smBorder,
              border: Border.all(
                color: FansivibeColors.accentGold.withValues(alpha: 0.35),
              ),
            ),
            child: Text(
              _partialExtractionNotice!,
              style: theme.textTheme.bodySmall?.copyWith(
                color: FansivibeColors.textPrimary,
              ),
            ),
          ),
          const SizedBox(height: FansivibeSpacing.sm),
        ],
        if (_errorMessage != null) ...[
          Container(
            padding: const EdgeInsets.all(FansivibeSpacing.sm),
            decoration: BoxDecoration(
              color: FansivibeColors.error.withValues(alpha: 0.1),
              borderRadius: FansivibeRadius.smBorder,
            ),
            child: Text(
              _errorMessage!,
              style: theme.textTheme.bodySmall?.copyWith(
                color: FansivibeColors.error,
              ),
            ),
          ),
          const SizedBox(height: FansivibeSpacing.md),
        ],
        Expanded(
          child: ListView.separated(
            physics: const BouncingScrollPhysics(),
            itemCount: _candidates.length,
            separatorBuilder: (_, __) =>
                const SizedBox(height: FansivibeSpacing.sm),
            itemBuilder: (context, index) {
              final candidate = _candidates[index];
              return _CandidateCard(
                candidate: candidate,
                onToggle: () => _toggleCandidateSelection(index),
                onInspect: () => _inspectCandidate(index),
                onEdit: () => _editCandidate(index),
              );
            },
          ),
        ),
        const SizedBox(height: FansivibeSpacing.md),
        SizedBox(
          width: double.infinity,
          child: FansiButton.primary(
            label: 'Save Selected to Wardrobe ($selectedCount)',
            icon: Icons.checkroom_rounded,
            onPressed: selectedCount > 0 ? _saveSelectedGarments : null,
          ),
        ),
        const SizedBox(height: FansivibeSpacing.xs),
        SizedBox(
          width: double.infinity,
          child: FansiButton.secondary(
            label: 'Cancel',
            onPressed: () {
              _cleanupCurrentRunAssets();
              Navigator.of(context).pop();
            },
          ),
        ),
      ],
    );
  }
}

class _CandidateCard extends StatelessWidget {
  const _CandidateCard({
    required this.candidate,
    required this.onToggle,
    required this.onInspect,
    required this.onEdit,
  });

  final GarmentCandidate candidate;
  final VoidCallback onToggle;
  final VoidCallback onInspect;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final categoryLabel = (candidate.category ?? 'Item').toUpperCase();
    final name =
        candidate.subcategory ??
        '${candidate.color ?? ''} ${candidate.category ?? 'Garment'}'.trim();

    return Container(
      decoration: BoxDecoration(
        color: candidate.isSelected
            ? FansivibeColors.surfaceContainerHigh
            : FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.baseBorder,
        border: Border.all(
          color: candidate.isSelected
              ? FansivibeColors.accentGold.withValues(alpha: 0.5)
              : FansivibeColors.outlineVariant,
        ),
      ),
      child: InkWell(
        onTap: onToggle,
        borderRadius: FansivibeRadius.baseBorder,
        child: Padding(
          padding: const EdgeInsets.all(FansivibeSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Checkbox(
                    value: candidate.isSelected,
                    activeColor: FansivibeColors.accentGold,
                    onChanged: candidate.isSaved ? null : (_) => onToggle(),
                  ),
                  GestureDetector(
                    onTap: onInspect,
                    child: ClipRRect(
                      borderRadius: FansivibeRadius.smBorder,
                      child: Container(
                        width: 52,
                        height: 52,
                        color: FansivibeColors.surfaceContainerLowest,
                        child: candidate.cropBytes != null
                            ? Image.memory(
                                candidate.cropBytes!,
                                fit: BoxFit.cover,
                              )
                            : Icon(
                                Icons.checkroom_outlined,
                                color: FansivibeColors.accentGold.withValues(
                                  alpha: 0.8,
                                ),
                                size: 24,
                              ),
                      ),
                    ),
                  ),
                  const SizedBox(width: FansivibeSpacing.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          name,
                          style: theme.textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: FansivibeColors.textPrimary,
                          ),
                        ),
                        Text(
                          candidate.isSaved
                              ? '$categoryLabel • SAVED'
                              : categoryLabel,
                          style: theme.textTheme.labelSmall?.copyWith(
                            color: candidate.isSaved
                                ? FansivibeColors.success
                                : FansivibeColors.accentGold,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.visibility_outlined, size: 20),
                    tooltip: 'Inspect garment',
                    color: FansivibeColors.textSecondary,
                    onPressed: onInspect,
                  ),
                  IconButton(
                    icon: const Icon(Icons.edit_outlined, size: 20),
                    tooltip: 'Edit garment',
                    color: FansivibeColors.textSecondary,
                    onPressed: candidate.isSaved ? null : onEdit,
                  ),
                ],
              ),
              const SizedBox(height: FansivibeSpacing.sm),
              Wrap(
                spacing: 8,
                runSpacing: 4,
                children: [
                  if (candidate.color != null)
                    _MetadataPill(
                      label: 'Color: ${candidate.color}',
                      icon: Icons.palette_outlined,
                    ),
                  if (candidate.secondaryColors != null &&
                      candidate.secondaryColors!.isNotEmpty)
                    _MetadataPill(
                      label:
                          'Secondary: ${candidate.secondaryColors!.join(", ")}',
                      icon: Icons.color_lens_outlined,
                    ),
                  if (candidate.pattern != null)
                    _MetadataPill(
                      label: 'Pattern: ${candidate.pattern}',
                      icon: Icons.grid_on_rounded,
                    ),
                  if (candidate.material != null)
                    _MetadataPill(
                      label: 'Material: ${candidate.material}',
                      icon: Icons.texture_rounded,
                    ),
                  if (candidate.fit != null)
                    _MetadataPill(
                      label: 'Fit: ${candidate.fit}',
                      icon: Icons.accessibility_new_rounded,
                    ),
                  if (candidate.sleeveType != null)
                    _MetadataPill(
                      label: 'Sleeve: ${candidate.sleeveType}',
                      icon: Icons.straighten_rounded,
                    ),
                  if (candidate.neckline != null)
                    _MetadataPill(
                      label: 'Neckline: ${candidate.neckline}',
                      icon: Icons.face_rounded,
                    ),
                  if (candidate.condition != null)
                    _MetadataPill(
                      label: 'Condition: ${candidate.condition}',
                      icon: Icons.verified_outlined,
                    ),
                  if (candidate.hasCrop)
                    const _MetadataPill(
                      label: 'BBox crop',
                      icon: Icons.crop_rounded,
                    ),
                  if (candidate.confidence != null)
                    _MetadataPill(
                      label: '${(candidate.confidence! * 100).toInt()}% match',
                      icon: Icons.auto_awesome_rounded,
                      color: FansivibeColors.success,
                    ),
                ],
              ),
              if (candidate.description != null &&
                  candidate.description!.isNotEmpty) ...[
                const SizedBox(height: FansivibeSpacing.xs),
                Text(
                  candidate.description!,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: FansivibeColors.textSecondary,
                    fontStyle: FontStyle.italic,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _CandidateInspectSheet extends StatelessWidget {
  const _CandidateInspectSheet({
    required this.candidate,
    required this.fallbackPhotoBytes,
    required this.onToggleSelected,
    required this.onEdit,
  });

  final GarmentCandidate candidate;
  final Uint8List? fallbackPhotoBytes;
  final VoidCallback onToggleSelected;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final displayBytes = candidate.cropBytes ?? fallbackPhotoBytes;
    final name =
        candidate.subcategory ??
        '${candidate.color ?? ''} ${candidate.category ?? 'Garment'}'.trim();
    final segReason =
        candidate.segmentation?['reason'] as String? ??
        'Local VLM provides 2D bounding-box crops only; pixel-level segmentation masks are not supported.';

    return Padding(
      padding: const EdgeInsets.all(FansivibeSpacing.lg),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    name,
                    style: theme.textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: FansivibeColors.textPrimary,
                    ),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.close_rounded),
                  onPressed: () => Navigator.of(context).pop(),
                ),
              ],
            ),
            const SizedBox(height: FansivibeSpacing.md),
            if (displayBytes != null)
              Center(
                child: ClipRRect(
                  borderRadius: FansivibeRadius.baseBorder,
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxHeight: 220),
                    child: Image.memory(displayBytes, fit: BoxFit.contain),
                  ),
                ),
              ),
            const SizedBox(height: FansivibeSpacing.md),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(FansivibeSpacing.sm),
              decoration: BoxDecoration(
                color: FansivibeColors.surfaceContainerLowest,
                borderRadius: FansivibeRadius.smBorder,
              ),
              child: Text(
                candidate.cropBytes != null
                    ? 'Extracted via bounding-box crop. $segReason'
                    : (candidate.hasCrop
                          ? 'Bounding-box crop stored privately. $segReason'
                          : 'No bounding-box crop extracted; showing full photo reference. $segReason'),
                style: theme.textTheme.bodySmall?.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
              ),
            ),
            const SizedBox(height: FansivibeSpacing.md),
            _InspectRow('Category', candidate.category ?? 'Not detected'),
            _InspectRow('Subcategory', candidate.subcategory ?? 'Not detected'),
            _InspectRow('Primary Color', candidate.color ?? 'Not detected'),
            if (candidate.secondaryColors != null &&
                candidate.secondaryColors!.isNotEmpty)
              _InspectRow(
                'Secondary Colors',
                candidate.secondaryColors!.join(', '),
              ),
            _InspectRow('Pattern', candidate.pattern ?? 'Not detected'),
            _InspectRow(
              'Material',
              candidate.material != null
                  ? '${candidate.material} (visual estimate)'
                  : 'Not visually determinable',
            ),
            if (candidate.fit != null) _InspectRow('Fit', candidate.fit!),
            if (candidate.sleeveType != null)
              _InspectRow('Sleeve', candidate.sleeveType!),
            if (candidate.neckline != null)
              _InspectRow('Neckline', candidate.neckline!),
            if (candidate.length != null)
              _InspectRow('Length', candidate.length!),
            if (candidate.condition != null)
              _InspectRow('Condition', candidate.condition!),
            _InspectRow(
              'Confidence',
              candidate.confidence != null
                  ? '${(candidate.confidence! * 100).toInt()}%'
                  : 'Not reported',
            ),
            _InspectRow(
              'Segmentation Mask',
              candidate.hasSegmentationMask
                  ? 'Supported'
                  : 'Not supported (crop only)',
            ),
            if (candidate.description != null) ...[
              const SizedBox(height: FansivibeSpacing.sm),
              Text(
                candidate.description!,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: FansivibeColors.textSecondary,
                  fontStyle: FontStyle.italic,
                ),
              ),
            ],
            const SizedBox(height: FansivibeSpacing.lg),
            Row(
              children: [
                Expanded(
                  child: FansiButton.secondary(
                    label: 'Edit Details',
                    icon: Icons.edit_outlined,
                    onPressed: candidate.isSaved ? null : onEdit,
                  ),
                ),
                const SizedBox(width: FansivibeSpacing.sm),
                Expanded(
                  child: FansiButton.primary(
                    label: candidate.isSelected ? 'Deselect' : 'Select',
                    onPressed: candidate.isSaved ? null : onToggleSelected,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _InspectRow extends StatelessWidget {
  const _InspectRow(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 130,
            child: Text(
              label,
              style: theme.textTheme.bodySmall?.copyWith(
                color: FansivibeColors.textSecondary,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: theme.textTheme.bodySmall?.copyWith(
                color: FansivibeColors.textPrimary,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _MetadataPill extends StatelessWidget {
  const _MetadataPill({required this.label, required this.icon, this.color});

  final String label;
  final IconData icon;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLowest,
        borderRadius: FansivibeRadius.fullBorder,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12, color: color ?? FansivibeColors.textSecondary),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 11,
              color: color ?? FansivibeColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

class _CandidateEditSheet extends StatefulWidget {
  const _CandidateEditSheet({
    required this.candidate,
    required this.categoryConfig,
  });

  final GarmentCandidate candidate;
  final AddItemCategoryConfig categoryConfig;

  @override
  State<_CandidateEditSheet> createState() => _CandidateEditSheetState();
}

class _CandidateEditSheetState extends State<_CandidateEditSheet> {
  late final TextEditingController _nameController;
  late String _category;
  String? _color;
  String? _material;
  String? _fit;

  static String? _matchColorOption(String? raw) {
    if (raw == null) return null;
    final clean = raw.trim().toLowerCase().replaceAll('_', ' ');
    for (final c in AddItemConfig.colors) {
      if (c.name.toLowerCase() == clean) return c.name;
    }
    const aliases = {
      'blue': 'Navy',
      'dark blue': 'Navy',
      'gray': 'Grey',
      'dark gray': 'Charcoal',
      'dark grey': 'Charcoal',
      'brown': 'Tan',
      'red': 'Burgundy',
      'green': 'Olive',
      'pink': 'Blush',
      'yellow': 'Cream',
      'purple': 'Indigo',
      'off white': 'Cream',
      'off-white': 'Cream',
      'ivory': 'Cream',
    };
    return aliases[clean];
  }

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(
      text: widget.candidate.subcategory ?? widget.candidate.category ?? 'Item',
    );
    _category = widget.candidate.category ?? 'tops';
    final candColor = widget.candidate.color;
    if (candColor != null && candColor.trim().isNotEmpty) {
      final cleanColor = candColor.trim().toLowerCase().replaceAll('_', ' ');
      final exact = AddItemConfig.colors.where(
        (c) => c.name.toLowerCase() == cleanColor,
      );
      _color = exact.isNotEmpty ? exact.first.name : candColor;
    } else {
      _color = 'Navy';
    }
    final candMat = widget.candidate.material;
    if (candMat != null) {
      final cleanMat = candMat.trim().toLowerCase().replaceAll('_', ' ');
      final match = AddItemConfig.textures.where(
        (t) => t.name.toLowerCase() == cleanMat,
      );
      _material = match.isNotEmpty ? match.first.name : candMat;
    }
    final candFit = widget.candidate.fit;
    if (candFit != null) {
      final match = AddItemConfig.fitOptions.where(
        (f) => f.toLowerCase() == candFit.toLowerCase(),
      );
      _fit = match.isNotEmpty ? match.first : candFit;
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: EdgeInsets.only(
        top: FansivibeSpacing.lg,
        left: FansivibeSpacing.lg,
        right: FansivibeSpacing.lg,
        bottom: MediaQuery.of(context).viewInsets.bottom + FansivibeSpacing.lg,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Edit Candidate Details',
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.bold,
                color: FansivibeColors.textPrimary,
              ),
            ),
            const SizedBox(height: FansivibeSpacing.md),
            TextField(
              controller: _nameController,
              decoration: const InputDecoration(
                labelText: 'Item Name',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: FansivibeSpacing.md),
            DropdownButtonFormField<String>(
              initialValue: _category,
              decoration: const InputDecoration(
                labelText: 'Category',
                border: OutlineInputBorder(),
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
              onChanged: (val) {
                if (val != null) setState(() => _category = val);
              },
            ),
            const SizedBox(height: FansivibeSpacing.md),
            DropdownButtonFormField<String>(
              initialValue: AddItemConfig.colors.any((c) => c.name == _color)
                  ? _color
                  : _matchColorOption(_color),
              decoration: const InputDecoration(
                labelText: 'Color',
                border: OutlineInputBorder(),
              ),
              items: AddItemConfig.colors
                  .map(
                    (c) => DropdownMenuItem(value: c.name, child: Text(c.name)),
                  )
                  .toList(),
              onChanged: (val) {
                if (val != null) setState(() => _color = val);
              },
            ),
            const SizedBox(height: FansivibeSpacing.md),
            DropdownButtonFormField<String>(
              initialValue:
                  AddItemConfig.textures.any((t) => t.name == _material)
                  ? _material
                  : null,
              decoration: const InputDecoration(
                labelText: 'Material',
                border: OutlineInputBorder(),
              ),
              items: AddItemConfig.textures
                  .map(
                    (t) => DropdownMenuItem(value: t.name, child: Text(t.name)),
                  )
                  .toList(),
              onChanged: (val) {
                if (val != null) setState(() => _material = val);
              },
            ),
            const SizedBox(height: FansivibeSpacing.md),
            DropdownButtonFormField<String>(
              initialValue: AddItemConfig.fitOptions.contains(_fit)
                  ? _fit
                  : null,
              decoration: const InputDecoration(
                labelText: 'Fit',
                border: OutlineInputBorder(),
              ),
              items: AddItemConfig.fitOptions
                  .map((f) => DropdownMenuItem(value: f, child: Text(f)))
                  .toList(),
              onChanged: (val) {
                if (val != null) setState(() => _fit = val);
              },
            ),
            const SizedBox(height: FansivibeSpacing.lg),
            SizedBox(
              width: double.infinity,
              child: FansiButton.primary(
                label: 'Done',
                onPressed: () {
                  final updated = widget.candidate.copyWith(
                    subcategory: _nameController.text.trim(),
                    category: _category,
                    color: _color,
                    material: _material,
                    fit: _fit,
                  );
                  Navigator.of(context).pop(updated);
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
