import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/hairstyle/presentation/widgets/hairstyle_widgets.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/analytics/analytics_service.dart';

/// Guided capture angle. The arrows are positioning guidance only — the
/// app does not measure head angles; the user confirms each view manually.
enum FaceScanAngle { front, left, right }

/// One confirmed angle capture held in memory (never persisted, never logged).
class AngleCapture {
  const AngleCapture({required this.bytes, required this.name});

  final Uint8List bytes;
  final String name;
}

/// Face scan entry screen: camera-first guided capture (FRONT → LEFT →
/// RIGHT) with explicit per-scan consent, or gallery per angle, or skip.
///
/// Each angle is captured, previewed, and confirmed by the user before
/// advancing; retake is always available. The three captures travel to
/// the processing screen as in-memory bytes for real multi-angle backend
/// analysis — no angle is silently discarded. Skip performs no backend
/// call, creates no FaceProfile, and assigns no default face shape.
class FaceScanScreen extends StatefulWidget {
  const FaceScanScreen({
    super.key,
    this.pickImage = _defaultPickImage,
    this.analytics,
  });

  /// Injectable gallery picker (defaults to [ImagePicker]); tests supply
  /// a fake so no platform channel is needed. Camera capture uses the
  /// shared `camera` plugin path (same as the outfit scan flow).
  final Future<XFile?> Function(ImageSource source) pickImage;

  /// Injectable analytics; defaults to the shared instance.
  final AnalyticsService? analytics;

  static Future<XFile?> _defaultPickImage(ImageSource source) {
    // Gallery-only: camera capture goes through the live preview below.
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

enum _CameraUiState { initial, loading, ready, permissionDenied, unavailable, error }

class _FaceScanScreenState extends State<FaceScanScreen>
    with WidgetsBindingObserver {
  static const List<FaceScanAngle> _angles = FaceScanAngle.values;

  CameraController? _controller;
  _CameraUiState _cameraState = _CameraUiState.initial;
  String? _cameraError;

  int _stepIndex = 0;
  final Map<FaceScanAngle, AngleCapture> _captures = {};
  bool _consent = false;

  bool get _isTestMode {
    final bindingType = WidgetsBinding.instance.runtimeType.toString();
    return bindingType.contains('TestWidgetsFlutterBinding');
  }

  FaceScanAngle get _currentAngle => _angles[_stepIndex];
  AngleCapture? get _currentCapture => _captures[_currentAngle];

  bool get _allCaptured => FaceScanAngle.values.every(_captures.containsKey);
  bool get _canAnalyze =>
      _allCaptured && _consent;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    if (!_isTestMode) {
      SchedulerBinding.instance.addPostFrameCallback((_) async {
        await _initCamera();
      });
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller?.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (_controller == null) return;
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused) {
      _controller?.dispose();
      _controller = null;
      _cameraState = _CameraUiState.initial;
      return;
    }
    if (state == AppLifecycleState.resumed) {
      SchedulerBinding.instance.addPostFrameCallback((_) async {
        await _initCamera();
      });
    }
  }

  Future<void> _initCamera() async {
    if (!mounted) return;
    setState(() {
      _cameraState = _CameraUiState.loading;
      _cameraError = null;
    });
    try {
      // Front camera first for a face scan (unlike the outfit rear default).
      final cameras = await availableCameras();
      if (cameras.isEmpty) {
        if (!mounted) return;
        setState(() => _cameraState = _CameraUiState.unavailable);
        return;
      }
      final frontIndex = cameras.indexWhere(
        (c) => c.lensDirection == CameraLensDirection.front,
      );
      final controller = CameraController(
        cameras[frontIndex >= 0 ? frontIndex : 0],
        ResolutionPreset.medium,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.jpeg,
      );
      _controller = controller;
      await controller.initialize();
      if (!mounted) return;
      setState(() => _cameraState = _CameraUiState.ready);
    } on CameraException catch (e) {
      if (!mounted) return;
      final code = e.code.toLowerCase();
      if (code.contains('denied') ||
          code.contains('accessdenied') ||
          code.contains('permission')) {
        setState(() => _cameraState = _CameraUiState.permissionDenied);
      } else {
        setState(() {
          _cameraState = _CameraUiState.error;
          _cameraError = e.description ?? e.code;
        });
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _cameraState = _CameraUiState.error;
        _cameraError = e.toString();
      });
    }
  }

  /// Camera-first capture for the current angle: live preview →
  /// takePicture → in-memory preview (never gallery, never silent).
  Future<void> _takePhoto() async {
    if (_isTestMode) return;
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) {
      await _initCamera();
      return;
    }
    try {
      final xFile = await controller.takePicture();
      final bytes = await xFile.readAsBytes();
      if (!mounted || bytes.isEmpty) return;
      setState(() {
        _captures[_currentAngle] = AngleCapture(
          bytes: bytes,
          name: xFile.name.isNotEmpty
              ? xFile.name
              : 'face_${_currentAngle.name}.jpg',
        );
      });
    } on CameraException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Could not take a photo (${e.code}). Try again.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Could not take a photo. Please try again.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  /// Explicit gallery alternative for the current angle (kept separate —
  /// Take Photo never falls back to gallery).
  Future<void> _pickFromGallery() async {
    try {
      final picked = await widget.pickImage(ImageSource.gallery);
      if (picked == null || !mounted) return;
      final bytes = await picked.readAsBytes();
      if (!mounted || bytes.isEmpty) return;
      setState(() {
        _captures[_currentAngle] = AngleCapture(
          bytes: bytes,
          name: picked.name.isNotEmpty
              ? picked.name
              : 'face_${_currentAngle.name}.jpg',
        );
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

  void _retake() {
    setState(() {
      _captures.remove(_currentAngle);
    });
  }

  void _confirmStep() {
    if (_currentCapture == null) return;
    if (_stepIndex < _angles.length - 1) {
      setState(() {
        _stepIndex++;
      });
    }
  }

  void _analyze() {
    if (!_canAnalyze) return;
    (widget.analytics ?? _analytics).emitAppearanceScanStarted(
      cameraSource: 'multi-angle',
      imageQuality: null,
    );
    context.pushNamed(
      RouteNames.hairstyleProcessing,
      extra: <String, dynamic>{
        'angleFront': _captures[FaceScanAngle.front]!.bytes,
        'angleFrontName': _captures[FaceScanAngle.front]!.name,
        'angleLeft': _captures[FaceScanAngle.left]!.bytes,
        'angleLeftName': _captures[FaceScanAngle.left]!.name,
        'angleRight': _captures[FaceScanAngle.right]!.bytes,
        'angleRightName': _captures[FaceScanAngle.right]!.name,
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

                        _buildStepHeader(),
                        const SizedBox(height: 16),

                        _buildViewfinder(),
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

  /// Guided stepper: current angle, progress dots, and turn guidance.
  Widget _buildStepHeader() {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            for (var i = 0; i < _angles.length; i++) ...[
              _StepDot(
                label: _angleLabel(_angles[i]),
                state: i < _stepIndex
                    ? _StepState.done
                    : i == _stepIndex
                    ? _StepState.current
                    : _StepState.todo,
              ),
              if (i < _angles.length - 1)
                Expanded(
                  child: Container(
                    height: 1,
                    margin: const EdgeInsets.symmetric(horizontal: 6),
                    color: FansivibeColors.primary.withValues(
                      alpha: i < _stepIndex ? 0.6 : 0.2,
                    ),
                  ),
                ),
            ],
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Icon(
              _angleIcon(_currentAngle),
              size: 20,
              color: FansivibeColors.primary,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                _angleGuidance(_currentAngle),
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.textPrimary,
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  String _angleLabel(FaceScanAngle angle) {
    return switch (angle) {
      FaceScanAngle.front => 'Front',
      FaceScanAngle.left => 'Left',
      FaceScanAngle.right => 'Right',
    };
  }

  IconData _angleIcon(FaceScanAngle angle) {
    return switch (angle) {
      FaceScanAngle.front => Icons.face_rounded,
      FaceScanAngle.left => Icons.arrow_back_rounded,
      FaceScanAngle.right => Icons.arrow_forward_rounded,
    };
  }

  String _angleGuidance(FaceScanAngle angle) {
    return switch (angle) {
      FaceScanAngle.front => 'Front — face the camera straight on',
      // Guidance only: the user confirms each view manually.
      FaceScanAngle.left => 'Turn slowly to your left',
      FaceScanAngle.right => 'Turn slowly to your right',
    };
  }

  /// Live camera preview with an oval positioning guide overlay, the
  /// confirmed capture preview, or an honest camera-state card.
  Widget _buildViewfinder() {
    final capture = _currentCapture;
    if (capture != null) {
      return Column(
        children: [
          ClipRRect(
            borderRadius: FansivibeRadius.baseBorder,
            child: AspectRatio(
              aspectRatio: 4 / 3,
              child: Image.memory(
                capture.bytes,
                fit: BoxFit.cover,
                gaplessPlayback: true,
              ),
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: FansiButton.secondary(
                  label: 'Retake',
                  icon: Icons.refresh_rounded,
                  onPressed: _retake,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FansiButton.primary(
                  label: _stepIndex < _angles.length - 1
                      ? 'Continue'
                      : 'Done',
                  icon: Icons.check_rounded,
                  onPressed: _stepIndex < _angles.length - 1
                      ? _confirmStep
                      : null,
                ),
              ),
            ],
          ),
        ],
      );
    }
    if (_isTestMode) {
      return const FacePreviewPlaceholder();
    }
    return switch (_cameraState) {
      _CameraUiState.ready when _controller != null &&
          _controller!.value.isInitialized =>
        ClipRRect(
          borderRadius: FansivibeRadius.baseBorder,
          child: AspectRatio(
            aspectRatio: 4 / 3,
            child: Stack(
              fit: StackFit.expand,
              children: [
                CameraPreview(_controller!),
                // Positioning guide overlay (decorative alignment aid).
                Center(
                  child: Container(
                    width: 180,
                    height: 230,
                    decoration: BoxDecoration(
                      border: Border.all(
                        color: FansivibeColors.primary.withValues(alpha: 0.7),
                        width: 2,
                      ),
                      borderRadius: BorderRadius.circular(90),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      _CameraUiState.permissionDenied => _cameraCard(
        title: 'Camera permission denied',
        description:
            'Enable camera access in system settings to scan your face, '
            'or choose a photo from the gallery.',
        actionLabel: 'Retry',
        onAction: _initCamera,
      ),
      _CameraUiState.unavailable => _cameraCard(
        title: 'Camera unavailable',
        description:
            'No camera device was detected. Choose a photo from the gallery.',
        actionLabel: 'Retry',
        onAction: _initCamera,
      ),
      _CameraUiState.error => _cameraCard(
        title: 'Camera error',
        description: _cameraError ?? 'Please try again.',
        actionLabel: 'Retry',
        onAction: _initCamera,
      ),
      _ => const SizedBox(
        height: 240,
        child: Center(child: CircularProgressIndicator()),
      ),
    };
  }

  Widget _cameraCard({
    required String title,
    required String description,
    required String actionLabel,
    required VoidCallback onAction,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: FansivibeRadius.baseBorder,
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.15),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.videocam_off_rounded,
            size: 48,
            color: FansivibeColors.accentGold.withValues(alpha: 0.5),
          ),
          const SizedBox(height: 12),
          Text(
            title,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w700,
              color: FansivibeColors.textPrimary,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            description,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: FansivibeColors.textSecondary.withValues(alpha: 0.8),
            ),
          ),
          const SizedBox(height: 16),
          FansiButton.primary(
            label: actionLabel,
            icon: Icons.refresh_rounded,
            onPressed: onAction,
          ),
        ],
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
            // Camera-first: live-preview capture, never gallery.
            onPressed: _takePhoto,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: FansiButton.secondary(
            label: 'Gallery',
            icon: Icons.photo_library_rounded,
            expanded: false,
            onPressed: _pickFromGallery,
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
                'I consent to these photos being used for appearance analysis. '
                'The images are processed to estimate appearance attributes and '
                'are not stored permanently. Results are estimates and may be '
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
      label: _allCaptured
          ? 'Analyze Photos'
          : 'Analyze Photo (${_captures.length}/3)',
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

enum _StepState { done, current, todo }

class _StepDot extends StatelessWidget {
  const _StepDot({required this.label, required this.state});

  final String label;
  final _StepState state;

  @override
  Widget build(BuildContext context) {
    final color = switch (state) {
      _StepState.done => FansivibeColors.success,
      _StepState.current => FansivibeColors.primary,
      _StepState.todo =>
        FansivibeColors.textSecondary.withValues(alpha: 0.4),
    };
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 22,
          height: 22,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: state == _StepState.done
                ? FansivibeColors.success.withValues(alpha: 0.15)
                : Colors.transparent,
            border: Border.all(color: color, width: 1.5),
          ),
          child: Center(
            child: state == _StepState.done
                ? Icon(Icons.check_rounded, size: 13, color: color)
                : Container(
                    width: 7,
                    height: 7,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: color,
                    ),
                  ),
          ),
        ),
        const SizedBox(width: 6),
        Text(
          label,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
            color: color,
            fontWeight: state == _StepState.current
                ? FontWeight.w700
                : FontWeight.w500,
          ),
        ),
      ],
    );
  }
}
