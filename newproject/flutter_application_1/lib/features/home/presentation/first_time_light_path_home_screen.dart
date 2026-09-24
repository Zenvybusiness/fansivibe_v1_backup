import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/home/presentation/widgets/first_time_home_widgets.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/user_session.dart';

/// First-time Home screen for the light path (Explore Without Scanning).
///
/// Shares the exact visual architecture from Homes.pdf:
/// - FANSIVIBE Branding & greeting
/// - Today's Look curated recommendation card (dynamically tuned to selected vibe)
/// - Scan My Outfit action banner
/// - Style Score uncalibrated baseline (starts at 0)
/// - AI Stylist discovery (Scan Outfit, Hairstyle, Wardrobe)
/// - Style Journey & AI Insight card (state-aware: acknowledges if style direction is chosen or pending)
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
  late Animation<double> _lookAnim;
  late Animation<double> _scanBannerAnim;
  late Animation<double> _scoreAnim;
  late Animation<double> _discoveryAnim;
  late Animation<double> _journeyAnim;

  String? get _resolvedDisplayName {
    final stored = LocalStorage.displayName;
    if (stored != null && stored.trim().isNotEmpty) {
      return stored.trim();
    }
    return null;
  }

  String? get _effectiveVibe => widget.vibeName ?? LocalStorage.vibe;

  bool get _hasSelectedPreferences =>
      _effectiveVibe != null && _effectiveVibe!.trim().isNotEmpty;

  bool get _hasWardrobeItems {
    if (UserSession.hasSavedWardrobeItem) return true;
    try {
      return LearningService.instance.wardrobe.isNotEmpty;
    } catch (_) {
      return false;
    }
  }

  bool get _hasScannedOutfit => LocalStorage.analysisCached;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
    );
    _headerAnim = _buildAnim(0.0, 0.25);
    _lookAnim = _buildAnim(0.12, 0.45);
    _scanBannerAnim = _buildAnim(0.30, 0.60);
    _scoreAnim = _buildAnim(0.45, 0.75);
    _discoveryAnim = _buildAnim(0.60, 0.88);
    _journeyAnim = _buildAnim(0.72, 1.0);
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

  Widget _buildAnimatedSection(Animation<double> anim, Widget child) {
    return AnimatedBuilder(
      animation: anim,
      builder: (context, _) {
        return Opacity(
          opacity: anim.value,
          child: Transform.translate(
            offset: Offset(0, 18 * (1 - anim.value)),
            child: child,
          ),
        );
      },
    );
  }

  void _onTryThisLook() {
    context.pushNamed(RouteNames.dailyOutfit);
  }

  void _onChangeStyle() {
    context.pushNamed(
      RouteNames.vibeSelect,
      extra: {'photoPath': false, 'vibeRequired': false},
    );
  }

  void _onScanOutfit() {
    context.pushNamed(RouteNames.scanOutfit);
  }

  void _onFindHairstyle() {
    context.pushNamed(RouteNames.hairstyle);
  }

  void _onBuildWardrobe() {
    context.goNamed(RouteNames.wardrobe);
  }

  @override
  Widget build(BuildContext context) {
    final curatedLook = getCuratedLookForVibe(_effectiveVibe);

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
                      vertical: 12,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // 1. Branding & Greeting Header
                        _buildAnimatedSection(
                          _headerAnim,
                          FirstTimeHeader(displayName: _resolvedDisplayName),
                        ),
                        const SizedBox(height: 22),

                        // 2. Today's Look Card (dynamically reflects selected vibe)
                        _buildAnimatedSection(
                          _lookAnim,
                          TodaysLookCard(
                            look: curatedLook,
                            onTryLook: _onTryThisLook,
                            onChangeStyle: _onChangeStyle,
                          ),
                        ),
                        const SizedBox(height: 22),

                        // 3. Scan My Outfit Banner
                        _buildAnimatedSection(
                          _scanBannerAnim,
                          ScanOutfitBanner(onScan: _onScanOutfit),
                        ),
                        const SizedBox(height: 24),

                        // 4. Style Score Card (starts at 0 uncalibrated)
                        _buildAnimatedSection(
                          _scoreAnim,
                          StyleScoreCard(onReadyTap: _onScanOutfit),
                        ),
                        const SizedBox(height: 28),

                        // 5. AI Stylist Discovery Section
                        _buildAnimatedSection(
                          _discoveryAnim,
                          AiStylistDiscoverySection(
                            onScanOutfit: _onScanOutfit,
                            onFindHairstyle: _onFindHairstyle,
                            onBuildWardrobe: _onBuildWardrobe,
                          ),
                        ),
                        const SizedBox(height: 28),

                        // 6. Style Journey & AI Insight Card (state-aware)
                        _buildAnimatedSection(
                          _journeyAnim,
                          StyleJourneyCard(
                            hasPreferencesSelected: _hasSelectedPreferences,
                            hasOutfitScanned: _hasScannedOutfit,
                            hasWardrobeItem: _hasWardrobeItems,
                          ),
                        ),
                        const SizedBox(height: 36),
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
