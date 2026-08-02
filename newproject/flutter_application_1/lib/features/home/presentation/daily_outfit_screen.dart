import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:fansivibe/features/home/data/daily_outfit_mock_data.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

class DailyOutfitScreen extends StatefulWidget {
  const DailyOutfitScreen({super.key});

  @override
  State<DailyOutfitScreen> createState() => _DailyOutfitScreenState();
}

class _DailyOutfitScreenState extends State<DailyOutfitScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _heroAnim;
  late Animation<double> _editorialAnim;
  late Animation<double> _breakdownAnim;
  late Animation<double> _insightsAnim;
  late Animation<double> _alternativesAnim;
  late Animation<double> _actionsAnim;
  late Animation<double> _tipAnim;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2400),
    );
    _heroAnim = _buildAnim(0.0, 0.25);
    _editorialAnim = _buildAnim(0.18, 0.38);
    _breakdownAnim = _buildAnim(0.30, 0.50);
    _insightsAnim = _buildAnim(0.42, 0.62);
    _alternativesAnim = _buildAnim(0.55, 0.75);
    _actionsAnim = _buildAnim(0.67, 0.85);
    _tipAnim = _buildAnim(0.78, 0.98);
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
    final data = DailyOutfitData.mock;
    final reduceMotion = MediaQuery.of(context).disableAnimations;

    return Scaffold(
      backgroundColor: FansivibeColors.surface,
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final isTablet = maxWidth > 600;
            final horizontalPadding = isTablet ? 48.0 : 20.0;
            final contentMaxWidth = isTablet ? 600.0 : double.infinity;

            return SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              child: Center(
                child: ConstrainedBox(
                  constraints: BoxConstraints(maxWidth: contentMaxWidth),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _animatedSection(
                        _heroAnim,
                        reduceMotion,
                        _buildHeroSection(context, data, constraints),
                      ),
                      Padding(
                        padding: EdgeInsets.symmetric(
                          horizontal: horizontalPadding,
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            SizedBox(height: FansivibeSpacing.xl),
                            _animatedSection(
                              _editorialAnim,
                              reduceMotion,
                              _buildEditorialSummary(context, data),
                            ),
                            SizedBox(height: FansivibeSpacing.xxl),
                            _animatedSection(
                              _breakdownAnim,
                              reduceMotion,
                              _buildOutfitBreakdown(context, data),
                            ),
                            SizedBox(height: FansivibeSpacing.xxl),
                            _animatedSection(
                              _insightsAnim,
                              reduceMotion,
                              _buildWhyItWorks(context, data),
                            ),
                            SizedBox(height: FansivibeSpacing.xxl),
                            _animatedSection(
                              _alternativesAnim,
                              reduceMotion,
                              _buildAlternatives(context, data),
                            ),
                            SizedBox(height: FansivibeSpacing.xxl),
                            _animatedSection(
                              _actionsAnim,
                              reduceMotion,
                              _buildQuickActions(context, data),
                            ),
                            SizedBox(height: FansivibeSpacing.xl),
                            _animatedSection(
                              _tipAnim,
                              reduceMotion,
                              _buildDailyStyleTip(context, data),
                            ),
                            SizedBox(height: FansivibeSpacing.xxxl),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _animatedSection(
    Animation<double> anim,
    bool reduceMotion,
    Widget child,
  ) {
    if (reduceMotion) return child;
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

  // ────────────────────────────── HERO ──────────────────────────────

  Widget _buildHeroSection(
    BuildContext context,
    DailyOutfitData data,
    BoxConstraints constraints,
  ) {
    final viewHeight = MediaQuery.of(context).size.height;
    final heroHeight = (viewHeight * 0.6).clamp(380.0, 520.0).toDouble();
    final w = constraints.maxWidth;
    final isTablet = w > 600;
    final p = isTablet ? 48.0 : 20.0;
    final scoreColor = _scoreColor(data.matchScore);

    final panelWidth = w * 0.62;
    final panelHeight = heroHeight * 0.5;
    final panelTop = heroHeight * 0.17;
    final panelLeft = w - panelWidth + 14;

    return SizedBox(
      height: heroHeight,
      width: double.infinity,
      child: Stack(
        fit: StackFit.expand,
        children: [
          Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  FansivibeColors.surfaceContainerHigh,
                  FansivibeColors.surfaceContainerLow,
                  FansivibeColors.surface,
                ],
                stops: const [0.0, 0.55, 1.0],
              ),
            ),
            child: Stack(
              fit: StackFit.expand,
              children: [
                Positioned(
                  top: -40,
                  right: -60,
                  child: Container(
                    width: 220,
                    height: 220,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: FansivibeColors.primary.withValues(alpha: 0.05),
                    ),
                  ),
                ),
                Positioned(
                  bottom: 40,
                  left: -70,
                  child: Container(
                    width: 170,
                    height: 170,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: FansivibeColors.primary.withValues(alpha: 0.03),
                    ),
                  ),
                ),
              ],
            ),
          ),
          Positioned(
            top: p,
            left: p,
            child: Semantics(
              button: true,
              child: GestureDetector(
                onTap: () => Navigator.of(context).pop(),
                child: _glassCircle(icon: Icons.arrow_back_rounded, size: 40),
              ),
            ),
          ),
          Positioned(
            top: p,
            right: p,
            child: _glassPill(
              icon: Icons.auto_awesome_rounded,
              text: '${data.matchScore}%',
              color: scoreColor,
            ),
          ),
          Positioned(
            left: panelLeft,
            top: panelTop,
            child: Container(
              width: panelWidth,
              height: panelHeight,
              decoration: BoxDecoration(
                borderRadius: FansivibeRadius.lgBorder,
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    FansivibeColors.surfaceContainerHigh,
                    FansivibeColors.surfaceContainer,
                  ],
                ),
              ),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Center(
                    child: Icon(
                      Icons.checkroom_rounded,
                      size: 68,
                      color: FansivibeColors.primary.withValues(alpha: 0.1),
                    ),
                  ),
                  Positioned(
                    right: 16,
                    bottom: 16,
                    child: Icon(
                      Icons.expand_less_rounded,
                      size: 18,
                      color: FansivibeColors.primary.withValues(alpha: 0.25),
                    ),
                  ),
                ],
              ),
            ),
          ),
          Positioned(
            left: p,
            top: heroHeight * 0.40,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 28,
                  height: 3,
                  decoration: BoxDecoration(
                    color: FansivibeColors.primary,
                    borderRadius: FansivibeRadius.fullBorder,
                  ),
                ),
                SizedBox(height: 10),
                Container(
                  constraints: BoxConstraints(maxWidth: w - (p * 2)),
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    alignment: Alignment.centerLeft,
                    child: Text(
                      'TODAY\'S LOOK',
                      maxLines: 1,
                      style: FansivibeTypography.displayLargeWithFamily
                          .copyWith(
                            fontSize: isTablet ? 52 : 42,
                            fontWeight: FontWeight.w500,
                            height: 1.0,
                            letterSpacing: -0.5,
                          ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          Positioned(
            left: p,
            bottom: heroHeight * 0.17,
            child: _glassPill(
              icon: Icons.auto_awesome_rounded,
              text: 'Confidence Boost',
              color: FansivibeColors.primary,
            ),
          ),
          Positioned(
            left: p,
            bottom: p,
            child: Wrap(
              spacing: FansivibeSpacing.sm,
              runSpacing: FansivibeSpacing.sm,
              children: [
                _garmentTag(
                  data.occasion,
                  icon: Icons.event_outlined,
                  color: FansivibeColors.primary,
                ),
                _garmentTag(
                  data.weather,
                  icon: Icons.cloud_outlined,
                  color: FansivibeColors.secondary,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ─────────────────────── TONAL / GLASS BUILDING BLOCKS ───────────────────────

  /// Floating glass element — `surfaceContainerLow` @ 70% + 20px blur.
  /// No line; separation through glass and tonal depth.
  Widget _glassPill({IconData? icon, required String text, Color? color}) {
    final c = color ?? FansivibeColors.onSurface;
    return ClipRRect(
      borderRadius: FansivibeRadius.fullBorder,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: FansivibeColors.surfaceContainerLow.withValues(alpha: 0.7),
            borderRadius: FansivibeRadius.fullBorder,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (icon != null) ...[
                Icon(icon, size: 14, color: c),
                SizedBox(width: FansivibeSpacing.sm),
              ],
              Text(
                text,
                style: FansivibeTypography.labelSmallWithFamily.copyWith(
                  color: c,
                  fontWeight: FontWeight.w700,
                  fontSize: 12,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _glassCircle({required IconData icon, required double size}) {
    return ClipOval(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
        child: Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            color: FansivibeColors.surfaceContainerLow.withValues(alpha: 0.7),
          ),
          child: Center(
            child: Icon(
              icon,
              size: size * 0.5,
              color: FansivibeColors.onSurface,
            ),
          ),
        ),
      ),
    );
  }

  /// Garment-tag chip — `surfaceContainerHighest` @ `sm` radius, label text.
  Widget _garmentTag(String label, {IconData? icon, Color? color}) {
    final c = color ?? FansivibeColors.onSurface;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerHighest,
        borderRadius: FansivibeRadius.smBorder,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 13, color: c),
            SizedBox(width: FansivibeSpacing.xs + 2),
          ],
          Text(
            label,
            style: FansivibeTypography.labelSmallWithFamily.copyWith(
              color: c,
              fontWeight: FontWeight.w600,
              fontSize: 11,
            ),
          ),
        ],
      ),
    );
  }

  Widget _goldLabel(String text, {double fontSize = 10}) {
    return Text(
      text,
      style: FansivibeTypography.labelMediumWithFamily.copyWith(
        color: FansivibeColors.primary,
        fontWeight: FontWeight.w700,
        letterSpacing: 2.0,
        fontSize: fontSize,
      ),
    );
  }

  // ─────────────────────────── EDITORIAL SUMMARY ───────────────────────────

  Widget _buildEditorialSummary(BuildContext context, DailyOutfitData data) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _goldLabel('THE DAILY EDIT'),
        SizedBox(height: FansivibeSpacing.sm),
        Text(
          data.title,
          style: FansivibeTypography.displayLargeWithFamily.copyWith(
            fontSize: 36,
            fontWeight: FontWeight.w500,
            height: 1.1,
            letterSpacing: -0.5,
          ),
        ),
        SizedBox(height: FansivibeSpacing.md),
        Text(
          data.description,
          style: FansivibeTypography.bodyLargeWithFamily.copyWith(
            color: FansivibeColors.secondary,
            height: 1.6,
            fontSize: 16,
          ),
        ),
        if (data.aiSelectionReason != null) ...[
          SizedBox(height: FansivibeSpacing.lg),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _garmentTag(
                'AI NOTE',
                icon: Icons.auto_awesome_rounded,
                color: FansivibeColors.primary,
              ),
              SizedBox(width: FansivibeSpacing.sm + 4),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Text(
                    data.aiSelectionReason!,
                    style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                      color: FansivibeColors.primary,
                      fontSize: 14,
                      height: 1.5,
                      fontStyle: FontStyle.italic,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ],
    );
  }

  // ─────────────────────────── THE ENSEMBLE ───────────────────────────

  Widget _buildOutfitBreakdown(BuildContext context, DailyOutfitData data) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionHeader('The Ensemble', '${data.components.length} pieces'),
        SizedBox(height: FansivibeSpacing.md + 4),
        SizedBox(
          height: isTablet(context) ? 190 : 175,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            physics: const BouncingScrollPhysics(),
            padding: EdgeInsets.only(
              left: isTablet(context) ? 0 : 4,
              right: FansivibeSpacing.lg,
            ),
            itemCount: data.components.length,
            separatorBuilder: (_, __) =>
                SizedBox(width: FansivibeSpacing.sm + 4),
            itemBuilder: (context, index) {
              return _componentCard(
                context,
                data.components[index],
                isTablet(context),
              );
            },
          ),
        ),
      ],
    );
  }

  bool isTablet(BuildContext context) {
    return MediaQuery.of(context).size.width > 600;
  }

  Widget _componentCard(
    BuildContext context,
    DailyOutfitComponent component,
    bool isTablet,
  ) {
    final color = _parseColor(component.colorHex);
    final cardWidth = isTablet ? 200.0 : 170.0;

    return SizedBox(
      width: cardWidth,
      child: Container(
        decoration: BoxDecoration(
          color: FansivibeColors.surfaceContainerLow,
          borderRadius: FansivibeRadius.mdBorder,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              height: cardWidth * 0.5,
              width: double.infinity,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    color.withValues(alpha: 0.12),
                    FansivibeColors.surfaceContainerLow,
                  ],
                  stops: const [0.0, 0.9],
                ),
                borderRadius: BorderRadius.vertical(
                  top: Radius.circular(FansivibeRadius.md),
                ),
              ),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Center(
                    child: Icon(
                      _categoryIcon(component.category),
                      size: 34,
                      color: color.withValues(alpha: 0.45),
                    ),
                  ),
                  Positioned(
                    top: 10,
                    left: 10,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: FansivibeColors.surfaceContainerHighest,
                        borderRadius: FansivibeRadius.smBorder,
                      ),
                      child: Text(
                        component.category.toUpperCase(),
                        style: FansivibeTypography.labelSmallWithFamily
                            .copyWith(
                              color: FansivibeColors.primary,
                              fontSize: 8.5,
                              fontWeight: FontWeight.w700,
                              letterSpacing: 1,
                            ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    component.name,
                    style: FansivibeTypography.titleLargeWithFamily.copyWith(
                      fontWeight: FontWeight.w600,
                      color: FansivibeColors.onSurface,
                      fontSize: 13,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  SizedBox(height: FansivibeSpacing.xs + 2),
                  Row(
                    children: [
                      Container(
                        width: 8,
                        height: 8,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: color,
                        ),
                      ),
                      SizedBox(width: FansivibeSpacing.xs + 2),
                      Flexible(
                        child: Text(
                          component.material == null
                              ? component.color
                              : '${component.color} \u2022 ${component.material}',
                          style: FansivibeTypography.labelSmallWithFamily
                              .copyWith(
                                color: FansivibeColors.secondary,
                                fontSize: 10,
                              ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ─────────────────────────── WHY IT WORKS ───────────────────────────

  Widget _buildWhyItWorks(BuildContext context, DailyOutfitData data) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionHeader('Why It Works', 'AI style analysis'),
        SizedBox(height: FansivibeSpacing.md + 4),
        if (data.aiInsights.isNotEmpty)
          ...List.generate(data.aiInsights.length, (index) {
            final insight = data.aiInsights[index];
            return Padding(
              padding: EdgeInsets.only(
                bottom: index < data.aiInsights.length - 1
                    ? FansivibeSpacing.sm + 4
                    : 0,
              ),
              child: _insightCard(context, insight),
            );
          }),
      ],
    );
  }

  Widget _insightCard(BuildContext context, AiInsightData insight) {
    final icon = _insightIcon(insight.iconName);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 18),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.mdBorder,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color: FansivibeColors.primary.withValues(alpha: 0.1),
              borderRadius: FansivibeRadius.smBorder,
            ),
            child: Center(
              child: Icon(icon, size: 18, color: FansivibeColors.primary),
            ),
          ),
          SizedBox(width: FansivibeSpacing.sm + 4),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  insight.title,
                  style: FansivibeTypography.titleLargeWithFamily.copyWith(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                SizedBox(height: FansivibeSpacing.xs + 2),
                Text(
                  insight.description,
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
    );
  }

  // ─────────────────────────── ALTERNATIVES ───────────────────────────

  Widget _buildAlternatives(BuildContext context, DailyOutfitData data) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionHeader('Alternatives', '3 more looks for you'),
        SizedBox(height: FansivibeSpacing.md + 4),
        SizedBox(
          height: isTablet(context) ? 240 : 220,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            physics: const BouncingScrollPhysics(),
            padding: EdgeInsets.only(
              left: isTablet(context) ? 0 : 4,
              right: FansivibeSpacing.lg,
            ),
            itemCount: data.alternatives.length,
            separatorBuilder: (_, __) =>
                SizedBox(width: FansivibeSpacing.sm + 4),
            itemBuilder: (context, index) {
              return _alternativeCard(
                context,
                data.alternatives[index],
                isTablet(context),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _alternativeCard(
    BuildContext context,
    AlternativeLookData alt,
    bool isTablet,
  ) {
    final cardWidth = isTablet ? 220.0 : 190.0;
    final scoreColor = _scoreColor(alt.matchScore);

    return SizedBox(
      width: cardWidth,
      child: Container(
        decoration: BoxDecoration(
          color: FansivibeColors.surfaceContainerLow,
          borderRadius: FansivibeRadius.mdBorder,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              height: cardWidth * 0.5,
              width: double.infinity,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    FansivibeColors.surfaceContainerHigh,
                    FansivibeColors.surfaceContainer,
                  ],
                ),
                borderRadius: BorderRadius.vertical(
                  top: Radius.circular(FansivibeRadius.md),
                ),
              ),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Center(
                    child: Icon(
                      Icons.checkroom_rounded,
                      size: 36,
                      color: FansivibeColors.primary.withValues(alpha: 0.08),
                    ),
                  ),
                  Positioned(
                    top: FansivibeSpacing.sm,
                    right: FansivibeSpacing.sm,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: FansivibeColors.surfaceContainerHighest,
                        borderRadius: FansivibeRadius.smBorder,
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.star_rounded, size: 10, color: scoreColor),
                          SizedBox(width: 3),
                          Text(
                            '${alt.matchScore}%',
                            style: FansivibeTypography.labelSmallWithFamily
                                .copyWith(
                                  color: scoreColor,
                                  fontWeight: FontWeight.w700,
                                  fontSize: 10,
                                ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 12, 12, 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    alt.name,
                    style: FansivibeTypography.titleLargeWithFamily.copyWith(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  SizedBox(height: FansivibeSpacing.xs - 2),
                  Text(
                    alt.styleName,
                    style: FansivibeTypography.labelSmallWithFamily.copyWith(
                      color: FansivibeColors.secondary,
                      fontSize: 10,
                    ),
                  ),
                  SizedBox(height: FansivibeSpacing.sm),
                  SizedBox(
                    width: double.infinity,
                    child: GestureDetector(
                      onTap: () => _handleSeeDetails(context, alt),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: 6),
                        child: Text(
                          'See Details',
                          style: FansivibeTypography.labelMediumWithFamily
                              .copyWith(
                                color: FansivibeColors.primary,
                                fontWeight: FontWeight.w600,
                                fontSize: 12,
                                letterSpacing: 0.5,
                                decoration: TextDecoration.underline,
                                decorationColor: FansivibeColors.primary,
                                decorationThickness: 1,
                              ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ─────────────────────────── QUICK ACTIONS ───────────────────────────

  Widget _buildQuickActions(BuildContext context, DailyOutfitData data) {
    return Column(
      children: [
        _goldGradientCta(
          label: 'Wear This Look',
          icon: Icons.check_circle_outline_rounded,
          onTap: () => _handleWearThis(context),
        ),
        SizedBox(height: FansivibeSpacing.sm + 4),
        FansiButton.secondary(
          label: 'Generate Another Look',
          icon: Icons.refresh_rounded,
          onPressed: () => _handleGenerateAnother(context),
        ),
        SizedBox(height: FansivibeSpacing.sm + 4),
        FansiButton.secondary(
          label: 'Save Look',
          icon: Icons.bookmark_outline_rounded,
          onPressed: () => _handleSaveOutfit(context),
        ),
        SizedBox(height: FansivibeSpacing.sm + 4),
        SizedBox(
          width: double.infinity,
          child: GestureDetector(
            onTap: () => _handleShare(context),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    Icons.share_outlined,
                    size: 16,
                    color: FansivibeColors.primary,
                  ),
                  SizedBox(width: FansivibeSpacing.sm),
                  Text(
                    'Share',
                    style: FansivibeTypography.labelMediumWithFamily.copyWith(
                      color: FansivibeColors.primary,
                      fontWeight: FontWeight.w600,
                      fontSize: 13,
                      letterSpacing: 0.5,
                      decoration: TextDecoration.underline,
                      decorationColor: FansivibeColors.primary,
                      decorationThickness: 1,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  /// Signature primary CTA — `primary` → `primaryContainer` at 135 degrees.
  Widget _goldGradientCta({
    required String label,
    required IconData icon,
    required VoidCallback onTap,
  }) {
    return ClipRRect(
      borderRadius: FansivibeRadius.fullBorder,
      child: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [FansivibeColors.primary, FansivibeColors.primaryContainer],
          ),
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: onTap,
            child: Container(
              height: 52,
              padding: const EdgeInsets.symmetric(horizontal: 24),
              alignment: Alignment.center,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(
                    Icons.check_circle_outline_rounded,
                    size: 18,
                    color: FansivibeColors.onPrimary,
                  ),
                  const SizedBox(width: 8),
                  Text(
                    label,
                    style: FansivibeTypography.bodyLargeWithFamily.copyWith(
                      color: FansivibeColors.onPrimary,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  // ─────────────────────────── DAILY STYLE TIP ───────────────────────────

  Widget _buildDailyStyleTip(BuildContext context, DailyOutfitData data) {
    if (data.dailyStyleTip == null) return const SizedBox.shrink();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            FansivibeColors.primary.withValues(alpha: 0.05),
            FansivibeColors.surfaceContainerLow,
          ],
          stops: const [0.0, 0.7],
        ),
        borderRadius: FansivibeRadius.mdBorder,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 34,
            height: 34,
            decoration: BoxDecoration(
              color: FansivibeColors.primary.withValues(alpha: 0.12),
              borderRadius: FansivibeRadius.smBorder,
            ),
            child: Center(
              child: Icon(
                Icons.lightbulb_outline_rounded,
                size: 17,
                color: FansivibeColors.primary,
              ),
            ),
          ),
          SizedBox(width: FansivibeSpacing.sm + 4),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _goldLabel('Daily Style Tip', fontSize: 10),
                SizedBox(height: FansivibeSpacing.xs + 2),
                Text(
                  data.dailyStyleTip!,
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.onSurface,
                    fontSize: 13,
                    height: 1.5,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionHeader(String title, String subtitle) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 26,
          height: 3,
          decoration: BoxDecoration(
            color: FansivibeColors.primary,
            borderRadius: FansivibeRadius.fullBorder,
          ),
        ),
        SizedBox(height: FansivibeSpacing.sm),
        Text(
          title,
          style: FansivibeTypography.headlineMediumWithFamily.copyWith(
            fontSize: 22,
            fontWeight: FontWeight.w500,
          ),
        ),
        SizedBox(height: FansivibeSpacing.xs),
        Text(
          subtitle,
          style: FansivibeTypography.labelMediumWithFamily.copyWith(
            color: FansivibeColors.primary,
            fontWeight: FontWeight.w600,
            fontSize: 10,
            letterSpacing: 1.5,
          ),
        ),
      ],
    );
  }

  void _handleWearThis(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('Wearing this look!'),
        backgroundColor: FansivibeColors.primary,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.smdBorder),
      ),
    );
  }

  void _handleGenerateAnother(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('Generating a new look...'),
        backgroundColor: FansivibeColors.primary,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.smdBorder),
      ),
    );
  }

  void _handleSaveOutfit(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('Outfit saved to your looks'),
        backgroundColor: FansivibeColors.primary,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.smdBorder),
      ),
    );
  }

  void _handleShare(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('Share feature coming soon'),
        backgroundColor: FansivibeColors.surfaceContainerHighest,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.smdBorder),
      ),
    );
  }

  void _handleSeeDetails(BuildContext context, AlternativeLookData alt) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Viewing ${alt.name} details...'),
        backgroundColor: FansivibeColors.primary,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.smdBorder),
      ),
    );
  }

  Color _scoreColor(int score) {
    if (score >= 90) return FansivibeColors.success;
    if (score >= 80) return FansivibeColors.primary;
    if (score >= 70) return FansivibeColors.warning;
    return FansivibeColors.error;
  }

  Color _parseColor(String? hex) {
    if (hex == null) return FansivibeColors.primary;
    final h = hex.replaceFirst('#', '');
    final fullHex = h.length == 6 ? 'FF$h' : h;
    return Color(int.parse(fullHex, radix: 16));
  }

  IconData _categoryIcon(String category) {
    switch (category) {
      case 'Outerwear':
        return Icons.checkroom_rounded;
      case 'Tops':
        return Icons.person_rounded;
      case 'Bottoms':
        return Icons.accessibility_rounded;
      case 'Footwear':
        return Icons.directions_walk_rounded;
      case 'Accessories':
        return Icons.diamond_rounded;
      default:
        return Icons.category_rounded;
    }
  }

  IconData _insightIcon(String iconName) {
    switch (iconName) {
      case 'palette_outlined':
        return Icons.palette_outlined;
      case 'accessibility_new_rounded':
        return Icons.accessibility_new_rounded;
      case 'auto_awesome_rounded':
        return Icons.auto_awesome_rounded;
      case 'event_outlined':
        return Icons.event_outlined;
      default:
        return Icons.lightbulb_outline_rounded;
    }
  }
}
