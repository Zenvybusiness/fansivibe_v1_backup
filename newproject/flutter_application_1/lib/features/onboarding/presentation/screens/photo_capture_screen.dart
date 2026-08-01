import 'dart:async';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

class PhotoCaptureScreen extends StatefulWidget {
  final String? source;
  const PhotoCaptureScreen({this.source, super.key});

  @override
  State<PhotoCaptureScreen> createState() => _PhotoCaptureScreenState();
}

class _PhotoCaptureScreenState extends State<PhotoCaptureScreen>
    with SingleTickerProviderStateMixin {
  bool _captured = false;
  bool _showGuide = false;

  late AnimationController _previewController;
  late Animation<double> _previewAnim;

  @override
  void initState() {
    super.initState();
    _previewController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    );
    _previewAnim = CurvedAnimation(
      parent: _previewController,
      curve: Curves.easeOut,
    );

    WidgetsBinding.instance.addPostFrameCallback((_) {
      setState(() => _showGuide = true);
    });
  }

  @override
  void dispose() {
    _previewController.dispose();
    super.dispose();
  }

  void _onCapture() {
    setState(() => _captured = true);
    _previewController.forward();
    Timer(const Duration(seconds: 2), () {
      if (!mounted) return;
      context.goNamed(RouteNames.aiAnalysis, extra: {'photoPath': 'captured'});
    });
  }

  void _onRetake() {
    setState(() {
      _captured = false;
    });
    _previewController.reverse();
  }

  void _onSkip() {
    context.goNamed(RouteNames.home, extra: {'vibe': null});
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: FansivibeColors.surface,
      body: Stack(
        children: [
          Container(
            color: FansivibeColors.surfaceContainerLow,
            child: Center(
              child: Icon(
                Icons.image_outlined,
                size: 80,
                color: FansivibeColors.surfaceContainerHighest,
              ),
            ),
          ),
          if (_showGuide && !_captured)
            Center(
              child: Container(
                width: 240,
                height: 360,
                decoration: BoxDecoration(
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.3),
                    width: 1.5,
                  ),
                  borderRadius: FansivibeRadius.mdBorder,
                ),
                child: CustomPaint(
                  painter: _SilhouettePainter(
                    color: Colors.white.withValues(alpha: 0.15),
                  ),
                ),
              ),
            ),
          if (_captured)
            AnimatedBuilder(
              animation: _previewAnim,
              builder: (context, _) {
                return Center(
                  child: Container(
                    width: 240 + (60 * (1 - _previewAnim.value)),
                    height: 360 + (90 * (1 - _previewAnim.value)),
                    decoration: BoxDecoration(
                      color: FansivibeColors.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(
                        FansivibeRadius.md + (8 * (1 - _previewAnim.value)),
                      ),
                      border: Border.all(
                        color: FansivibeColors.primary.withValues(alpha: 0.4),
                        width: 2,
                      ),
                    ),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(
                        FansivibeRadius.md + (8 * (1 - _previewAnim.value)) - 1,
                      ),
                      child: Stack(
                        alignment: Alignment.center,
                        children: [
                          Icon(
                            Icons.image_rounded,
                            size: 40,
                            color: FansivibeColors.primary.withValues(
                              alpha: 0.3,
                            ),
                          ),
                          Positioned(
                            bottom: 16,
                            child: Text(
                              'Looks great!',
                              style: TextStyle(
                                color: FansivibeColors.primary,
                                fontSize: 14,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                );
              },
            ),
          Positioned(
            bottom: 48,
            left: 0,
            right: 0,
            child: _captured
                ? Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      _CaptureButton(
                        icon: Icons.refresh_rounded,
                        onPressed: _onRetake,
                        label: 'Retake',
                      ),
                    ],
                  )
                : Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      _CaptureButton(
                        icon: Icons.circle_rounded,
                        onPressed: _onCapture,
                        label: '',
                        isPrimary: true,
                      ),
                    ],
                  ),
          ),
          Positioned(
            top: 16,
            right: 16,
            child: SafeArea(
              child: TextButton(
                onPressed: _onSkip,
                child: Text(
                  'Skip',
                  style: TextStyle(
                    color: FansivibeColors.secondary.withValues(alpha: 0.7),
                    fontSize: 14,
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _CaptureButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onPressed;
  final String label;
  final bool isPrimary;

  const _CaptureButton({
    required this.icon,
    required this.onPressed,
    required this.label,
    this.isPrimary = false,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onPressed,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: isPrimary ? 72 : 48,
            height: isPrimary ? 72 : 48,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: isPrimary
                  ? Colors.white
                  : Colors.white.withValues(alpha: 0.2),
              border: isPrimary
                  ? Border.all(color: FansivibeColors.primary, width: 3)
                  : null,
            ),
            child: Center(
              child: isPrimary
                  ? Container(
                      width: 62,
                      height: 62,
                      decoration: const BoxDecoration(
                        shape: BoxShape.circle,
                        color: Colors.white,
                      ),
                    )
                  : Icon(icon, size: 20, color: Colors.white),
            ),
          ),
          if (label.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              label,
              style: const TextStyle(color: Colors.white70, fontSize: 12),
            ),
          ],
        ],
      ),
    );
  }
}

class _SilhouettePainter extends CustomPainter {
  final Color color;
  _SilhouettePainter({required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;

    final path = Path()
      ..moveTo(size.width * 0.5, size.height * 0.08)
      ..quadraticBezierTo(
        size.width * 0.75,
        size.height * 0.08,
        size.width * 0.75,
        size.height * 0.22,
      )
      ..quadraticBezierTo(
        size.width * 0.78,
        size.height * 0.35,
        size.width * 0.75,
        size.height * 0.48,
      )
      ..lineTo(size.width * 0.8, size.height * 0.55)
      ..lineTo(size.width * 0.72, size.height * 0.6)
      ..lineTo(size.width * 0.68, size.height * 0.5)
      ..lineTo(size.width * 0.62, size.height * 0.5)
      ..lineTo(size.width * 0.62, size.height * 0.88)
      ..lineTo(size.width * 0.38, size.height * 0.88)
      ..lineTo(size.width * 0.38, size.height * 0.5)
      ..lineTo(size.width * 0.32, size.height * 0.5)
      ..lineTo(size.width * 0.28, size.height * 0.6)
      ..lineTo(size.width * 0.2, size.height * 0.55)
      ..lineTo(size.width * 0.25, size.height * 0.48)
      ..quadraticBezierTo(
        size.width * 0.22,
        size.height * 0.35,
        size.width * 0.25,
        size.height * 0.22,
      )
      ..quadraticBezierTo(
        size.width * 0.25,
        size.height * 0.08,
        size.width * 0.5,
        size.height * 0.08,
      )
      ..close();

    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
