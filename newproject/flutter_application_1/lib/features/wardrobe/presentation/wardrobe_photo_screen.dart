import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:image_picker/image_picker.dart';

import 'package:fansivibe/shared/camera/camera_lifecycle_coordinator.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

/// Captured wardrobe photo handed back to the add-item flow.
class WardrobePhoto {
  const WardrobePhoto({required this.bytes, required this.filename});

  final Uint8List bytes;
  final String filename;
}

/// Rear-camera photo capture for a wardrobe item (M11).
///
/// Same camera architecture as the hairstyle/outfit scan screens
/// (`availableCameras` → `CameraController` → `CameraPreview`, lifecycle
/// handling, permission/denied/unavailable/error cards, web-safe
/// `Image.memory` bytes). Gallery is an explicit separate action via the
/// injectable [pickImage] — Take Photo never falls back to gallery.
/// Capture → preview → [Retake] / [Use Photo] (pops a [WardrobePhoto]).
class WardrobePhotoScreen extends StatefulWidget {
  const WardrobePhotoScreen({
    super.key,
    this.pickImage,
    this.takePhoto,
  });

  /// Gallery picker override (tests only). Production uses ImagePicker.
  final Future<XFile?> Function(ImageSource source)? pickImage;

  /// Custom capture override (tests only).
  final Future<XFile?> Function()? takePhoto;

  @override
  State<WardrobePhotoScreen> createState() => _WardrobePhotoScreenState();
}

enum _WardrobeCameraUiState {
  initial,
  loading,
  ready,
  permissionDenied,
  unavailable,
  error,
}

class _WardrobePhotoScreenState extends State<WardrobePhotoScreen>
    with WidgetsBindingObserver {
  CameraController? _controller;
  CameraLifecycleState _sessionState = CameraLifecycleState.off;

  /// Visible for testing to verify controller lifecycle release.
  CameraController? get cameraController => _controller;

  _WardrobeCameraUiState _uiState = _WardrobeCameraUiState.initial;
  String? _errorMessage;

  Uint8List? _previewBytes;
  String? _previewFilename;

  bool get _isTestMode {
    final bindingType = WidgetsBinding.instance.runtimeType.toString();
    return bindingType.contains('TestWidgetsFlutterBinding');
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    CameraLifecycleCoordinator.register(_disposeCamera);
    if (!_isTestMode) {
      SchedulerBinding.instance.addPostFrameCallback((_) async {
        await _initCamera();
      });
    } else if (widget.takePhoto != null) {
      _uiState = _WardrobeCameraUiState.ready;
    }
  }

  bool _isDisposed = false;

  /// Stops any active image stream and safely disposes the camera controller.
  Future<void> _disposeCamera() async {
    if (_sessionState == CameraLifecycleState.off && _controller == null) {
      return;
    }
    _sessionState = CameraLifecycleState.stopping;
    final controller = _controller;
    _controller = null;
    if (controller != null) {
      if (controller.value.isStreamingImages) {
        try {
          await controller.stopImageStream();
        } catch (_) {}
      }
      try {
        await controller.dispose();
      } catch (_) {}
    }
    _sessionState = CameraLifecycleState.off;
    if (mounted && !_isDisposed) {
      setState(() {
        if (_previewBytes == null) {
          _uiState = _WardrobeCameraUiState.initial;
        }
      });
    }
  }

  @override
  void dispose() {
    _isDisposed = true;
    CameraLifecycleCoordinator.unregister(_disposeCamera);
    WidgetsBinding.instance.removeObserver(this);
    _disposeCamera();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden ||
        state == AppLifecycleState.detached) {
      _disposeCamera();
      return;
    }
    // Rule 7: On app resume, keep camera OFF. Do not automatically restart.
  }

  Future<void> _initCamera() async {
    if (!mounted) return;
    if (_isTestMode) {
      if (widget.takePhoto != null) {
        setState(() => _uiState = _WardrobeCameraUiState.ready);
      } else {
        setState(() => _uiState = _WardrobeCameraUiState.unavailable);
      }
      return;
    }
    if (_sessionState == CameraLifecycleState.opening ||
        _sessionState == CameraLifecycleState.active) {
      return;
    }
    _sessionState = CameraLifecycleState.opening;
    setState(() {
      _uiState = _WardrobeCameraUiState.loading;
      _errorMessage = null;
    });
    try {
      final cameras = await availableCameras();
      if (!mounted || _sessionState != CameraLifecycleState.opening) {
        _sessionState = CameraLifecycleState.off;
        return;
      }
      if (cameras.isEmpty) {
        _sessionState = CameraLifecycleState.off;
        setState(() => _uiState = _WardrobeCameraUiState.unavailable);
        return;
      }
      final rearIndex = cameras.indexWhere(
        (c) => c.lensDirection == CameraLensDirection.back,
      );
      final controller = CameraController(
        cameras[rearIndex >= 0 ? rearIndex : 0],
        ResolutionPreset.medium,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.jpeg,
      );
      await controller.initialize();
      if (!mounted || _sessionState != CameraLifecycleState.opening) {
        try {
          await controller.dispose();
        } catch (_) {}
        _sessionState = CameraLifecycleState.off;
        return;
      }
      _controller = controller;
      _sessionState = CameraLifecycleState.active;
      setState(() => _uiState = _WardrobeCameraUiState.ready);
    } on CameraException catch (e) {
      _sessionState = CameraLifecycleState.off;
      if (!mounted) return;
      final code = e.code.toLowerCase();
      if (code.contains('denied') ||
          code.contains('accessdenied') ||
          code.contains('permission')) {
        setState(() => _uiState = _WardrobeCameraUiState.permissionDenied);
      } else {
        setState(() {
          _uiState = _WardrobeCameraUiState.error;
          _errorMessage = e.description ?? e.code;
        });
      }
    } catch (e) {
      _sessionState = CameraLifecycleState.off;
      if (!mounted) return;
      setState(() {
        _uiState = _WardrobeCameraUiState.error;
        _errorMessage = e.toString();
      });
    }
  }

  Future<void> _takePhoto() async {
    final isCustomTestTaker = widget.takePhoto != null;
    if (_isTestMode && !isCustomTestTaker) return;

    final controller = _controller;
    if (!isCustomTestTaker) {
      if (controller == null || !controller.value.isInitialized) return;
      if (controller.value.isTakingPicture) return;
    }
    try {
      final XFile? shot = isCustomTestTaker
          ? await widget.takePhoto!()
          : await controller!.takePicture();
      if (shot == null || !mounted) return;
      final bytes = await shot.readAsBytes();
      // Camera capture operation finished: release camera resources immediately!
      await _disposeCamera();
      if (!mounted) return;
      setState(() {
        _previewBytes = bytes;
        _previewFilename = shot.name.isNotEmpty
            ? shot.name
            : 'wardrobe_item.jpg';
        _errorMessage = null;
      });
    } on CameraException catch (e) {
      await _disposeCamera();
      if (!mounted) return;
      setState(() => _errorMessage = e.description ?? e.code);
    } catch (e) {
      await _disposeCamera();
      if (!mounted) return;
      setState(() => _errorMessage = 'Could not capture the photo.');
    }
  }

  Future<void> _pickFromGallery() async {
    try {
      final pick = widget.pickImage ??
          (ImageSource source) => ImagePicker().pickImage(
                source: source,
                maxWidth: 1024,
                maxHeight: 1024,
              );
      final file = await pick(ImageSource.gallery);
      if (file == null || !mounted) return;
      final bytes = await file.readAsBytes();
      if (!mounted) return;
      await _disposeCamera();
      setState(() {
        _previewBytes = bytes;
        _previewFilename =
            file.name.isNotEmpty ? file.name : 'wardrobe_item.jpg';
        _errorMessage = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _errorMessage = 'Could not open the gallery.');
    }
  }

  void _retake() {
    setState(() {
      _previewBytes = null;
      _previewFilename = null;
      _errorMessage = null;
      if (_isTestMode && widget.takePhoto != null) {
        _uiState = _WardrobeCameraUiState.ready;
      }
    });
    if (!_isTestMode) {
      _initCamera();
    }
  }

  void _usePhoto() async {
    final bytes = _previewBytes;
    if (bytes == null) return;
    await _disposeCamera();
    if (!mounted) return;
    Navigator.of(context).pop(
      WardrobePhoto(bytes: bytes, filename: _previewFilename ?? 'wardrobe_item.jpg'),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Photograph Item'),
        leading: IconButton(
          icon: Icon(
            Icons.arrow_back_rounded,
            color: FansivibeColors.textPrimary,
          ),
          onPressed: () async {
            await _disposeCamera();
            if (context.mounted) {
              Navigator.of(context).pop();
            }
          },
        ),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            children: [
              Expanded(child: _buildStage(context)),
              if (_errorMessage != null) ...[
                const SizedBox(height: 12),
                Text(
                  _errorMessage!,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: FansivibeColors.error,
                  ),
                ),
              ],
              const SizedBox(height: 16),
              _buildActions(),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildStage(BuildContext context) {
    final preview = _previewBytes;
    if (preview != null) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: Image.memory(preview, fit: BoxFit.contain),
      );
    }
    switch (_uiState) {
      case _WardrobeCameraUiState.ready:
        final controller = _controller;
        if (controller != null && controller.value.isInitialized) {
          return ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: CameraPreview(controller),
          );
        }
        return const Center(child: CircularProgressIndicator());
      case _WardrobeCameraUiState.loading:
      case _WardrobeCameraUiState.initial:
        // ponytail: static placeholder in widget tests — an indeterminate
        // spinner never settles under pumpAndSettle (face-screen precedent).
        if (_isTestMode) {
          return const Center(
            child: Icon(
              Icons.photo_camera_outlined,
              size: 64,
              color: FansivibeColors.textSecondary,
            ),
          );
        }
        if (_sessionState == CameraLifecycleState.off) {
          return _buildStatusCard(
            context,
            icon: Icons.videocam_off_rounded,
            title: 'Camera Paused',
            body: 'The camera is currently off. Tap below to start.',
          );
        }
        return const Center(child: CircularProgressIndicator());
      case _WardrobeCameraUiState.permissionDenied:
        return _buildStatusCard(
          context,
          icon: Icons.videocam_off_outlined,
          title: 'Camera permission denied',
          body: 'Allow camera access to photograph the item, '
              'or choose from the gallery instead.',
        );
      case _WardrobeCameraUiState.unavailable:
        return _buildStatusCard(
          context,
          icon: Icons.no_photography_outlined,
          title: 'No camera available',
          body: 'This device has no usable camera. '
              'Choose from the gallery instead.',
        );
      case _WardrobeCameraUiState.error:
        return _buildStatusCard(
          context,
          icon: Icons.error_outline_rounded,
          title: 'Camera error',
          body: 'The camera could not start. '
              'Retry, or choose from the gallery instead.',
        );
    }
  }

  Widget _buildStatusCard(
    BuildContext context, {
    required IconData icon,
    required String title,
    required String body,
  }) {
    final theme = Theme.of(context);
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 64, color: FansivibeColors.textSecondary),
          const SizedBox(height: 16),
          Text(
            title,
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w600,
              color: FansivibeColors.textPrimary,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            body,
            textAlign: TextAlign.center,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: FansivibeColors.textSecondary,
            ),
          ),
          const SizedBox(height: 16),
          FansiButton.secondary(
            label: 'Retry Camera',
            icon: Icons.refresh_rounded,
            onPressed: _initCamera,
          ),
        ],
      ),
    );
  }

  Widget _buildActions() {
    if (_previewBytes != null) {
      return Row(
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
              label: 'Use Photo',
              icon: Icons.check_rounded,
              onPressed: _usePhoto,
            ),
          ),
        ],
      );
    }
    return Column(
      children: [
        SizedBox(
          width: double.infinity,
          child: FansiButton.primary(
            label: 'Take Photo',
            icon: Icons.photo_camera_rounded,
            onPressed:
                _uiState == _WardrobeCameraUiState.ready ? _takePhoto : null,
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
}
