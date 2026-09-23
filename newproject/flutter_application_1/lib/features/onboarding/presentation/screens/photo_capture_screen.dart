import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

/// Onboarding photo capture (Phase 22, Step 3).
///
/// Real camera/gallery flow — no simulated capture:
///
/// Camera path → live [CameraController] preview → takePicture → bytes.
/// Gallery path → [ImagePicker] gallery → bytes. Preview → validation
/// → Continue submits the bytes to the real analysis pipeline.
///
/// The camera path deliberately avoids `ImagePicker` with
/// `ImageSource.camera`: on desktop browsers (Edge/Chrome) the web plugin
/// renders a plain file input for both sources, so "Allow Camera" used to
/// open the gallery. The `camera` plugin drives the real browser camera
/// permission prompt and capture instead.
///
/// The image is held in memory only (never persisted, never logged).
/// An empty/cancelled pick stays on this screen with a truthful message;
/// it never fabricates a capture.
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

  /// Live-camera state (camera path only; the gallery path never touches
  /// the controller). Mirrors the FaceScan/OutfitScan camera pattern.
  CameraController? _cameraController;
  _CameraUiState _cameraState = _CameraUiState.initial;
  String? _cameraError;
  bool _cameraRequested = false;

  bool get _isTestMode {
    final bindingType = WidgetsBinding.instance.runtimeType.toString();
    return bindingType.contains('TestWidgetsFlutterBinding');
  }

  bool get _cameraActive =>
      _cameraRequested && _cameraState == _CameraUiState.ready;

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
    // 'camera' or 'gallery'). Camera opens the real live preview;
    // gallery opens the OS picker. Neither path fakes a capture.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_autoAttempted || !mounted) return;
      _autoAttempted = true;
      final source = widget.source;
      if (source == 'camera') {
        _startCamera();
      } else if (source == 'gallery') {
        _pick(ImageSource.gallery);
      }
    });
  }

  @override
  void dispose() {
    _cameraController?.dispose();
    super.dispose();
  }

  /// Opens the real camera: requests permission through the `camera`
  /// plugin and shows a live preview. Front camera first (style selfie),
  /// matching the face-scan flow.
  Future<void> _startCamera() async {
    if (!mounted) return;
    setState(() {
      _cameraRequested = true;
      _cameraState = _CameraUiState.loading;
      _cameraError = null;
      _errorMessage = null;
    });
    if (_isTestMode) {
      // No platform camera under widget tests — honest unavailable state.
      if (!mounted) return;
      setState(() => _cameraState = _CameraUiState.unavailable);
      return;
    }
    try {
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
      _cameraController = controller;
      await controller.initialize();
      if (!mounted) return;
      SchedulerBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        setState(() => _cameraState = _CameraUiState.ready);
      });
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

  /// Captures a real photo from the live preview into memory.
  Future<void> _capturePhoto() async {
    final controller = _cameraController;
    if (controller == null || !controller.value.isInitialized) {
      await _startCamera();
      return;
    }
    setState(() {
      _isPicking = true;
      _errorMessage = null;
    });
    try {
      final xFile = await controller.takePicture();
      final bytes = await xFile.readAsBytes();
      if (!mounted) return;
      if (bytes.isEmpty || bytes.lengthInBytes > _maxBytes) {
        setState(() {
          _isPicking = false;
          _errorMessage = bytes.isEmpty
              ? 'The camera returned an empty photo. Please try again.'
              : 'That photo is too large (max 20 MB). Please try again.';
        });
        return;
      }
      setState(() {
        _isPicking = false;
        _imageBytes = bytes;
        _errorMessage = null;
      });
    } on CameraException catch (e) {
      if (!mounted) return;
      setState(() {
        _isPicking = false;
        _errorMessage = 'Could not take a photo (${e.code}). Try again.';
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isPicking = false;
        _errorMessage = 'Could not take a photo. Please try again. ($e)';
      });
    }
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
    final bytes = _imageBytes;
    if (bytes == null || bytes.isEmpty) return;
    // Authenticated: the captured bytes travel to the existing scan
    // processing flow (POST /v1/analysis/hairstyle + poll + real result
    // screen). Guest (no session): stay on the public onboarding chain
    // (analysis preview → results → Continue Without Account → Stylist
    // tab) so the journey never bounces to entry. Camera capture above
    // is untouched; only the Continue destination branches.
    if (AuthSession.isAuthenticated) {
      context.pushNamed(
        RouteNames.hairstyleProcessing,
        extra: <String, dynamic>{
          'imageBytes': bytes,
          'imageFilename': 'style_capture.jpg',
          'imageContentType': 'image/jpeg',
        },
      );
      return;
    }
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
                  if (_cameraRequested) ...[
                    FansiButton.primary(
                      label: 'Capture Photo',
                      icon: Icons.camera_alt_rounded,
                      onPressed: _cameraActive && !_isPicking
                          ? () => _capturePhoto()
                          : null,
                    ),
                    const SizedBox(height: 12),
                    FansiButton.secondary(
                      label: 'Choose from Gallery',
                      icon: Icons.photo_library_outlined,
                      onPressed: _isPicking ? null : () => _pick(ImageSource.gallery),
                    ),
                  ] else ...[
                    FansiButton.primary(
                      label: 'Take Photo',
                      icon: Icons.camera_alt_rounded,
                      onPressed: _isPicking ? null : _startCamera,
                    ),
                    const SizedBox(height: 12),
                    FansiButton.secondary(
                      label: 'Choose from Gallery',
                      icon: Icons.photo_library_outlined,
                      onPressed: _isPicking ? null : () => _pick(ImageSource.gallery),
                    ),
                  ],
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
      // Captured confirmation (mobile-style constrained width on desktop).
      return _centerConstrained(
        ClipRRect(
          borderRadius: FansivibeRadius.baseBorder,
          child: AspectRatio(
            aspectRatio: 3 / 4,
            child: Image.memory(
              _imageBytes!,
              fit: BoxFit.cover,
              gaplessPlayback: true,
            ),
          ),
        ),
      );
    }
    // Camera path: live preview with honest permission/device states.
    // The gallery path never reaches this branch with _cameraRequested.
    if (_cameraRequested) {
      return _centerConstrained(_buildCameraView());
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

  /// Constrains the capture visuals to a mobile-style column on wide
  /// screens (desktop Edge) instead of stretching full-bleed. Phones
  /// (narrow viewports) render unchanged.
  Widget _centerConstrained(Widget child) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 400),
        child: child,
      ),
    );
  }

  /// Live camera viewfinder with honest device/permission states.
  ///
  /// The oval is a static framing aid (same as the face-scan flow): the
  /// app performs no on-device face detection, so the guide never turns
  /// red/green and never claims to measure alignment. The user positions
  /// their face and confirms the capture manually.
  Widget _buildCameraView() {
    switch (_cameraState) {
      case _CameraUiState.ready:
        final controller = _cameraController;
        if (controller != null && controller.value.isInitialized) {
          return Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ClipRRect(
                borderRadius: FansivibeRadius.baseBorder,
                child: AspectRatio(
                  aspectRatio: 3 / 4,
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      CameraPreview(controller),
                      Center(
                        child: Container(
                          width: 200,
                          height: 260,
                          decoration: BoxDecoration(
                            border: Border.all(
                              color: FansivibeColors.primary.withValues(
                                alpha: 0.8,
                              ),
                              width: 2,
                            ),
                            borderRadius: BorderRadius.circular(100),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Position your face inside the oval, then capture.',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: FansivibeColors.textSecondary,
                    ),
              ),
            ],
          );
        }
        return _cameraMessageCard(
          icon: Icons.camera_alt_outlined,
          title: 'Starting camera…',
          body: 'Please wait a moment.',
          actionLabel: null,
        );
      case _CameraUiState.loading:
      case _CameraUiState.initial:
        return _cameraMessageCard(
          icon: Icons.camera_alt_outlined,
          title: 'Starting camera…',
          body: 'Allow camera access in your browser when asked.',
          actionLabel: null,
        );
      case _CameraUiState.permissionDenied:
        return _cameraMessageCard(
          icon: Icons.videocam_off_outlined,
          title: 'Camera permission denied',
          body:
              'Allow camera access in your browser settings to take a photo, or choose from the gallery instead.',
          actionLabel: 'Retry',
        );
      case _CameraUiState.unavailable:
        return _cameraMessageCard(
          icon: Icons.videocam_off_outlined,
          title: 'Camera unavailable',
          body:
              'No camera was found on this device. Choose from the gallery instead.',
          actionLabel: 'Retry',
        );
      case _CameraUiState.error:
        return _cameraMessageCard(
          icon: Icons.error_outline_rounded,
          title: 'Camera error',
          body: _cameraError ?? 'Please try again.',
          actionLabel: 'Retry',
        );
    }
  }

  Widget _cameraMessageCard({
    required IconData icon,
    required String title,
    required String body,
    required String? actionLabel,
  }) {
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
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (_cameraState == _CameraUiState.loading ||
                  _cameraState == _CameraUiState.initial)
                const CircularProgressIndicator()
              else
                Icon(
                  icon,
                  size: 56,
                  color: FansivibeColors.surfaceContainerHighest,
                ),
              const SizedBox(height: 12),
              Text(
                title,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: FansivibeColors.textPrimary,
                      fontWeight: FontWeight.w600,
                    ),
              ),
              const SizedBox(height: 8),
              Text(
                body,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: FansivibeColors.textSecondary,
                    ),
              ),
              if (actionLabel != null) ...[
                const SizedBox(height: 16),
                FansiButton.secondary(
                  label: actionLabel,
                  icon: Icons.refresh_rounded,
                  onPressed: _startCamera,
                ),
              ],
            ],
          ),
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

enum _CameraUiState {
  initial,
  loading,
  ready,
  permissionDenied,
  unavailable,
  error,
}
