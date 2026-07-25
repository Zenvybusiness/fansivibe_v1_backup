import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/onboarding/data/onboarding_data.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

class FirstTimeHomeScreen extends StatefulWidget {
  final String? displayName;

  const FirstTimeHomeScreen({super.key, this.displayName});

  @override
  State<FirstTimeHomeScreen> createState() => _FirstTimeHomeScreenState();
}

class _FirstTimeHomeScreenState extends State<FirstTimeHomeScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _greetingAnim;
  late Animation<double> _heroCardAnim;
  late Animation<double> _recommendationAnim;
  late Animation<double> _capabilitiesAnim;
  late Animation<double> _quickActionsAnim;
  late Animation<double> _insightAnim;

  static const _mockScore = 82;
  static const _mockDna = 'Refined Minimalist';
  static const _mockPalette = [
    PaletteSwatch(color: 0xFF2D2D2D, label: 'Charcoal'),
    PaletteSwatch(color: 0xFF8B7D6B, label: 'Taupe'),
    PaletteSwatch(color: 0xFFC5A059, label: 'Gold'),
    PaletteSwatch(color: 0xFFF5F0EB, label: 'Cream'),
    PaletteSwatch(color: 0xFF4A6741, label: 'Sage'),
  ];

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1800),
    );
    _greetingAnim = _buildAnim(0.0, 0.2);
    _heroCardAnim = _buildAnim(0.15, 0.4);
    _recommendationAnim = _buildAnim(0.3, 0.55);
    _capabilitiesAnim = _buildAnim(0.45, 0.7);
    _quickActionsAnim = _buildAnim(0.6, 0.82);
    _insightAnim = _buildAnim(0.75, 1.0);
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: FansivibeColors.surface,
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
                        SizedBox(height: FansivibeSpacing.lg),
                        _buildAnimatedSection(
                          _greetingAnim,
                          _buildHeroGreeting(),
                        ),
                        SizedBox(height: FansivibeSpacing.xl),
                        _buildAnimatedSection(
                          _heroCardAnim,
                          _buildHeroCard(),
                        ),
                        SizedBox(height: FansivibeSpacing.lg + 4),
                        _buildAnimatedSection(
                          _recommendationAnim,
                          _buildRecommendation(context),
                        ),
                        SizedBox(height: FansivibeSpacing.lg + 4),
                        _buildAnimatedSection(
                          _capabilitiesAnim,
                          _buildCapabilities(),
                        ),
                        SizedBox(height: FansivibeSpacing.lg + 4),
                        _buildAnimatedSection(
                          _quickActionsAnim,
                          _buildQuickActions(context),
                        ),
                        SizedBox(height: FansivibeSpacing.lg + 4),
                        _buildAnimatedSection(
                          _insightAnim,
                          _buildAiInsight(),
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
            offset: Offset(0, 24 * (1 - anim.value)),
            child: child,
          ),
        );
      },
    );
  }

  Widget _buildHeroGreeting() {
    final name = widget.displayName ?? 'you';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Welcome to Fansivibe',
          style: FansivibeTypography.labelMediumWithFamily.copyWith(
            color: FansivibeColors.primary,
            letterSpacing: 2.0,
            fontSize: 13,
            fontWeight: FontWeight.w600,
          ),
        ),
        SizedBox(height: FansivibeSpacing.sm),
        Text(
          'Your analysis is ready, $name.',
          style: FansivibeTypography.displayLargeWithFamily.copyWith(
            fontSize: 36,
            height: 1.15,
          ),
        ),
        SizedBox(height: FansivibeSpacing.sm + 4),
        Text(
          'We\'ve analyzed your features and style preferences. Here\'s what we discovered — your personal style journey starts now.',
          style: FansivibeTypography.bodyMediumWithFamily.copyWith(
            color: FansivibeColors.secondary,
            height: 1.5,
            fontSize: 15,
          ),
        ),
      ],
    );
  }

  Widget _buildHeroCard() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(24, 28, 24, 24),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            FansivibeColors.surfaceContainerLow,
            FansivibeColors.surfaceContainer,
          ],
        ),
        borderRadius: FansivibeRadius.lgBorder,
        boxShadow: [
          BoxShadow(
            color: FansivibeColors.primary.withValues(alpha: 0.06),
            blurRadius: 24,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              _buildScoreBadge(),
              SizedBox(width: FansivibeSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Style Score',
                      style: FansivibeTypography.labelMediumWithFamily.copyWith(
                        color: FansivibeColors.secondary,
                        letterSpacing: 1.2,
                        fontSize: 11,
                      ),
                    ),
                    SizedBox(height: FansivibeSpacing.xs),
                    Text(
                      _mockDna,
                      style: FansivibeTypography.titleLargeWithFamily.copyWith(
                        fontSize: 20,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          SizedBox(height: FansivibeSpacing.lg),
          _buildColorPalette(),
          SizedBox(height: FansivibeSpacing.lg),
          _buildInsightPreview(),
        ],
      ),
    );
  }

  Widget _buildScoreBadge() {
    return Container(
      width: 80,
      height: 80,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: RadialGradient(
          colors: [
            FansivibeColors.primary.withValues(alpha: 0.1),
            FansivibeColors.primary.withValues(alpha: 0.02),
            Colors.transparent,
          ],
          stops: const [0.0, 0.5, 1.0],
        ),
      ),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              '$_mockScore',
              style: FansivibeTypography.displayLargeWithFamily.copyWith(
                fontSize: 32,
                fontWeight: FontWeight.w600,
                color: FansivibeColors.primary,
              ),
            ),
            Text(
              'of 100',
              style: FansivibeTypography.labelSmallWithFamily.copyWith(
                fontSize: 9,
                color: FansivibeColors.secondary.withValues(alpha: 0.6),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildColorPalette() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Dominant Palette',
          style: FansivibeTypography.labelMediumWithFamily.copyWith(
            color: FansivibeColors.secondary,
            letterSpacing: 1.2,
            fontSize: 11,
          ),
        ),
        SizedBox(height: FansivibeSpacing.sm + 4),
        Row(
          children: [
            for (int i = 0; i < _mockPalette.length; i++)
              Padding(
                padding: EdgeInsets.only(
                  right: i < _mockPalette.length - 1
                      ? FansivibeSpacing.sm
                      : 0,
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: Color(_mockPalette[i].color),
                        borderRadius: FansivibeRadius.smBorder,
                        border: Border.all(
                          color: Colors.white.withValues(alpha: 0.08),
                          width: 1,
                        ),
                      ),
                    ),
                    SizedBox(height: FansivibeSpacing.xs),
                    Text(
                      _mockPalette[i].label,
                      style: FansivibeTypography.labelSmallWithFamily.copyWith(
                        fontSize: 9,
                        color: FansivibeColors.secondary.withValues(alpha: 0.7),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ],
    );
  }

  Widget _buildInsightPreview() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(FansivibeSpacing.md),
      decoration: BoxDecoration(
        color: FansivibeColors.primary.withValues(alpha: 0.06),
        borderRadius: FansivibeRadius.smBorder,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            Icons.auto_awesome_rounded,
            size: 16,
            color: FansivibeColors.primary,
          ),
          SizedBox(width: FansivibeSpacing.sm),
          Expanded(
            child: Text(
              'Your balanced proportions create a clean foundation. Structured shoulders enhance your natural frame.',
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.onSurface,
                fontSize: 13,
                height: 1.5,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRecommendation(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Your First Recommendation',
          style: FansivibeTypography.headlineMediumWithFamily.copyWith(
            fontSize: 20,
          ),
        ),
        SizedBox(height: FansivibeSpacing.md),
        ClipRRect(
          borderRadius: FansivibeRadius.mdBorder,
          child: Column(
            children: [
              _buildRecImageSection(context),
              _buildRecContent(context),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildRecImageSection(BuildContext context) {
    return Container(
      height: 180,
      width: double.infinity,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            FansivibeColors.surfaceContainerHigh,
            FansivibeColors.surfaceContainerLow,
          ],
        ),
      ),
      child: Stack(
        fit: StackFit.expand,
        children: [
          Center(
            child: Icon(
              Icons.checkroom_rounded,
              size: 64,
              color: FansivibeColors.primary.withValues(alpha: 0.15),
            ),
          ),
          Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.bottomCenter,
                end: Alignment.topCenter,
                colors: [
                  FansivibeColors.surface.withValues(alpha: 0.9),
                  Colors.transparent,
                  Colors.transparent,
                ],
                stops: const [0.0, 0.3, 1.0],
              ),
            ),
          ),
          Positioned(
            bottom: FansivibeSpacing.md,
            left: FansivibeSpacing.md,
            child: Container(
              padding: const EdgeInsets.symmetric(
                horizontal: 10,
                vertical: 5,
              ),
              decoration: BoxDecoration(
                color: FansivibeColors.primary.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(
                'AI RECOMMENDED',
                style: FansivibeTypography.labelSmallWithFamily.copyWith(
                  color: FansivibeColors.primary,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.8,
                  fontSize: 10,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRecContent(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 24),
      decoration: const BoxDecoration(
        color: FansivibeColors.surfaceContainer,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Modern Minimalist',
            style: FansivibeTypography.titleLargeWithFamily.copyWith(
              fontSize: 20,
            ),
          ),
          SizedBox(height: FansivibeSpacing.sm),
          Text(
            'Clean lines meet relaxed sophistication. This look complements your refined silhouette and warm neutral palette.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
              height: 1.5,
            ),
          ),
          SizedBox(height: FansivibeSpacing.md + 4),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _buildGarmentChip('Unstructured Blazer', Icons.checkroom_rounded),
              _buildGarmentChip('Merino Crewneck', Icons.person_rounded),
              _buildGarmentChip('Tapered Trousers', Icons.accessibility_rounded),
            ],
          ),
          SizedBox(height: FansivibeSpacing.md + 4),
          Text(
            'Why this suits you',
            style: FansivibeTypography.labelMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
              letterSpacing: 1.0,
              fontSize: 11,
            ),
          ),
          SizedBox(height: FansivibeSpacing.sm),
          Text(
            'Vertical lines and a tonal palette elongate your frame. The unstructured blazer adds polish without stiffness — matching your natural ease.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.secondary.withValues(alpha: 0.8),
              fontSize: 13,
              height: 1.5,
            ),
          ),
          SizedBox(height: FansivibeSpacing.md + 4),
          FansiButton.primary(
            label: 'Try This Look',
            icon: Icons.check_circle_outline_rounded,
            onPressed: () => context.pushNamed(RouteNames.dailyOutfit),
          ),
        ],
      ),
    );
  }

  Widget _buildGarmentChip(String label, IconData icon) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerHigh,
        borderRadius: FansivibeRadius.smBorder,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 13, color: FansivibeColors.secondary),
          SizedBox(width: FansivibeSpacing.xs + 2),
          Text(
            label,
            style: FansivibeTypography.labelSmallWithFamily.copyWith(
              color: FansivibeColors.secondary,
              fontSize: 11,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCapabilities() {
    return Column(
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
              'Continue Building Your Style',
              style: FansivibeTypography.headlineMediumWithFamily.copyWith(
                fontSize: 20,
              ),
            ),
          ],
        ),
        SizedBox(height: FansivibeSpacing.sm),
        Text(
          'Unlock the full power of your AI style intelligence.',
          style: FansivibeTypography.bodyMediumWithFamily.copyWith(
            color: FansivibeColors.secondary,
          ),
        ),
        SizedBox(height: FansivibeSpacing.md),
        ...allCapabilities.map(_buildCapabilityItem),
      ],
    );
  }

  Widget _buildCapabilityItem(AiCapability cap) {
    return Padding(
      padding: const EdgeInsets.only(bottom: FansivibeSpacing.sm + 4),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(FansivibeSpacing.md),
        decoration: BoxDecoration(
          color: cap.active
              ? FansivibeColors.primary.withValues(alpha: 0.04)
              : FansivibeColors.surfaceContainerLow,
          borderRadius: FansivibeRadius.mdBorder,
          border: cap.active
              ? Border.all(
                  color: FansivibeColors.primary.withValues(alpha: 0.12),
                  width: 1,
                )
              : null,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: cap.active
                    ? FansivibeColors.primary.withValues(alpha: 0.12)
                    : FansivibeColors.surfaceContainerHighest,
                border: cap.active
                    ? Border.all(
                        color: FansivibeColors.primary.withValues(alpha: 0.3),
                        width: 1.5,
                      )
                    : null,
              ),
              child: Center(
                child: Icon(
                  cap.active
                      ? Icons.check_circle_rounded
                      : Icons.lock_rounded,
                  size: 18,
                  color: cap.active
                      ? FansivibeColors.primary
                      : FansivibeColors.secondary.withValues(alpha: 0.5),
                ),
              ),
            ),
            SizedBox(width: FansivibeSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    cap.name,
                    style: FansivibeTypography.titleLargeWithFamily.copyWith(
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                      color: cap.active
                          ? FansivibeColors.primary
                          : FansivibeColors.onSurface,
                    ),
                  ),
                  SizedBox(height: FansivibeSpacing.xs),
                  Text(
                    cap.description,
                    style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                      color: FansivibeColors.secondary,
                      fontSize: 13,
                      height: 1.4,
                    ),
                  ),
                  if (!cap.active && cap.unlockHint != null) ...[
                    SizedBox(height: FansivibeSpacing.sm + 2),
                    GestureDetector(
                      onTap: () => _onUnlockCapability(cap.name),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 6,
                        ),
                        decoration: BoxDecoration(
                          color: FansivibeColors.primary.withValues(alpha: 0.08),
                          borderRadius: FansivibeRadius.fullBorder,
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              cap.unlockHint!,
                              style: FansivibeTypography.labelSmallWithFamily.copyWith(
                                color: FansivibeColors.primary,
                                fontWeight: FontWeight.w600,
                                fontSize: 11,
                              ),
                            ),
                            SizedBox(width: FansivibeSpacing.xs),
                            Icon(
                              Icons.arrow_forward_rounded,
                              size: 12,
                              color: FansivibeColors.primary,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildQuickActions(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Quick Actions',
          style: FansivibeTypography.headlineMediumWithFamily.copyWith(
            fontSize: 20,
          ),
        ),
        SizedBox(height: FansivibeSpacing.md),
        _buildGlassActionCard(
          context,
          icon: Icons.camera_alt_outlined,
          title: 'Scan Another Look',
          subtitle: 'Get AI analysis on any outfit',
          onTap: () => context.pushNamed(RouteNames.scanOutfit),
        ),
        SizedBox(height: FansivibeSpacing.sm + 4),
        _buildGlassActionCard(
          context,
          icon: Icons.checkroom_outlined,
          title: 'Add Wardrobe',
          subtitle: 'Build your digital wardrobe',
          onTap: () => context.goNamed(RouteNames.wardrobe),
        ),
        SizedBox(height: FansivibeSpacing.sm + 4),
        _buildGlassActionCard(
          context,
          icon: Icons.face_rounded,
          title: 'Explore Hairstyles',
          subtitle: 'Find your perfect hairstyle',
          onTap: () => context.pushNamed(RouteNames.hairstyle),
        ),
        SizedBox(height: FansivibeSpacing.sm + 4),
        _buildGlassActionCard(
          context,
          icon: Icons.lightbulb_outline_rounded,
          title: 'Discover Style Tips',
          subtitle: 'Personalized style insights',
          onTap: () => context.goNamed(RouteNames.discover),
        ),
      ],
    );
  }

  Widget _buildGlassActionCard(
    BuildContext context, {
    required IconData icon,
    required String title,
    required String subtitle,
    required VoidCallback onTap,
  }) {
    return Semantics(
      button: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: FansivibeRadius.mdBorder,
        child: ClipRRect(
          borderRadius: FansivibeRadius.mdBorder,
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 8, sigmaY: 8),
            child: Container(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
              decoration: BoxDecoration(
                color: FansivibeColors.surfaceContainerLow.withValues(alpha: 0.6),
                borderRadius: FansivibeRadius.mdBorder,
              ),
              child: Row(
                children: [
                  Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                      color: FansivibeColors.primary.withValues(alpha: 0.1),
                      borderRadius: FansivibeRadius.smBorder,
                    ),
                    child: Icon(icon, size: 22, color: FansivibeColors.primary),
                  ),
                  SizedBox(width: FansivibeSpacing.md),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          title,
                          style: FansivibeTypography.titleLargeWithFamily.copyWith(
                            fontSize: 15,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        SizedBox(height: FansivibeSpacing.xs),
                        Text(
                          subtitle,
                          style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                            color: FansivibeColors.secondary,
                            fontSize: 13,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Icon(
                    Icons.arrow_forward_rounded,
                    size: 18,
                    color: FansivibeColors.primary.withValues(alpha: 0.6),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildAiInsight() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(FansivibeSpacing.lg),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            FansivibeColors.primary.withValues(alpha: 0.06),
            FansivibeColors.surfaceContainerLow,
          ],
        ),
        borderRadius: FansivibeRadius.lgBorder,
        border: Border.all(
          color: FansivibeColors.primary.withValues(alpha: 0.1),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: FansivibeColors.primary.withValues(alpha: 0.12),
                  borderRadius: FansivibeRadius.smBorder,
                ),
                child: Icon(
                  Icons.auto_awesome_rounded,
                  size: 20,
                  color: FansivibeColors.primary,
                ),
              ),
              SizedBox(width: FansivibeSpacing.md),
              Text(
                'AI Insight',
                style: FansivibeTypography.labelMediumWithFamily.copyWith(
                  color: FansivibeColors.primary,
                  letterSpacing: 1.2,
                  fontSize: 11,
                ),
              ),
            ],
          ),
          SizedBox(height: FansivibeSpacing.md + 4),
          Text(
            'Your facial structure pairs exceptionally well with textured hairstyles.',
            style: FansivibeTypography.titleLargeWithFamily.copyWith(
              fontSize: 18,
              height: 1.35,
            ),
          ),
          SizedBox(height: FansivibeSpacing.sm + 4),
          Text(
            'Based on your face shape analysis, adding volume at the crown creates a balanced proportion with your jawline. Explore hairstyle recommendations to see what works best.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
              height: 1.6,
            ),
          ),
          SizedBox(height: FansivibeSpacing.md + 4),
          FansiButton.secondary(
            label: 'Explore Hairstyles',
            icon: Icons.arrow_forward_rounded,
            onPressed: () => context.pushNamed(RouteNames.hairstyle),
            expanded: false,
          ),
        ],
      ),
    );
  }

  void _onUnlockCapability(String name) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Coming soon: $name'),
        backgroundColor: FansivibeColors.surfaceContainerHighest,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: FansivibeRadius.smBorder,
        ),
        duration: const Duration(seconds: 2),
      ),
    );
  }
}
