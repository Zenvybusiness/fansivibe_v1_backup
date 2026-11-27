import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/try_on/data/try_on_device_saver.dart';
import 'package:fansivibe/features/try_on/data/try_on_models.dart';
import 'package:fansivibe/features/try_on/data/try_on_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart'
    show WardrobeItemData;
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/widgets/wardrobe_widgets.dart'
    show WardrobeItemImage;
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/components/fansi_image_well.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

/// Complete Virtual Try-On Screen.
///
/// End-to-end journey:
/// 1. Select or capture a person photograph with preview, validation, replace & remove.
/// 2. Select garment(s) from the authenticated user's Digital Wardrobe
///    (respecting backend-reported single/multi garment limits & ownership).
/// 3. Review selected photo, garments, count, and consent before submitting.
/// 4. Submit with idempotency + duplicate-submit protection & poll safely.
/// 5. Handle queued, processing, completed, failed, timeout, network drop,
///    and app/navigation recovery without duplicate paid job creation.
/// 6. View generated result via authorized endpoint, inspect full-screen,
///    save to device (non-mock), delete, or return to Wardrobe / AI Stylist.
class TryOnScreen extends StatefulWidget {
  const TryOnScreen({
    required this.outfitSource,
    required this.garmentIds,
    required this.title,
    this.initialJobId,
    this.tryOnRepository,
    this.wardrobeRepository,
    this.pickImage,
    this.saveResultImage,
    this.capabilities,
    this.strictImageValidation,
    this.pollInterval = defaultPollInterval,
    this.maxPollDuration = defaultMaxPollDuration,
    this.now,
    super.key,
  });

  static const Duration defaultPollInterval = Duration(seconds: 1);
  static const Duration defaultMaxPollDuration = Duration(seconds: 135);

  final String outfitSource;
  final List<String> garmentIds;
  final String title;

  /// Optional job ID to recover/revisit immediately.
  final String? initialJobId;

  /// Backend try-on repository seam. Defaults to live implementation.
  final TryOnRepository? tryOnRepository;

  /// Wardrobe repository seam for fetching user garments.
  final WardrobeRepository? wardrobeRepository;

  /// Photo picker seam (gallery/camera). Defaults to [ImagePicker].
  final Future<XFile?> Function(ImageSource source)? pickImage;

  /// Optional device image saver seam for tests.
  final Future<TryOnSaveOutcome> Function(Uint8List bytes, String jobId)?
  saveResultImage;

  /// Optional capabilities override for deterministic testing.
  final TryOnCapabilities? capabilities;

  /// When true, enforces magic-byte MIME, size, and dimension validation on
  /// picked person photos. Defaults to `true` in production (`pickImage == null`)
  /// and `false` when a legacy test injects `pickImage` without opting in.
  final bool? strictImageValidation;

  /// Interval between status polls.
  final Duration pollInterval;

  /// Maximum client polling window aligned with backend 120s timeout + headroom.
  final Duration maxPollDuration;

  /// Clock seam for deterministic elapsed-time testing.
  final DateTime Function()? now;

  @override
  State<TryOnScreen> createState() => _TryOnScreenState();
}

enum _Phase {
  input,
  submitting,
  polling,
  timedOut,
  networkInterrupted,
  done,
  failed,
}

class _TryOnScreenState extends State<TryOnScreen> with WidgetsBindingObserver {
  static const int _maxConsecutivePollFailures = 5;

  late final TryOnRepository _repository;
  late final WardrobeRepository _wardrobeRepo;

  TryOnCapabilities _capabilities = TryOnCapabilities.fallback;

  bool _consent = false;
  Uint8List? _personBytes;
  String _personFilename = 'tryon_person.jpg';
  String? _personMimeType;
  (int, int)? _personDimensions;
  String? _imageError;

  List<WardrobeItemData> _wardrobeItems = [];
  final List<String> _selectedGarmentIds = [];
  final Map<String, WardrobeItemData> _selectedGarmentMap = {};
  bool _isLoadingWardrobe = false;
  bool _wardrobeLoaded = false;
  String? _wardrobeLoadError;
  String? _garmentSelectionWarning;
  int _wardrobeLoadGeneration = 0;

  _Phase _phase = _Phase.input;
  TryOnFailure? _failure;
  String? _failureDetail;
  int _pollCount = 0;
  int _consecutivePollFailures = 0;
  String? _activeJobId;
  String? _pendingIdempotencyKey;
  TryOnJobState? _lastJobState;
  int? _backendProgress;
  bool _isMock = true;
  Uint8List? _resultBytes;
  String? _imageFetchError;
  bool _isSavingToDevice = false;
  bool _isSubmittingGuard = false;
  bool _recoveredJobBanner = false;

  DateTime? _pollingStartedAt;
  bool _isAppBackgrounded = false;
  bool _pollInFlight = false;
  int _pollSessionToken = 0;

  bool get _strictValidation =>
      widget.strictImageValidation ?? (widget.pickImage == null);

  bool get _isWardrobeFlow => widget.outfitSource == TryOnOutfitSource.wardrobe;

  Duration get _effectivePollInterval {
    if (widget.pollInterval != TryOnScreen.defaultPollInterval) {
      return widget.pollInterval;
    }
    return _capabilities.pollInterval;
  }

  Duration get _effectiveMaxPollDuration {
    if (widget.maxPollDuration != TryOnScreen.defaultMaxPollDuration) {
      return widget.maxPollDuration;
    }
    return _capabilities.maxPollDuration;
  }

  DateTime _currentTime() => (widget.now ?? DateTime.now)();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _repository = widget.tryOnRepository ?? TryOnRepositoryImpl();
    _wardrobeRepo = widget.wardrobeRepository ?? WardrobeRepositoryImpl();
    if (widget.capabilities != null) {
      _capabilities = widget.capabilities!;
      _isMock = _capabilities.isMock;
    }

    for (final id in widget.garmentIds) {
      if (id.isNotEmpty && !_selectedGarmentIds.contains(id)) {
        if (_selectedGarmentIds.length < _capabilities.maxGarments) {
          _selectedGarmentIds.add(id);
        }
      }
    }

    unawaited(_initializeScreenData());
  }

  Future<void> _initializeScreenData() async {
    await Future.wait([_loadCapabilities(), _loadWardrobeItems()]);
    if (!mounted) return;
    await _attemptJobRecovery();
  }

  Future<void> _loadCapabilities() async {
    if (widget.capabilities != null) return;
    final caps = await _repository.getCapabilities();
    if (!mounted || caps == null) return;
    setState(() {
      _capabilities = caps;
      if (_activeJobId == null) {
        _isMock = caps.isMock;
      }
      if (_selectedGarmentIds.length > caps.maxGarments) {
        _selectedGarmentIds.removeRange(
          caps.maxGarments,
          _selectedGarmentIds.length,
        );
        _syncSelectedMap();
        _garmentSelectionWarning =
            'Only ${caps.maxGarments} garment(s) can be selected at a time.';
      }
    });
  }

  @override
  void dispose() {
    _pollSessionToken++;
    _wardrobeLoadGeneration++;
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden ||
        state == AppLifecycleState.detached) {
      _isAppBackgrounded = true;
      return;
    }
    if (state == AppLifecycleState.resumed) {
      _isAppBackgrounded = false;
      final jobId = _activeJobId;
      if (jobId != null && _phase == _Phase.polling) {
        unawaited(_pollOnce(jobId, _pollSessionToken));
      }
    }
  }

  void _syncSelectedMap() {
    _selectedGarmentMap.clear();
    for (final id in _selectedGarmentIds) {
      final match = _wardrobeItems.where((i) => i.id == id);
      if (match.isNotEmpty) {
        _selectedGarmentMap[id] = match.first;
      }
    }
  }

  Future<void> _loadWardrobeItems() async {
    if (!mounted) return;
    final generation = ++_wardrobeLoadGeneration;
    setState(() {
      _isLoadingWardrobe = true;
      _wardrobeLoadError = null;
    });
    try {
      const pageSize = 100;
      const maxPages = 100;
      final allItems = <WardrobeItemData>[];
      final seenIds = <String>{};

      for (var page = 1; page <= maxPages; page++) {
        final pageItems = await _wardrobeRepo.listItems(
          page: page,
          pageSize: pageSize,
        );
        if (!mounted || generation != _wardrobeLoadGeneration) return;

        var addedThisPage = 0;
        for (final item in pageItems) {
          if (seenIds.add(item.id)) {
            allItems.add(item);
            addedThisPage++;
          }
        }

        if (pageItems.isEmpty ||
            pageItems.length < pageSize ||
            (page > 1 && addedThisPage == 0)) {
          break;
        }
      }

      if (!mounted || generation != _wardrobeLoadGeneration) return;
      setState(() {
        _wardrobeItems = allItems;
        _wardrobeLoaded = true;
        _isLoadingWardrobe = false;
        // Enforce ownership for wardrobe-sourced selections when wardrobe loaded.
        if (_isWardrobeFlow && _selectedGarmentIds.isNotEmpty) {
          final ownedIds = allItems.map((e) => e.id).toSet();
          final validIds = _selectedGarmentIds
              .where(ownedIds.contains)
              .toList();
          if (validIds.length != _selectedGarmentIds.length) {
            _selectedGarmentIds
              ..clear()
              ..addAll(validIds);
            _garmentSelectionWarning =
                'Removed garment selection that does not belong to your Digital Wardrobe.';
          }
        }
        _syncSelectedMap();
      });
    } catch (_) {
      if (!mounted || generation != _wardrobeLoadGeneration) return;
      setState(() {
        _isLoadingWardrobe = false;
        _wardrobeLoadError = 'Could not load your Digital Wardrobe.';
      });
    }
  }

  Future<void> _attemptJobRecovery() async {
    if (isGuestUser || _phase != _Phase.input) return;
    final persisted = TryOnJobPersistence.load();
    final targetJobId = widget.initialJobId ?? persisted?.jobId;
    if (targetJobId == null || targetJobId.isEmpty) return;

    // Only auto-restore persisted completed results when opened from Stylist
    // (or explicitly via initialJobId), so outfit-specific entries still let the
    // user preview the new outfit unless an active job is running.
    final outcome = await _repository.getJobStatusOutcome(targetJobId);
    if (!mounted || _phase != _Phase.input) return;

    if (outcome.statusCode == 404 ||
        outcome.failure == TryOnFailure.notFound ||
        outcome.failure == TryOnFailure.unauthorized) {
      TryOnJobPersistence.clear();
      return;
    }

    final status = outcome.status;
    if (status == null) return;

    if (status.state == TryOnJobState.queued ||
        status.state == TryOnJobState.processing) {
      setState(() {
        _activeJobId = status.jobId;
        _isMock = status.isMock;
        _lastJobState = status.state;
        _backendProgress = status.progress;
        _recoveredJobBanner = true;
        _phase = _Phase.polling;
        _pollingStartedAt = _currentTime();
        if (status.garmentIds.isNotEmpty) {
          _selectedGarmentIds
            ..clear()
            ..addAll(status.garmentIds);
          _syncSelectedMap();
        }
      });
      await _pollUntilDone(status.jobId);
      return;
    }

    if (status.state == TryOnJobState.cancelled) {
      TryOnJobPersistence.clear();
      return;
    }

    final allowTerminalRestore =
        widget.initialJobId != null || widget.garmentIds.isEmpty;
    if (allowTerminalRestore && status.state == TryOnJobState.failed) {
      setState(() {
        _activeJobId = status.jobId;
        _isMock = status.isMock;
        _lastJobState = status.state;
        _backendProgress = status.progress;
        _failure = TryOnFailure.unknown;
        _failureDetail = status.errorMessage ?? 'Try-on processing failed.';
        _recoveredJobBanner = true;
        if (status.garmentIds.isNotEmpty) {
          _selectedGarmentIds
            ..clear()
            ..addAll(status.garmentIds);
          _syncSelectedMap();
        }
        _phase = _Phase.failed;
      });
      return;
    }

    if (allowTerminalRestore && status.state == TryOnJobState.completed) {
      final imgOutcome = await _repository.getJobImageOutcome(status.jobId);
      if (!mounted || _phase != _Phase.input) return;
      setState(() {
        _activeJobId = status.jobId;
        _isMock = status.isMock;
        _lastJobState = status.state;
        _backendProgress = status.progress;
        _resultBytes = imgOutcome.bytes;
        _imageFetchError = imgOutcome.bytes == null
            ? (imgOutcome.errorMessage ??
                  'Could not load the generated image. Tap retry below.')
            : null;
        _recoveredJobBanner = true;
        if (status.garmentIds.isNotEmpty) {
          _selectedGarmentIds
            ..clear()
            ..addAll(status.garmentIds);
          _syncSelectedMap();
        }
        _phase = _Phase.done;
      });
    }
  }

  Future<XFile?> _defaultPickImage(ImageSource source) {
    return ImagePicker().pickImage(
      source: source,
      maxWidth: 1600,
      maxHeight: 1600,
      imageQuality: 90,
    );
  }

  Future<void> _onAttachPhoto(ImageSource source) async {
    if (_phase == _Phase.submitting || _phase == _Phase.polling) return;
    XFile? picked;
    try {
      picked = await (widget.pickImage ?? _defaultPickImage)(source);
    } on PlatformException catch (e) {
      if (!mounted) return;
      final code = e.code.toLowerCase();
      final msg = (e.message ?? '').toLowerCase();
      final isPermission =
          code.contains('denied') ||
          code.contains('permission') ||
          code.contains('access') ||
          msg.contains('permission') ||
          msg.contains('denied');
      final isPermanent =
          code.contains('permanent') ||
          code == 'camera_access_denied' ||
          code == 'photo_access_denied' ||
          msg.contains('permanently');
      setState(() {
        _imageError = isPermission
            ? (source == ImageSource.camera
                  ? (isPermanent
                        ? 'Camera permission denied. Open device Settings to enable camera access, or choose a photo from gallery.'
                        : 'Camera permission denied. Enable camera access in settings or choose from gallery.')
                  : (isPermanent
                        ? 'Photo library permission denied. Open device Settings to enable photo access.'
                        : 'Photo library permission denied. Enable photo access in settings to select a photo.'))
            : 'Could not access photo (${e.message ?? e.code}).';
      });
      return;
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _imageError = source == ImageSource.camera
            ? 'Could not open the camera. Please try again or choose from gallery.'
            : 'Could not open the photo gallery. Please try again.';
      });
      return;
    }

    if (picked == null || !mounted) return;

    Uint8List bytes;
    try {
      bytes = await picked.readAsBytes();
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _imageError = 'Could not read the selected photo file.';
      });
      return;
    }
    if (!mounted) return;

    if (bytes.isEmpty) {
      setState(() {
        _imageError = 'Selected photo is empty. Please choose another image.';
      });
      return;
    }

    String? detectedMime;
    (int, int)? dims;
    if (_strictValidation) {
      final validation = await validateTryOnPersonImage(
        bytes,
        capabilities: _capabilities,
      );
      if (!mounted) return;
      if (!validation.isValid) {
        setState(() {
          _imageError =
              validation.errorMessage ?? 'Selected photo is not valid.';
        });
        return;
      }
      detectedMime = validation.mimeType;
      if (validation.width != null && validation.height != null) {
        dims = (validation.width!, validation.height!);
      }
    }

    setState(() {
      _imageError = null;
      _personBytes = bytes;
      _personFilename = picked!.name.isNotEmpty ? picked.name : _personFilename;
      _personMimeType = detectedMime;
      _personDimensions = dims;
      _pendingIdempotencyKey = null;
      _activeJobId = null;
      _recoveredJobBanner = false;
      if (_phase == _Phase.failed ||
          _phase == _Phase.done ||
          _phase == _Phase.timedOut ||
          _phase == _Phase.networkInterrupted) {
        _phase = _Phase.input;
        _failure = null;
        _failureDetail = null;
        _resultBytes = null;
      }
    });
  }

  void _onRemovePersonPhoto() {
    if (_phase == _Phase.submitting || _phase == _Phase.polling) return;
    setState(() {
      _personBytes = null;
      _personMimeType = null;
      _personDimensions = null;
      _imageError = null;
      _pendingIdempotencyKey = null;
      _activeJobId = null;
      if (_phase == _Phase.failed) {
        _phase = _Phase.input;
        _failure = null;
        _failureDetail = null;
      }
    });
  }

  void _showSnackBar(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: FansivibeColors.primary,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.smdBorder),
      ),
    );
  }

  void _onToggleGarment(WardrobeItemData item, {VoidCallback? onLimitHit}) {
    if (_phase == _Phase.submitting || _phase == _Phase.polling) return;
    if (!_wardrobeItems.any((owned) => owned.id == item.id)) {
      setState(() {
        _garmentSelectionWarning =
            'Only garments from your own Digital Wardrobe can be selected.';
      });
      return;
    }

    setState(() {
      _garmentSelectionWarning = null;
      if (_selectedGarmentIds.contains(item.id)) {
        _selectedGarmentIds.remove(item.id);
      } else if (_capabilities.maxGarments == 1) {
        if (_selectedGarmentIds.isNotEmpty) {
          _garmentSelectionWarning =
              'Only 1 garment can be selected at a time; replaced previous selection.';
        }
        _selectedGarmentIds
          ..clear()
          ..add(item.id);
      } else if (_selectedGarmentIds.length >= _capabilities.maxGarments) {
        _garmentSelectionWarning =
            'You can select up to ${_capabilities.maxGarments} garments for one try-on.';
        onLimitHit?.call();
        return;
      } else {
        _selectedGarmentIds.add(item.id);
      }
      _syncSelectedMap();
      _pendingIdempotencyKey = null;
      _activeJobId = null;
      _recoveredJobBanner = false;
      if (_phase == _Phase.failed ||
          _phase == _Phase.done ||
          _phase == _Phase.timedOut ||
          _phase == _Phase.networkInterrupted) {
        _phase = _Phase.input;
        _failure = null;
        _failureDetail = null;
        _resultBytes = null;
      }
    });
  }

  void _onRemoveGarment(String garmentId) {
    if (_phase == _Phase.submitting || _phase == _Phase.polling) return;
    setState(() {
      _garmentSelectionWarning = null;
      _selectedGarmentIds.remove(garmentId);
      _selectedGarmentMap.remove(garmentId);
      _pendingIdempotencyKey = null;
      _activeJobId = null;
      if (_phase == _Phase.failed) {
        _phase = _Phase.input;
        _failure = null;
        _failureDetail = null;
      }
    });
  }

  void _navigateToAddGarment() {
    if (GoRouter.maybeOf(context) != null) {
      context.pushNamed(RouteNames.wardrobeAddCategory).then((_) {
        if (mounted) _loadWardrobeItems();
      });
    }
  }

  void _navigateToWardrobe() {
    if (GoRouter.maybeOf(context) != null) {
      context.goNamed(RouteNames.wardrobe);
    }
  }

  void _navigateToStylist() {
    if (GoRouter.maybeOf(context) != null) {
      context.goNamed(RouteNames.stylist);
    }
  }

  void _showGarmentPicker() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: FansivibeColors.surface,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setModalState) {
            return SafeArea(
              child: ConstrainedBox(
                constraints: BoxConstraints(
                  maxHeight: MediaQuery.sizeOf(ctx).height * 0.78,
                ),
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    vertical: 16,
                    horizontal: 20,
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Select Digital Wardrobe Garment',
                                  style:
                                      FansivibeTypography.titleLargeWithFamily,
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  _capabilities.maxGarments == 1
                                      ? 'Choose 1 garment to try on'
                                      : 'Choose up to ${_capabilities.maxGarments} garments (${_selectedGarmentIds.length}/${_capabilities.maxGarments})',
                                  style: FansivibeTypography
                                      .labelMediumWithFamily
                                      .copyWith(
                                        color: FansivibeColors.textSecondary,
                                      ),
                                ),
                              ],
                            ),
                          ),
                          IconButton(
                            icon: const Icon(Icons.close_rounded),
                            onPressed: () => Navigator.of(ctx).pop(),
                          ),
                        ],
                      ),
                      if (_garmentSelectionWarning != null) ...[
                        const SizedBox(height: 8),
                        Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: FansivibeColors.warning.withValues(
                              alpha: 0.14,
                            ),
                            borderRadius: FansivibeRadius.smBorder,
                          ),
                          child: Text(
                            _garmentSelectionWarning!,
                            style: FansivibeTypography.labelMediumWithFamily
                                .copyWith(color: FansivibeColors.warning),
                          ),
                        ),
                      ],
                      const SizedBox(height: 12),
                      if (_isLoadingWardrobe) ...[
                        const Padding(
                          padding: EdgeInsets.symmetric(vertical: 28),
                          child: Center(child: CircularProgressIndicator()),
                        ),
                      ] else if (_wardrobeLoadError != null) ...[
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 20),
                          child: Column(
                            children: [
                              Text(
                                _wardrobeLoadError!,
                                style: FansivibeTypography.bodyMediumWithFamily,
                              ),
                              const SizedBox(height: 12),
                              FansiButton.secondary(
                                label: 'Retry Loading Wardrobe',
                                icon: Icons.refresh_rounded,
                                onPressed: () async {
                                  await _loadWardrobeItems();
                                  if (ctx.mounted) setModalState(() {});
                                },
                              ),
                            ],
                          ),
                        ),
                      ] else if (_wardrobeItems.isEmpty) ...[
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 20),
                          child: Column(
                            children: [
                              const Icon(
                                Icons.checkroom_outlined,
                                size: 42,
                                color: FansivibeColors.primary,
                              ),
                              const SizedBox(height: 10),
                              const Text(
                                'No garments found in your Digital Wardrobe.',
                                textAlign: TextAlign.center,
                              ),
                              const SizedBox(height: 14),
                              FansiButton.primary(
                                label: 'Add Garment to Wardrobe',
                                icon: Icons.add_rounded,
                                onPressed: () {
                                  Navigator.of(ctx).pop();
                                  _navigateToAddGarment();
                                },
                              ),
                            ],
                          ),
                        ),
                      ] else ...[
                        Flexible(
                          child: ListView.separated(
                            shrinkWrap: true,
                            itemCount: _wardrobeItems.length,
                            separatorBuilder: (_, __) =>
                                const Divider(height: 1),
                            itemBuilder: (context, index) {
                              final item = _wardrobeItems[index];
                              final isChosen = _selectedGarmentIds.contains(
                                item.id,
                              );
                              return ListTile(
                                contentPadding: const EdgeInsets.symmetric(
                                  vertical: 4,
                                ),
                                leading: SizedBox(
                                  width: 48,
                                  height: 48,
                                  child: ClipRRect(
                                    borderRadius: FansivibeRadius.smBorder,
                                    child: WardrobeItemImage(
                                      item: item,
                                      iconSize: 22,
                                    ),
                                  ),
                                ),
                                title: Text(
                                  item.name,
                                  style: FansivibeTypography.bodyLargeWithFamily
                                      .copyWith(
                                        fontWeight: isChosen
                                            ? FontWeight.w700
                                            : FontWeight.w500,
                                      ),
                                ),
                                subtitle: Text(
                                  '${item.category} • ${item.color}',
                                  style: FansivibeTypography
                                      .labelMediumWithFamily
                                      .copyWith(
                                        color: FansivibeColors.textSecondary,
                                      ),
                                ),
                                trailing: isChosen
                                    ? const Icon(
                                        Icons.check_circle_rounded,
                                        color: FansivibeColors.primary,
                                      )
                                    : const Icon(
                                        Icons.radio_button_unchecked_rounded,
                                        color: FansivibeColors.textSecondary,
                                      ),
                                onTap: () {
                                  _onToggleGarment(item);
                                  setModalState(() {});
                                  if (_capabilities.maxGarments == 1 &&
                                      _selectedGarmentIds.contains(item.id)) {
                                    Navigator.of(ctx).pop();
                                  }
                                },
                              );
                            },
                          ),
                        ),
                        if (_capabilities.maxGarments > 1) ...[
                          const SizedBox(height: 12),
                          FansiButton.primary(
                            label: 'Done (${_selectedGarmentIds.length})',
                            onPressed: () => Navigator.of(ctx).pop(),
                          ),
                        ],
                      ],
                    ],
                  ),
                ),
              ),
            );
          },
        );
      },
    );
  }

  Future<void> _onSubmit() async {
    if (isGuestUser) {
      promptGuestSignIn(
        context,
        action: 'Sign in to preview try-ons. Browsing stays free.',
      );
      return;
    }
    if (_isSubmittingGuard ||
        _phase == _Phase.submitting ||
        _phase == _Phase.polling) {
      return;
    }
    if (!_consent) {
      _showSnackBar('Please accept the test-preview consent first.');
      return;
    }
    final bytes = _personBytes;
    if (bytes == null || bytes.isEmpty) {
      _showSnackBar('Attach a person photo to preview.');
      return;
    }
    if (_selectedGarmentIds.isEmpty) {
      _showSnackBar('Select a garment from your Digital Wardrobe.');
      return;
    }
    if (_selectedGarmentIds.length > _capabilities.maxGarments) {
      _showSnackBar(
        'Select at most ${_capabilities.maxGarments} garment(s) for try-on.',
      );
      return;
    }
    if (_isWardrobeFlow && _wardrobeLoaded && _wardrobeLoadError == null) {
      final owned = _wardrobeItems.map((e) => e.id).toSet();
      if (_selectedGarmentIds.any((id) => !owned.contains(id))) {
        _showSnackBar('Selected garment is not in your Digital Wardrobe.');
        return;
      }
    }

    if (_activeJobId != null &&
        (_phase == _Phase.timedOut || _phase == _Phase.networkInterrupted)) {
      await _onResumePolling();
      return;
    }

    final key = _pendingIdempotencyKey ??= newTryOnIdempotencyKey();
    await _submitWithKey(
      bytes: bytes,
      garmentIds: List<String>.from(_selectedGarmentIds),
      idempotencyKey: key,
    );
  }

  Future<void> _submitWithKey({
    required Uint8List bytes,
    required List<String> garmentIds,
    required String idempotencyKey,
  }) async {
    if (_isSubmittingGuard) return;
    _isSubmittingGuard = true;
    setState(() {
      _phase = _Phase.submitting;
      _failure = null;
      _failureDetail = null;
      _recoveredJobBanner = false;
    });

    try {
      final result = await _repository.submitTryOn(
        personBytes: bytes,
        personFilename: _personFilename,
        personContentType: _personMimeType,
        outfitSource: widget.outfitSource,
        garmentIds: garmentIds,
        consentVersion: _capabilities.consentVersion,
        consentAccepted: true,
        idempotencyKey: idempotencyKey,
        maxBytes: _capabilities.maxPersonImageBytes,
      );

      if (!mounted) return;
      final job = result.job;
      if (job == null) {
        if (result.failure == TryOnFailure.conflict) {
          _pendingIdempotencyKey = null;
        }
        setState(() {
          _phase = _Phase.failed;
          _failure = result.failure ?? TryOnFailure.networkError;
          _failureDetail = result.errorMessage;
        });
        return;
      }

      TryOnJobPersistence.save(
        TryOnSavedJobRef(
          jobId: job.jobId,
          outfitSource: widget.outfitSource,
          garmentIds: garmentIds,
          title: widget.title,
          isMock: job.isMock,
          savedAtIso: _currentTime().toUtc().toIso8601String(),
        ),
      );

      setState(() {
        _phase = _Phase.polling;
        _activeJobId = job.jobId;
        _lastJobState = job.state;
        _backendProgress = job.state == TryOnJobState.completed ? 100 : 0;
        _isMock = job.isMock;
        _pollCount = 0;
        _consecutivePollFailures = 0;
        _pollingStartedAt = _currentTime();
      });

      await _pollUntilDone(job.jobId);
    } finally {
      _isSubmittingGuard = false;
    }
  }

  Future<bool> _pollOnce(String jobId, int token) async {
    if (!mounted || token != _pollSessionToken || _phase != _Phase.polling) {
      return true;
    }
    if (_pollInFlight) {
      return false;
    }
    _pollInFlight = true;
    try {
      final outcome = await _repository.getJobStatusOutcome(jobId);
      if (!mounted || token != _pollSessionToken || _phase != _Phase.polling) {
        return true;
      }

      if (outcome.failure == TryOnFailure.unauthorized) {
        setState(() {
          _phase = _Phase.failed;
          _failure = TryOnFailure.unauthorized;
          _failureDetail =
              outcome.errorMessage ??
              'Your session expired. Please sign in again.';
        });
        return true;
      }

      if (outcome.failure == TryOnFailure.notFound) {
        TryOnJobPersistence.clear();
        setState(() {
          _phase = _Phase.failed;
          _failure = TryOnFailure.notFound;
          _failureDetail = 'This try-on job could not be found or has expired.';
        });
        return true;
      }

      final status = outcome.status;
      if (status == null) {
        final failures = _consecutivePollFailures + 1;
        if (failures >= _maxConsecutivePollFailures) {
          setState(() {
            _pollCount++;
            _consecutivePollFailures = failures;
            _phase = _Phase.networkInterrupted;
          });
          return true;
        }
        setState(() {
          _pollCount++;
          _consecutivePollFailures = failures;
        });
        return false;
      }

      setState(() {
        _pollCount++;
        _consecutivePollFailures = 0;
        _isMock = status.isMock;
        _lastJobState = status.state;
        _backendProgress = status.progress;
      });

      if (status.state == TryOnJobState.completed) {
        final imgOutcome = await _repository.getJobImageOutcome(jobId);
        if (!mounted || token != _pollSessionToken) return true;
        if (imgOutcome.failure == TryOnFailure.unauthorized) {
          setState(() {
            _phase = _Phase.failed;
            _failure = TryOnFailure.unauthorized;
            _failureDetail =
                imgOutcome.errorMessage ??
                'Your session expired. Please sign in again.';
            _pendingIdempotencyKey = null;
          });
          return true;
        }
        setState(() {
          _phase = _Phase.done;
          _resultBytes = imgOutcome.bytes;
          _imageFetchError = imgOutcome.bytes == null
              ? (imgOutcome.errorMessage ??
                    'Result is ready, but loading the image failed. Check connection and retry.')
              : null;
          _pendingIdempotencyKey = null;
        });
        return true;
      }
      if (status.state == TryOnJobState.failed) {
        setState(() {
          _phase = _Phase.failed;
          _failure = TryOnFailure.unknown;
          _failureDetail = status.errorMessage ?? 'Try-on processing failed.';
          _pendingIdempotencyKey = null;
        });
        return true;
      }
      if (status.state == TryOnJobState.cancelled) {
        TryOnJobPersistence.clear();
        setState(() {
          _phase = _Phase.failed;
          _failure = TryOnFailure.unknown;
          _failureDetail =
              status.errorMessage ??
              (!status.isMock
                  ? 'Cancelled locally. An already-submitted remote generation may still consume a credit.'
                  : 'Try-on request was cancelled.');
          _pendingIdempotencyKey = null;
        });
        return true;
      }
      return false;
    } finally {
      _pollInFlight = false;
    }
  }

  Future<void> _pollUntilDone(String jobId) async {
    final token = ++_pollSessionToken;
    _pollingStartedAt ??= _currentTime();
    final interval = _effectivePollInterval;
    final maxDuration = _effectiveMaxPollDuration;

    while (mounted && token == _pollSessionToken && _phase == _Phase.polling) {
      await Future<void>.delayed(interval);
      if (!mounted || token != _pollSessionToken || _phase != _Phase.polling) {
        return;
      }

      if (!_isAppBackgrounded) {
        final terminal = await _pollOnce(jobId, token);
        if (terminal || !mounted || token != _pollSessionToken) {
          return;
        }
      }

      final elapsed = _currentTime().difference(_pollingStartedAt!);
      if (elapsed >= maxDuration && !_pollInFlight) {
        setState(() {
          _phase = _Phase.timedOut;
        });
        return;
      }
    }
  }

  Future<void> _onResumePolling() async {
    final jid = _activeJobId;
    if (jid == null) return;
    setState(() {
      _phase = _Phase.polling;
      _consecutivePollFailures = 0;
      _pollingStartedAt = _currentTime();
    });
    await _pollUntilDone(jid);
  }

  Future<void> _onRetryFetchImage() async {
    final jid = _activeJobId;
    if (jid == null) return;
    setState(() {
      _imageFetchError = null;
    });
    final imgOutcome = await _repository.getJobImageOutcome(jid);
    if (!mounted) return;
    if (imgOutcome.failure == TryOnFailure.unauthorized) {
      setState(() {
        _phase = _Phase.failed;
        _failure = TryOnFailure.unauthorized;
        _failureDetail = 'Please sign in again to view your try-on result.';
      });
      return;
    }
    setState(() {
      _resultBytes = imgOutcome.bytes;
      _imageFetchError = imgOutcome.bytes == null
          ? (imgOutcome.errorMessage ?? 'Could not load result image.')
          : null;
    });
  }

  Future<void> _onCancel() async {
    final jid = _activeJobId;
    if (jid == null) return;
    _pollSessionToken++;
    final res = await _repository.cancelJob(jid);
    if (!mounted) return;
    if (res != null) {
      TryOnJobPersistence.clear();
      setState(() {
        _phase = _Phase.failed;
        _failure = TryOnFailure.unknown;
        _failureDetail =
            res.errorMessage ??
            (!res.isMock
                ? 'Cancelled locally. An already-submitted remote generation may still consume a credit.'
                : 'Try-on request cancelled by user.');
        _pendingIdempotencyKey = null;
      });
      _showSnackBar(
        !res.isMock
            ? 'Cancelled locally (submitted remote job may still use a credit).'
            : 'Try-on job cancelled.',
      );
    } else {
      _showSnackBar('Could not cancel right now. Checking current job status…');
    }
  }

  Future<void> _onRetrySubmit() async {
    if (_isSubmittingGuard) return;
    final jid = _activeJobId;
    if (jid == null) {
      final bytes = _personBytes;
      final pendingKey = _pendingIdempotencyKey;
      if (bytes != null &&
          bytes.isNotEmpty &&
          _selectedGarmentIds.isNotEmpty &&
          pendingKey != null) {
        await _submitWithKey(
          bytes: bytes,
          garmentIds: List<String>.from(_selectedGarmentIds),
          idempotencyKey: pendingKey,
        );
        return;
      }
      _onRetry();
      return;
    }

    _isSubmittingGuard = true;
    setState(() {
      _phase = _Phase.submitting;
      _failure = null;
      _failureDetail = null;
    });
    try {
      final res = await _repository.retryJob(jid);
      if (!mounted) return;
      final job = res.job;
      if (job == null) {
        setState(() {
          _phase = _Phase.failed;
          _failure = res.failure ?? TryOnFailure.networkError;
          _failureDetail = res.errorMessage;
        });
        return;
      }
      setState(() {
        _phase = _Phase.polling;
        _activeJobId = job.jobId;
        _lastJobState = job.state;
        _backendProgress = 0;
        _isMock = job.isMock;
        _pollCount = 0;
        _consecutivePollFailures = 0;
        _pollingStartedAt = _currentTime();
      });
      await _pollUntilDone(job.jobId);
    } finally {
      _isSubmittingGuard = false;
    }
  }

  Future<void> _onDeleteResult() async {
    final jid = _activeJobId;
    if (jid == null) {
      _onRetry();
      return;
    }
    final success = await _repository.deleteJob(jid);
    if (!mounted) return;
    if (success) {
      TryOnJobPersistence.clear();
      _showSnackBar('Try-on result and media deleted.');
      _onRetry();
    } else {
      _showSnackBar('Could not delete result. Please try again.');
    }
  }

  Future<String?> _onSaveToDevice({BuildContext? feedbackContext}) async {
    if (_isMock || _isSavingToDevice) return null;
    final bytes = _resultBytes;
    final jid = _activeJobId ?? 'result';
    if (bytes == null || bytes.isEmpty) {
      const msg = 'Image is not loaded yet.';
      if (feedbackContext != null && feedbackContext.mounted) {
        ScaffoldMessenger.of(
          feedbackContext,
        ).showSnackBar(const SnackBar(content: Text(msg)));
      } else {
        _showSnackBar(msg);
      }
      return msg;
    }
    setState(() => _isSavingToDevice = true);
    try {
      final outcome = await (widget.saveResultImage != null
          ? widget.saveResultImage!(bytes, jid)
          : TryOnDeviceSaver.saveImage(bytes, jobId: jid));
      if (!mounted) return null;
      final msg = switch (outcome.status) {
        TryOnSaveStatus.saved =>
          outcome.message ?? 'Result saved to your device.',
        TryOnSaveStatus.permissionDenied =>
          outcome.message ??
              'Storage permission denied. Please grant permission in device settings.',
        _ => outcome.message ?? 'Could not save result to your device.',
      };
      if (feedbackContext != null && feedbackContext.mounted) {
        ScaffoldMessenger.of(
          feedbackContext,
        ).showSnackBar(SnackBar(content: Text(msg)));
      } else {
        _showSnackBar(msg);
      }
      return msg;
    } finally {
      if (mounted) setState(() => _isSavingToDevice = false);
    }
  }

  void _openFullScreenViewer() {
    final bytes = _resultBytes;
    if (bytes == null || bytes.isEmpty) return;
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        fullscreenDialog: true,
        builder: (ctx) => _FullScreenResultViewer(
          imageBytes: bytes,
          isMock: _isMock,
          onSave: _isMock
              ? null
              : (viewerCtx) => _onSaveToDevice(feedbackContext: viewerCtx),
        ),
      ),
    );
  }

  void _onRetry() {
    _pollSessionToken++;
    TryOnJobPersistence.clear();
    setState(() {
      _phase = _Phase.input;
      _failure = null;
      _failureDetail = null;
      _pollCount = 0;
      _consecutivePollFailures = 0;
      _resultBytes = null;
      _imageFetchError = null;
      _activeJobId = null;
      _pendingIdempotencyKey = null;
      _lastJobState = null;
      _backendProgress = null;
      _pollingStartedAt = null;
      _recoveredJobBanner = false;
      _isMock = _capabilities.isMock;
    });
  }

  String _failureMessage(TryOnFailure? failure) {
    if (_failureDetail != null && _failureDetail!.isNotEmpty) {
      return _failureDetail!;
    }
    switch (failure) {
      case TryOnFailure.unauthorized:
        return 'Please sign in again to preview try-ons.';
      case TryOnFailure.notFound:
        return 'The requested try-on job or garment was not found.';
      case TryOnFailure.conflict:
        return 'This request conflicted with an existing try-on job state. Refresh or start a new request.';
      case TryOnFailure.invalidInput:
        return 'That preview request was invalid. Check the photo and try again.';
      case TryOnFailure.quotaExceeded:
        return 'Daily preview limit reached. Please try again tomorrow.';
      case TryOnFailure.rateLimited:
        return 'Too many active try-on jobs. Please wait for in-progress jobs to finish.';
      case TryOnFailure.serviceUnavailable:
        return 'Virtual Try-On is currently unavailable. Please try again later.';
      case TryOnFailure.timeout:
        return 'Try-on processing timed out. Please retry with the button below.';
      case TryOnFailure.networkError:
        return 'Please check your connection and try again.';
      default:
        return 'Something went wrong during try-on processing. Please try again.';
    }
  }

  @override
  Widget build(BuildContext context) {
    final showEmptyLegacyOutfit =
        !_isWardrobeFlow &&
        widget.garmentIds.isEmpty &&
        _selectedGarmentIds.isEmpty &&
        _phase == _Phase.input;

    return Scaffold(
      backgroundColor: FansivibeColors.surface,
      appBar: AppBar(title: const Text('Virtual Try-On')),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final isWide = constraints.maxWidth > 600;
            final horizontalPad = isWide ? 32.0 : 20.0;
            return SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              padding: EdgeInsets.symmetric(
                horizontal: horizontalPad,
                vertical: 20,
              ),
              child: Center(
                child: ConstrainedBox(
                  constraints: BoxConstraints(
                    maxWidth: isWide ? 640.0 : double.infinity,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _buildProviderBanner(),
                      if (_recoveredJobBanner) ...[
                        const SizedBox(height: 12),
                        Container(
                          width: double.infinity,
                          padding: const EdgeInsets.symmetric(
                            horizontal: 12,
                            vertical: 8,
                          ),
                          decoration: BoxDecoration(
                            color: FansivibeColors.primary.withValues(
                              alpha: 0.12,
                            ),
                            borderRadius: FansivibeRadius.smBorder,
                          ),
                          child: Text(
                            'Resumed your previous try-on job.',
                            style: FansivibeTypography.labelMediumWithFamily
                                .copyWith(color: FansivibeColors.primary),
                          ),
                        ),
                      ],
                      const SizedBox(height: 16),
                      Text(
                        widget.title,
                        style: FansivibeTypography.headlineMediumWithFamily
                            .copyWith(fontWeight: FontWeight.w500),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '${_selectedGarmentIds.length} piece(s) • ${widget.outfitSource}',
                        style: FansivibeTypography.labelMediumWithFamily
                            .copyWith(color: FansivibeColors.textSecondary),
                      ),
                      if (showEmptyLegacyOutfit) ...[
                        const SizedBox(height: 16),
                        const Text(
                          'No outfit selected. Go back and pick a look.',
                        ),
                      ] else ...[
                        const SizedBox(height: 16),
                        _buildBody(),
                      ],
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildProviderBanner() {
    if (_isMock) {
      return Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 14),
        decoration: BoxDecoration(
          color: FansivibeColors.warning,
          borderRadius: FansivibeRadius.smdBorder,
        ),
        child: Text(
          'TEST DATA — NOT AI TRY-ON',
          textAlign: TextAlign.center,
          style: FansivibeTypography.labelMediumWithFamily.copyWith(
            color: FansivibeColors.surfaceContainerLowest,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.0,
          ),
        ),
      );
    }
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 14),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainer,
        borderRadius: FansivibeRadius.smdBorder,
        border: Border.all(
          color: FansivibeColors.primary.withValues(alpha: 0.5),
        ),
      ),
      child: Column(
        children: [
          Wrap(
            alignment: WrapAlignment.center,
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: 6,
            runSpacing: 4,
            children: [
              const Icon(
                Icons.auto_awesome_rounded,
                size: 16,
                color: FansivibeColors.primary,
              ),
              Text(
                'AI Try-On Result',
                style: FansivibeTypography.labelMediumWithFamily.copyWith(
                  color: FansivibeColors.primary,
                  fontWeight: FontWeight.w700,
                ),
              ),
              if (_capabilities.aiDisclosureRequired || !_isMock) ...[
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 6,
                    vertical: 2,
                  ),
                  decoration: BoxDecoration(
                    color: FansivibeColors.primary.withValues(alpha: 0.16),
                    borderRadius: FansivibeRadius.fullBorder,
                  ),
                  child: Text(
                    'AI MODIFIED',
                    style: FansivibeTypography.labelSmallWithFamily.copyWith(
                      color: FansivibeColors.primary,
                      fontSize: 9.5,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: 2),
          Text(
            'Visual representation only; does not represent physical garment sizing or fit.',
            textAlign: TextAlign.center,
            style: FansivibeTypography.labelSmallWithFamily.copyWith(
              color: FansivibeColors.textSecondary,
              fontSize: 11,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBody() {
    switch (_phase) {
      case _Phase.submitting:
        return const Center(
          child: Padding(
            padding: EdgeInsets.symmetric(vertical: 32),
            child: Column(
              children: [
                CircularProgressIndicator(),
                SizedBox(height: 16),
                Text('Creating try-on job…'),
              ],
            ),
          ),
        );
      case _Phase.polling:
        final totalSeconds = _effectiveMaxPollDuration.inSeconds;
        final elapsedSeconds = _pollingStartedAt != null
            ? _currentTime()
                  .difference(_pollingStartedAt!)
                  .inSeconds
                  .clamp(0, totalSeconds)
            : 0;
        final progressValue =
            (_backendProgress != null && _backendProgress! > 0)
            ? (_backendProgress! / 100.0).clamp(0.0, 1.0)
            : (totalSeconds > 0 && elapsedSeconds > 0
                  ? (elapsedSeconds / totalSeconds).clamp(0.0, 1.0)
                  : null);
        final statusLabel = _lastJobState == TryOnJobState.queued
            ? 'Queued for virtual try-on…'
            : (_isMock
                  ? 'Rendering test preview… (poll ${_pollCount + 1})'
                  : 'Generating virtual try-on… (${elapsedSeconds}s / ${totalSeconds}s)');
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            LinearProgressIndicator(
              value: progressValue,
              backgroundColor: FansivibeColors.surfaceContainer,
              color: FansivibeColors.primary,
            ),
            SizedBox(height: FansivibeSpacing.md),
            Text(
              statusLabel,
              textAlign: TextAlign.center,
              style: FansivibeTypography.bodyMediumWithFamily,
            ),
            if (_consecutivePollFailures > 0) ...[
              const SizedBox(height: 8),
              Text(
                'Connection interrupted — retrying status check…',
                textAlign: TextAlign.center,
                style: FansivibeTypography.labelMediumWithFamily.copyWith(
                  color: FansivibeColors.warning,
                ),
              ),
            ],
            const SizedBox(height: 16),
            FansiButton.secondary(
              label: 'Cancel Request',
              icon: Icons.cancel_outlined,
              onPressed: _onCancel,
            ),
          ],
        );
      case _Phase.timedOut:
      case _Phase.networkInterrupted:
        final isNetwork = _phase == _Phase.networkInterrupted;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: FansivibeColors.warning.withValues(alpha: 0.12),
                borderRadius: FansivibeRadius.smdBorder,
                border: Border.all(
                  color: FansivibeColors.warning.withValues(alpha: 0.45),
                ),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    isNetwork
                        ? Icons.wifi_off_rounded
                        : Icons.hourglass_top_rounded,
                    color: FansivibeColors.warning,
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          isNetwork
                              ? 'Connection interrupted'
                              : 'Still processing',
                          style: FansivibeTypography.titleLargeWithFamily
                              .copyWith(
                                fontSize: 16,
                                fontWeight: FontWeight.w600,
                              ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          isNetwork
                              ? 'We lost connection while checking your try-on job. '
                                    'Check status once your connection returns without creating a duplicate request.'
                              : 'Your try-on is taking longer than expected, but it has not failed. '
                                    'Check status to continue waiting without starting a duplicate request.',
                          style: FansivibeTypography.bodyMediumWithFamily,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 14),
            FansiButton.primary(
              label: 'Check Status',
              icon: Icons.sync_rounded,
              onPressed: _onResumePolling,
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: FansiButton.secondary(
                    label: 'Cancel Request',
                    icon: Icons.cancel_outlined,
                    onPressed: _onCancel,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FansiButton.secondary(
                    label: 'Start Over',
                    icon: Icons.restart_alt_rounded,
                    onPressed: _onRetry,
                  ),
                ),
              ],
            ),
          ],
        );
      case _Phase.done:
        return _buildDone();
      case _Phase.failed:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
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
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      _failureMessage(_failure),
                      style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                        color: FansivibeColors.error,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            _buildResponsiveActionPair(
              FansiButton.secondary(
                label: 'Try Again',
                icon: Icons.refresh_rounded,
                onPressed: _onRetrySubmit,
              ),
              FansiButton.secondary(
                label: 'Change Inputs',
                icon: Icons.edit_outlined,
                onPressed: _onRetry,
              ),
            ),
            const SizedBox(height: 20),
            _buildInput(enabled: true),
          ],
        );
      case _Phase.input:
        return _buildInput(enabled: true);
    }
  }

  Widget _buildGarmentSection(bool enabled) {
    final maxGarments = _capabilities.maxGarments;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainer,
        borderRadius: FansivibeRadius.smdBorder,
        border: Border.all(color: FansivibeColors.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Selected Garments (${_selectedGarmentIds.length})',
                      style: FansivibeTypography.titleLargeWithFamily.copyWith(
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    Text(
                      maxGarments == 1
                          ? 'Single garment supported per generation'
                          : 'Up to $maxGarments garments supported',
                      style: FansivibeTypography.labelSmallWithFamily.copyWith(
                        color: FansivibeColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              if (enabled)
                TextButton.icon(
                  icon: const Icon(Icons.swap_horiz_rounded, size: 18),
                  label: Text(
                    _selectedGarmentIds.isEmpty ? 'Select' : 'Change',
                  ),
                  onPressed: _showGarmentPicker,
                ),
            ],
          ),
          if (_garmentSelectionWarning != null) ...[
            const SizedBox(height: 8),
            Text(
              _garmentSelectionWarning!,
              style: FansivibeTypography.labelMediumWithFamily.copyWith(
                color: FansivibeColors.warning,
              ),
            ),
          ],
          const SizedBox(height: 10),
          if (_isLoadingWardrobe && _selectedGarmentIds.isEmpty) ...[
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: Center(child: CircularProgressIndicator()),
            ),
          ] else if (_wardrobeLoadError != null &&
              _selectedGarmentIds.isEmpty) ...[
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _wardrobeLoadError!,
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.error,
                  ),
                ),
                const SizedBox(height: 10),
                FansiButton.secondary(
                  label: 'Retry Loading Wardrobe',
                  icon: Icons.refresh_rounded,
                  onPressed: enabled ? _loadWardrobeItems : null,
                ),
              ],
            ),
          ] else if (_wardrobeLoaded &&
              _wardrobeItems.isEmpty &&
              _selectedGarmentIds.isEmpty) ...[
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Your Digital Wardrobe is empty. Add a garment photo first to try it on.',
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.textSecondary,
                  ),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: FansiButton.primary(
                        label: 'Add Garment to Wardrobe',
                        icon: Icons.add_rounded,
                        onPressed: enabled ? _navigateToAddGarment : null,
                      ),
                    ),
                    const SizedBox(width: 8),
                    IconButton(
                      tooltip: 'Refresh Wardrobe',
                      icon: const Icon(Icons.refresh_rounded),
                      onPressed: enabled ? _loadWardrobeItems : null,
                    ),
                  ],
                ),
              ],
            ),
          ] else if (_selectedGarmentIds.isEmpty) ...[
            FansiButton.secondary(
              label: 'Select from Digital Wardrobe',
              icon: Icons.add_circle_outline_rounded,
              onPressed: enabled ? _showGarmentPicker : null,
            ),
          ] else ...[
            for (var i = 0; i < _selectedGarmentIds.length; i++) ...[
              if (i > 0) const SizedBox(height: 8),
              _buildSelectedGarmentTile(_selectedGarmentIds[i], enabled),
            ],
            if (maxGarments > 1 &&
                _selectedGarmentIds.length < maxGarments &&
                enabled) ...[
              const SizedBox(height: 10),
              FansiButton.secondary(
                label: 'Add Another Garment',
                icon: Icons.add_rounded,
                onPressed: _showGarmentPicker,
              ),
            ],
          ],
        ],
      ),
    );
  }

  Widget _buildSelectedGarmentTile(String garmentId, bool enabled) {
    final garment = _selectedGarmentMap[garmentId];
    return Container(
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.smBorder,
        border: Border.all(
          color: FansivibeColors.primary.withValues(alpha: 0.35),
        ),
      ),
      child: Row(
        children: [
          SizedBox(
            width: 56,
            height: 56,
            child: ClipRRect(
              borderRadius: FansivibeRadius.smBorder,
              child: garment != null
                  ? WardrobeItemImage(item: garment, iconSize: 26)
                  : const FansiImageWell(
                      icon: Icons.checkroom_rounded,
                      color: FansivibeColors.primary,
                    ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: garment != null
                ? Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        garment.name,
                        style: FansivibeTypography.bodyLargeWithFamily.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '${garment.category} • ${garment.color}',
                        style: FansivibeTypography.bodyMediumWithFamily
                            .copyWith(color: FansivibeColors.textSecondary),
                      ),
                    ],
                  )
                : Text(
                    garmentId,
                    style: FansivibeTypography.bodyLargeWithFamily,
                  ),
          ),
          if (enabled)
            IconButton(
              tooltip: 'Remove garment',
              icon: const Icon(
                Icons.close_rounded,
                color: FansivibeColors.textSecondary,
              ),
              onPressed: () => _onRemoveGarment(garmentId),
            ),
        ],
      ),
    );
  }

  Widget _buildReviewCard() {
    final hasPhoto = _personBytes != null && _personBytes!.isNotEmpty;
    final garmentCount = _selectedGarmentIds.length;
    final maxMb = (_capabilities.maxPersonImageBytes / (1024 * 1024)).round();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.smdBorder,
        border: Border.all(color: FansivibeColors.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '3. Review Summary',
            style: FansivibeTypography.titleLargeWithFamily.copyWith(
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Icon(
                hasPhoto
                    ? Icons.check_circle_rounded
                    : Icons.radio_button_unchecked_rounded,
                size: 18,
                color: hasPhoto
                    ? FansivibeColors.success
                    : FansivibeColors.textSecondary,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  hasPhoto
                      ? (_personDimensions != null
                            ? 'Person photo ready (${_personDimensions!.$1}×${_personDimensions!.$2})'
                            : 'Person photo ready')
                      : 'No person photo selected (JPEG/PNG/WebP, up to $maxMb MB)',
                  style: FansivibeTypography.bodyMediumWithFamily,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              Icon(
                garmentCount > 0
                    ? Icons.check_circle_rounded
                    : Icons.radio_button_unchecked_rounded,
                size: 18,
                color: garmentCount > 0
                    ? FansivibeColors.success
                    : FansivibeColors.textSecondary,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  garmentCount > 0
                      ? '$garmentCount garment(s) selected'
                      : 'No garment selected',
                  style: FansivibeTypography.bodyMediumWithFamily,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildResponsiveActionPair(Widget first, Widget second) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final scale = MediaQuery.textScalerOf(context).scale(14) / 14.0;
        final stackVertically =
            constraints.maxWidth < 340 ||
            (scale > 1.1 && constraints.maxWidth < 420);
        if (stackVertically) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [first, const SizedBox(height: 10), second],
          );
        }
        return Row(
          children: [
            Expanded(child: first),
            const SizedBox(width: 12),
            Expanded(child: second),
          ],
        );
      },
    );
  }

  Widget _buildInput({required bool enabled}) {
    final bytes = _personBytes;
    final hasPhoto = bytes != null && bytes.isNotEmpty;
    final ctaLabel = _isMock ? 'Preview Try-On (Test Data)' : 'Generate Try-On';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '1. Your Photograph',
          style: FansivibeTypography.titleLargeWithFamily.copyWith(
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 8),
        if (hasPhoto) ...[
          Stack(
            children: [
              Container(
                height: 220,
                width: double.infinity,
                margin: EdgeInsets.only(bottom: FansivibeSpacing.sm),
                child: ClipRRect(
                  borderRadius: FansivibeRadius.smdBorder,
                  child: Image.memory(
                    bytes,
                    fit: BoxFit.cover,
                    errorBuilder: (context, error, stackTrace) =>
                        const FansiImageWell(
                          icon: Icons.person_outline_rounded,
                          color: FansivibeColors.primary,
                        ),
                  ),
                ),
              ),
              if (enabled)
                Positioned(
                  top: 8,
                  right: 8,
                  child: Material(
                    color: Colors.black.withValues(alpha: 0.65),
                    borderRadius: FansivibeRadius.fullBorder,
                    child: InkWell(
                      onTap: _onRemovePersonPhoto,
                      borderRadius: FansivibeRadius.fullBorder,
                      child: const Padding(
                        padding: EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 6,
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              Icons.delete_outline_rounded,
                              size: 16,
                              color: Colors.white,
                            ),
                            SizedBox(width: 4),
                            Text(
                              'Remove',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ] else ...[
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 14),
            margin: EdgeInsets.only(bottom: FansivibeSpacing.sm),
            decoration: BoxDecoration(
              color: FansivibeColors.surfaceContainer,
              borderRadius: FansivibeRadius.smdBorder,
              border: Border.all(color: FansivibeColors.outlineVariant),
            ),
            child: Column(
              children: [
                const Icon(
                  Icons.person_outline_rounded,
                  size: 36,
                  color: FansivibeColors.textSecondary,
                ),
                const SizedBox(height: 6),
                Text(
                  'No person photograph selected',
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
        ],
        if (_imageError != null) ...[
          Container(
            width: double.infinity,
            margin: EdgeInsets.only(bottom: FansivibeSpacing.sm),
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: FansivibeColors.error.withValues(alpha: 0.12),
              borderRadius: FansivibeRadius.smBorder,
              border: Border.all(
                color: FansivibeColors.error.withValues(alpha: 0.35),
              ),
            ),
            child: Row(
              children: [
                const Icon(
                  Icons.warning_amber_rounded,
                  size: 18,
                  color: FansivibeColors.error,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    _imageError!,
                    style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                      color: FansivibeColors.error,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
        _buildResponsiveActionPair(
          FansiButton.secondary(
            label: hasPhoto ? 'Replace Photo' : 'Choose Photo',
            icon: Icons.photo_library_outlined,
            onPressed: enabled
                ? () => _onAttachPhoto(ImageSource.gallery)
                : null,
          ),
          FansiButton.secondary(
            label: 'Take Photo',
            icon: Icons.camera_alt_outlined,
            onPressed: enabled
                ? () => _onAttachPhoto(ImageSource.camera)
                : null,
          ),
        ),
        SizedBox(height: FansivibeSpacing.lg),
        Text(
          '2. Wardrobe Piece',
          style: FansivibeTypography.titleLargeWithFamily.copyWith(
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 8),
        _buildGarmentSection(enabled),
        SizedBox(height: FansivibeSpacing.md),
        _buildReviewCard(),
        SizedBox(height: FansivibeSpacing.md),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Checkbox(
              value: _consent,
              onChanged: enabled
                  ? (value) => setState(() => _consent = value ?? false)
                  : null,
            ),
            const Expanded(
              child: Padding(
                padding: EdgeInsets.only(top: 12),
                child: Text(
                  'I agree to process this photo for a virtual try-on preview. '
                  'Photos are stored privately and automatically deleted after 24 hours '
                  '(results after 72 hours), and you can delete them at any time.',
                ),
              ),
            ),
          ],
        ),
        SizedBox(height: FansivibeSpacing.md),
        FansiButton.primary(
          key: const ValueKey('tryon_generate_button'),
          label: ctaLabel,
          icon: _isMock
              ? Icons.visibility_outlined
              : Icons.auto_awesome_rounded,
          onPressed: enabled ? _onSubmit : null,
        ),
      ],
    );
  }

  bool _isSvgBytes(Uint8List bytes) {
    if (bytes.length < 4) return false;
    final prefix = utf8
        .decode(bytes.take(64).toList(), allowMalformed: true)
        .trimLeft();
    return prefix.startsWith('<svg') ||
        (prefix.startsWith('<?xml') && prefix.contains('<svg'));
  }

  Widget _buildDone() {
    final resultBytes = _resultBytes;
    final hasImage = resultBytes != null && resultBytes.isNotEmpty;
    final isSvgMock = _isMock && hasImage && _isSvgBytes(resultBytes);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (hasImage) ...[
          GestureDetector(
            onTap: _openFullScreenViewer,
            child: Stack(
              children: [
                Container(
                  height: 360,
                  width: double.infinity,
                  decoration: BoxDecoration(
                    color: FansivibeColors.surfaceContainerLowest,
                    borderRadius: FansivibeRadius.smdBorder,
                    border: Border.all(color: FansivibeColors.outlineVariant),
                  ),
                  child: ClipRRect(
                    borderRadius: FansivibeRadius.smdBorder,
                    child: isSvgMock
                        ? _MockSvgPreviewCard(
                            garmentLabels: _selectedGarmentIds
                                .map(
                                  (id) => _selectedGarmentMap[id]?.name ?? id,
                                )
                                .toList(),
                          )
                        : Image.memory(
                            resultBytes,
                            fit: BoxFit.contain,
                            errorBuilder: (_, __, ___) => const FansiImageWell(
                              icon: Icons.checkroom_rounded,
                              color: FansivibeColors.primary,
                            ),
                          ),
                  ),
                ),
                Positioned(
                  bottom: 10,
                  right: 10,
                  child: Material(
                    color: Colors.black.withValues(alpha: 0.65),
                    borderRadius: FansivibeRadius.fullBorder,
                    child: InkWell(
                      onTap: _openFullScreenViewer,
                      borderRadius: FansivibeRadius.fullBorder,
                      child: const Padding(
                        padding: EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 6,
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              Icons.fullscreen_rounded,
                              size: 18,
                              color: Colors.white,
                            ),
                            SizedBox(width: 4),
                            Text(
                              'Full Screen',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ] else if (_imageFetchError != null) ...[
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: FansivibeColors.surfaceContainer,
              borderRadius: FansivibeRadius.smdBorder,
              border: Border.all(color: FansivibeColors.outlineVariant),
            ),
            child: Column(
              children: [
                const Icon(
                  Icons.broken_image_outlined,
                  size: 40,
                  color: FansivibeColors.warning,
                ),
                const SizedBox(height: 8),
                Text(
                  _imageFetchError!,
                  textAlign: TextAlign.center,
                  style: FansivibeTypography.bodyMediumWithFamily,
                ),
                const SizedBox(height: 12),
                FansiButton.secondary(
                  label: 'Retry Loading Image',
                  icon: Icons.refresh_rounded,
                  onPressed: _onRetryFetchImage,
                ),
              ],
            ),
          ),
        ] else ...[
          const FansiImageWell(
            icon: Icons.checkroom_rounded,
            color: FansivibeColors.primary,
          ),
        ],
        SizedBox(height: FansivibeSpacing.md),
        Text(
          _isMock
              ? 'Mock preview ready. This is UI test data — not an AI-generated '
                    'try-on, and it cannot be saved or shared as one.'
              : 'Virtual Try-On generation complete. Result saved privately to your profile.',
          style: FansivibeTypography.bodyMediumWithFamily,
        ),
        if (_selectedGarmentIds.isNotEmpty) ...[
          SizedBox(height: FansivibeSpacing.sm),
          Wrap(
            spacing: 8,
            runSpacing: 6,
            children: [
              for (final id in _selectedGarmentIds)
                Chip(label: Text(_selectedGarmentMap[id]?.name ?? id)),
            ],
          ),
        ],
        SizedBox(height: FansivibeSpacing.lg),
        if (!_isMock && hasImage) ...[
          FansiButton.primary(
            label: _isSavingToDevice ? 'Saving…' : 'Save to Device',
            icon: Icons.download_rounded,
            onPressed: _isSavingToDevice ? null : _onSaveToDevice,
          ),
          SizedBox(height: FansivibeSpacing.sm),
        ],
        FansiButton.secondary(
          label: 'Preview Again',
          icon: Icons.refresh_rounded,
          onPressed: _onRetry,
        ),
        SizedBox(height: FansivibeSpacing.sm),
        FansiButton.secondary(
          label: 'Delete Result',
          icon: Icons.delete_outline_rounded,
          onPressed: _onDeleteResult,
        ),
        SizedBox(height: FansivibeSpacing.sm),
        _buildResponsiveActionPair(
          FansiButton.secondary(
            label: 'Wardrobe',
            icon: Icons.checkroom_outlined,
            onPressed: _navigateToWardrobe,
          ),
          FansiButton.secondary(
            label: 'AI Stylist',
            icon: Icons.auto_awesome_outlined,
            onPressed: _navigateToStylist,
          ),
        ),
        SizedBox(height: FansivibeSpacing.sm),
        FansiButton.secondary(
          label: 'Back to Outfit',
          icon: Icons.arrow_back_rounded,
          onPressed: () => Navigator.of(context).maybePop(),
        ),
      ],
    );
  }
}

class _MockSvgPreviewCard extends StatelessWidget {
  const _MockSvgPreviewCard({required this.garmentLabels});

  final List<String> garmentLabels;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: FansivibeColors.surfaceContainer,
      padding: const EdgeInsets.all(20),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.checkroom_rounded,
              size: 56,
              color: FansivibeColors.warning,
            ),
            const SizedBox(height: 12),
            Text(
              'TEST DATA — MOCK TRY-ON',
              style: FansivibeTypography.labelMediumWithFamily.copyWith(
                color: FansivibeColors.warning,
                fontWeight: FontWeight.w700,
              ),
            ),
            if (garmentLabels.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(
                garmentLabels.join(', '),
                textAlign: TextAlign.center,
                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _FullScreenResultViewer extends StatelessWidget {
  const _FullScreenResultViewer({
    required this.imageBytes,
    required this.isMock,
    this.onSave,
  });

  final Uint8List imageBytes;
  final bool isMock;
  final Future<String?> Function(BuildContext viewerContext)? onSave;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: Text(isMock ? 'Test Preview' : 'AI Try-On Result'),
        actions: [
          if (!isMock && onSave != null)
            Builder(
              builder: (btnContext) => IconButton(
                tooltip: 'Save to Device',
                icon: const Icon(Icons.download_rounded),
                onPressed: () => unawaited(onSave!(btnContext)),
              ),
            ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            if (!isMock)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 6,
                ),
                color: FansivibeColors.surfaceContainerLow,
                child: Text(
                  'AI MODIFIED • Visual representation only',
                  textAlign: TextAlign.center,
                  style: FansivibeTypography.labelSmallWithFamily.copyWith(
                    color: FansivibeColors.primary,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            Expanded(
              child: Center(
                child: InteractiveViewer(
                  minScale: 0.8,
                  maxScale: 4.0,
                  child: Image.memory(
                    imageBytes,
                    fit: BoxFit.contain,
                    errorBuilder: (_, __, ___) => const Icon(
                      Icons.checkroom_rounded,
                      size: 64,
                      color: FansivibeColors.primary,
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
