import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/onboarding/data/onboarding_data.dart';
import 'package:fansivibe/features/onboarding/presentation/widgets/animated_score_counter.dart';
import 'package:fansivibe/features/onboarding/presentation/widgets/color_palette_display.dart';
import 'package:fansivibe/features/onboarding/presentation/widgets/ai_capability_icon.dart';
import 'package:fansivibe/features/onboarding/presentation/widgets/analysis_insight_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';

class YourAnalysisScreen extends StatefulWidget {
  const YourAnalysisScreen({super.key});

  @override
  State<YourAnalysisScreen> createState() => _YourAnalysisScreenState();
}

class _YourAnalysisScreenState extends State<YourAnalysisScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _scoreAnim;
  late Animation<double> _paletteAnim;
  late Animation<double> _insight1Anim;
  late Animation<double> _insight2Anim;
  late Animation<double> _insight3Anim;
  late Animation<double> _progressAnim;
  late Animation<double> _ctaAnim;

  static const _mockPalette = [
    PaletteSwatch(color: 0xFF2D2D2D, label: 'Charcoal'),
    PaletteSwatch(color: 0xFF8B7D6B, label: 'Taupe'),
    PaletteSwatch(color: 0xFFC5A059, label: 'Gold'),
    PaletteSwatch(color: 0xFFF5F0EB, label: 'Cream'),
    PaletteSwatch(color: 0xFF4A6741, label: 'Sage'),
  ];

  static const _mockScore = 82;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
    );
    _scoreAnim = _buildAnim(0.0, 0.3);
    _paletteAnim = _buildAnim(0.2, 0.45);
    _insight1Anim = _buildAnim(0.3, 0.55);
    _insight2Anim = _buildAnim(0.4, 0.65);
    _insight3Anim = _buildAnim(0.5, 0.75);
    _progressAnim = _buildAnim(0.55, 0.85);
    _ctaAnim = _buildAnim(0.7, 1.0);
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

  void _onSave() {
    context.pushNamed(RouteNames.accountCreation);
  }

  void _onRetake() {
    if (context.canPop()) {
      context.pop();
    } else {
      context.goNamed(RouteNames.photoCapture);
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
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SizedBox(height: FansivibeSpacing.lg),
                        _buildScoreSection(),
                        SizedBox(height: FansivibeSpacing.xl),
                        _buildAnimatedSection(
                          _paletteAnim,
                          ColorPaletteDisplay(swatches: _mockPalette),
                        ),
                        SizedBox(height: FansivibeSpacing.xl),
                        Text(
                          'AI Insights',
                          style: FansivibeTypography.headlineMediumWithFamily
                              .copyWith(fontSize: 20),
                        ),
                        SizedBox(height: FansivibeSpacing.md),
                        _buildAnimatedSection(
                          _insight1Anim,
                          const AnalysisInsightCard(
                            icon: Icons.accessibility_new_rounded,
                            title: 'Strong Silhouette',
                            body:
                                'Your balanced proportions create a clean foundation. Structured shoulders enhance your natural frame.',
                          ),
                        ),
                        SizedBox(height: FansivibeSpacing.sm + 4),
                        _buildAnimatedSection(
                          _insight2Anim,
                          const AnalysisInsightCard(
                            icon: Icons.palette_outlined,
                            title: 'Color Harmony',
                            body:
                                'Your palette leans toward warm neutrals. Jewel tones would add depth while maintaining your refined aesthetic.',
                          ),
                        ),
                        SizedBox(height: FansivibeSpacing.sm + 4),
                        _buildAnimatedSection(
                          _insight3Anim,
                          const AnalysisInsightCard(
                            icon: Icons.tune_rounded,
                            title: 'Refinement Tip',
                            body:
                                'Try a tapered hem on your trousers for a cleaner line from waist to shoe. Small adjustments, big impact.',
                          ),
                        ),
                        SizedBox(height: FansivibeSpacing.xl),
                        _buildProgressSection(),
                        SizedBox(height: FansivibeSpacing.xl),
                        _buildAnimatedSection(
                          _ctaAnim,
                          Column(
                            children: [
                              FansiButton.primary(
                                label: 'Save My Progress',
                                icon: Icons.save_rounded,
                                onPressed: _onSave,
                              ),
                              SizedBox(height: FansivibeSpacing.sm + 4),
                              FansiButton.tertiary(
                                label: 'Retake Photo',
                                onPressed: _onRetake,
                              ),
                            ],
                          ),
                        ),
                        SizedBox(height: FansivibeSpacing.xxl),
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

  Widget _buildAnimatedSection(Animation<double> anim, Widget child) {
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

  Widget _buildScoreSection() {
    return _buildAnimatedSection(
      _scoreAnim,
      Center(
        child: Column(
          children: [
            Container(
              width: 160,
              height: 160,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(
                  colors: [
                    FansivibeColors.primary.withValues(alpha: 0.06),
                    Colors.transparent,
                  ],
                  stops: const [0.0, 1.0],
                ),
              ),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  AnimatedScoreCounter(targetScore: _mockScore, fontSize: 64),
                  Text(
                    'Style Score',
                    style: FansivibeTypography.labelMediumWithFamily.copyWith(
                      color: FansivibeColors.secondary,
                      letterSpacing: 1.5,
                    ),
                  ),
                ],
              ),
            ),
            SizedBox(height: FansivibeSpacing.sm),
            Text(
              'Strong foundation with room to evolve.',
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.secondary,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildProgressSection() {
    return _buildAnimatedSection(
      _progressAnim,
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.auto_awesome_rounded,
                size: 16,
                color: FansivibeColors.primary,
              ),
              SizedBox(width: FansivibeSpacing.sm),
              Text(
                'Appearance Intelligence',
                style: FansivibeTypography.titleLargeWithFamily.copyWith(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          SizedBox(height: FansivibeSpacing.md),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(FansivibeSpacing.md),
            decoration: BoxDecoration(
              color: FansivibeColors.surfaceContainerLow,
              borderRadius: FansivibeRadius.mdBorder,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '2 of 7 capabilities active',
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.secondary,
                  ),
                ),
                SizedBox(height: FansivibeSpacing.md),
                SizedBox(
                  height: 80,
                  child: ListView(
                    scrollDirection: Axis.horizontal,
                    physics: const BouncingScrollPhysics(),
                    children: allCapabilities.map((cap) {
                      return AiCapabilityIcon(capability: cap);
                    }).toList(),
                  ),
                ),
                SizedBox(height: FansivibeSpacing.sm),
                Text(
                  'Try more features to unlock your full Appearance Intelligence',
                  style: FansivibeTypography.labelSmallWithFamily.copyWith(
                    color: FansivibeColors.secondary.withValues(alpha: 0.5),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
