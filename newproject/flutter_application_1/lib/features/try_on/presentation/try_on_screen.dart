import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import 'package:fansivibe/features/try_on/data/try_on_models.dart';
import 'package:fansivibe/features/try_on/data/try_on_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart'
    show WardrobeItemData;
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/components/fansi_image_well.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

/// Complete Virtual Try-On Screen (Phase 5C).
///
/// Supports end-to-end user journey:
/// - Selecting or capturing a person photograph with preview.
/// - Selecting a verified garment from the user's Digital Wardrobe with preview.
/// - Clear explanation of VTON consent and explicit confirmation.
/// - Submitting try-on job with duplicate-submission protection.
/// - Real processing progress with optional cancellation.
/// - Truthful display of actual generated result pixels.
/// - Clear labeling of mock vs genuine AI inference.
/// - Retrying failed jobs and deleting generated results.
class TryOnScreen extends StatefulWidget {
  const TryOnScreen({
    required this.outfitSource,
    required this.garmentIds,
    required this.title,
    this.tryOnRepository,
    this.wardrobeRepository,
    this.pickImage,
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

  /// Backend try-on repository seam. Defaults to live implementation.
  final TryOnRepository? tryOnRepository;

  /// Wardrobe repository seam for fetching user garments.
  final WardrobeRepository? wardrobeRepository;

  /// Photo picker seam (gallery/camera). Defaults to [ImagePicker].
  final Future<XFile?> Function(ImageSource source)? pickImage;

  /// Interval between status polls.
  final Duration pollInterval;

  /// Maximum client polling window aligned with backend 120s timeout + headroom.
  final Duration maxPollDuration;

  /// Clock seam for deterministic elapsed-time testing.
  final DateTime Function()? now;

  @override
  State<TryOnScreen> createState() => _TryOnScreenState();
}

enum _Phase { input, submitting, polling, timedOut, done, failed }

class _TryOnScreenState extends State<TryOnScreen> with WidgetsBindingObserver {
  late final TryOnRepository _repository;
  late final WardrobeRepository _wardrobeRepo;

  bool _consent = false;
  Uint8List? _personBytes;
  String _personFilename = 'tryon_person.jpg';

  List<WardrobeItemData> _wardrobeItems = [];
  WardrobeItemData? _selectedGarment;
  String? _selectedGarmentId;
  bool _isLoadingWardrobe = false;

  _Phase _phase = _Phase.input;
  TryOnFailure? _failure;
  String? _failureDetail;
  int _pollCount = 0;
  String? _activeJobId;
  String? _pendingIdempotencyKey;
  TryOnJobState? _lastJobState;
  int? _backendProgress;
  bool _isMock = true;
  Uint8List? _resultBytes;

  DateTime? _pollingStartedAt;
  bool _isAppBackgrounded = false;
  bool _pollInFlight = false;
  int _pollSessionToken = 0;

  DateTime _currentTime() => (widget.now ?? DateTime.now)();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _repository = widget.tryOnRepository ?? TryOnRepositoryImpl();
    _wardrobeRepo = widget.wardrobeRepository ?? WardrobeRepositoryImpl();

    if (widget.garmentIds.isNotEmpty) {
      _selectedGarmentId = widget.garmentIds.first;
    }
    _loadWardrobeItems();
  }

  @override
  void dispose() {
    _pollSessionToken++;
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

  Future<void> _loadWardrobeItems() async {
    setState(() => _isLoadingWardrobe = true);
    try {
      final items = await _wardrobeRepo.listItems(pageSize: 50);
      if (!mounted) return;
      setState(() {
        _wardrobeItems = items;
        if (_selectedGarmentId != null && _wardrobeItems.isNotEmpty) {
          final found = _wardrobeItems.where((i) => i.id == _selectedGarmentId);
          if (found.isNotEmpty) {
            _selectedGarment = found.first;
          }
        }
        _isLoadingWardrobe = false;
      });
    } catch (_) {
      if (mounted) setState(() => _isLoadingWardrobe = false);
    }
  }

  Future<XFile?> _defaultPickImage(ImageSource source) {
    return ImagePicker().pickImage(
      source: source,
      maxWidth: 1024,
      maxHeight: 1024,
      imageQuality: 85,
    );
  }

  Future<void> _onAttachPhoto(ImageSource source) async {
    if (_phase == _Phase.submitting || _phase == _Phase.polling) return;
    final picked = await (widget.pickImage ?? _defaultPickImage)(source);
    if (picked == null || !mounted) return;
    final bytes = await picked.readAsBytes();
    if (!mounted || bytes.isEmpty) return;
    setState(() {
      _personBytes = bytes;
      _personFilename = picked.name.isNotEmpty ? picked.name : _personFilename;
      _pendingIdempotencyKey = null;
      _activeJobId = null;
      if (_phase == _Phase.failed ||
          _phase == _Phase.done ||
          _phase == _Phase.timedOut) {
        _phase = _Phase.input;
        _failure = null;
        _resultBytes = null;
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

  void _onSelectGarment(WardrobeItemData item) {
    setState(() {
      _selectedGarment = item;
      _selectedGarmentId = item.id;
      _pendingIdempotencyKey = null;
      _activeJobId = null;
      if (_phase == _Phase.failed ||
          _phase == _Phase.done ||
          _phase == _Phase.timedOut) {
        _phase = _Phase.input;
        _failure = null;
        _resultBytes = null;
      }
    });
  }

  void _showGarmentPicker() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: FansivibeColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      'Select Digital Wardrobe Garment',
                      style: FansivibeTypography.titleLargeWithFamily,
                    ),
                    IconButton(
                      icon: const Icon(Icons.close_rounded),
                      onPressed: () => Navigator.of(ctx).pop(),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                if (_isLoadingWardrobe) ...[
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 24),
                    child: Center(
                      child: CircularProgressIndicator(),
                    ),
                  ),
                ] else if (_wardrobeItems.isEmpty) ...[
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 24),
                    child: Center(
                      child: Text('No garments found in your Digital Wardrobe.'),
                    ),
                  ),
                ] else ...[
                  Flexible(
                    child: ListView.separated(
                      shrinkWrap: true,
                      itemCount: _wardrobeItems.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (context, index) {
                        final item = _wardrobeItems[index];
                        final isChosen = item.id == _selectedGarmentId;
                        return ListTile(
                          contentPadding: const EdgeInsets.symmetric(vertical: 4),
                          leading: SizedBox(
                            width: 44,
                            height: 44,
                            child: ClipRRect(
                              borderRadius: FansivibeRadius.smBorder,
                              child: item.imageUrl != null
                                  ? Image.network(
                                      item.imageUrl!,
                                      fit: BoxFit.cover,
                                      errorBuilder: (_, __, ___) =>
                                          const FansiImageWell(
                                            icon: Icons.checkroom_rounded,
                                            color: FansivibeColors.primary,
                                          ),
                                    )
                                  : const FansiImageWell(
                                      icon: Icons.checkroom_rounded,
                                      color: FansivibeColors.primary,
                                    ),
                            ),
                          ),
                          title: Text(
                            item.name,
                            style: FansivibeTypography.bodyLargeWithFamily.copyWith(
                              fontWeight: isChosen ? FontWeight.w700 : FontWeight.w500,
                            ),
                          ),
                          subtitle: Text(
                            '${item.category} • ${item.color}',
                            style: FansivibeTypography.labelMediumWithFamily.copyWith(
                              color: FansivibeColors.textSecondary,
                            ),
                          ),
                          trailing: isChosen
                              ? const Icon(Icons.check_circle_rounded, color: FansivibeColors.primary)
                              : null,
                          onTap: () {
                            _onSelectGarment(item);
                            Navigator.of(ctx).pop();
                          },
                        );
                      },
                    ),
                  ),
                ],
              ],
            ),
          ),
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
    if (!_consent) {
      _showSnackBar('Please accept the test-preview consent first.');
      return;
    }
    final bytes = _personBytes;
    if (bytes == null || bytes.isEmpty) {
      _showSnackBar('Attach a person photo to preview.');
      return;
    }
    final chosenId = _selectedGarmentId ?? (widget.garmentIds.isNotEmpty ? widget.garmentIds.first : null);
    if (chosenId == null || chosenId.isEmpty) {
      _showSnackBar('Select a garment from your Digital Wardrobe.');
      return;
    }

    if (_phase == _Phase.submitting || _phase == _Phase.polling) return;
    if (_activeJobId != null && _phase == _Phase.timedOut) {
      await _onResumePolling();
      return;
    }

    final key = _pendingIdempotencyKey ??= newTryOnIdempotencyKey();
    await _submitWithKey(
      bytes: bytes,
      chosenId: chosenId,
      idempotencyKey: key,
    );
  }

  Future<void> _submitWithKey({
    required Uint8List bytes,
    required String chosenId,
    required String idempotencyKey,
  }) async {
    setState(() {
      _phase = _Phase.submitting;
      _failure = null;
      _failureDetail = null;
    });

    final garmentList = [chosenId];
    final result = await _repository.submitMockTryOn(
      personBytes: bytes,
      personFilename: _personFilename,
      outfitSource: widget.outfitSource,
      garmentIds: garmentList,
      consentAccepted: true,
      idempotencyKey: idempotencyKey,
    );

    if (!mounted) return;
    final job = result.job;
    if (job == null) {
      setState(() {
        _phase = _Phase.failed;
        _failure = result.failure ?? TryOnFailure.networkError;
      });
      return;
    }

    setState(() {
      _phase = _Phase.polling;
      _activeJobId = job.jobId;
      _lastJobState = job.state;
      _backendProgress = job.state == TryOnJobState.completed ? 100 : 0;
      _isMock = job.isMock;
      _pollCount = 0;
      _pollingStartedAt = _currentTime();
    });

    await _pollUntilDone(job.jobId);
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
      final status = await _repository.getJobStatus(jobId);
      if (!mounted || token != _pollSessionToken || _phase != _Phase.polling) {
        return true;
      }
      if (status == null) {
        setState(() {
          _pollCount++;
        });
        return false;
      }

      setState(() {
        _pollCount++;
        _isMock = status.isMock;
        _lastJobState = status.state;
        _backendProgress = status.progress;
      });

      if (status.state == TryOnJobState.completed) {
        final img = await _repository.getJobImage(jobId);
        if (!mounted || token != _pollSessionToken) return true;
        setState(() {
          _phase = _Phase.done;
          _resultBytes = img;
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

    while (mounted && token == _pollSessionToken && _phase == _Phase.polling) {
      await Future<void>.delayed(widget.pollInterval);
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
      if (elapsed >= widget.maxPollDuration) {
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
      _pollingStartedAt = _currentTime();
    });
    await _pollUntilDone(jid);
  }

  Future<void> _onCancel() async {
    final jid = _activeJobId;
    if (jid == null) return;
    _pollSessionToken++;
    final res = await _repository.cancelJob(jid);
    if (!mounted) return;
    if (res != null) {
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
    }
  }

  Future<void> _onRetrySubmit() async {
    final jid = _activeJobId;
    if (jid == null) {
      final bytes = _personBytes;
      final chosenId =
          _selectedGarmentId ??
          (widget.garmentIds.isNotEmpty ? widget.garmentIds.first : null);
      final pendingKey = _pendingIdempotencyKey;
      if (bytes != null &&
          bytes.isNotEmpty &&
          chosenId != null &&
          chosenId.isNotEmpty &&
          pendingKey != null) {
        await _submitWithKey(
          bytes: bytes,
          chosenId: chosenId,
          idempotencyKey: pendingKey,
        );
        return;
      }
      _onRetry();
      return;
    }
    setState(() {
      _phase = _Phase.submitting;
      _failure = null;
      _failureDetail = null;
    });
    final res = await _repository.retryJob(jid);
    if (!mounted) return;
    final job = res.job;
    if (job == null) {
      setState(() {
        _phase = _Phase.failed;
        _failure = res.failure ?? TryOnFailure.networkError;
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
      _pollingStartedAt = _currentTime();
    });
    await _pollUntilDone(job.jobId);
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
      _showSnackBar('Try-on result and media deleted.');
      _onRetry();
    } else {
      _showSnackBar('Could not delete result. Please try again.');
    }
  }

  void _onRetry() {
    _pollSessionToken++;
    setState(() {
      _phase = _Phase.input;
      _failure = null;
      _failureDetail = null;
      _pollCount = 0;
      _resultBytes = null;
      _activeJobId = null;
      _pendingIdempotencyKey = null;
      _lastJobState = null;
      _backendProgress = null;
      _pollingStartedAt = null;
    });
  }

  String _failureMessage(TryOnFailure? failure) {
    if (_failureDetail != null && _failureDetail!.isNotEmpty) {
      return _failureDetail!;
    }
    switch (failure) {
      case TryOnFailure.unauthorized:
        return 'Please sign in again to preview try-ons.';
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
    return Scaffold(
      backgroundColor: FansivibeColors.surface,
      appBar: AppBar(title: const Text('Virtual Try-On')),
      body: SafeArea(
        child: SingleChildScrollView(
          physics: const BouncingScrollPhysics(),
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildProviderBanner(),
              const SizedBox(height: 16),
              Text(
                widget.title,
                style: FansivibeTypography.headlineMediumWithFamily.copyWith(
                  fontWeight: FontWeight.w500,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                '${widget.garmentIds.length} piece(s) • ${widget.outfitSource}',
                style: FansivibeTypography.labelMediumWithFamily.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
              ),
              if (widget.garmentIds.isEmpty && _selectedGarmentId == null) ...[
                const SizedBox(height: 16),
                const Text('No outfit selected. Go back and pick a look.'),
              ] else ...[
                const SizedBox(height: 16),
                _buildBody(),
              ],
            ],
          ),
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
        border: Border.all(color: FansivibeColors.primary.withValues(alpha: 0.5)),
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.auto_awesome_rounded, size: 16, color: FansivibeColors.primary),
              const SizedBox(width: 6),
              Text(
                'AI Try-On Result',
                style: FansivibeTypography.labelMediumWithFamily.copyWith(
                  color: FansivibeColors.primary,
                  fontWeight: FontWeight.w700,
                ),
              ),
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
        final elapsedSeconds = _pollingStartedAt != null
            ? _currentTime().difference(_pollingStartedAt!).inSeconds.clamp(0, widget.maxPollDuration.inSeconds)
            : 0;
        final totalSeconds = widget.maxPollDuration.inSeconds;
        final progressValue = (_backendProgress != null && _backendProgress! > 0)
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
          children: [
            LinearProgressIndicator(
              value: progressValue,
              backgroundColor: FansivibeColors.surfaceContainer,
              color: FansivibeColors.primary,
            ),
            SizedBox(height: FansivibeSpacing.md),
            Text(
              statusLabel,
              style: FansivibeTypography.bodyMediumWithFamily,
            ),
            const SizedBox(height: 16),
            FansiButton.secondary(
              label: 'Cancel Request',
              icon: Icons.cancel_outlined,
              onPressed: _onCancel,
            ),
          ],
        );
      case _Phase.timedOut:
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
                  const Icon(
                    Icons.hourglass_top_rounded,
                    color: FansivibeColors.warning,
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Still processing',
                          style: FansivibeTypography.titleLargeWithFamily.copyWith(
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Your try-on is taking longer than expected, but it has not failed. '
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
            _buildInput(enabled: true),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: FansivibeColors.error.withValues(alpha: 0.1),
                borderRadius: FansivibeRadius.smdBorder,
                border: Border.all(color: FansivibeColors.error.withValues(alpha: 0.3)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.error_outline_rounded, color: FansivibeColors.error),
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
            Row(
              children: [
                Expanded(
                  child: FansiButton.secondary(
                    label: 'Try Again',
                    icon: Icons.refresh_rounded,
                    onPressed: _onRetrySubmit,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FansiButton.secondary(
                    label: 'Change Inputs',
                    icon: Icons.edit_outlined,
                    onPressed: _onRetry,
                  ),
                ),
              ],
            ),
          ],
        );
      case _Phase.input:
        return _buildInput(enabled: true);
    }
  }

  Widget _buildGarmentSection(bool enabled) {
    final garment = _selectedGarment;
    final garmentId = _selectedGarmentId ?? (widget.garmentIds.isNotEmpty ? widget.garmentIds.first : null);

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
              Text(
                'Selected Garment',
                style: FansivibeTypography.titleLargeWithFamily.copyWith(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
              ),
              if (enabled)
                TextButton.icon(
                  icon: const Icon(Icons.swap_horiz_rounded, size: 18),
                  label: const Text('Change'),
                  onPressed: _showGarmentPicker,
                ),
            ],
          ),
          const SizedBox(height: 8),
          if (garment != null) ...[
            Row(
              children: [
                SizedBox(
                  width: 60,
                  height: 60,
                  child: ClipRRect(
                    borderRadius: FansivibeRadius.smBorder,
                    child: garment.imageUrl != null
                        ? Image.network(
                            garment.imageUrl!,
                            fit: BoxFit.cover,
                            errorBuilder: (_, __, ___) =>
                                const FansiImageWell(
                                  icon: Icons.checkroom_rounded,
                                  color: FansivibeColors.primary,
                                ),
                          )
                        : const FansiImageWell(
                            icon: Icons.checkroom_rounded,
                            color: FansivibeColors.primary,
                          ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
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
                        style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                          color: FansivibeColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ] else if (garmentId != null) ...[
            Row(
              children: [
                const SizedBox(
                  width: 50,
                  height: 50,
                  child: FansiImageWell(
                    icon: Icons.checkroom_rounded,
                    color: FansivibeColors.primary,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    garmentId,
                    style: FansivibeTypography.bodyLargeWithFamily,
                  ),
                ),
              ],
            ),
          ] else ...[
            FansiButton.secondary(
              label: 'Select from Digital Wardrobe',
              icon: Icons.add_circle_outline_rounded,
              onPressed: enabled ? _showGarmentPicker : null,
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildInput({required bool enabled}) {
    final bytes = _personBytes;
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
        if (bytes != null && bytes.isNotEmpty)
          Container(
            height: 200,
            width: double.infinity,
            margin: EdgeInsets.only(bottom: FansivibeSpacing.md),
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
        Row(
          children: [
            Expanded(
              child: FansiButton.secondary(
                label: 'Choose Photo',
                icon: Icons.photo_library_outlined,
                onPressed: enabled
                    ? () => _onAttachPhoto(ImageSource.gallery)
                    : null,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: FansiButton.secondary(
                label: 'Take Photo',
                icon: Icons.camera_alt_outlined,
                onPressed: enabled
                    ? () => _onAttachPhoto(ImageSource.camera)
                    : null,
              ),
            ),
          ],
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
          label: 'Preview Try-On (Test Data)',
          icon: Icons.visibility_outlined,
          onPressed: enabled ? _onSubmit : null,
        ),
      ],
    );
  }

  Widget _buildDone() {
    final resultBytes = _resultBytes;
    final garmentId = _selectedGarmentId ?? (widget.garmentIds.isNotEmpty ? widget.garmentIds.first : '');

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (resultBytes != null && resultBytes.isNotEmpty) ...[
          Container(
            height: 360,
            width: double.infinity,
            decoration: BoxDecoration(
              borderRadius: FansivibeRadius.smdBorder,
              border: Border.all(color: FansivibeColors.outlineVariant),
            ),
            child: ClipRRect(
              borderRadius: FansivibeRadius.smdBorder,
              child: Image.memory(
                resultBytes,
                fit: BoxFit.contain,
                errorBuilder: (_, __, ___) => const FansiImageWell(
                  icon: Icons.checkroom_rounded,
                  color: FansivibeColors.primary,
                ),
              ),
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
        if (garmentId.isNotEmpty) ...[
          SizedBox(height: FansivibeSpacing.sm),
          Chip(
            label: Text(
              _selectedGarment != null ? _selectedGarment!.name : garmentId,
            ),
          ),
        ],
        SizedBox(height: FansivibeSpacing.lg),
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
        FansiButton.secondary(
          label: 'Back to Outfit',
          icon: Icons.arrow_back_rounded,
          onPressed: () => context.pop(),
        ),
      ],
    );
  }
}
