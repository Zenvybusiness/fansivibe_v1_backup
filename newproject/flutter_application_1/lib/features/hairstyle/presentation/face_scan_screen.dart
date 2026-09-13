import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/hairstyle/presentation/widgets/hairstyle_widgets.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/analytics/analytics_service.dart';

/// Face scan entry screen: obtain a real photo (camera or gallery) with
/// explicit per-scan consent, or skip honestly.
///
/// The selected image is held in memory only until the processing screen
/// uploads it — never written to [LearningService], never logged. Skip
/// performs no backend call, creates no [FaceProfile], and assigns no
/// default face shape; it continues through the existing processing flow,
/// which resolves to the offline path without stored appearance state.
class FaceScanScreen extends StatefulWidget {
  const FaceScanScreen({
    super.key,
    this.pickImage = _defaultPickImage,
    this.analytics,
  });

  /// Injectable image picker (defaults to [ImagePicker]); tests supply a
  /// fake so no platform channel is needed.
  final Future<XFile?> Function(ImageSource source) pickImage;

  /// Injectable analytics; defaults to the shared instance.
  final AnalyticsService? analytics;

  static Future<XFile?> _defaultPickImage(ImageSource source) {
    // Lightweight UX sizing only; the backend validates media
    // authoritatively (JPEG/PNG/WebP, 20 MB max, content checks).
    return ImagePicker().pickImage(
      source: source,
      maxWidth: 1024,
      maxHeight: 1024,
    );
  }

  @override
  State<FaceScanScreen> createState() => _FaceScanScreenState();
}

class _FaceScanScreenState extends State<FaceScanScreen> {
  Uint8List? _imageBytes;
  String? _imageName;
  ImageSource? _pickedSource;
  bool _consent = false;

  bool get _canAnalyze => _imageBytes != null && _imageBytes!.isNotEmpty && _consent;

  Future<void> _selectImage(ImageSource source) async {
    try {
      final picked = await widget.pickImage(source);
      if (picked == null || !mounted) return;
      final bytes = await picked.readAsBytes();
      if (!mounted || bytes.isEmpty) return;
      setState(() {
        // In-memory only: preview bytes, never persisted or logged.
        _imageBytes = bytes;
        _imageName = picked.name.isNotEmpty ? picked.name : 'face_scan.jpg';
        _pickedSource = source;
      });
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Could not load that photo. Please try another.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  void _analyze() {
    if (!_canAnalyze) return;
    (widget.analytics ?? _analytics).emitAppearanceScanStarted(
      cameraSource: _pickedSource == ImageSource.gallery ? 'gallery' : 'camera',
      imageQuality: null,
    );
    context.pushNamed(
      RouteNames.hairstyleProcessing,
      extra: <String, dynamic>{
        'imageBytes': _imageBytes,
        'imageFilename': _imageName,
      },
    );
  }

  void _skip() {
    // First-class skip: no backend call, no FaceProfile, no default shape.
    context.pushNamed(RouteNames.hairstyleProcessing);
  }

  static final AnalyticsService _analytics = AnalyticsService.instance;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Face Scan'),
        leading: IconButton(
          icon: Icon(
            Icons.arrow_back_rounded,
            color: FansivibeColors.textPrimary,
          ),
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

                        if (_imageBytes != null)
                          _buildPreview()
                        else
                          const FacePreviewPlaceholder(),

                        const SizedBox(height: 20),

                        _buildCheckRow(),
                        const SizedBox(height: 16),

                        _buildSourceButtons(),
                        const SizedBox(height: 16),

                        _buildConsent(),
                        const SizedBox(height: 16),

                        _buildAnalyzeButton(),
                        const SizedBox(height: 12),

                        _buildSkipButton(),
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

  Widget _buildPreview() {
    return ClipRRect(
      borderRadius: FansivibeRadius.baseBorder,
      child: AspectRatio(
        aspectRatio: 4 / 3,
        child: Image.memory(
          _imageBytes!,
          fit: BoxFit.cover,
          gaplessPlayback: true,
        ),
      ),
    );
  }

  Widget _buildSourceButtons() {
    return Row(
      children: [
        Expanded(
          child: FansiButton.secondary(
            label: 'Take Photo',
            icon: Icons.camera_alt_rounded,
            expanded: false,
            onPressed: () => _selectImage(ImageSource.camera),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: FansiButton.secondary(
            label: 'Gallery',
            icon: Icons.photo_library_rounded,
            expanded: false,
            onPressed: () => _selectImage(ImageSource.gallery),
          ),
        ),
      ],
    );
  }

  Widget _buildConsent() {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.baseBorder,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Checkbox(
            value: _consent,
            onChanged: (value) => setState(() => _consent = value ?? false),
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(top: 10),
              child: Text(
                'I consent to this photo being used for appearance analysis. '
                'The image is processed to estimate appearance attributes and '
                'is not stored permanently. Results are estimates and may be '
                'inaccurate.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: FansivibeColors.textSecondary,
                  height: 1.5,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAnalyzeButton() {
    return FansiButton.primary(
      label: 'Analyze Photo',
      icon: Icons.face_retouching_natural,
      onPressed: _canAnalyze ? _analyze : null,
    );
  }

  Widget _buildSkipButton() {
    return FansiButton.tertiary(
      label: 'Skip for now',
      onPressed: _skip,
    );
  }

  Widget _buildCheckRow() {
    final checks = FaceScanCheck.mockChecks;
    final failingMessage = checks
        .where((c) => !c.isPassing)
        .firstOrNull
        ?.message;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.baseBorder,
      ),
      child: Column(
        children: [
          Row(
            children: checks
                .map(
                  (check) => Expanded(
                    child: HairstyleCheckIndicator(
                      label: check.label,
                      isPassing: check.isPassing,
                    ),
                  ),
                )
                .toList(),
          ),
          if (failingMessage != null) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                Icon(
                  Icons.info_outline_rounded,
                  size: 14,
                  color: FansivibeColors.accentGold.withValues(alpha: 0.7),
                ),
                const SizedBox(width: 6),
                Flexible(
                  child: Text(
                    failingMessage,
                    style: TextStyle(
                      color: FansivibeColors.accentGold.withValues(alpha: 0.7),
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
