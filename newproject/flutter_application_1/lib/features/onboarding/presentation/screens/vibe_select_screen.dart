import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/onboarding/data/onboarding_data.dart';
import 'package:fansivibe/features/onboarding/presentation/widgets/vibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';

class VibeSelectScreen extends StatefulWidget {
  const VibeSelectScreen({super.key});

  @override
  State<VibeSelectScreen> createState() => _VibeSelectScreenState();
}

class _VibeSelectScreenState extends State<VibeSelectScreen>
    with SingleTickerProviderStateMixin {
  StyleVibe? _selected;
  bool _photoPath = true;

  late AnimationController _animController;
  late Animation<double> _questionAnim;
  late List<Animation<double>> _cardAnims;

  static const _vibeVisuals = [
    _VibeVisual(
      [Color(0xFFD4D0C8), Color(0xFF8A8580)],
      [Offset(0.2, 0.0), Offset(0.5, 0.0), Offset(0.3, 0.0)],
    ),
    _VibeVisual(
      [Color(0xFFD4456A), Color(0xFF1E3A8A)],
      [Offset(0.1, 0.3), Offset(0.6, 0.1), Offset(0.4, 0.6)],
    ),
    _VibeVisual(
      [Color(0xFFC5A059), Color(0xFFF5EDD6)],
      [Offset(0.2, 0.2), Offset(0.5, 0.5), Offset(0.8, 0.8)],
    ),
    _VibeVisual(
      [Color(0xFF6B21A8), Color(0xFF00BFFF)],
      [Offset(0.0, 0.4), Offset(0.7, 0.0), Offset(0.3, 0.7)],
    ),
    _VibeVisual(
      [Color(0xFF6B8E23), Color(0xFFD2691E)],
      [Offset(0.2, 0.1), Offset(0.8, 0.3), Offset(0.5, 0.9)],
    ),
    _VibeVisual(
      [Color(0xFF1A1A2E), Color(0xFFE94560)],
      [Offset(0.0, 0.0), Offset(0.9, 0.4), Offset(0.2, 0.8)],
    ),
  ];

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
    _questionAnim = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(
        parent: _animController,
        curve: const Interval(0.0, 0.3, curve: Curves.easeOut),
      ),
    );
    _cardAnims = List.generate(6, (i) {
      return Tween<double>(begin: 0, end: 1).animate(
        CurvedAnimation(
          parent: _animController,
          curve: Interval(
            0.15 + i * 0.08,
            0.6 + i * 0.05,
            curve: Curves.easeOut,
          ),
        ),
      );
    });
    _animController.forward();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final extra = GoRouterState.of(context).extra as Map<String, dynamic>?;
    if (extra != null && extra.containsKey('photoPath')) {
      _photoPath = extra['photoPath'] as bool;
    }
  }

  @override
  void dispose() {
    _animController.dispose();
    super.dispose();
  }

  void _onContinue() {
    if (_photoPath) {
      context.pushNamed(
        RouteNames.cameraPermission,
        extra: {'vibe': _selected?.name},
      );
    } else {
      context.goNamed(RouteNames.home, extra: {'vibe': _selected?.name});
    }
  }

  void _onSkip() {
    if (_photoPath) {
      context.pushNamed(RouteNames.cameraPermission, extra: {'vibe': null});
    } else {
      context.goNamed(RouteNames.home, extra: {'vibe': null});
    }
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
                        SizedBox(height: FansivibeSpacing.xl + 8),
                        AnimatedBuilder(
                          animation: _questionAnim,
                          builder: (context, _) {
                            return Opacity(
                              opacity: _questionAnim.value,
                              child: Column(
                                children: [
                                  Text(
                                    'Which style feels\nmost like you?',
                                    textAlign: TextAlign.center,
                                    style: FansivibeTypography
                                        .headlineMediumWithFamily
                                        .copyWith(fontSize: 28, height: 1.2),
                                  ),
                                  SizedBox(height: FansivibeSpacing.sm),
                                  Text(
                                    'Choose one that resonates',
                                    style: FansivibeTypography
                                        .bodyMediumWithFamily
                                        .copyWith(
                                          color: FansivibeColors.secondary,
                                        ),
                                  ),
                                ],
                              ),
                            );
                          },
                        ),
                        SizedBox(height: FansivibeSpacing.xl),
                        GridView.count(
                          crossAxisCount: 2,
                          shrinkWrap: true,
                          physics: const NeverScrollableScrollPhysics(),
                          mainAxisSpacing: FansivibeSpacing.md,
                          crossAxisSpacing: FansivibeSpacing.md,
                          childAspectRatio: 0.65,
                          children: List.generate(6, (i) {
                            final vibe = StyleVibe.values[i];
                            final visual = _vibeVisuals[i];
                            return AnimatedBuilder(
                              animation: _cardAnims[i],
                              builder: (context, _) {
                                return Transform.translate(
                                  offset: Offset(
                                    0,
                                    60 * (1 - _cardAnims[i].value),
                                  ),
                                  child: Opacity(
                                    opacity: _cardAnims[i].value,
                                    child: VibeCard(
                                      label: vibe.label,
                                      gradientColors: visual.gradientColors,
                                      lineOffsets: visual.lineOffsets,
                                      isSelected: _selected == vibe,
                                      onTap: () => setState(() {
                                        _selected = (_selected == vibe)
                                            ? null
                                            : vibe;
                                      }),
                                    ),
                                  ),
                                );
                              },
                            );
                          }),
                        ),
                        SizedBox(height: FansivibeSpacing.lg),
                        AnimatedOpacity(
                          opacity: _selected != null ? 1.0 : 0.3,
                          duration: const Duration(milliseconds: 200),
                          child: FansiButton.primary(
                            label: 'Continue',
                            onPressed: _selected != null ? _onContinue : null,
                          ),
                        ),
                        SizedBox(height: FansivibeSpacing.sm + 4),
                        FansiButton.tertiary(
                          label: "I'm not sure — skip for now",
                          onPressed: _onSkip,
                        ),
                        SizedBox(height: FansivibeSpacing.xl),
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

class _VibeVisual {
  final List<Color> gradientColors;
  final List<Offset> lineOffsets;
  const _VibeVisual(this.gradientColors, this.lineOffsets);
}
