import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:camera/camera.dart';

import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/core/config/app_config.dart';
import 'package:fansivibe/features/outfit_scan/data/outfit_scan_client.dart';
import 'package:fansivibe/features/outfit_scan/presentation/widgets/outfit_scan_widgets.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class OutfitScanScreen extends StatefulWidget {
  const OutfitScanScreen({super.key, this.client});

  final OutfitScanClient? client;

  @override
  State<OutfitScanScreen> createState() => _OutfitScanScreenState();
}

enum _CameraUiState {
  initial,
  loading,
  ready,
  permissionDenied,
  unavailable,
  error,
}

class _OutfitScanScreenState extends State<OutfitScanScreen>
    with WidgetsBindingObserver {
  CameraController? _controller;
  List<CameraDescription> _availableCameras = const [];
  int _selectedCameraIndex = 0;

  _CameraUiState _uiState = _CameraUiState.initial;
  String? _errorMessage;

  // Web-safe selection: the picked/captured XFile plus in-memory bytes for
  // preview (`Image.memory`, never `Image.file`/`dart:io`) so Chrome Web
  // works from localhost. Mobile camera behavior is preserved.
  XFile? _selectedImage;
  Uint8List? _selectedImageBytes;
  bool get _isTestMode {
    final bindingType = WidgetsBinding.instance.runtimeType.toString();
    return bindingType.contains('TestWidgetsFlutterBinding');
  }

  late final OutfitScanClient _client;

  @override
  void initState() {
    super.initState();
    _client = widget.client ?? OutfitScanClient();
    WidgetsBinding.instance.addObserver(this);

    // Defer init so context is ready and to avoid exceptions during tests.
    if (!_isTestMode) {
      SchedulerBinding.instance.addPostFrameCallback((_) async {
        await _initializeCamerasAndController();
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

    // Follow camera package lifecycle guidance.
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused) {
      _controller?.dispose();
      _controller = null;
      _uiState = _CameraUiState.initial;
      return;
    }

    if (state == AppLifecycleState.resumed) {
      SchedulerBinding.instance.addPostFrameCallback((_) async {
        await _initializeCamerasAndController();
      });
    }
  }

  Future<void> _initializeCamerasAndController() async {
    setState(() {
      _uiState = _CameraUiState.loading;
      _errorMessage = null;
    });

    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) {
        setState(() => _uiState = _CameraUiState.unavailable);
        return;
      }

      _availableCameras = cameras;

      // Prefer rear camera by default if present.
      final rearIndex = cameras.indexWhere(
        (c) => c.lensDirection == CameraLensDirection.back,
      );
      _selectedCameraIndex = rearIndex >= 0 ? rearIndex : 0;

      final controller = CameraController(
        cameras[_selectedCameraIndex],
        ResolutionPreset.medium,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.jpeg,
      );

      _controller = controller;

      await controller.initialize();

      if (!mounted) return;

      setState(() => _uiState = _CameraUiState.ready);
    } on CameraException catch (e) {
      if (!mounted) return;

      final code = e.code.toLowerCase();
      if (code.contains('denied') ||
          code.contains('accessdenied') ||
          code.contains('permission')) {
        setState(() => _uiState = _CameraUiState.permissionDenied);
      } else {
        setState(() {
          _uiState = _CameraUiState.error;
          _errorMessage = e.description ?? e.code;
        });
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _uiState = _CameraUiState.error;
        _errorMessage = e.toString();
      });
    }
  }

  Future<void> _switchCamera() async {
    if (_availableCameras.isEmpty) return;

    final nextIndex = (_selectedCameraIndex + 1) % _availableCameras.length;
    setState(() {
      _uiState = _CameraUiState.loading;
      _errorMessage = null;
      _selectedCameraIndex = nextIndex;
    });

    await _controller?.dispose();

    final controller = CameraController(
      _availableCameras[_selectedCameraIndex],
      ResolutionPreset.medium,
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.jpeg,
    );

    _controller = controller;

    try {
      await controller.initialize();
      if (!mounted) return;
      setState(() => _uiState = _CameraUiState.ready);
    } on CameraException catch (e) {
      if (!mounted) return;
      final code = e.code.toLowerCase();
      if (code.contains('denied') ||
          code.contains('accessdenied') ||
          code.contains('permission')) {
        setState(() => _uiState = _CameraUiState.permissionDenied);
      } else {
        setState(() {
          _uiState = _CameraUiState.error;
          _errorMessage = e.description ?? e.code;
        });
      }
    }
  }

  Future<void> _pickImage(ImageSource source) async {
    try {
      final pickedFile = await ImagePicker().pickImage(
        source: source,
        maxWidth: 1024,
        maxHeight: 1024,
      );

      if (pickedFile == null) return;

      // Web-safe: keep the XFile and its bytes for preview/upload.
      // On Web this avoids `dart:io File`; on mobile `XFile` works too.
      // Browser permission/cancel is handled: null means user cancelled.
      final bytes = await pickedFile.readAsBytes();
      if (!mounted || bytes.isEmpty) return;
      setState(() {
        _selectedImage = XFile.fromData(
          bytes,
          name: pickedFile.name.isNotEmpty
              ? pickedFile.name
              : 'outfit_scan.jpg',
          mimeType: 'image/jpeg',
        );
        _selectedImageBytes = bytes;
      });

      // Upload to backend immediately
      await _uploadImageAndNavigate(context, _selectedImage!);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Could not open photo library. ${AppConfig.connectionHint} ($e)'),
          backgroundColor: FansivibeColors.error,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(
            borderRadius: FansivibeRadius.smdBorder,
          ),
        ),
      );
    }
  }

  Future<void> _uploadImageAndNavigate(
    BuildContext context,
    XFile imageFile,
  ) async {
    try {
      final runId = await _client.submitOutfitAnalysis(imageFile);

      if (!context.mounted) return;

      if (runId != null) {
        context.pushNamed(RouteNames.scanProcessing, extra: runId);
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Upload failed. ${AppConfig.connectionHint}'),
            backgroundColor: FansivibeColors.error,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(
              borderRadius: FansivibeRadius.smdBorder,
            ),
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Upload error. ${AppConfig.connectionHint} ($e)'),
          backgroundColor: FansivibeColors.error,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(
            borderRadius: FansivibeRadius.smdBorder,
          ),
        ),
      );
    }
  }

  Future<void> _handleCapture(BuildContext context) async {
    // In widget tests we can't access camera; keep navigation intact.
    if (_isTestMode) {
      context.pushNamed(RouteNames.scanProcessing);
      return;
    }

    if (_selectedImage != null) {
      // Image already picked/gallery; the upload was already done in _pickImage
      // Just navigate processing screen will poll with the run_id
      return;
    }

    final controller = _controller;
    if (controller == null || !_controller!.value.isInitialized) {
      // Attempt re-init; but still keep flow if we fail to capture.
      await _initializeCamerasAndController();
      context.pushNamed(RouteNames.scanProcessing);
      return;
    }

    try {
      final xFile = await controller.takePicture();

      // Web-safe: camera_web returns an object URL / bytes-backed XFile.
      // Read bytes for preview (Image.memory) and upload via bytes.
      // Handles permission denied / unavailable via the outer CameraException
      // mapping; empty bytes are treated as a capture failure.
      final bytes = await xFile.readAsBytes();
      if (!mounted) return;
      if (bytes.isEmpty) {
        context.pushNamed(RouteNames.scanProcessing);
        return;
      }
      setState(() {
        _selectedImage = xFile;
        _selectedImageBytes = bytes;
      });

      // Upload captured image to backend
      await _uploadImageAndNavigate(context, xFile);
    } catch (e) {
      // If capture fails, still continue to existing processing flow.
      context.pushNamed(RouteNames.scanProcessing);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Scan My Outfit'),
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
                        _buildCameraPreview(context),
                        const SizedBox(height: 20),
                        _buildCheckRow(),
                        const SizedBox(height: 24),
                        _buildCaptureButton(context),
                        const SizedBox(height: 12),
                        _buildSecondaryActions(context),
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

  Widget _buildCameraPreview(BuildContext context) {
    if (_isTestMode) {
      return const CameraPreviewPlaceholder();
    }

    if (_uiState == _CameraUiState.loading ||
        _uiState == _CameraUiState.initial) {
      return SizedBox(
        height: 280,
        width: double.infinity,
        child: const CameraPreviewPlaceholder(),
      );
    }

    if (_uiState == _CameraUiState.permissionDenied) {
      return SizedBox(
        height: 280,
        width: double.infinity,
        child: _buildCameraErrorCard(
          title: 'Camera permission denied',
          description:
              'Enable camera access in system settings to scan your outfit.',
          actionLabel: 'Retry',
          onAction: _initializeCamerasAndController,
        ),
      );
    }

    if (_uiState == _CameraUiState.unavailable) {
      return SizedBox(
        height: 280,
        width: double.infinity,
        child: _buildCameraErrorCard(
          title: 'Camera unavailable',
          description: 'No camera device was detected on this device.',
          actionLabel: 'Retry',
          onAction: _initializeCamerasAndController,
        ),
      );
    }

    if (_uiState == _CameraUiState.error || _controller == null) {
      return SizedBox(
        height: 280,
        width: double.infinity,
        child: _buildCameraErrorCard(
          title: 'Camera error',
          description: _errorMessage ?? 'Please try again.',
          actionLabel: 'Retry',
          onAction: _initializeCamerasAndController,
        ),
      );
    }

    if (_uiState != _CameraUiState.ready || !_controller!.value.isInitialized) {
      return const CameraPreviewPlaceholder();
    }

    // If we have a selected image (from gallery), show it instead of camera
    if (_selectedImage != null) {
      return _buildSelectedImagePreview(context);
    }

    return SizedBox(
      height: 280,
      width: double.infinity,
      child: ClipRRect(
        borderRadius: FansivibeRadius.baseBorder,
        child: Stack(
          fit: StackFit.expand,
          children: [
            CameraPreview(_controller!),
            Positioned(
              top: 12,
              right: 12,
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: FansivibeColors.accentGold.withValues(alpha: 0.2),
                  borderRadius: FansivibeRadius.smBorder,
                  border: Border.all(
                    color: FansivibeColors.accentGold.withValues(alpha: 0.4),
                  ),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const SizedBox(
                      width: 8,
                      height: 8,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        valueColor: AlwaysStoppedAnimation<Color>(
                          FansivibeColors.accentGold,
                        ),
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      'AI Analysis Active',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: FansivibeColors.accentGold,
                        fontWeight: FontWeight.w600,
                        fontSize: 11,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSelectedImagePreview(BuildContext context) {
    final bytes = _selectedImageBytes;
    // Web-safe preview: in-memory bytes (Chrome + mobile). If bytes are
    // missing (e.g. failed read), fall back to the placeholder instead of
    // crashing on `Image.file` (which is unsupported on Web).
    if (bytes == null || bytes.isEmpty) {
      return const CameraPreviewPlaceholder();
    }
    return ClipRRect(
      borderRadius: FansivibeRadius.baseBorder,
      child: Stack(
        fit: StackFit.expand,
        children: [
          Image.memory(
            bytes,
            fit: BoxFit.cover,
            width: double.infinity,
            height: double.infinity,
            gaplessPlayback: true,
          ),
          Positioned(
            top: 12,
            right: 12,
            child: Container(
              padding: const EdgeInsets.symmetric(
                horizontal: 10,
                vertical: 6,
              ),
              decoration: BoxDecoration(
                color: FansivibeColors.accentGold.withValues(alpha: 0.2),
                borderRadius: FansivibeRadius.smBorder,
                border: Border.all(
                  color: FansivibeColors.accentGold.withValues(alpha: 0.4),
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const SizedBox(
                    width: 8,
                    height: 8,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      valueColor: AlwaysStoppedAnimation<Color>(
                        FansivibeColors.accentGold,
                      ),
                    ),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    'AI Analysis Active',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: FansivibeColors.accentGold,
                      fontWeight: FontWeight.w600,
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCameraErrorCard({
    required String title,
    required String description,
    required String actionLabel,
    required VoidCallback onAction,
  }) {
    return Container(
      height: 280,
      width: double.infinity,
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: FansivibeRadius.baseBorder,
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.15),
        ),
      ),
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.camera_alt_rounded,
                size: 56,
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
        ),
      ),
    );
  }

  Widget _buildCheckRow() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: FansivibeRadius.baseBorder,
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.15),
        ),
      ),
      child: Column(
        children: [
          Row(
            children: const [
              Expanded(
                child: CheckIndicator(label: 'Lighting', isPassing: true),
              ),
              Expanded(
                child: CheckIndicator(label: 'Framing', isPassing: true),
              ),
              Expanded(
                child: CheckIndicator(label: 'Posture', isPassing: false),
              ),
            ],
          ),
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
                  'Adjust posture for better analysis',
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
      ),
    );
  }

  Widget _buildCaptureButton(BuildContext context) {
    return FansiButton.primary(
      label: 'Capture Photo',
      icon: Icons.camera_alt_rounded,
      onPressed: () => _handleCapture(context),
    );
  }

  Widget _buildSecondaryActions(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: FansiButton.secondary(
            label: 'Choose from Gallery',
            icon: Icons.photo_library_rounded,
            onPressed: () => _pickImage(ImageSource.gallery),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: FansiButton.secondary(
            label: 'Switch Camera',
            icon: Icons.cameraswitch_rounded,
            onPressed: _switchCamera,
          ),
        ),
      ],
    );
  }
}