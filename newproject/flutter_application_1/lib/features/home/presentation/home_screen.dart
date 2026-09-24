import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/home/data/home_mock_data.dart';
import 'package:fansivibe/features/home/presentation/first_time_home_screen.dart';
import 'package:fansivibe/features/home/presentation/first_time_light_path_home_screen.dart';
import 'package:fansivibe/features/home/presentation/widgets/backend_summary_cards.dart';
import 'package:fansivibe/features/home/presentation/widgets/home_widgets.dart';
import 'package:fansivibe/features/home/today_look.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/widgets/wardrobe_widgets.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/user_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

class HomeScreen extends StatefulWidget {
  final Map<String, dynamic>? onboardingData;

  /// Backend summary source (M10-C). Defaults to the live repository;
  /// tests inject a fake. Null future while loading is impossible here:
  /// the future is created once in [initState] for the main branch.
  final LearningSummaryRepository? summaryRepository;

  /// Backend Today's Look source (M9, STEP 19.25). Defaults to the live
  /// repository; tests inject a fake. Fetched once for the main branch
  /// only — first-visit onboarding shows no look slot.
  final TodayLookRepository? todayLookRepository;

  /// Backend wardrobe insight source (P2-8). Defaults to the live
  /// repository; tests inject a fake. Fetched once for the main branch
  /// only — first-visit onboarding shows no insight slot.
  final WardrobeRepository? wardrobeRepository;

  const HomeScreen({
    super.key,
    this.onboardingData,
    this.summaryRepository,
    this.todayLookRepository,
    this.wardrobeRepository,
  });

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late final LearningSummaryRepository _summaryRepository;
  Future<LearningSummary?>? _summaryFuture;
  late final TodayLookRepository _todayLookRepository;
  Future<TodayLookResult>? _todayLookFuture;
  late final WardrobeRepository _wardrobeRepository;
  Future<WardrobeInsightData?>? _insightFuture;

  @override
  void initState() {
    super.initState();
    // Backend-first M10 summary (STEP 19.16): fetched once for the main
    // branch only — first-visit onboarding shows no summary slots.
    // Null means unavailable: slots render their honest error state.
    // Phase 2.1 guests run the score slot on-device (see
    // _buildScoreSlot): hydrate the persisted local model and refresh
    // the slot live as wardrobe items are added.
    if (isGuestUser) {
      LearningService.instance.addListener(_onLocalChanged);
      LearningService.instance.load().then((_) {
        if (mounted) setState(() {});
      });
    }
    if (!_isFirstVisit && !isGuestUser) {
      _summaryRepository =
          widget.summaryRepository ?? LearningSummaryRepositoryImpl();
      _summaryFuture = _summaryRepository.getSummary();
      // Backend-first M9 Today's Look (STEP 19.25): same single-fetch
      // discipline — one GET feeds the slot; failures render honest
      // loading/error/empty states, never mock content.
      _todayLookRepository =
          widget.todayLookRepository ?? TodayLookRepositoryImpl();
      _todayLookFuture = _todayLookRepository.getTodayLook();
      // Backend-first wardrobe insight (P2-8): live backend insight renders
      // truthful intelligence; empty/null response hides the card.
      _wardrobeRepository =
          widget.wardrobeRepository ?? WardrobeRepositoryImpl();
      _insightFuture = _wardrobeRepository.getInsight();
    }
  }

  void _retrySummary() {
    if (isGuestUser) return;
    setState(() {
      _summaryFuture = _summaryRepository.getSummary();
    });
  }

  @override
  void dispose() {
    if (isGuestUser) {
      LearningService.instance.removeListener(_onLocalChanged);
    }
    super.dispose();
  }

  void _onLocalChanged() {
    if (mounted) setState(() {});
  }

  void _retryTodayLook() {
    if (isGuestUser) return;
    setState(() {
      _todayLookFuture = _todayLookRepository.getTodayLook();
    });
  }

  Map<String, dynamic>? _onboardingDataFromLocalStorage() {
    if (widget.onboardingData != null) return null;
    final hasCompleted = LocalStorage.onboardingComplete;
    final storedDisplayName = LocalStorage.displayName;
    final storedVibe = LocalStorage.vibe;
    if (hasCompleted || storedVibe != null) {
      return <String, dynamic>{
        'onboarding_complete': hasCompleted,
        'display_name': storedDisplayName,
        'vibe': storedVibe,
        'analysis_cached': LocalStorage.analysisCached,
        'saved_locally': LocalStorage.savedLocally,
      };
    }
    return null;
  }

  bool get _hasEstablishedHistory {
    // If the user already has saved wardrobe items
    if (UserSession.hasSavedWardrobeItem) return true;
    try {
      if (LearningService.instance.signals.isNotEmpty) return true;
      if (LearningService.instance.savedLooks.isNotEmpty) return true;
    } catch (_) {}
    if (LocalStorage.savedLookIds.isNotEmpty) return true;
    return false;
  }

  // First-time users see the Homes.pdf first-time Home experience (whether
  // newly registered or exploring as guest) until they build wardrobe/scan history.
  // Returning login users or users with established history enter the established Home.
  bool get _isFirstVisit {
    if (widget.onboardingData?['is_login'] == true) return false;
    if (_hasEstablishedHistory) return false;
    final data = widget.onboardingData ?? _onboardingDataFromLocalStorage();
    return data != null;
  }

  bool get _hasAnalysis {
    final data = widget.onboardingData ?? _onboardingDataFromLocalStorage();
    return data?['onboarding_complete'] == true ||
        LocalStorage.analysisCached ||
        (data?['display_name'] != null &&
            (data!['display_name'] as String).trim().isNotEmpty);
  }

  String? get _displayName {
    final raw = widget.onboardingData?['display_name'] as String? ??
        _onboardingDataFromLocalStorage()?['display_name'] as String? ??
        LocalStorage.displayName;
    if (raw == null || raw.trim().isEmpty) return null;
    return raw.trim();
  }

  String? get _vibeName =>
      widget.onboardingData?['vibe'] as String? ??
      _onboardingDataFromLocalStorage()?['vibe'] as String?;

  @override
  Widget build(BuildContext context) {
    final learningService = LearningService.instance;

    final String chosenWidget;
    if (_isFirstVisit && _hasAnalysis) {
      chosenWidget = 'FirstTimeHomeScreen';
    } else if (_isFirstVisit) {
      chosenWidget = 'FirstTimeLightPathHomeScreen';
    } else {
      chosenWidget = 'HomeScreen';
    }

    debugPrint(
      'FIRST_TIME_HOME_RUNTIME:\n'
      'route=/home\n'
      'widget=$chosenWidget\n'
      'auth=${AuthSession.isAuthenticated}\n'
      'firstTime=$_isFirstVisit\n'
      'hasAnalysis=$_hasAnalysis\n'
      'preferences=${_vibeName != null || LocalStorage.vibe != null}\n'
      'displayName=$_displayName\n'
      'onboardingData=${widget.onboardingData}',
    );

    if (_isFirstVisit && _hasAnalysis) {
      return FirstTimeHomeScreen(displayName: _displayName);
    }
    if (_isFirstVisit) {
      return FirstTimeLightPathHomeScreen(vibeName: _vibeName);
    }

    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
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
                        const SizedBox(height: 8),
                        _buildGreetingHeader(theme, _displayName),
                        const SizedBox(height: 28),
                        _buildTodaysLookSlot(context),
                        const SizedBox(height: 24),
                        _buildScoreSlot(),
                        const SizedBox(height: 24),
                        HomeSectionTitle(
                          title: 'Quick Actions',
                          subtitle: 'AI-powered style tools',
                        ),
                        const SizedBox(height: 16),
                        _buildQuickActions(context, learningService),
                        const SizedBox(height: 24),
                        _buildStreakSlot(),
                        _buildAIInsight(),
                        const SizedBox(height: 32),
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

  Widget _buildScoreSlot() {
    // Phase 2.1 guests: the real on-device score (60 + wardrobe items +
    // saved looks, via LearningService) — no fetch, no faking, and the
    // limitation (device-only until sign-in) is stated on the card.
    if (isGuestUser) {
      final service = LearningService.instance;
      final pieces = service.wardrobe.length;
      final favorites =
          service.wardrobe.where((e) => e.isFavorite).length;
      final theme = Theme.of(context);
      return FansivibeCard(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Style Score',
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w600,
                color: FansivibeColors.textPrimary,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              '${service.styleScore}',
              style: theme.textTheme.displayLarge?.copyWith(
                fontWeight: FontWeight.bold,
                color: FansivibeColors.accentGold,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              '$pieces ${pieces == 1 ? 'piece' : 'pieces'} · '
              '$favorites ${favorites == 1 ? 'favorite' : 'favorites'} '
              'on this device — grows as you add clothes.',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: FansivibeColors.textSecondary,
              ),
            ),
            const SizedBox(height: 8),
            FansiButton.tertiary(
              label: 'Sign in to sync & back up',
              onPressed: () => promptGuestSignIn(context),
            ),
          ],
        ),
      );
    }
    // Backend-first M10 score (STEP 19.16): the server value renders
    // verbatim. Loading and error states keep the slot title with no
    // value — there is deliberately no mock fallback here.
    return FutureBuilder<LearningSummary?>(
      future: _summaryFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const SummaryLoadingCard(title: 'Style Score');
        }
        final summary = snapshot.data;
        if (snapshot.hasError || summary == null) {
          return SummaryErrorCard(
            title: 'Style Score',
            message:
                'Couldn\'t load style summary. Please check your connection.',
            onRetry: _retrySummary,
          );
        }
        return BackendStyleScoreCard(summary: summary);
      },
    );
  }

  Widget _buildStreakSlot() {
    // Phase 2.1 guests: streaks are server-tracked — no on-device
    // equivalent exists, so the slot hides rather than inventing one.
    if (isGuestUser) return const SizedBox.shrink();
    // Backend-first M10 streak (STEP 19.16): same future as the score
    // slot, so one GET feeds both — no second request, no local math.
    return FutureBuilder<LearningSummary?>(
      future: _summaryFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const SummaryLoadingCard(title: 'Style Streak');
        }
        final summary = snapshot.data;
        if (snapshot.hasError || summary == null) {
          return SummaryErrorCard(
            title: 'Style Streak',
            message:
                'Couldn\'t load style summary. Please check your connection.',
            onRetry: _retrySummary,
          );
        }
        return BackendStyleStreakCard(streak: summary.streak);
      },
    );
  }

  Widget _buildGreetingHeader(ThemeData theme, String? displayName) {
    return GreetingHeader(
      data: GreetingData(
        greeting: 'Good morning',
        name: displayName ?? '',
        dateLabel: _formatDate(),
      ),
    );
  }

  String _formatDate() {
    final now = DateTime.now();
    final weekdays = [
      'Monday',
      'Tuesday',
      'Wednesday',
      'Thursday',
      'Friday',
      'Saturday',
      'Sunday',
    ];
    final months = [
      'January',
      'February',
      'March',
      'April',
      'May',
      'June',
      'July',
      'August',
      'September',
      'October',
      'November',
      'December',
    ];
    return '${weekdays[now.weekday - 1]}, ${months[now.month - 1]} ${now.day}';
  }

  Widget _buildTodaysLookSlot(BuildContext context) {
    // Phase 2 guests: no session, no fetch — honest sign-in prompt
    // instead of a 401-backed error card.
    if (isGuestUser) {
      return const GuestSignInCard(
        title: "Today's Look",
        message:
            'Your daily look lives in your account. Sign in to get personalized recommendations — browsing stays free.',
      );
    }
    // Backend-first M9 Today's Look (STEP 19.25): the server derivation
    // renders verbatim. Loading/empty/error states keep the slot title
    // with no value — there is deliberately no mock fallback here, and a
    // failed look never makes the rest of Home unusable. Navigation is
    // preserved: Try opens the Daily Outfit detail surface, Change Style
    // opens the outfit builder.
    return FutureBuilder<TodayLookResult>(
      future: _todayLookFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const SummaryLoadingCard(title: "Today's Look");
        }
        final result = snapshot.data;
        if (result == null || result.failure != null) {
          return SummaryErrorCard(
            title: "Today's Look",
            message:
                'Couldn\'t load today\'s look. Please check your connection.',
            onRetry: _retryTodayLook,
          );
        }
        if (result.noneAvailable) {
          return SummaryErrorCard(
            title: "Today's Look",
            message:
                'No today\'s look available right now. Add wardrobe pieces '
                'to unlock your daily recommendation.',
            onRetry: _retryTodayLook,
          );
        }
        final look = result.look!;
        return TodaysLookCard(
          data: _todayLookCardData(look),
          onTryThisLook: () => context.pushNamed(RouteNames.dailyOutfit),
          onChangeStyle: () => context.pushNamed(RouteNames.buildOutfit),
        );
      },
    );
  }

  /// Maps the backend [TodayLook] onto the existing card data without
  /// inventing content: title/description/scores verbatim, component UUIDs
  /// and names verbatim (never resolved against local mock IDs, never
  /// fetched again here). `occasion` shows only when the backend derived
  /// one — the static 'Everyday' fallback is presentation copy, never an
  /// event recalculation (no event fetch happens in this layer).
  TodaysLookData _todayLookCardData(TodayLook look) {
    return TodaysLookData(
      title: look.title,
      occasion: look.occasion ?? 'Everyday',
      weather: '',
      description: look.description,
      items: look.components
          .map(
            (component) => OutfitItemData(
              id: component.id,
              name: component.name,
              category: component.category,
              color: component.color,
            ),
          )
          .toList(),
      styleScore: look.styleScore,
    );
  }

  Widget _buildQuickActions(
    BuildContext context,
    LearningService learningService,
  ) {
    final hasData =
        learningService.wardrobe.isNotEmpty ||
        learningService.savedLooks.isNotEmpty;

    if (!hasData) {
      return const SizedBox.shrink();
    }

    final actions = QuickActionData.mockActions;
    return Column(
      children: actions.map((action) {
        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: QuickActionCard(
            data: action,
            onTap: () => _handleQuickAction(context, action),
          ),
        );
      }).toList(),
    );
  }

  Widget _buildAIInsight() {
    // Backend-first wardrobe insight (P2-8): live backend insight renders
    // verbatim via [WardrobeInsightCard]. When unavailable (204 empty
    // wardrobe, loading, or network error), the slot is hidden rather than
    // fabricating user intelligence or mock advice.
    return FutureBuilder<WardrobeInsightData?>(
      future: _insightFuture,
      builder: (context, snapshot) {
        final insight = snapshot.data;
        if (insight == null) {
          return const SizedBox.shrink();
        }
        return Padding(
          padding: const EdgeInsets.only(top: 24),
          child: WardrobeInsightCard(data: insight),
        );
      },
    );
  }

  void _handleQuickAction(BuildContext context, QuickActionData action) {
    switch (action.id) {
      case 'scan_outfit':
        context.pushNamed(RouteNames.scanOutfit);
        break;
      case 'build_outfit':
        context.pushNamed(RouteNames.buildOutfit);
        break;
      case 'change_style':
        context.pushNamed(RouteNames.buildOutfit);
        break;
      default:
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Opening ${action.title}...'),
            backgroundColor: Color(action.accentColor),
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(
              borderRadius: FansivibeRadius.smdBorder,
            ),
          ),
        );
    }
  }
}
