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
    if (!_isFirstVisit) {
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
    setState(() {
      _summaryFuture = _summaryRepository.getSummary();
    });
  }

  void _retryTodayLook() {
    setState(() {
      _todayLookFuture = _todayLookRepository.getTodayLook();
    });
  }

  Map<String, dynamic>? _onboardingDataFromLocalStorage() {
    if (widget.onboardingData != null) return null;
    final hasCompleted = LocalStorage.onboardingComplete;
    final storedDisplayName = LocalStorage.displayName;
    final storedVibe = LocalStorage.vibe;
    if (hasCompleted && storedDisplayName != null) {
      return <String, dynamic>{
        'onboarding_complete': true,
        'display_name': storedDisplayName,
        'vibe': storedVibe,
        'analysis_cached': LocalStorage.analysisCached,
        'saved_locally': LocalStorage.savedLocally,
      };
    }
    return null;
  }

  // Authenticated users always enter the real shell: the first-time/mock
  // branch is onboarding-only (logged-out Maybe-Later / cached preview).
  // A login/register extra must never trap a session into mock content.
  bool get _isFirstVisit =>
      !AuthSession.isAuthenticated &&
      (widget.onboardingData != null ||
          _onboardingDataFromLocalStorage() != null);
  bool get _hasAnalysis =>
      widget.onboardingData?.containsKey('onboarding_complete') == true ||
      (_onboardingDataFromLocalStorage()?.containsKey('onboarding_complete') ==
          true);
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

    if (_isFirstVisit && _hasAnalysis && UserSession.hasSavedWardrobeItem) {
      return FirstTimeLightPathHomeScreen(vibeName: _vibeName);
    }
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
