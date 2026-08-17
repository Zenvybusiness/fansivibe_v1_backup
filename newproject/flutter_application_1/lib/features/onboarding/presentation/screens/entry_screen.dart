import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

class EntryScreen extends StatefulWidget {
  const EntryScreen({super.key});

  @override
  State<EntryScreen> createState() => _EntryScreenState();
}

class _EntryScreenState extends State<EntryScreen>
    with TickerProviderStateMixin {
  late AnimationController _controller;
  late AnimationController _breathController;
  late Animation<double> _breath;
  late Animation<double> _wordmarkAnim;
  late Animation<double> _mirrorAnim;
  late Animation<double> _headlineAnim;
  late Animation<double> _valueAnim;
  late Animation<double> _ctaAnim;
  late Animation<double> _gateAnim;
  late Animation<double> _privacyAnim;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
    _breathController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2800),
    )..repeat(reverse: true);

    _breath = Tween<double>(begin: 0.45, end: 0.85).animate(
      CurvedAnimation(parent: _breathController, curve: Curves.easeInOut),
    );

    _wordmarkAnim = _buildAnim(0.0, 0.3);
    _mirrorAnim = _buildAnim(0.15, 0.45);
    _headlineAnim = _buildAnim(0.35, 0.6);
    _valueAnim = _buildAnim(0.5, 0.72);
    _ctaAnim = _buildAnim(0.62, 0.85);
    _gateAnim = _buildAnim(0.75, 0.95);
    _privacyAnim = _buildAnim(0.85, 1.0);

    _checkReturningUser();
  }

  void _checkReturningUser() {
    if (LocalStorage.onboardingComplete) {
      // Returning user - skip onboarding and go directly to home
      Future.delayed(const Duration(milliseconds: 1500), () {
        if (mounted) {
          context.goNamed(RouteNames.home);
        }
      });
    }
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
    _breathController.dispose();
    super.dispose();
  }

  void _onAnalyze() {
    context.pushNamed(
      RouteNames.vibeSelect,
      extra: {'photoPath': true, 'vibeRequired': false},
    );
  }

  void _onExplore() {
    context.pushNamed(
      RouteNames.vibeSelect,
      extra: {'photoPath': false, 'vibeRequired': false},
    );
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
            final contentMaxWidth = maxWidth > 600 ? 460.0 : double.infinity;

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
                        SizedBox(height: FansivibeSpacing.xxl + 12),
                        _Reveal(anim: _wordmarkAnim, child: const _Wordmark()),
                        SizedBox(height: FansivibeSpacing.xxl + 8),
                        _Reveal(
                          anim: _mirrorAnim,
                          child: _Mirror(breath: _breath),
                        ),
                        SizedBox(height: FansivibeSpacing.xl + 8),
                        _Reveal(
                          anim: _headlineAnim,
                          offset: 12,
                          child: const _Headline(),
                        ),
                        SizedBox(height: FansivibeSpacing.lg),
                        _Reveal(
                          anim: _valueAnim,
                          offset: 10,
                          child: const _ValueStatement(),
                        ),
                        SizedBox(height: FansivibeSpacing.xxl),
                        _Reveal(
                          anim: _ctaAnim,
                          offset: 10,
                          child: _PrimaryCTA(onPressed: _onAnalyze),
                        ),
                        SizedBox(height: FansivibeSpacing.sm + 4),
                        _Reveal(
                          anim: _ctaAnim,
                          offset: 10,
                          child: _SecondaryCTA(onPressed: _onExplore),
                        ),
                        SizedBox(height: FansivibeSpacing.xl + 8),
                        _Reveal(
                          anim: _gateAnim,
                          offset: 10,
                          child: _AccountGate(onSignIn: _onSignIn),
                        ),
                        SizedBox(height: FansivibeSpacing.lg + 8),
                        _Reveal(
                          anim: _privacyAnim,
                          child: const _PrivacyNote(),
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

class _Reveal extends StatelessWidget {
  final Animation<double> anim;
  final Widget child;
  final double offset;

  const _Reveal({required this.anim, required this.child, this.offset = 8});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: anim,
      builder: (context, _) {
        return Opacity(
          opacity: anim.value,
          child: Transform.translate(
            offset: Offset(0, offset * (1 - anim.value)),
            child: child,
          ),
        );
      },
    );
  }
}

class _Wordmark extends StatelessWidget {
  const _Wordmark();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          'FANSIVIBE',
          style: FansivibeTypography.titleLargeWithFamily.copyWith(
            color: FansivibeColors.onSurface,
            fontSize: 26,
            letterSpacing: 4,
            fontWeight: FontWeight.w500,
          ),
        ),
        SizedBox(height: FansivibeSpacing.sm),
        Text(
          'APPEARANCE INTELLIGENCE',
          style: FansivibeTypography.labelSmallWithFamily.copyWith(
            color: FansivibeColors.primary,
            letterSpacing: 3,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }
}

class _Mirror extends StatelessWidget {
  final Animation<double> breath;
  const _Mirror({required this.breath});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: breath,
      builder: (context, _) {
        return Container(
          width: 148,
          height: 148,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: RadialGradient(
              colors: [
                FansivibeColors.primary.withValues(alpha: 0.10 * breath.value),
                Colors.transparent,
              ],
              stops: const [0.0, 1.0],
            ),
          ),
          child: Stack(
            alignment: Alignment.center,
            children: [
              Container(
                width: 104,
                height: 104,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: FansivibeColors.surfaceContainerLow,
                  border: Border.all(
                    color: FansivibeColors.primary.withValues(alpha: 0.5),
                    width: 1.4,
                  ),
                ),
                child: Icon(
                  Icons.person_outline_rounded,
                  size: 52,
                  color: FansivibeColors.primary.withValues(alpha: 0.9),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _Headline extends StatelessWidget {
  const _Headline();

  @override
  Widget build(BuildContext context) {
    return Text.rich(
      TextSpan(
        children: [
          TextSpan(
            text: 'Your best style,\n',
            style: FansivibeTypography.displayLargeWithFamily.copyWith(
              fontSize: 34,
              height: 1.2,
              letterSpacing: -0.5,
            ),
          ),
          TextSpan(
            text: 'discovered by AI.',
            style: FansivibeTypography.displayLargeWithFamily.copyWith(
              fontSize: 34,
              height: 1.2,
              fontStyle: FontStyle.italic,
              letterSpacing: -0.5,
              color: FansivibeColors.primary,
            ),
          ),
        ],
      ),
      textAlign: TextAlign.center,
    );
  }
}

class _ValueStatement extends StatelessWidget {
  const _ValueStatement();

  @override
  Widget build(BuildContext context) {
    return Text(
      'Look better. Dress smarter. Build confidence.',
      textAlign: TextAlign.center,
      style: FansivibeTypography.bodyLargeWithFamily.copyWith(
        color: FansivibeColors.secondary,
        fontSize: 15,
        height: 1.5,
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

class _AccountGate extends StatelessWidget {
  final VoidCallback onSignIn;
  const _AccountGate({required this.onSignIn});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          height: 1,
          color: FansivibeColors.outlineVariant.withValues(alpha: 0.3),
        ),
        SizedBox(height: FansivibeSpacing.lg),
        Text(
          'Already have a Fansivibe account?',
          style: FansivibeTypography.bodyMediumWithFamily.copyWith(
            color: FansivibeColors.secondary,
          ),
        ),
        SizedBox(height: FansivibeSpacing.md),
        _GateButton(
          label: 'Sign In',
          icon: Icons.login_rounded,
          onPressed: onSignIn,
        ),
      ],
    );
  }
}

class _GateButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final VoidCallback onPressed;

  const _GateButton({
    required this.label,
    required this.icon,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return FilledButton.icon(
      onPressed: onPressed,
      icon: Icon(icon, size: 18),
      label: Text(label, textAlign: TextAlign.center),
      style: FilledButton.styleFrom(
        backgroundColor: Colors.transparent,
        foregroundColor: FansivibeColors.primary,
        side: BorderSide(
          color: FansivibeColors.primary.withValues(alpha: 0.35),
          width: 1.2,
        ),
        shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.fullBorder),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
        textStyle: FansivibeTypography.bodyMediumWithFamily.copyWith(
          fontWeight: FontWeight.w600,
          height: 1.3,
        ),
      ),
    );
  }
}

class _PrivacyNote extends StatelessWidget {
  const _PrivacyNote();

  @override
  Widget build(BuildContext context) {
    return Wrap(
      alignment: WrapAlignment.center,
      crossAxisAlignment: WrapCrossAlignment.center,
      spacing: FansivibeSpacing.sm,
      runSpacing: FansivibeSpacing.xs,
      children: [
        Icon(
          Icons.lock_outline_rounded,
          size: 13,
          color: FansivibeColors.secondary.withValues(alpha: 0.6),
        ),
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
