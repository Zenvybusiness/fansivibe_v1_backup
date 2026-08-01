import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';

class CameraPermissionScreen extends StatefulWidget {
  const CameraPermissionScreen({super.key});

  @override
  State<CameraPermissionScreen> createState() => _CameraPermissionScreenState();
}

class _CameraPermissionScreenState extends State<CameraPermissionScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _illustrationAnim;
  late Animation<double> _contentAnim;
  late Animation<double> _trust1Anim;
  late Animation<double> _trust2Anim;
  late Animation<double> _trust3Anim;
  late Animation<double> _ctaAnim;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
    _illustrationAnim = _buildAnim(0.0, 0.4);
    _contentAnim = _buildAnim(0.2, 0.5);
    _trust1Anim = _buildAnim(0.35, 0.6);
    _trust2Anim = _buildAnim(0.45, 0.7);
    _trust3Anim = _buildAnim(0.55, 0.8);
    _ctaAnim = _buildAnim(0.65, 1.0);
    _controller.forward();
  }

  Animation<double> _buildAnim(double start, double end) {
    return Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(
        parent: _controller,
        curve: Interval(start, end, curve: Curves.easeOut),
      ),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onAllowCamera() {
    context.goNamed(RouteNames.photoCapture, extra: {'source': 'camera'});
  }

  void _onGallery() {
    context.goNamed(RouteNames.photoCapture, extra: {'source': 'gallery'});
  }

  void _onSkip() {
    context.goNamed(RouteNames.home, extra: {'vibe': null});
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: FansivibeColors.surface,
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 24.0;
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
                      children: [
                        SizedBox(height: FansivibeSpacing.xxl + 8),
                        _AnimatedSection(
                          anim: _illustrationAnim,
                          child: Container(
                            width: 200,
                            height: 200,
                            decoration: BoxDecoration(
                              color: FansivibeColors.surfaceContainerHigh,
                              borderRadius: FansivibeRadius.lgBorder,
                            ),
                            child: Stack(
                              alignment: Alignment.center,
                              children: [
                                Icon(
                                  Icons.camera_alt_outlined,
                                  size: 64,
                                  color: FansivibeColors.primary.withValues(
                                    alpha: 0.3,
                                  ),
                                ),
                                Positioned(
                                  top: 36,
                                  right: 36,
                                  child: Icon(
                                    Icons.lock_outline_rounded,
                                    size: 20,
                                    color: FansivibeColors.primary.withValues(
                                      alpha: 0.6,
                                    ),
                                  ),
                                ),
                                Positioned(
                                  bottom: 36,
                                  left: 36,
                                  child: Container(
                                    width: 8,
                                    height: 8,
                                    decoration: BoxDecoration(
                                      shape: BoxShape.circle,
                                      color: FansivibeColors.success.withValues(
                                        alpha: 0.5,
                                      ),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        SizedBox(height: FansivibeSpacing.xl),
                        _AnimatedSection(
                          anim: _contentAnim,
                          child: Column(
                            children: [
                              Text(
                                'One Photo Is\nAll It Takes',
                                textAlign: TextAlign.center,
                                style: FansivibeTypography
                                    .headlineMediumWithFamily
                                    .copyWith(fontSize: 28, height: 1.2),
                              ),
                              SizedBox(height: FansivibeSpacing.md),
                              Text(
                                'AI analyzes your look and suggests improvements.\nNo data is stored without your permission.',
                                textAlign: TextAlign.center,
                                style: FansivibeTypography.bodyMediumWithFamily
                                    .copyWith(
                                      color: FansivibeColors.secondary,
                                      height: 1.5,
                                    ),
                              ),
                            ],
                          ),
                        ),
                        SizedBox(height: FansivibeSpacing.xl),
                        _TrustItem(
                          anim: _trust1Anim,
                          text: 'Your photo is analyzed and stored securely.',
                        ),
                        SizedBox(height: FansivibeSpacing.sm + 4),
                        _TrustItem(
                          anim: _trust2Anim,
                          text: 'Only you decide what to share and save.',
                        ),
                        SizedBox(height: FansivibeSpacing.sm + 4),
                        _TrustItem(
                          anim: _trust3Anim,
                          text: 'We never post or share your images.',
                        ),
                        SizedBox(height: FansivibeSpacing.xl),
                        _AnimatedSection(
                          anim: _ctaAnim,
                          child: Column(
                            children: [
                              FansiButton.primary(
                                label: 'Allow Camera',
                                icon: Icons.camera_alt_rounded,
                                onPressed: _onAllowCamera,
                              ),
                              SizedBox(height: FansivibeSpacing.sm + 4),
                              FansiButton.secondary(
                                label: 'Choose from Gallery',
                                icon: Icons.photo_library_outlined,
                                onPressed: _onGallery,
                              ),
                              SizedBox(height: FansivibeSpacing.md),
                              FansiButton.tertiary(
                                label: 'Skip for now',
                                onPressed: _onSkip,
                              ),
                            ],
                          ),
                        ),
                        SizedBox(height: FansivibeSpacing.lg),
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
}

class _AnimatedSection extends StatelessWidget {
  final Animation<double> anim;
  final Widget child;
  const _AnimatedSection({required this.anim, required this.child});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: anim,
      builder: (context, _) {
        return Opacity(
          opacity: anim.value,
          child: Transform.translate(
            offset: Offset(0, 30 * (1 - anim.value)),
            child: child,
          ),
        );
      },
    );
  }
}

class _TrustItem extends StatelessWidget {
  final Animation<double> anim;
  final String text;
  const _TrustItem({required this.anim, required this.text});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: anim,
      builder: (context, _) {
        return Opacity(
          opacity: anim.value,
          child: Row(
            children: [
              Icon(
                Icons.shield_outlined,
                size: 16,
                color: FansivibeColors.primary.withValues(alpha: 0.7),
              ),
              SizedBox(width: FansivibeSpacing.sm),
              Text(
                text,
                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                  color: FansivibeColors.secondary,
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
