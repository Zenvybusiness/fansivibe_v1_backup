import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import 'package:fansivibe/features/try_on/data/try_on_models.dart';
import 'package:fansivibe/features/try_on/data/try_on_repository.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/components/fansi_image_well.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

/// Stage F0 mock try-on screen (test data only, $0).
///
/// One shared flow for both product paths: the caller passes
/// [outfitSource] (`today`/`outfit`/`saved`/`wardrobe`) plus the outfit
/// [garmentIds] as labels — never as pixels, since the backend cannot
/// retrieve wardrobe image bytes (audit finding). The user attaches a
/// fresh person photo here; onboarding selfies are never reused (not
/// retained by design).
///
/// Every result view carries the TEST DATA banner: the mock composite
/// is UI scaffolding, never genuine AI output, and this screen offers
/// no save/share/export path (mock outputs must not enter real flows).
class TryOnScreen extends StatefulWidget {
  const TryOnScreen({
    required this.outfitSource,
    required this.garmentIds,
    required this.title,
    this.tryOnRepository,
    this.pickImage,
    super.key,
  });

  final String outfitSource;
  final List<String> garmentIds;
  final String title;

  /// Backend source. Defaults to the live repository; tests inject a fake.
  final TryOnRepository? tryOnRepository;

  /// Photo picker seam (gallery/camera). Defaults to [ImagePicker].
  final Future<XFile?> Function(ImageSource source)? pickImage;

  @override
  State<TryOnScreen> createState() => _TryOnScreenState();
}

enum _Phase { input, submitting, polling, done, failed }

class _TryOnScreenState extends State<TryOnScreen> {
  late final TryOnRepository _repository;

  bool _consent = false;
  Uint8List? _personBytes;
  String _personFilename = 'tryon_person.jpg';

  _Phase _phase = _Phase.input;
  TryOnFailure? _failure;
  int _pollCount = 0;

  static const int _maxPolls = 20;
  static const Duration _pollInterval = Duration(seconds: 1);

  @override
  void initState() {
    super.initState();
    _repository = widget.tryOnRepository ?? TryOnRepositoryImpl();
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
      if (_phase == _Phase.failed || _phase == _Phase.done) {
        _phase = _Phase.input;
        _failure = null;
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
    if (_phase == _Phase.submitting || _phase == _Phase.polling) return;
    final key = newTryOnIdempotencyKey();
    setState(() {
      _phase = _Phase.submitting;
      _failure = null;
    });
    final result = await _repository.submitMockTryOn(
      personBytes: bytes,
      personFilename: _personFilename,
      outfitSource: widget.outfitSource,
      garmentIds: widget.garmentIds,
      consentAccepted: true,
      idempotencyKey: key,
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
      _pollCount = 0;
    });
    await _pollUntilDone(job.jobId);
  }

  Future<void> _pollUntilDone(String jobId) async {
    for (var i = 0; i < _maxPolls; i++) {
      await Future<void>.delayed(_pollInterval);
      if (!mounted) return;
      final status = await _repository.getJobStatus(jobId);
      if (!mounted) return;
      if (status == null) continue;
      setState(() => _pollCount = i + 1);
      if (status.state == TryOnJobState.completed) {
        setState(() => _phase = _Phase.done);
        return;
      }
      if (status.state == TryOnJobState.failed) {
        setState(() {
          _phase = _Phase.failed;
          _failure = TryOnFailure.unknown;
        });
        return;
      }
    }
    if (!mounted) return;
    setState(() {
      _phase = _Phase.failed;
      _failure = TryOnFailure.networkError;
    });
  }

  void _onRetry() {
    setState(() {
      _phase = _Phase.input;
      _failure = null;
      _pollCount = 0;
    });
  }

  String _failureMessage(TryOnFailure? failure) {
    switch (failure) {
      case TryOnFailure.unauthorized:
        return 'Please sign in again to preview try-ons.';
      case TryOnFailure.invalidInput:
        return 'That preview request was invalid. Check the photo and try again.';
      case TryOnFailure.quotaExceeded:
      case TryOnFailure.rateLimited:
        return 'Daily preview limit reached. Please try again tomorrow.';
      case TryOnFailure.serviceUnavailable:
        return 'Mock try-on previews are turned off right now.';
      case TryOnFailure.networkError:
        return 'Please check your connection and try again.';
      default:
        return 'Something went wrong. Please try again.';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: FansivibeColors.surface,
      appBar: AppBar(title: const Text('Try-On Preview')),
      body: SafeArea(
        child: SingleChildScrollView(
          physics: const BouncingScrollPhysics(),
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildTestDataBanner(),
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
              if (widget.garmentIds.isEmpty) ...[
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

  /// Permanent TEST DATA banner — every phase of this screen is labelled.
  Widget _buildTestDataBanner() {
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
          color: FansivibeColors.textPrimary,
          fontWeight: FontWeight.w700,
          letterSpacing: 1.0,
        ),
      ),
    );
  }

  Widget _buildBody() {
    switch (_phase) {
      case _Phase.submitting:
        return const Center(
          child: Padding(
            padding: EdgeInsets.symmetric(vertical: 32),
            child: CircularProgressIndicator(),
          ),
        );
      case _Phase.polling:
        return Column(
          children: [
            LinearProgressIndicator(
              value: _pollCount > 0 ? _pollCount / _maxPolls : null,
            ),
            SizedBox(height: FansivibeSpacing.md),
            Text('Rendering test preview… (poll ${_pollCount + 1})'),
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
            Text(_failureMessage(_failure)),
            const SizedBox(height: 12),
            FansiButton.secondary(
              label: 'Try Again',
              icon: Icons.refresh_rounded,
              onPressed: _onRetry,
            ),
          ],
        );
      case _Phase.input:
        return _buildInput(enabled: true);
    }
  }

  Widget _buildInput({required bool enabled}) {
    final bytes = _personBytes;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (bytes != null && bytes.isNotEmpty)
          Container(
            height: 180,
            width: double.infinity,
            margin: EdgeInsets.only(bottom: FansivibeSpacing.md),
            child: ClipRRect(
              borderRadius: FansivibeRadius.smdBorder,
              // Widget-test env never delivers image frames and user
              // bytes may be corrupt: fall back to the well (wardrobe
              // photo precedent) instead of a decode error.
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
                  'I agree to process this photo for a test-only mock '
                  'preview. Photos are hashed and discarded on the server '
                  'and never sent to an AI provider in Stage F0.',
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

  /// Mock result: labelled placeholder + garment labels. Deliberately no
  /// save/share/export actions — mock outputs stay out of real flows.
  Widget _buildDone() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const FansiImageWell(
          icon: Icons.checkroom_rounded,
          color: FansivibeColors.accentGold,
        ),
        SizedBox(height: FansivibeSpacing.md),
        const Text(
          'Mock preview ready. This is UI test data — not an AI-generated '
          'try-on, and it cannot be saved or shared as one.',
        ),
        SizedBox(height: FansivibeSpacing.sm),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final id in widget.garmentIds) Chip(label: Text(id)),
          ],
        ),
        SizedBox(height: FansivibeSpacing.md),
        FansiButton.secondary(
          label: 'Preview Again',
          icon: Icons.refresh_rounded,
          onPressed: _onRetry,
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
