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

/// First-visit Home for the light path (Explore Without Scanning).
///
/// The user chose a style direction but has not scanned a photo yet.
/// This screen acknowledges their choice, makes the single next step
/// (one photo) impossible to miss, and offers immediate editorial value
/// (curated look + tools) while the full analysis is pending.
class FirstTimeLightPathHomeScreen extends StatefulWidget {
  final String? vibeName;

  const FirstTimeLightPathHomeScreen({super.key, this.vibeName});

  @override
  State<FirstTimeLightPathHomeScreen> createState() =>
      _FirstTimeLightPathHomeScreenState();
}

class _FirstTimeLightPathHomeScreenState
    extends State<FirstTimeLightPathHomeScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _headerAnim;
  late Animation<double> _vibeAnim;
  late Animation<double> _analysisAnim;
  late Animation<double> _lookAnim;
  late Animation<double> _toolsAnim;
  late Animation<double> _quoteAnim;

  StyleVibe? get _vibe => _vibeFromName(widget.vibeName);

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2000),
    );
    _headerAnim = _buildAnim(0.0, 0.18);
    _vibeAnim = _buildAnim(0.12, 0.35);
    _analysisAnim = _buildAnim(0.28, 0.52);
    _lookAnim = _buildAnim(0.42, 0.65);
    _toolsAnim = _buildAnim(0.55, 0.78);
    _quoteAnim = _buildAnim(0.68, 0.95);
    _controller.forward();
  }

  Animation<double> _buildAnim(double start, double end) {
    return Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(
        parent: _controller,
        curve: Interval(start, end, curve: Curves.easeOutCubic),
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
            final contentMaxWidth = maxWidth > 600 ? 560.0 : double.infinity;

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
                        SizedBox(height: FansivibeSpacing.sm),
                        _buildAnimatedSection(_headerAnim, _buildHeader()),
                        SizedBox(height: FansivibeSpacing.xl + 4),
                        _buildAnimatedSection(_vibeAnim, _buildVibeCard()),
                        SizedBox(height: FansivibeSpacing.xl + 4),
                        _buildAnimatedSection(
                          _analysisAnim,
                          _buildAnalysisCard(context),
                        ),
                        SizedBox(height: FansivibeSpacing.xl + 4),
                        _buildAnimatedSection(
                          _lookAnim,
                          _buildPreviewLook(context),
                        ),
                        SizedBox(height: FansivibeSpacing.xl + 4),
                        _buildAnimatedSection(
                          _toolsAnim,
                          _buildQuickTools(context),
                        ),
                        SizedBox(height: FansivibeSpacing.xl + 4),
                        _buildAnimatedSection(_quoteAnim, _buildAiQuote()),
                        SizedBox(height: FansivibeSpacing.xxxl),
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
            offset: Offset(0, 20 * (1 - anim.value)),
            child: child,
          ),
        );
      },
    );
  }

  Widget _buildSectionLabel(String text) {
    return Row(
      children: [
        Container(
          height: 2,
          width: 32,
          decoration: BoxDecoration(
            color: FansivibeColors.primary,
            borderRadius: BorderRadius.circular(1),
          ),
        ),
        SizedBox(width: FansivibeSpacing.sm + 4),
        Text(
          text,
          style: FansivibeTypography.labelMediumWithFamily.copyWith(
            color: FansivibeColors.primary,
            letterSpacing: 2.0,
            fontSize: 11,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }

  Widget _craftedCard({
    required Widget child,
    EdgeInsetsGeometry padding = const EdgeInsets.all(FansivibeSpacing.lg),
    Alignment glowAlign = Alignment.topRight,
    Color glowColor = FansivibeColors.primary,
    double glowOpacity = 0.06,
  }) {
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        borderRadius: FansivibeRadius.lgBorder,
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            FansivibeColors.surfaceContainerLow,
            FansivibeColors.surfaceContainer.withValues(alpha: 0.55),
          ],
        ),
      ),
      child: ClipRRect(
        borderRadius: FansivibeRadius.lgBorder,
        child: Stack(
          children: [
            Positioned.fill(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: RadialGradient(
                    radius: 1.15,
                    center: glowAlign,
                    colors: [
                      glowColor.withValues(alpha: glowOpacity),
                      Colors.transparent,
                    ],
                  ),
                ),
              ),
            ),
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              child: Container(
                height: 1,
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      Colors.transparent,
                      glowColor.withValues(alpha: 0.22),
                      Colors.transparent,
                    ],
                  ),
                ),
              ),
            ),
            Padding(padding: padding, child: child),
          ],
        ),
      ),
    );
  }

  Widget _medallion({
    required IconData icon,
    double size = 56,
    double iconSize = 22,
    Color accent = FansivibeColors.primary,
    Color iconColor = FansivibeColors.primary,
  }) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: RadialGradient(
          radius: 1.0,
          colors: [
            accent.withValues(alpha: 0.22),
            accent.withValues(alpha: 0.04),
          ],
        ),
        border: Border.all(color: accent.withValues(alpha: 0.28), width: 1),
      ),
      child: Center(
        child: Container(
          width: size * 0.64,
          height: size * 0.64,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: FansivibeColors.surfaceContainerHigh,
            border: Border.all(color: accent.withValues(alpha: 0.18), width: 1),
          ),
          child: Icon(icon, size: iconSize, color: iconColor),
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          height: 3,
          width: 48,
          decoration: BoxDecoration(
            color: FansivibeColors.primary,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        SizedBox(height: FansivibeSpacing.md),
        Text(
          'WELCOME TO FANSIVIBE',
          style: FansivibeTypography.labelMediumWithFamily.copyWith(
            color: FansivibeColors.primary,
            letterSpacing: 3.0,
            fontSize: 12,
            fontWeight: FontWeight.w600,
          ),
        ),
        SizedBox(height: FansivibeSpacing.sm),
        Text(
          'Your style journey\nbegins today.',
          style: FansivibeTypography.displayLargeWithFamily.copyWith(
            fontSize: 40,
            height: 1.08,
            letterSpacing: -0.5,
          ),
        ),
        SizedBox(height: FansivibeSpacing.sm + 4),
        Text(
          'You\'ve set a direction. Curated looks and tools await — '
          'and one photo unlocks your complete Style DNA.',
          style: FansivibeTypography.bodyLargeWithFamily.copyWith(
            color: FansivibeColors.secondary,
            height: 1.5,
            fontSize: 16,
          ),
        ),
      ],
    );
  }

  Widget _buildVibeCard() {
    final motif = _vibe != null ? _vibeMotifs[_vibe!] : null;
    final accent = motif?.gradient.first ?? FansivibeColors.primary;
    return _craftedCard(
      glowColor: accent,
      glowOpacity: 0.08,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildSectionLabel('STYLE DIRECTION'),
          SizedBox(height: FansivibeSpacing.md + 4),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _medallion(
                icon: motif?.icon ?? Icons.auto_awesome_rounded,
                accent: accent,
                iconColor: FansivibeColors.primary,
              ),
              SizedBox(width: FansivibeSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _vibe?.label ?? 'Open to Everything',
                      style: FansivibeTypography.titleLargeWithFamily.copyWith(
                        fontSize: 22,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    SizedBox(height: FansivibeSpacing.xs),
                    Text(
                      _vibe?.description ??
                          'You haven\'t chosen a direction yet — and that\'s fine.',
                      style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                        color: FansivibeColors.secondary,
                        fontSize: 13,
                        height: 1.5,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          SizedBox(height: FansivibeSpacing.md + 4),
          Container(
            width: double.infinity,
            height: 1,
            color: FansivibeColors.outlineVariant.withValues(alpha: 0.45),
          ),
          SizedBox(height: FansivibeSpacing.md),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                Icons.auto_awesome_rounded,
                size: 13,
                color: FansivibeColors.primary,
              ),
              SizedBox(width: FansivibeSpacing.sm),
              Expanded(
                child: Text(
                  _vibe != null
                      ? 'Every recommendation from here on will be tuned toward '
                            'this direction.'
                      : 'Skip the guesswork — one photo lets our AI define a '
                            'direction for you.',
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.secondary.withValues(alpha: 0.85),
                    fontSize: 13,
                    height: 1.5,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildAnalysisCard(BuildContext context) {
    return _craftedCard(
      padding: const EdgeInsets.fromLTRB(24, 28, 24, 24),
      glowAlign: Alignment.topLeft,
      glowOpacity: 0.12,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _medallion(
                icon: Icons.camera_alt_rounded,
                size: 56,
                iconSize: 26,
              ),
              SizedBox(width: FansivibeSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'YOUR ANALYSIS IS WAITING',
                      style: FansivibeTypography.labelSmallWithFamily.copyWith(
                        color: FansivibeColors.primary,
                        letterSpacing: 1.8,
                        fontSize: 10,
                      ),
                    ),
                    SizedBox(height: FansivibeSpacing.xs),
                    Text(
                      'Unlock your Style DNA',
                      style: FansivibeTypography.headlineMediumWithFamily
                          .copyWith(fontSize: 24, height: 1.2),
                    ),
                    SizedBox(height: FansivibeSpacing.sm + 2),
                    Text(
                      'One photo. Fansivibe AI reads your proportions, palette, '
                      'and best silhouettes — then scores your look and starts '
                      'personalizing everything.',
                      style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                        color: FansivibeColors.secondary,
                        fontSize: 14,
                        height: 1.5,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          SizedBox(height: FansivibeSpacing.lg),
          FansiButton.primary(
            label: 'Analyze My Style',
            icon: Icons.camera_alt_outlined,
            onPressed: () => context.pushNamed(RouteNames.cameraPermission),
          ),
          SizedBox(height: FansivibeSpacing.sm + 4),
          Center(
            child: FansiButton.tertiary(
              label: 'Explore looks while you wait',
              onPressed: () => context.goNamed(RouteNames.discover),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPreviewLook(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionLabel('A PREVIEW OF WHAT\'S WAITING'),
        SizedBox(height: FansivibeSpacing.sm),
        Text(
          'A curated first look — your analysis will refine these picks.',
          style: FansivibeTypography.bodyLargeWithFamily.copyWith(
            color: FansivibeColors.secondary,
            fontSize: 15,
          ),
        ),
        SizedBox(height: FansivibeSpacing.md + 4),
        ClipRRect(
          borderRadius: FansivibeRadius.mdBorder,
          child: Column(children: [_buildLookImage(), _buildLookContent()]),
        ),
      ],
    );
  }

  Widget _buildLookImage() {
    return Container(
      height: 200,
      width: double.infinity,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            FansivibeColors.surfaceContainerHigh,
            FansivibeColors.surfaceContainer.withValues(alpha: 0.8),
            FansivibeColors.surface,
          ],
          stops: const [0.0, 0.5, 1.0],
        ),
      ),
      child: Stack(
        fit: StackFit.expand,
        children: [
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: RadialGradient(
                radius: 1.0,
                center: const Alignment(0.0, -0.7),
                colors: [
                  FansivibeColors.primary.withValues(alpha: 0.14),
                  Colors.transparent,
                ],
              ),
            ),
          ),
          Center(
            child: Icon(
              Icons.checkroom_rounded,
              size: 72,
              color: FansivibeColors.primary.withValues(alpha: 0.12),
            ),
          ),
          Positioned(
            top: FansivibeSpacing.md,
            left: FansivibeSpacing.md,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: FansivibeColors.surface.withValues(alpha: 0.72),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 5,
                    height: 5,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: FansivibeColors.primary,
                    ),
                  ),
                  SizedBox(width: 6),
                  Text(
                    'EDITOR\'S PICK',
                    style: FansivibeTypography.labelSmallWithFamily.copyWith(
                      color: FansivibeColors.primary,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 2.0,
                      fontSize: 9,
                    ),
                  ),
                ],
              ),
            ),
          ),
          Positioned(
            bottom: FansivibeSpacing.md,
            right: FansivibeSpacing.md,
            child: Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: FansivibeColors.surface.withValues(alpha: 0.6),
                borderRadius: FansivibeRadius.fullBorder,
                border: Border.all(
                  color: FansivibeColors.primary.withValues(alpha: 0.18),
                  width: 1,
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.star_rounded,
                    size: 14,
                    color: FansivibeColors.primary,
                  ),
                  SizedBox(width: FansivibeSpacing.xs),
                  Text(
                    '87',
                    style: FansivibeTypography.labelSmallWithFamily.copyWith(
                      color: FansivibeColors.primary,
                      fontWeight: FontWeight.w700,
                      fontSize: 13,
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

  Widget _buildLookContent() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 24),
      decoration: BoxDecoration(color: FansivibeColors.surfaceContainer),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Modern Minimalist',
            style: FansivibeTypography.displayLargeWithFamily.copyWith(
              fontSize: 26,
              fontWeight: FontWeight.w500,
              height: 1.1,
            ),
          ),
          SizedBox(height: FansivibeSpacing.sm + 2),
          Text(
            'Clean lines, relaxed sophistication. A starting point we\'ll '
            'tune to you once your analysis is ready.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
              height: 1.5,
              fontSize: 14,
            ),
          ),
          SizedBox(height: FansivibeSpacing.md + 4),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _editorialTag('Unstructured Blazer'),
              _editorialTag('Merino Crewneck'),
              _editorialTag('Tapered Trousers'),
              _editorialTag('Chelsea Boots'),
            ],
          ),
          SizedBox(height: FansivibeSpacing.md + 4),
          FansiButton.primary(
            label: 'Try This Look',
            icon: Icons.arrow_forward_rounded,
            onPressed: () => context.pushNamed(RouteNames.dailyOutfit),
          ),
        ],
      ),
    );
  }

  Widget _editorialTag(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerHigh.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: FansivibeColors.primary.withValues(alpha: 0.08),
          width: 0.5,
        ),
      ),
      child: Text(
        label,
        style: FansivibeTypography.labelSmallWithFamily.copyWith(
          color: FansivibeColors.secondary,
          fontSize: 11,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }

  Widget _buildQuickTools(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionLabel('EXPLORE THE ATELIER'),
        SizedBox(height: FansivibeSpacing.sm),
        Text(
          'Everything here works without an analysis.',
          style: FansivibeTypography.bodyLargeWithFamily.copyWith(
            color: FansivibeColors.secondary,
            fontSize: 15,
          ),
        ),
        SizedBox(height: FansivibeSpacing.md + 4),
        SizedBox(
          height: 118,
          child: ListView(
            scrollDirection: Axis.horizontal,
            physics: const BouncingScrollPhysics(),
            children: [
              _glassTool(
                icon: Icons.camera_alt_outlined,
                label: 'Scan\nOutfit',
                onTap: () => context.pushNamed(RouteNames.scanOutfit),
              ),
              _glassTool(
                icon: Icons.checkroom_outlined,
                label: 'Add\nWardrobe',
                onTap: () => context.goNamed(RouteNames.wardrobe),
              ),
              _glassTool(
                icon: Icons.face_rounded,
                label: 'Hairstyle\nStudio',
                onTap: () => context.pushNamed(RouteNames.hairstyle),
              ),
              _glassTool(
                icon: Icons.lightbulb_outline_rounded,
                label: 'Style\nTips',
                onTap: () => context.goNamed(RouteNames.discover),
              ),
              _glassTool(
                icon: Icons.event_outlined,
                label: 'Event\nStyling',
                onTap: () => context.goNamed(RouteNames.events),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _glassTool({
    required IconData icon,
    required String label,
    required VoidCallback onTap,
  }) {
    return Semantics(
      button: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: FansivibeRadius.mdBorder,
        child: Padding(
          padding: const EdgeInsets.only(right: FansivibeSpacing.sm + 4),
          child: ClipRRect(
            borderRadius: FansivibeRadius.mdBorder,
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
              child: Container(
                width: 88,
                padding: const EdgeInsets.symmetric(
                  vertical: 14,
                  horizontal: 12,
                ),
                decoration: BoxDecoration(
                  color: FansivibeColors.surfaceContainerLow.withValues(
                    alpha: 0.55,
                  ),
                  borderRadius: FansivibeRadius.mdBorder,
                  border: Border.all(
                    color: FansivibeColors.primary.withValues(alpha: 0.06),
                    width: 0.5,
                  ),
                ),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: FansivibeColors.primary.withValues(alpha: 0.1),
                        borderRadius: FansivibeRadius.smBorder,
                      ),
                      child: Icon(
                        icon,
                        size: 20,
                        color: FansivibeColors.primary,
                      ),
                    ),
                    SizedBox(height: FansivibeSpacing.sm),
                    Flexible(
                      child: Text(
                        label,
                        style: FansivibeTypography.labelSmallWithFamily
                            .copyWith(
                              color: FansivibeColors.onSurface,
                              fontSize: 10,
                              fontWeight: FontWeight.w500,
                              height: 1.3,
                            ),
                        textAlign: TextAlign.center,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildAiQuote() {
    return _craftedCard(
      glowAlign: Alignment.bottomLeft,
      glowOpacity: 0.07,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _medallion(
                icon: Icons.auto_awesome_rounded,
                size: 36,
                iconSize: 18,
              ),
              SizedBox(width: FansivibeSpacing.sm + 4),
              Text(
                'AI IS READY WHEN YOU ARE',
                style: FansivibeTypography.labelMediumWithFamily.copyWith(
                  color: FansivibeColors.primary,
                  letterSpacing: 2.0,
                  fontSize: 10,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          SizedBox(height: FansivibeSpacing.md + 4),
          Text(
            'The most powerful style tool is already in your pocket.',
            style: FansivibeTypography.titleLargeWithFamily.copyWith(
              fontSize: 20,
              height: 1.35,
              fontWeight: FontWeight.w500,
            ),
          ),
          SizedBox(height: FansivibeSpacing.sm + 4),
          Text(
            'Take your first photo whenever you\'re ready. Your Style DNA, '
            'score, and personalized recommendations begin there.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
              height: 1.6,
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }
}

class _VibeMotif {
  final IconData icon;
  final List<Color> gradient;
  const _VibeMotif(this.icon, this.gradient);
}

const Map<StyleVibe, _VibeMotif> _vibeMotifs = {
  StyleVibe.minimalist: _VibeMotif(Icons.remove_rounded, [
    Color(0xFFD4D0C8),
    Color(0xFF8A8580),
  ]),
  StyleVibe.bold: _VibeMotif(Icons.bolt_rounded, [
    Color(0xFFD4456A),
    Color(0xFF1E3A8A),
  ]),
  StyleVibe.classic: _VibeMotif(Icons.diamond_outlined, [
    Color(0xFFC5A059),
    Color(0xFFF5EDD6),
  ]),
  StyleVibe.trendy: _VibeMotif(Icons.trending_up_rounded, [
    Color(0xFF6B21A8),
    Color(0xFF00BFFF),
  ]),
  StyleVibe.natural: _VibeMotif(Icons.eco_outlined, [
    Color(0xFF6B8E23),
    Color(0xFFD2691E),
  ]),
  StyleVibe.edgy: _VibeMotif(Icons.flash_on_rounded, [
    Color(0xFF1A1A2E),
    Color(0xFFE94560),
  ]),
};

StyleVibe? _vibeFromName(String? name) {
  if (name == null) return null;
  for (final vibe in StyleVibe.values) {
    if (vibe.name == name) return vibe;
  }
  return null;
}
