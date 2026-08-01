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
  late Animation<double> _headerAnim;
  late Animation<double> _heroAnim;
  late Animation<double> _lookAnim;
  late Animation<double> _gridAnim;
  late Animation<double> _toolsAnim;
  late Animation<double> _quoteAnim;

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
      duration: const Duration(milliseconds: 2000),
    );
    _headerAnim = _buildAnim(0.0, 0.18);
    _heroAnim = _buildAnim(0.12, 0.35);
    _lookAnim = _buildAnim(0.28, 0.52);
    _gridAnim = _buildAnim(0.42, 0.65);
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
                        SizedBox(height: FansivibeSpacing.lg + 8),
                        _buildAnimatedSection(_heroAnim, _buildHeroSpread()),
                        SizedBox(height: FansivibeSpacing.xl + 4),
                        _buildAnimatedSection(
                          _lookAnim,
                          _buildLookEditorial(context),
                        ),
                        SizedBox(height: FansivibeSpacing.xl + 4),
                        _buildAnimatedSection(
                          _gridAnim,
                          _buildCapabilityGrid(),
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

  Widget _buildHeader() {
    final name = widget.displayName ?? 'you';
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
          'WELCOME',
          style: FansivibeTypography.labelMediumWithFamily.copyWith(
            color: FansivibeColors.primary,
            letterSpacing: 3.0,
            fontSize: 12,
            fontWeight: FontWeight.w600,
          ),
        ),
        SizedBox(height: FansivibeSpacing.sm),
        Text(
          'Your style\nawakening.',
          style: FansivibeTypography.displayLargeWithFamily.copyWith(
            fontSize: 40,
            height: 1.08,
            letterSpacing: -0.5,
          ),
        ),
        SizedBox(height: FansivibeSpacing.sm + 4),
        Text(
          'We analysed everything, $name.\nYour Style DNA is ready.',
          style: FansivibeTypography.bodyLargeWithFamily.copyWith(
            color: FansivibeColors.secondary,
            height: 1.5,
            fontSize: 16,
          ),
        ),
      ],
    );
  }

  Widget _buildHeroSpread() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(24, 28, 24, 28),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            FansivibeColors.surfaceContainerLow,
            FansivibeColors.surfaceContainer.withValues(alpha: 0.6),
          ],
        ),
        borderRadius: FansivibeRadius.lgBorder,
        boxShadow: [
          BoxShadow(
            color: FansivibeColors.primary.withValues(alpha: 0.05),
            blurRadius: 32,
            offset: const Offset(0, 12),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildScoreGlobe(),
              SizedBox(width: FansivibeSpacing.md + 4),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Style Score',
                      style: FansivibeTypography.labelMediumWithFamily.copyWith(
                        color: FansivibeColors.secondary,
                        letterSpacing: 1.8,
                        fontSize: 10,
                      ),
                    ),
                    SizedBox(height: FansivibeSpacing.xs),
                    Text(
                      'A strong foundation\nwith room to evolve.',
                      style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                        color: FansivibeColors.secondary.withValues(alpha: 0.8),
                        fontSize: 13,
                        height: 1.5,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          SizedBox(height: FansivibeSpacing.lg),
          Container(
            width: double.infinity,
            height: 1,
            color: FansivibeColors.primary.withValues(alpha: 0.12),
          ),
          SizedBox(height: FansivibeSpacing.md + 4),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Style DNA',
                      style: FansivibeTypography.labelMediumWithFamily.copyWith(
                        color: FansivibeColors.secondary,
                        letterSpacing: 1.8,
                        fontSize: 10,
                      ),
                    ),
                    SizedBox(height: FansivibeSpacing.xs + 2),
                    Text(
                      _mockDna,
                      style: FansivibeTypography.titleLargeWithFamily.copyWith(
                        fontSize: 22,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
              _buildPaletteBar(),
            ],
          ),
          SizedBox(height: FansivibeSpacing.lg),
          _buildPullQuote(),
        ],
      ),
    );
  }

  Widget _buildScoreGlobe() {
    return Container(
      width: 96,
      height: 96,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: RadialGradient(
          colors: [
            FansivibeColors.primary.withValues(alpha: 0.12),
            FansivibeColors.primary.withValues(alpha: 0.04),
            Colors.transparent,
          ],
          stops: const [0.0, 0.55, 1.0],
        ),
      ),
      child: Stack(
        alignment: Alignment.center,
        children: [
          SizedBox(
            width: 82,
            height: 82,
            child: CircularProgressIndicator(
              value: _mockScore / 100,
              strokeWidth: 3,
              backgroundColor: FansivibeColors.primary.withValues(alpha: 0.08),
              valueColor: AlwaysStoppedAnimation<Color>(
                FansivibeColors.primary,
              ),
              strokeCap: StrokeCap.round,
            ),
          ),
          Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                '$_mockScore',
                style: FansivibeTypography.displayLargeWithFamily.copyWith(
                  fontSize: 34,
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.primary,
                  height: 1.0,
                ),
              ),
              Text(
                'of 100',
                style: FansivibeTypography.labelSmallWithFamily.copyWith(
                  fontSize: 8,
                  color: FansivibeColors.secondary.withValues(alpha: 0.5),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildPaletteBar() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Text(
          'PALETTE',
          style: FansivibeTypography.labelSmallWithFamily.copyWith(
            fontSize: 8,
            color: FansivibeColors.secondary.withValues(alpha: 0.5),
            letterSpacing: 1.5,
          ),
        ),
        SizedBox(height: FansivibeSpacing.xs + 2),
        SizedBox(
          height: 32,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (int i = 0; i < _mockPalette.length; i++)
                Container(
                  width: 28,
                  height: 32,
                  decoration: BoxDecoration(
                    color: Color(_mockPalette[i].color),
                    borderRadius: i == 0
                        ? const BorderRadius.only(
                            topLeft: Radius.circular(6),
                            bottomLeft: Radius.circular(6),
                          )
                        : i == _mockPalette.length - 1
                        ? const BorderRadius.only(
                            topRight: Radius.circular(6),
                            bottomRight: Radius.circular(6),
                          )
                        : BorderRadius.zero,
                    border: Border(
                      right: BorderSide(
                        color: FansivibeColors.surface.withValues(alpha: 0.3),
                        width: 1,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildPullQuote() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      decoration: BoxDecoration(
        color: FansivibeColors.primary.withValues(alpha: 0.05),
        borderRadius: FansivibeRadius.smBorder,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '\u201C',
            style: FansivibeTypography.displayLargeWithFamily.copyWith(
              fontSize: 28,
              height: 0.9,
              color: FansivibeColors.primary,
            ),
          ),
          SizedBox(width: FansivibeSpacing.sm),
          Expanded(
            child: Text(
              'Your balanced proportions create a clean foundation. Structured shoulders enhance your natural frame.',
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.onSurface,
                fontSize: 13,
                height: 1.6,
                fontStyle: FontStyle.italic,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLookEditorial(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
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
              'FIRST RECOMMENDATION',
              style: FansivibeTypography.labelMediumWithFamily.copyWith(
                color: FansivibeColors.primary,
                letterSpacing: 2.0,
                fontSize: 11,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
        SizedBox(height: FansivibeSpacing.md + 4),
        ClipRRect(
          borderRadius: FansivibeRadius.mdBorder,
          child: Column(
            children: [_buildLookImage(), _buildLookContent(context)],
          ),
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
          Center(
            child: Icon(
              Icons.checkroom_rounded,
              size: 72,
              color: FansivibeColors.primary.withValues(alpha: 0.1),
            ),
          ),
          Positioned(
            top: FansivibeSpacing.md,
            left: FansivibeSpacing.md,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: FansivibeColors.surface.withValues(alpha: 0.7),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(
                'EDITOR\'S PICK',
                style: FansivibeTypography.labelSmallWithFamily.copyWith(
                  color: FansivibeColors.primary,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 2.0,
                  fontSize: 9,
                ),
              ),
            ),
          ),
          Positioned(
            bottom: FansivibeSpacing.md,
            right: FansivibeSpacing.md,
            child: Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: FansivibeColors.primary.withValues(alpha: 0.12),
                borderRadius: FansivibeRadius.fullBorder,
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

  Widget _buildLookContent(BuildContext context) {
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
            'Clean lines, relaxed sophistication. This look complements your refined silhouette and warm neutral palette.',
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
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(FansivibeSpacing.md),
            decoration: BoxDecoration(
              color: FansivibeColors.surfaceContainerLow,
              borderRadius: FansivibeRadius.smBorder,
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  Icons.auto_awesome_rounded,
                  size: 14,
                  color: FansivibeColors.primary,
                ),
                SizedBox(width: FansivibeSpacing.sm),
                Expanded(
                  child: Text(
                    'Vertical lines and a tonal palette elongate your frame. The unstructured blazer adds polish without stiffness.',
                    style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                      color: FansivibeColors.secondary.withValues(alpha: 0.85),
                      fontSize: 13,
                      height: 1.5,
                    ),
                  ),
                ),
              ],
            ),
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
        color: FansivibeColors.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(6),
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

  Widget _buildCapabilityGrid() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
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
              'CAPABILITIES',
              style: FansivibeTypography.labelMediumWithFamily.copyWith(
                color: FansivibeColors.primary,
                letterSpacing: 2.0,
                fontSize: 11,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
        SizedBox(height: FansivibeSpacing.sm),
        Text(
          'Your style intelligence grows with you.',
          style: FansivibeTypography.bodyLargeWithFamily.copyWith(
            color: FansivibeColors.secondary,
            fontSize: 15,
          ),
        ),
        SizedBox(height: FansivibeSpacing.md + 4),
        ...List.generate((allCapabilities.length + 1) ~/ 2, (rowIndex) {
          final first = allCapabilities[rowIndex * 2];
          final second = rowIndex * 2 + 1 < allCapabilities.length
              ? allCapabilities[rowIndex * 2 + 1]
              : null;
          return Padding(
            padding: EdgeInsets.only(
              bottom: rowIndex < ((allCapabilities.length + 1) ~/ 2) - 1
                  ? FansivibeSpacing.sm + 4
                  : 0,
            ),
            child: Row(
              children: [
                Expanded(child: _capabilityTile(first)),
                if (second != null) ...[
                  SizedBox(width: FansivibeSpacing.sm + 4),
                  Expanded(child: _capabilityTile(second)),
                ],
              ],
            ),
          );
        }),
      ],
    );
  }

  Widget _capabilityTile(AiCapability cap) {
    final isActive = cap.active;
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
      decoration: BoxDecoration(
        color: isActive
            ? FansivibeColors.primary.withValues(alpha: 0.04)
            : FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.mdBorder,
        border: isActive
            ? Border.all(
                color: FansivibeColors.primary.withValues(alpha: 0.15),
                width: 1,
              )
            : null,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: isActive
                      ? FansivibeColors.primary.withValues(alpha: 0.12)
                      : FansivibeColors.surfaceContainerHighest,
                  border: isActive
                      ? Border.all(
                          color: FansivibeColors.primary.withValues(alpha: 0.3),
                          width: 1.5,
                        )
                      : null,
                ),
                child: Center(
                  child: Icon(
                    isActive ? Icons.check_circle_rounded : Icons.lock_rounded,
                    size: 15,
                    color: isActive
                        ? FansivibeColors.primary
                        : FansivibeColors.secondary.withValues(alpha: 0.4),
                  ),
                ),
              ),
              SizedBox(width: FansivibeSpacing.sm + 2),
              Expanded(
                child: Text(
                  cap.name,
                  style: FansivibeTypography.titleLargeWithFamily.copyWith(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: isActive
                        ? FansivibeColors.primary
                        : FansivibeColors.onSurface,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          SizedBox(height: FansivibeSpacing.sm),
          Text(
            cap.description,
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
              fontSize: 11,
              height: 1.4,
            ),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          if (!isActive && cap.unlockHint != null) ...[
            SizedBox(height: FansivibeSpacing.sm + 2),
            GestureDetector(
              onTap: () => _onUnlockHint(cap.name, cap.unlockHint!),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    cap.unlockHint!,
                    style: FansivibeTypography.labelSmallWithFamily.copyWith(
                      color: FansivibeColors.primary,
                      fontWeight: FontWeight.w600,
                      fontSize: 10,
                    ),
                  ),
                  SizedBox(width: FansivibeSpacing.xs),
                  Icon(
                    Icons.arrow_forward_rounded,
                    size: 11,
                    color: FansivibeColors.primary,
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildQuickTools(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
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
              'TOOLS',
              style: FansivibeTypography.labelMediumWithFamily.copyWith(
                color: FansivibeColors.primary,
                letterSpacing: 2.0,
                fontSize: 11,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
        SizedBox(height: FansivibeSpacing.sm),
        Text(
          'Explore what\'s possible.',
          style: FansivibeTypography.bodyLargeWithFamily.copyWith(
            color: FansivibeColors.secondary,
            fontSize: 15,
          ),
        ),
        SizedBox(height: FansivibeSpacing.md + 4),
        SizedBox(
          height: 100,
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
                  vertical: 16,
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
                    Text(
                      label,
                      style: FansivibeTypography.labelSmallWithFamily.copyWith(
                        color: FansivibeColors.onSurface,
                        fontSize: 10,
                        fontWeight: FontWeight.w500,
                        height: 1.3,
                      ),
                      textAlign: TextAlign.center,
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
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(24, 24, 24, 24),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            FansivibeColors.primary.withValues(alpha: 0.05),
            FansivibeColors.surfaceContainerLow,
          ],
        ),
        borderRadius: FansivibeRadius.lgBorder,
        border: Border.all(
          color: FansivibeColors.primary.withValues(alpha: 0.08),
          width: 0.5,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: FansivibeColors.primary.withValues(alpha: 0.1),
                  borderRadius: FansivibeRadius.smBorder,
                ),
                child: Center(
                  child: Icon(
                    Icons.auto_awesome_rounded,
                    size: 18,
                    color: FansivibeColors.primary,
                  ),
                ),
              ),
              SizedBox(width: FansivibeSpacing.sm + 4),
              Text(
                'AI INSIGHT',
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
            'Your facial structure pairs exceptionally well with textured hairstyles.',
            style: FansivibeTypography.titleLargeWithFamily.copyWith(
              fontSize: 20,
              height: 1.35,
              fontWeight: FontWeight.w500,
            ),
          ),
          SizedBox(height: FansivibeSpacing.sm + 4),
          Text(
            'Adding volume at the crown creates a balanced proportion with your jawline. This is one of several insights generated from your facial analysis.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
              height: 1.6,
              fontSize: 14,
            ),
          ),
          SizedBox(height: FansivibeSpacing.md + 4),
          Row(
            children: [
              FansiButton.secondary(
                label: 'Explore Hairstyles',
                icon: Icons.arrow_forward_rounded,
                onPressed: () => context.pushNamed(RouteNames.hairstyle),
                expanded: false,
              ),
            ],
          ),
        ],
      ),
    );
  }

  void _onUnlockHint(String name, String hint) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('$name: $hint'),
        backgroundColor: FansivibeColors.surfaceContainerHighest,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.smBorder),
        duration: const Duration(seconds: 2),
      ),
    );
  }
}
