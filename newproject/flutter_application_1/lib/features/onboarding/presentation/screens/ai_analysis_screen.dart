import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

class AiAnalysisScreen extends StatefulWidget {
  const AiAnalysisScreen({super.key});

  @override
  State<AiAnalysisScreen> createState() => _AiAnalysisScreenState();
}

class _AiAnalysisScreenState extends State<AiAnalysisScreen>
    with TickerProviderStateMixin {
  late AnimationController _particleController;
  late AnimationController _arcController;
  late Animation<double> _arcAnim;
  late Animation<double> _photoAnim;

  @override
  void initState() {
    super.initState();
    _particleController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 3),
    )..repeat();

    _arcController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2500),
    );
    _arcAnim = CurvedAnimation(parent: _arcController, curve: Curves.easeInOut);
    _photoAnim = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(
        parent: _arcController,
        curve: const Interval(0.0, 0.15, curve: Curves.easeOut),
      ),
    );

    _arcController.forward();
    _arcController.addStatusListener((status) {
      if (status == AnimationStatus.completed) {
        Timer(const Duration(milliseconds: 500), _onComplete);
      }
    });
  }

  void _onComplete() {
    if (!mounted) return;
    context.goNamed(RouteNames.yourAnalysis);
  }

  @override
  void dispose() {
    _particleController.dispose();
    _arcController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: FansivibeColors.surface,
      body: Stack(
        children: [
          AnimatedBuilder(
            animation: _particleController,
            builder: (context, _) {
              return CustomPaint(
                size: Size.infinite,
                painter: _ParticlePainter(
                  progress: _particleController.value,
                  color: FansivibeColors.primary,
                ),
              );
            },
          ),
          Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                AnimatedBuilder(
                  animation: _photoAnim,
                  builder: (context, _) {
                    return Transform.scale(
                      scale: 0.6 + (0.4 * _photoAnim.value),
                      child: Container(
                        width: 120,
                        height: 120,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: FansivibeColors.surfaceContainerHighest,
                          border: Border.all(
                            color: FansivibeColors.primary.withValues(alpha: 0.3),
                            width: 2,
                          ),
                        ),
                        child: Center(
                          child: Icon(
                            Icons.image_rounded,
                            size: 48,
                            color: FansivibeColors.primary.withValues(alpha: 0.4),
                          ),
                        ),
                      ),
                    );
                  },
                ),
                const SizedBox(height: 32),
                AnimatedBuilder(
                  animation: _arcAnim,
                  builder: (context, _) {
                    return SizedBox(
                      width: 160,
                      height: 160,
                      child: CustomPaint(
                        painter: _ArcPainter(
                          progress: _arcAnim.value,
                          color: FansivibeColors.primary,
                        ),
                      ),
                    );
                  },
                ),
                const SizedBox(height: 24),
                const _FloatingTerms(),
              ],
            ),
          ),
          Positioned(
            bottom: 80,
            left: 0,
            right: 0,
            child: Center(
              child: Text(
                'Analyzing your style…',
                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                  color: FansivibeColors.secondary.withValues(alpha: 0.6),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _FloatingTerms extends StatefulWidget {
  const _FloatingTerms();

  @override
  State<_FloatingTerms> createState() => _FloatingTermsState();
}

class _FloatingTermsState extends State<_FloatingTerms>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 3),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        return Column(
          children: [
            _buildTerm(0, 'SILHOUETTE'),
            const SizedBox(height: 8),
            _buildTerm(1, 'HARMONY'),
            const SizedBox(height: 8),
            _buildTerm(2, 'PROPORTION'),
            const SizedBox(height: 8),
            _buildTerm(3, 'PALETTE'),
          ],
        );
      },
    );
  }

  Widget _buildTerm(int index, String term) {
    final delay = index * 0.15;
    final opacity = (_controller.value + delay) % 1.0;
    final adjusted = opacity < 0.5 ? opacity / 0.5 : (1.0 - opacity) / 0.5;
    return Opacity(
      opacity: adjusted.clamp(0.0, 0.4),
      child: Transform.translate(
        offset: Offset(
          (index.isEven ? 20 : -20) * (_controller.value - 0.5),
          0,
        ),
        child: Text(
          term,
          style: FansivibeTypography.labelMediumWithFamily.copyWith(
            color: FansivibeColors.primary,
            letterSpacing: 4,
            fontSize: 11,
          ),
        ),
      ),
    );
  }
}

class _ParticlePainter extends CustomPainter {
  final double progress;
  final Color color;

  _ParticlePainter({required this.progress, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..style = PaintingStyle.fill;

    final center = Offset(size.width / 2, size.height / 2);
    for (int i = 0; i < 12; i++) {
      final angle = (i / 12) * 3.14159 * 2 + (progress * 3.14159 * 2);
      final distance = 80.0 + (progress * 40) + (i * 8);
      final x = center.dx + distance * 0.7 * math.cos(angle);
      final y = center.dy + distance * 0.7 * math.sin(angle);

      final particleSize = 2.0 + ((i % 3) * 1.0);
      final alpha = ((i % 5) / 5.0) * 0.3;

      paint.color = color.withValues(alpha: alpha);
      canvas.drawCircle(Offset(x, y), particleSize, paint);
    }
  }

  @override
  bool shouldRepaint(_ParticlePainter oldDelegate) =>
      oldDelegate.progress != progress;
}

class _ArcPainter extends CustomPainter {
  final double progress;
  final Color color;

  _ArcPainter({required this.progress, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 4;

    final bgPaint = Paint()
      ..color = color.withValues(alpha: 0.08)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;

    canvas.drawCircle(center, radius, bgPaint);

    final arcPaint = Paint()
      ..color = color.withValues(alpha: 0.6)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round;

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -3.14159 / 2,
      3.14159 * 2 * progress,
      false,
      arcPaint,
    );
  }

  @override
  bool shouldRepaint(_ArcPainter oldDelegate) =>
      oldDelegate.progress != progress;
}
