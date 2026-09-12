import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:fansivibe/features/home/data/today_look_client.dart';
import 'package:fansivibe/features/home/data/today_look_models.dart';
import 'package:fansivibe/features/home/data/today_look_repository.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// Daily Outfit detail surface, backend-first on the M9 Today's Look
/// endpoints (STEP 19.25).
///
/// The backend derivation renders verbatim: title, occasion (only when the
/// backend derived one — never recalculated here, no event fetch), scores,
/// components (UUIDs/names verbatim, never resolved against local mock
/// IDs), reasons, and minimal alternatives. Sourceless mock fields
/// (weather, colorHex, AI notes, insights, style tips) have no backend
/// source and are never shown.
///
/// Regenerate uses `POST /v1/looks/today` with a deterministic seed
/// (`look-1`, `look-2`, … — same seed repeats the backend result, no
/// randomness introduced). Save uses `POST /v1/looks/today/save` with
/// `sourceContext: "daily"`, the response snapshot verbatim, and one fresh
/// `Idempotency-Key` per attempt. Saving never logs a wear event — there
/// is no wear call anywhere in this file.
class DailyOutfitScreen extends StatefulWidget {
  /// Backend Today's Look source. Defaults to the live repository; tests
  /// inject a fake.
  final TodayLookRepository? todayLookRepository;

  const DailyOutfitScreen({super.key, this.todayLookRepository});

  @override
  State<DailyOutfitScreen> createState() => _DailyOutfitScreenState();
}

class _DailyOutfitScreenState extends State<DailyOutfitScreen>
    with SingleTickerProviderStateMixin {
  late final TodayLookRepository _repository;
  late AnimationController _controller;
  late Animation<double> _heroAnim;
  late Animation<double> _editorialAnim;
  late Animation<double> _breakdownAnim;
  late Animation<double> _insightsAnim;
  late Animation<double> _alternativesAnim;
  late Animation<double> _actionsAnim;

  bool _loading = true;
  TodayLook? _look;
  TodayLookFailure? _failure;
  bool _noneAvailable = false;

  bool _regenerating = false;
  int _regenCount = 0;

  bool _saving = false;
  bool _saved = false;

  @override
  void initState() {
    super.initState();
    _repository = widget.todayLookRepository ?? TodayLookRepositoryImpl();
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
    _controller.forward();
    _fetchToday();
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

  Future<void> _fetchToday() async {
    final result = await _repository.getTodayLook();
    if (!mounted) return;
    setState(() {
      _loading = false;
      if (result.available) {
        _look = result.look;
        _failure = null;
        _noneAvailable = false;
      } else if (result.noneAvailable) {
        _look = null;
        _noneAvailable = true;
        _failure = null;
      } else {
        _failure = result.failure;
        _noneAvailable = false;
      }
    });
  }

  void _retry() {
    setState(() {
      _loading = true;
      _failure = null;
      _noneAvailable = false;
    });
    _fetchToday();
  }

  /// Regenerates via `POST /v1/looks/today` with the next deterministic
  /// seed. Guarded while any request is pending; the UI only updates when
  /// the response arrives (never optimistically). A failed regeneration
  /// keeps the current look visible with truthful feedback.
  Future<void> _handleGenerateAnother() async {
    if (_loading || _regenerating || _saving) return;
    setState(() => _regenerating = true);
    _regenCount += 1;
    final result = await _repository.regenerateTodayLook(
      seed: 'look-$_regenCount',
    );
    if (!mounted) return;
    if (result.available) {
      setState(() {
        _look = result.look;
        _failure = null;
        _noneAvailable = false;
        _regenerating = false;
        _saved = false;
      });
    } else {
      setState(() => _regenerating = false);
      _showSnackBar(_regenerateErrorMessage(result));
    }
  }

  String _regenerateErrorMessage(TodayLookResult result) {
    if (result.noneAvailable) {
      return 'No alternative look available right now.';
    }
    switch (result.failure) {
      case TodayLookFailure.serviceUnavailable:
        return 'Style service unavailable. Please try again.';
      case TodayLookFailure.rateLimited:
        return 'Too many requests. Please wait and try again.';
      case TodayLookFailure.networkError:
        return 'Couldn\'t regenerate. Please check your connection.';
      default:
        return 'Couldn\'t generate another look. Please try again.';
    }
  }

  /// Saves via `POST /v1/looks/today/save` (`sourceContext: "daily"`,
  /// snapshot verbatim, fresh Idempotency-Key per attempt). Guarded while
  /// any request is pending and disabled once saved, so repeated taps
  /// never duplicate the save. A failed save keeps the look visible with
  /// truthful retry feedback. Never logs a wear event.
  Future<void> _handleSaveOutfit() async {
    final look = _look;
    if (_loading || _saving || _regenerating || look == null || _saved) return;
    final title = look.title.trim();
    if (title.isEmpty || title.length > 200) {
      _showSnackBar('This look can\'t be saved (invalid title).');
      return;
    }
    setState(() => _saving = true);
    final saved = await _repository.saveTodayLook(
      title: look.title,
      snapshot: look.snapshot,
      idempotencyKey: newTodayLookIdempotencyKey(),
    );
    if (!mounted) return;
    setState(() => _saving = false);
    if (saved != null) {
      setState(() => _saved = true);
      _showSnackBar('Today\'s look saved');
    } else {
      _showSnackBar('Couldn\'t save this look. Please try again.');
    }
  }

  void _showSnackBar(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: FansivibeColors.primary,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.smdBorder),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final look = _look;
    if (_loading) {
      return _stateScaffold(
        context,
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    if (look == null) {
      if (_noneAvailable) {
        return _stateScaffold(
          context,
          body: _stateMessage(
            context,
            title: 'No today\'s look available',
            message:
                'There\'s no legal outfit candidate right now. Add wardrobe '
                'pieces to unlock your daily recommendation.',
          ),
        );
      }
      return _stateScaffold(
        context,
        body: _stateMessage(
          context,
          title: 'Couldn\'t load today\'s look',
          message: _failureMessage(_failure),
        ),
      );
    }

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
                        _buildHeroSection(context, look, constraints),
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
                              _buildEditorialSummary(context, look),
                            ),
                            SizedBox(height: FansivibeSpacing.xxl),
                            _animatedSection(
                              _breakdownAnim,
                              reduceMotion,
                              _buildOutfitBreakdown(context, look),
                            ),
                            if (look.reasons.isNotEmpty) ...[
                              SizedBox(height: FansivibeSpacing.xxl),
                              _animatedSection(
                                _insightsAnim,
                                reduceMotion,
                                _buildWhyItWorks(context, look),
                              ),
                            ],
                            if (look.alternatives.isNotEmpty) ...[
                              SizedBox(height: FansivibeSpacing.xxl),
                              _animatedSection(
                                _alternativesAnim,
                                reduceMotion,
                                _buildAlternatives(context, look),
                              ),
                            ],
                            SizedBox(height: FansivibeSpacing.xxl),
                            _animatedSection(
                              _actionsAnim,
                              reduceMotion,
                              _buildQuickActions(context, look),
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

  String _failureMessage(TodayLookFailure? failure) {
    switch (failure) {
      case TodayLookFailure.unauthorized:
        return 'Please sign in again to see today\'s look.';
      case TodayLookFailure.rateLimited:
        return 'Too many requests. Please wait and try again.';
      case TodayLookFailure.serviceUnavailable:
        return 'Style service unavailable. Please try again.';
      case TodayLookFailure.networkError:
        return 'Please check your connection and try again.';
      default:
        return 'Something went wrong. Please try again.';
    }
  }

  /// Chrome for loading/empty/error states: static back affordance plus
  /// the screen title so navigation out always works. Never poses data.
  Widget _stateScaffold(BuildContext context, {required Widget body}) {
    return Scaffold(
      backgroundColor: FansivibeColors.surface,
      body: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
              child: Row(
                children: [
                  Semantics(
                    button: true,
                    child: GestureDetector(
                      onTap: () => Navigator.of(context).pop(),
                      child: _glassCircle(
                        icon: Icons.arrow_back_rounded,
                        size: 40,
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Text(
                    'TODAY\'S LOOK',
                    style: FansivibeTypography.headlineMediumWithFamily
                        .copyWith(fontSize: 20, fontWeight: FontWeight.w500),
                  ),
                ],
              ),
            ),
            Expanded(child: body),
          ],
        ),
      ),
    );
  }

  Widget _stateMessage(
    BuildContext context, {
    required String title,
    required String message,
  }) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              title,
              textAlign: TextAlign.center,
              style: FansivibeTypography.headlineMediumWithFamily.copyWith(
                fontSize: 22,
                fontWeight: FontWeight.w500,
              ),
            ),
            SizedBox(height: FansivibeSpacing.sm),
            Text(
              message,
              textAlign: TextAlign.center,
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.secondary,
                fontSize: 14,
                height: 1.5,
              ),
            ),
            SizedBox(height: FansivibeSpacing.lg),
            FansiButton.secondary(
              label: 'Try Again',
              icon: Icons.refresh_rounded,
              onPressed: _retry,
            ),
          ],
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
    TodayLook look,
    BoxConstraints constraints,
  ) {
    final viewHeight = MediaQuery.of(context).size.height;
    final heroHeight = (viewHeight * 0.6).clamp(380.0, 520.0).toDouble();
    final w = constraints.maxWidth;
    final isTablet = w > 600;
    final p = isTablet ? 48.0 : 20.0;
    final scoreColor = _scoreColor(look.matchScore);

    final panelWidth = w * 0.62;
    final panelHeight = heroHeight * 0.5;
    final panelTop = heroHeight * 0.17;
    final panelLeft = w - panelWidth + 14;

    final occasion = look.occasion;

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
              text: '${look.matchScore}%',
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
          if (occasion != null)
            Positioned(
              left: p,
              bottom: p,
              child: Wrap(
                spacing: FansivibeSpacing.sm,
                runSpacing: FansivibeSpacing.sm,
                children: [
                  _garmentTag(
                    occasion,
                    icon: Icons.event_outlined,
                    color: FansivibeColors.primary,
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

  Widget _buildEditorialSummary(BuildContext context, TodayLook look) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _goldLabel('THE DAILY EDIT'),
        SizedBox(height: FansivibeSpacing.sm),
        Text(
          look.title,
          style: FansivibeTypography.displayLargeWithFamily.copyWith(
            fontSize: 36,
            fontWeight: FontWeight.w500,
            height: 1.1,
            letterSpacing: -0.5,
          ),
        ),
        SizedBox(height: FansivibeSpacing.md),
        Text(
          look.description,
          style: FansivibeTypography.bodyLargeWithFamily.copyWith(
            color: FansivibeColors.secondary,
            height: 1.6,
            fontSize: 16,
          ),
        ),
      ],
    );
  }

  // ─────────────────────────── THE ENSEMBLE ───────────────────────────

  Widget _buildOutfitBreakdown(BuildContext context, TodayLook look) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionHeader('The Ensemble', '${look.components.length} pieces'),
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
            itemCount: look.components.length,
            separatorBuilder: (_, __) =>
                SizedBox(width: FansivibeSpacing.sm + 4),
            itemBuilder: (context, index) {
              return _componentCard(
                context,
                look.components[index],
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
    TodayLookComponent component,
    bool isTablet,
  ) {
    // No colorHex on the wire (no server source): neutral primary tint.
    const color = FansivibeColors.primary;
    final cardWidth = isTablet ? 200.0 : 170.0;

    final detail = component.material == null
        ? component.color
        : '${component.color} \u2022 ${component.material}';

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
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Flexible(
                      child: Text(
                        component.name,
                        style: FansivibeTypography.titleLargeWithFamily
                            .copyWith(
                              fontWeight: FontWeight.w600,
                              color: FansivibeColors.onSurface,
                              fontSize: 13,
                            ),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    SizedBox(height: FansivibeSpacing.xs + 2),
                    Row(
                      children: [
                        Container(
                          width: 8,
                          height: 8,
                          decoration: const BoxDecoration(
                            shape: BoxShape.circle,
                            color: color,
                          ),
                        ),
                        SizedBox(width: FansivibeSpacing.xs + 2),
                        Flexible(
                          child: Text(
                            detail,
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
            ),
          ],
        ),
      ),
    );
  }

  // ─────────────────────────── WHY IT WORKS ───────────────────────────

  Widget _buildWhyItWorks(BuildContext context, TodayLook look) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionHeader('Why It Works', 'Grounded in your wardrobe'),
        SizedBox(height: FansivibeSpacing.md + 4),
        ...List.generate(look.reasons.length, (index) {
          final reason = look.reasons[index];
          return Padding(
            padding: EdgeInsets.only(
              bottom: index < look.reasons.length - 1
                  ? FansivibeSpacing.sm + 4
                  : 0,
            ),
            child: _reasonCard(context, reason),
          );
        }),
      ],
    );
  }

  Widget _reasonCard(BuildContext context, String reason) {
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
            child: const Center(
              child: Icon(
                Icons.check_rounded,
                size: 18,
                color: FansivibeColors.primary,
              ),
            ),
          ),
          SizedBox(width: FansivibeSpacing.sm + 4),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                reason,
                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                  color: FansivibeColors.secondary,
                  fontSize: 13,
                  height: 1.5,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ─────────────────────────── ALTERNATIVES ───────────────────────────

  Widget _buildAlternatives(BuildContext context, TodayLook look) {
    final alternatives = look.alternatives;
    final count = alternatives.length;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSectionHeader(
          'Alternatives',
          '$count more look${count == 1 ? '' : 's'} for you',
        ),
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
            itemCount: alternatives.length,
            separatorBuilder: (_, __) =>
                SizedBox(width: FansivibeSpacing.sm + 4),
            itemBuilder: (context, index) {
              return _alternativeCard(
                context,
                alternatives[index],
                index,
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
    TodayLookAlternative alternative,
    int index,
    bool isTablet,
  ) {
    final cardWidth = isTablet ? 220.0 : 190.0;
    final scoreColor = _scoreColor(alternative.matchScore);

    // Minimal backend mapping (id + score only): no invented names, no
    // fabricated detail navigation.
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
                            '${alternative.matchScore}%',
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
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(12, 12, 12, 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Flexible(
                      child: Text(
                        'Alternative ${index + 1}',
                        style: FansivibeTypography.titleLargeWithFamily
                            .copyWith(
                              fontSize: 14,
                              fontWeight: FontWeight.w600,
                            ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    SizedBox(height: FansivibeSpacing.xs - 2),
                    Flexible(
                      child: Text(
                        'Another way to wear your wardrobe',
                        style: FansivibeTypography.labelSmallWithFamily
                            .copyWith(
                              color: FansivibeColors.secondary,
                              fontSize: 10,
                            ),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ─────────────────────────── QUICK ACTIONS ───────────────────────────

  Widget _buildQuickActions(BuildContext context, TodayLook look) {
    final busy = _loading || _regenerating || _saving;
    return Column(
      children: [
        FansiButton.secondary(
          label: _regenerating ? 'Generating…' : 'Generate Another Look',
          icon: Icons.refresh_rounded,
          onPressed: busy ? null : _handleGenerateAnother,
        ),
        SizedBox(height: FansivibeSpacing.sm + 4),
        FansiButton.secondary(
          label: _saved ? 'Saved' : (_saving ? 'Saving…' : 'Save Look'),
          icon: _saved
              ? Icons.bookmark_rounded
              : Icons.bookmark_outline_rounded,
          onPressed: busy || _saved ? null : _handleSaveOutfit,
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

  Color _scoreColor(int score) {
    if (score >= 90) return FansivibeColors.success;
    if (score >= 80) return FansivibeColors.primary;
    if (score >= 70) return FansivibeColors.warning;
    return FansivibeColors.error;
  }

  IconData _categoryIcon(String category) {
    switch (category.toLowerCase()) {
      case 'outerwear':
        return Icons.checkroom_rounded;
      case 'tops':
        return Icons.person_rounded;
      case 'bottoms':
        return Icons.accessibility_rounded;
      case 'footwear':
        return Icons.directions_walk_rounded;
      case 'accessories':
        return Icons.diamond_rounded;
      default:
        return Icons.category_rounded;
    }
  }
}
