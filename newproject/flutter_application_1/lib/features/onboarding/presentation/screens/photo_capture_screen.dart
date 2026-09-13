import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

/// Onboarding photo capture (Phase 22, Step 3).
///
/// Real camera/gallery flow — no simulated capture:
///
/// UI → [ImagePicker] (camera or gallery) → bytes → preview → validation
/// → Continue to onboarding analysis preview.
///
/// The image is held in memory only (never persisted, never logged).
/// An empty/cancelled pick stays on this screen with a truthful message;
/// it never fabricates a capture. Backend analysis happens post-auth in
/// the real scan flows — the onboarding preview that follows is labeled
/// as a sample (see [YourAnalysisScreen]).
class PhotoCaptureScreen extends StatefulWidget {
  final String? source;

  /// Injectable picker for tests (defaults to [ImagePicker]).
  final Future<XFile?> Function(ImageSource source)? pickImage;

  const PhotoCaptureScreen({this.source, this.pickImage, super.key});

  @override
  State<PhotoCaptureScreen> createState() => _PhotoCaptureScreenState();
}

class _PhotoCaptureScreenState extends State<PhotoCaptureScreen> {
  static const int _maxBytes = 20 * 1024 * 1024;

  Uint8List? _imageBytes;
  String? _errorMessage;
  bool _isPicking = false;
  bool _autoAttempted = false;

  Future<XFile?> _defaultPick(ImageSource source) {
    return ImagePicker().pickImage(
      source: source,
      maxWidth: 1024,
      maxHeight: 1024,
    );
  }

  @override
  void initState() {
    super.initState();
    // Honor the incoming source once (camera-permission screen passes
    // 'camera' or 'gallery'): attempt the real OS picker instead of
    // showing a fake viewfinder.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_autoAttempted || !mounted) return;
      _autoAttempted = true;
      final source = widget.source;
      if (source == 'camera') {
        _pick(ImageSource.camera);
      } else if (source == 'gallery') {
        _pick(ImageSource.gallery);
      }
    });
  }

  Future<void> _pick(ImageSource source) async {
    if (_isPicking) return;
    setState(() {
      _isPicking = true;
      _errorMessage = null;
    });
    try {
      final picker = widget.pickImage ?? _defaultPick;
      final picked = await picker(source);
      if (!mounted) return;
      if (picked == null) {
        // User cancelled the OS picker — truthful empty state, no fake.
        setState(() {
          _isPicking = false;
          _errorMessage = 'No photo selected. Take a photo or choose one from your gallery.';
        });
        return;
      }
      final bytes = await picked.readAsBytes();
      if (!mounted) return;
      if (bytes.isEmpty) {
        setState(() {
          _isPicking = false;
          _errorMessage = 'Could not read that photo. Please try another.';
        });
        return;
      }
      if (bytes.lengthInBytes > _maxBytes) {
        setState(() {
          _isPicking = false;
          _errorMessage = 'That photo is too large (max 20 MB). Please choose a smaller one.';
        });
        return;
      }
      setState(() {
        _isPicking = false;
        _imageBytes = bytes;
        _errorMessage = null;
      });
    } catch (e) {
      if (!mounted) return;
      final message = e.toString().toLowerCase();
      final denied = message.contains('denied') || message.contains('permission');
      setState(() {
        _isPicking = false;
        _errorMessage = denied
            ? 'Photo access was denied. Enable camera/photos permission in system settings, then try again.'
            : 'Could not load that photo. Please try another. ($e)';
      });
    }
  }

  void _onRetake() {
    setState(() {
      _imageBytes = null;
      _errorMessage = null;
    });
  }

  void _onContinue() {
    if (_imageBytes == null) return;
    context.pushNamed(RouteNames.aiAnalysis);
  }

  void _onSkip() {
    context.goNamed(RouteNames.home, extra: {'vibe': null});
  }

  @override
  Widget build(BuildContext context) {
    final hasPhoto = _imageBytes != null && _imageBytes!.isNotEmpty;

    return Scaffold(
      backgroundColor: FansivibeColors.surface,
      appBar: AppBar(
        title: const Text('Add Your Photo'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded),
          onPressed: () => Navigator.of(context).pop(),
        ),
        actions: [
          TextButton(
            onPressed: _onSkip,
            child: Text(
              'Skip',
              style: TextStyle(
                color: FansivibeColors.secondary.withValues(alpha: 0.7),
                fontSize: 14,
              ),
            ),
          ),
        ],
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          physics: const BouncingScrollPhysics(),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const SizedBox(height: 8),
                _buildPreview(hasPhoto),
                const SizedBox(height: 20),
                if (_errorMessage != null) _buildError(),
                if (_isPicking)
                  const Center(
                    child: Padding(
                      padding: EdgeInsets.symmetric(vertical: 12),
                      child: CircularProgressIndicator(),
                    ),
                  ),
                const SizedBox(height: 8),
                if (!hasPhoto) ...[
                  FansiButton.primary(
                    label: 'Take Photo',
                    icon: Icons.camera_alt_rounded,
                    onPressed: _isPicking ? null : () => _pick(ImageSource.camera),
                  ),
                  const SizedBox(height: 12),
                  FansiButton.secondary(
                    label: 'Choose from Gallery',
                    icon: Icons.photo_library_outlined,
                    onPressed: _isPicking ? null : () => _pick(ImageSource.gallery),
                  ),
                ] else ...[
                  FansiButton.primary(
                    label: 'Continue',
                    icon: Icons.arrow_forward_rounded,
                    onPressed: _onContinue,
                  ),
                  const SizedBox(height: 12),
                  FansiButton.secondary(
                    label: 'Retake Photo',
                    icon: Icons.refresh_rounded,
                    onPressed: _onRetake,
                  ),
                ],
                const SizedBox(height: 32),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildPreview(bool hasPhoto) {
    if (hasPhoto) {
      return ClipRRect(
        borderRadius: FansivibeRadius.baseBorder,
        child: AspectRatio(
          aspectRatio: 3 / 4,
          child: Image.memory(
            _imageBytes!,
            fit: BoxFit.cover,
            gaplessPlayback: true,
          ),
        ),
      );
    }
    return Container(
      height: 360,
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.baseBorder,
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.15),
        ),
      ),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.image_outlined,
              size: 80,
              color: FansivibeColors.surfaceContainerHighest,
            ),
            const SizedBox(height: 12),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Text(
                'Take a photo or choose one from your gallery to continue.',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: FansivibeColors.textSecondary,
                    ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildError() {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: FansivibeColors.error.withValues(alpha: 0.1),
        borderRadius: FansivibeRadius.smdBorder,
        border: Border.all(
          color: FansivibeColors.error.withValues(alpha: 0.3),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
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
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: FansivibeColors.error,
                  ),
            ),
          ),
        ],
      ),
    );
  }
}
