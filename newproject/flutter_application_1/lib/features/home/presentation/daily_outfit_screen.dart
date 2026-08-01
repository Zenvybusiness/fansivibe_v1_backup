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
            final horizontalPadding = isTablet ? 48.0 : 0.0;
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
                          horizontal: horizontalPadding > 0
                              ? horizontalPadding
                              : FansivibeSpacing.lg,
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            SizedBox(height: FansivibeSpacing.lg),
                            _animatedSection(
                              _editorialAnim,
                              reduceMotion,
                              _buildEditorialSummary(context, data),
                            ),
                            SizedBox(height: FansivibeSpacing.xl),
                            _animatedSection(
                              _breakdownAnim,
                              reduceMotion,
                              _buildOutfitBreakdown(context, data),
                            ),
                            SizedBox(height: FansivibeSpacing.xl),
                            _animatedSection(
                              _insightsAnim,
                              reduceMotion,
                              _buildWhyItWorks(context, data),
                            ),
                            SizedBox(height: FansivibeSpacing.xl),
                            _animatedSection(
                              _alternativesAnim,
                              reduceMotion,
                              _buildAlternatives(context, data),
                            ),
                            SizedBox(height: FansivibeSpacing.xl),
                            _animatedSection(
                              _actionsAnim,
                              reduceMotion,
                              _buildQuickActions(context, data),
                            ),
                            SizedBox(height: FansivibeSpacing.lg),
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

  Widget _buildHeroSection(
    BuildContext context,
    DailyOutfitData data,
    BoxConstraints constraints,
  ) {
    final viewHeight = MediaQuery.of(context).size.height;
    final heroHeight = viewHeight * 0.68;
    final scoreColor = _scoreColor(data.matchScore);
    final isTablet = constraints.maxWidth > 600;

    return SizedBox(
      height: heroHeight.clamp(380, 600),
      width: double.infinity,
      child: Stack(
        fit: StackFit.expand,
        children: [
          Hero(
            tag: 'todays-outfit-hero',
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    FansivibeColors.surfaceContainerHigh,
                    FansivibeColors.surfaceContainerLow,
                    FansivibeColors.surface,
                  ],
                  stops: const [0.0, 0.5, 1.0],
                ),
              ),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Positioned(
                    top: -40,
                    right: -40,
                    child: Container(
                      width: 200,
                      height: 200,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: FansivibeColors.primary.withValues(alpha: 0.04),
                      ),
                    ),
                  ),
                  Positioned(
                    bottom: 60,
                    left: -60,
                    child: Container(
                      width: 160,
                      height: 160,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: FansivibeColors.primary.withValues(alpha: 0.03),
                      ),
                    ),
                  ),
                  Center(
                    child: Icon(
                      Icons.checkroom_rounded,
                      size: 96,
                      color: FansivibeColors.primary.withValues(alpha: 0.12),
                    ),
                  ),
                ],
              ),
            ),
          ),
          Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.bottomCenter,
                end: Alignment.topCenter,
                colors: [
                  FansivibeColors.surface.withValues(alpha: 0.92),
                  FansivibeColors.surface.withValues(alpha: 0.4),
                  Colors.transparent,
                  Colors.transparent,
                ],
                stops: const [0.0, 0.25, 0.55, 1.0],
              ),
            ),
          ),
          Positioned(
            top: isTablet ? 32 : 16,
            left: isTablet ? 48 : 20,
            child: Semantics(
              button: true,
              child: GestureDetector(
                onTap: () => Navigator.of(context).pop(),
                child: Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: FansivibeColors.surface.withValues(alpha: 0.5),
                    borderRadius: FansivibeRadius.fullBorder,
                    border: Border.all(
                      color: FansivibeColors.primary.withValues(alpha: 0.1),
                      width: 0.5,
                    ),
                  ),
                  child: Icon(
                    Icons.arrow_back_rounded,
                    size: 20,
                    color: FansivibeColors.onSurface,
                  ),
                ),
              ),
            ),
          ),
          Positioned(
            top: isTablet ? 32 : 16,
            right: isTablet ? 48 : 20,
            child: _glassChip(
              '${data.matchScore}%',
              icon: Icons.auto_awesome_rounded,
              color: scoreColor,
            ),
          ),
          Positioned(
            top: isTablet ? 88 : 68,
            left: isTablet ? 48 : 20,
            child: _sectionLabel('TODAY\'S LOOK'),
          ),
          Positioned(
            bottom: isTablet ? 120 : 100,
            left: isTablet ? 48 : 20,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _glassChip(
                  data.occasion,
                  icon: Icons.event_outlined,
                  color: FansivibeColors.primary,
                ),
                SizedBox(height: FansivibeSpacing.sm),
                _glassChip(
                  data.weather,
                  icon: Icons.cloud_outlined,
                  color: FansivibeColors.secondary,
                ),
              ],
            ),
          ),
          if (data.confidenceBoost != null)
            Positioned(
              bottom: isTablet ? 36 : 24,
              left: isTablet ? 48 : 20,
              child: _confidenceChip(data.confidenceBoost!),
            ),
        ],
      ),
    );
  }

  Widget _sectionLabel(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
      decoration: BoxDecoration(
        color: FansivibeColors.surface.withValues(alpha: 0.55),
        borderRadius: FansivibeRadius.fullBorder,
        border: Border.all(
          color: FansivibeColors.primary.withValues(alpha: 0.15),
          width: 0.5,
        ),
      ),
      child: Text(
        label,
        style: FansivibeTypography.labelMediumWithFamily.copyWith(
          color: FansivibeColors.primary,
          fontWeight: FontWeight.w700,
          letterSpacing: 2.0,
          fontSize: 11,
        ),
      ),
    );
  }

  Widget _glassChip(String label, {IconData? icon, Color? color}) {
    final chipColor = color ?? FansivibeColors.onSurface;
    return ClipRRect(
      borderRadius: FansivibeRadius.fullBorder,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 8, sigmaY: 8),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: FansivibeColors.surface.withValues(alpha: 0.4),
            borderRadius: FansivibeRadius.fullBorder,
            border: Border.all(
              color: chipColor.withValues(alpha: 0.15),
              width: 0.5,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (icon != null) ...[
                Icon(icon, size: 14, color: chipColor),
                SizedBox(width: FansivibeSpacing.sm),
              ],
              Text(
                label,
                style: FansivibeTypography.labelSmallWithFamily.copyWith(
                  color: chipColor,
                  fontWeight: FontWeight.w600,
                  fontSize: 12,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _confidenceChip(String text) {
    return ClipRRect(
      borderRadius: FansivibeRadius.fullBorder,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 8, sigmaY: 8),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                FansivibeColors.primary.withValues(alpha: 0.15),
                FansivibeColors.primary.withValues(alpha: 0.05),
              ],
            ),
            borderRadius: FansivibeRadius.fullBorder,
            border: Border.all(
              color: FansivibeColors.primary.withValues(alpha: 0.2),
              width: 0.5,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.auto_awesome_rounded,
                size: 14,
                color: FansivibeColors.primary,
              ),
              SizedBox(width: FansivibeSpacing.sm),
              Text(
                'Confidence Boost',
                style: FansivibeTypography.labelSmallWithFamily.copyWith(
                  color: FansivibeColors.primary,
                  fontWeight: FontWeight.w600,
                  fontSize: 11,
                  letterSpacing: 0.5,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildEditorialSummary(BuildContext context, DailyOutfitData data) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          data.title,
          style: FansivibeTypography.displayLargeWithFamily.copyWith(
            fontSize: 34,
            fontWeight: FontWeight.w500,
            height: 1.08,
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
          SizedBox(height: FansivibeSpacing.md),
          Row(
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
                  data.aiSelectionReason!,
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.primary,
                    fontSize: 14,
                    height: 1.5,
                    fontStyle: FontStyle.italic,
                  ),
                ),
              ),
            ],
          ),
        ],
      ],
    );
  }

  Widget _buildOutfitBreakdown(BuildContext context, DailyOutfitData data) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionHeader('The Ensemble', '${data.components.length} pieces'),
        SizedBox(height: FansivibeSpacing.md + 4),
        SizedBox(
          height: isTablet(context) ? 180 : 165,
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
    final theme = Theme.of(context);
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
                color: color.withValues(alpha: 0.08),
                borderRadius: BorderRadius.vertical(
                  top: Radius.circular(FansivibeRadius.md),
                ),
              ),
              child: Center(
                child: Icon(
                  _categoryIcon(component.category),
                  size: 36,
                  color: color.withValues(alpha: 0.4),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    component.name,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                      color: FansivibeColors.onSurface,
                      fontSize: 13,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  SizedBox(height: FansivibeSpacing.xs),
                  Text(
                    '${component.color} \u2022 ${component.category}',
                    style: FansivibeTypography.labelSmallWithFamily.copyWith(
                      color: FansivibeColors.secondary,
                      fontSize: 10,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

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

    return ClipRRect(
      borderRadius: FansivibeRadius.mdBorder,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 6, sigmaY: 6),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(16, 18, 16, 18),
          decoration: BoxDecoration(
            color: FansivibeColors.surfaceContainerLow.withValues(alpha: 0.6),
            borderRadius: FansivibeRadius.mdBorder,
            border: Border.all(
              color: FansivibeColors.primary.withValues(alpha: 0.05),
              width: 0.5,
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: FansivibeColors.primary.withValues(alpha: 0.08),
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
        ),
      ),
    );
  }

  Widget _buildAlternatives(BuildContext context, DailyOutfitData data) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionHeader('Alternatives', '3 more looks for you'),
        SizedBox(height: FansivibeSpacing.md + 4),
        SizedBox(
          height: isTablet(context) ? 230 : 210,
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
                        color: scoreColor.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(6),
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
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
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
                    child: OutlinedButton(
                      onPressed: () => _handleSeeDetails(context, alt),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: FansivibeColors.primary,
                        padding: const EdgeInsets.symmetric(vertical: 6),
                        shape: RoundedRectangleBorder(
                          borderRadius: FansivibeRadius.smBorder,
                        ),
                        side: BorderSide(
                          color: FansivibeColors.primary.withValues(alpha: 0.2),
                        ),
                        textStyle: FansivibeTypography.labelSmallWithFamily
                            .copyWith(
                              fontSize: 10,
                              fontWeight: FontWeight.w600,
                            ),
                      ),
                      child: const Text('See Details'),
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

  Widget _buildQuickActions(BuildContext context, DailyOutfitData data) {
    return Column(
      children: [
        FansiButton.primary(
          label: 'Wear This Look',
          icon: Icons.check_circle_outline_rounded,
          onPressed: () => _handleWearThis(context),
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
          child: OutlinedButton.icon(
            onPressed: () => _handleShare(context),
            icon: const Icon(Icons.share_outlined, size: 18),
            label: const Text('Share'),
            style: OutlinedButton.styleFrom(
              foregroundColor: FansivibeColors.secondary,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(
                borderRadius: FansivibeRadius.fullBorder,
              ),
              side: BorderSide(
                color: FansivibeColors.secondary.withValues(alpha: 0.2),
              ),
              textStyle: FansivibeTypography.bodyLargeWithFamily.copyWith(
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildDailyStyleTip(BuildContext context, DailyOutfitData data) {
    if (data.dailyStyleTip == null) return const SizedBox.shrink();

    return ClipRRect(
      borderRadius: FansivibeRadius.mdBorder,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 6, sigmaY: 6),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                FansivibeColors.primary.withValues(alpha: 0.04),
                FansivibeColors.surfaceContainerLow.withValues(alpha: 0.6),
              ],
            ),
            borderRadius: FansivibeRadius.mdBorder,
            border: Border.all(
              color: FansivibeColors.primary.withValues(alpha: 0.06),
              width: 0.5,
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  color: FansivibeColors.primary.withValues(alpha: 0.1),
                  borderRadius: FansivibeRadius.smBorder,
                ),
                child: Center(
                  child: Icon(
                    Icons.lightbulb_outline_rounded,
                    size: 16,
                    color: FansivibeColors.primary,
                  ),
                ),
              ),
              SizedBox(width: FansivibeSpacing.sm + 4),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Daily Style Tip',
                      style: FansivibeTypography.labelMediumWithFamily.copyWith(
                        color: FansivibeColors.primary,
                        letterSpacing: 1.5,
                        fontSize: 10,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
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
        ),
      ),
    );
  }

  Widget _buildSectionHeader(String title, String subtitle) {
    return Padding(
      padding: const EdgeInsets.only(left: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
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
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
            ),
          ),
        ],
      ),
    );
  }

  void _handleWearThis(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('Wearing this look!'),
        backgroundColor: FansivibeColors.primary,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  void _handleGenerateAnother(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('Generating a new look...'),
        backgroundColor: FansivibeColors.primary,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  void _handleSaveOutfit(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('Outfit saved to your looks'),
        backgroundColor: FansivibeColors.primary,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  void _handleShare(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('Share feature coming soon'),
        backgroundColor: FansivibeColors.surfaceContainerHighest,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  void _handleSeeDetails(BuildContext context, AlternativeLookData alt) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Viewing ${alt.name} details...'),
        backgroundColor: FansivibeColors.primary,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
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
