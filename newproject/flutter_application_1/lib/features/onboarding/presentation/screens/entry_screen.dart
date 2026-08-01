import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';

class EntryScreen extends StatefulWidget {
  const EntryScreen({super.key});

  @override
  State<EntryScreen> createState() => _EntryScreenState();
}

class _EntryScreenState extends State<EntryScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _logoAnim;
  late Animation<double> _headlineAnim;
  late Animation<double> _subtitleAnim;
  late Animation<double> _illustrationAnim;
  late Animation<double> _cta1Anim;
  late Animation<double> _cta2Anim;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
    _logoAnim = _buildAnim(0.0, 0.3);
    _headlineAnim = _buildAnim(0.2, 0.6);
    _subtitleAnim = _buildAnim(0.35, 0.7);
    _illustrationAnim = _buildAnim(0.5, 0.85);
    _cta1Anim = _buildAnim(0.65, 0.95);
    _cta2Anim = _buildAnim(0.75, 1.0);
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

  void _onAnalyze() {
    context.goNamed(RouteNames.vibeSelect, extra: {'photoPath': true});
  }

  void _onExplore() {
    context.goNamed(RouteNames.vibeSelect, extra: {'photoPath': false});
  }

  void _onSignIn() {
    context.goNamed(RouteNames.home);
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
                        SizedBox(height: FansivibeSpacing.xxl),
                        _buildAnimatedOpacity(_logoAnim, _Logo()),
                        SizedBox(height: FansivibeSpacing.xxxl),
                        _buildAnimatedSlide(_headlineAnim, _Headline(), 30),
                        SizedBox(height: FansivibeSpacing.md),
                        _buildAnimatedSlide(_subtitleAnim, _Subtitle(), 20),
                        SizedBox(height: FansivibeSpacing.xl + 8),
                        _buildAnimatedOpacity(
                          _illustrationAnim,
                          const _HeroIllustration(),
                        ),
                        SizedBox(height: FansivibeSpacing.xl + 8),
                        _buildAnimatedSlide(
                          _cta1Anim,
                          _PrimaryCTA(onPressed: _onAnalyze),
                          20,
                        ),
                        SizedBox(height: FansivibeSpacing.sm + 4),
                        _buildAnimatedSlide(
                          _cta2Anim,
                          _SecondaryCTA(onPressed: _onExplore),
                          20,
                        ),
                        SizedBox(height: FansivibeSpacing.xxl + 8),
                        _SignInSection(onPressed: _onSignIn),
                        SizedBox(height: FansivibeSpacing.xl),
                        const _PrivacyNote(),
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

  Widget _buildAnimatedOpacity(Animation<double> anim, Widget child) {
    return AnimatedBuilder(
      animation: anim,
      builder: (context, _) => Opacity(opacity: anim.value, child: child),
    );
  }

  Widget _buildAnimatedSlide(
    Animation<double> anim,
    Widget child,
    double offset,
  ) {
    return AnimatedBuilder(
      animation: anim,
      builder: (context, _) {
        return Transform.translate(
          offset: Offset(0, offset * (1 - anim.value)),
          child: Opacity(opacity: anim.value, child: child),
        );
      },
    );
  }
}

class _Logo extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Text(
      'FANSIVIBE',
      style: FansivibeTypography.labelMediumWithFamily.copyWith(
        color: FansivibeColors.primary,
        fontSize: 14,
        letterSpacing: 4,
        fontWeight: FontWeight.w600,
      ),
    );
  }
}

class _Headline extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Text(
      'Your Personal\nAppearance Intelligence',
      textAlign: TextAlign.center,
      style: FansivibeTypography.displayLargeWithFamily.copyWith(
        fontSize: 36,
        height: 1.15,
        letterSpacing: -0.5,
      ),
    );
  }
}

class _Subtitle extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Text(
      'Discover your best hairstyle, outfits, colors, and grooming with AI.',
      textAlign: TextAlign.center,
      style: FansivibeTypography.bodyLargeWithFamily.copyWith(
        color: FansivibeColors.secondary,
        fontSize: 15,
        height: 1.5,
      ),
    );
  }
}

class _HeroIllustration extends StatelessWidget {
  const _HeroIllustration();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      height: 280,
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(28),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(28),
        child: Stack(
          alignment: Alignment.center,
          children: [
            Positioned(
              top: -40,
              right: -40,
              child: Container(
                width: 160,
                height: 160,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: FansivibeColors.primary.withValues(alpha: 0.04),
                ),
              ),
            ),
            Positioned(
              bottom: -30,
              left: -30,
              child: Container(
                width: 130,
                height: 130,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: FansivibeColors.primary.withValues(alpha: 0.03),
                ),
              ),
            ),
            Container(
              width: 140,
              height: 140,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(
                  colors: [
                    FansivibeColors.primary.withValues(alpha: 0.15),
                    FansivibeColors.primary.withValues(alpha: 0.02),
                    Colors.transparent,
                  ],
                  stops: const [0.0, 0.5, 1.0],
                ),
              ),
            ),
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: FansivibeColors.surfaceContainerHighest,
              ),
              child: Icon(
                Icons.person_outline_rounded,
                size: 40,
                color: FansivibeColors.primary.withValues(alpha: 0.8),
              ),
            ),
            Positioned(
              top: 52,
              right: 56,
              child: Icon(
                Icons.auto_awesome,
                size: 18,
                color: FansivibeColors.primary.withValues(alpha: 0.5),
              ),
            ),
            Positioned(
              top: 80,
              left: 52,
              child: Icon(
                Icons.star_outline_rounded,
                size: 14,
                color: FansivibeColors.primary.withValues(alpha: 0.35),
              ),
            ),
            Positioned(
              bottom: 56,
              right: 64,
              child: Icon(
                Icons.star_outline_rounded,
                size: 12,
                color: FansivibeColors.primary.withValues(alpha: 0.3),
              ),
            ),
            Positioned(
              bottom: 72,
              left: 60,
              child: Container(
                width: 6,
                height: 6,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: FansivibeColors.primary.withValues(alpha: 0.25),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PrimaryCTA extends StatelessWidget {
  final VoidCallback onPressed;
  const _PrimaryCTA({required this.onPressed});

  @override
  Widget build(BuildContext context) {
    return FansiButton.primary(
      label: 'Analyze My Style',
      icon: Icons.auto_awesome_rounded,
      onPressed: onPressed,
    );
  }
}

class _SecondaryCTA extends StatelessWidget {
  final VoidCallback onPressed;
  const _SecondaryCTA({required this.onPressed});

  @override
  Widget build(BuildContext context) {
    return FansiButton.secondary(
      label: 'Explore Without Scanning',
      onPressed: onPressed,
    );
  }
}

class _SignInSection extends StatelessWidget {
  final VoidCallback onPressed;
  const _SignInSection({required this.onPressed});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          'Already have an account?',
          style: FansivibeTypography.bodyMediumWithFamily.copyWith(
            color: FansivibeColors.secondary,
          ),
        ),
        SizedBox(height: FansivibeSpacing.md),
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            onPressed: onPressed,
            icon: const Icon(Icons.login_rounded, size: 18),
            label: const Text('Sign In'),
            style: FilledButton.styleFrom(
              backgroundColor: Colors.transparent,
              foregroundColor: FansivibeColors.primary,
              side: BorderSide(
                color: FansivibeColors.primary.withValues(alpha: 0.4),
                width: 1.2,
              ),
              shape: RoundedRectangleBorder(
                borderRadius: FansivibeRadius.fullBorder,
              ),
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
              textStyle: FansivibeTypography.bodyLargeWithFamily.copyWith(
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _PrivacyNote extends StatelessWidget {
  const _PrivacyNote();

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(
          Icons.lock_outline_rounded,
          size: 12,
          color: FansivibeColors.secondary.withValues(alpha: 0.6),
        ),
        SizedBox(width: FansivibeSpacing.sm),
        Text(
          'Your photos stay private and secure.',
          style: FansivibeTypography.labelSmallWithFamily.copyWith(
            color: FansivibeColors.secondary.withValues(alpha: 0.6),
          ),
        ),
      ],
    );
  }
}
