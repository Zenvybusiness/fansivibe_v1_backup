import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/events/data/event_models.dart';
import 'package:fansivibe/features/events/data/events_repository.dart';
import 'package:fansivibe/features/home/data/home_mock_data.dart';
import 'package:fansivibe/features/home/presentation/first_time_home_screen.dart';
import 'package:fansivibe/features/home/presentation/first_time_light_path_home_screen.dart';
import 'package:fansivibe/features/home/presentation/widgets/backend_summary_cards.dart';
import 'package:fansivibe/features/home/presentation/widgets/existing_user_home_widgets.dart';
import 'package:fansivibe/features/home/presentation/widgets/home_widgets.dart';
import 'package:fansivibe/features/home/today_look.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart'
    show WardrobeInsightData;
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/user_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

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

  /// Backend event calendar source (M8). Defaults to live repository;
  /// tests inject a fake.
  final EventsRepository? eventsRepository;

  const HomeScreen({
    super.key,
    this.onboardingData,
    this.summaryRepository,
    this.todayLookRepository,
    this.wardrobeRepository,
    this.eventsRepository,
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
  late final EventsRepository _eventsRepository;
  Future<EventListPage?>? _eventsFuture;

  void _initEstablishedFuturesIfNeeded() {
    if (_summaryFuture != null) return;
    _summaryRepository =
        widget.summaryRepository ?? LearningSummaryRepositoryImpl();
    _summaryFuture = _summaryRepository.getSummary();
    _todayLookRepository =
        widget.todayLookRepository ?? TodayLookRepositoryImpl();
    _todayLookFuture = _todayLookRepository.getTodayLook();
    _wardrobeRepository =
        widget.wardrobeRepository ?? WardrobeRepositoryImpl();
    _insightFuture = _wardrobeRepository.getInsight();
    _eventsRepository =
        widget.eventsRepository ?? EventsRepositoryImpl();
    if (AuthSession.isAuthenticated && !isGuestUser) {
      _eventsFuture = _eventsRepository.listEvents(page: 1, pageSize: 5);
    }
  }

  @override
  void initState() {
    super.initState();
    LearningService.instance.addListener(_onLocalChanged);
    UserSession.savedWardrobeItemNotifier.addListener(_onLocalChanged);

    if (isGuestUser) {
      LearningService.instance.load().then((_) {
        if (mounted) setState(() {});
      });
    }
    if (!_isFirstVisit && !isGuestUser) {
      _initEstablishedFuturesIfNeeded();
    }
  }

  void _retrySummary() {
    if (isGuestUser) return;
    _initEstablishedFuturesIfNeeded();
    setState(() {
      _summaryFuture = _summaryRepository.getSummary();
    });
  }

  @override
  void dispose() {
    LearningService.instance.removeListener(_onLocalChanged);
    UserSession.savedWardrobeItemNotifier.removeListener(_onLocalChanged);
    super.dispose();
  }

  void _onLocalChanged() {
    if (!mounted) return;
    if (!_isFirstVisit && !isGuestUser) {
      _initEstablishedFuturesIfNeeded();
    }
    setState(() {});
  }

  void _retryTodayLook() {
    if (isGuestUser) return;
    _initEstablishedFuturesIfNeeded();
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
    if (widget.onboardingData?['is_login'] == true) {
      UserSession.isReturningUser = true;
      return false;
    }
    if (UserSession.isReturningUser) return false;
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

    if (!_isFirstVisit && !isGuestUser) {
      _initEstablishedFuturesIfNeeded();
    }

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
                        const SizedBox(height: 12),
                        // 1. Header (FANSIVIBE wordmark, notification bell, profile avatar)
                        ExistingUserHeader(
                          onNotificationTap: () {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text('No new notifications'),
                                duration: Duration(seconds: 2),
                              ),
                            );
                          },
                          onAvatarTap: () => context.goNamed(RouteNames.profile),
                        ),
                        const SizedBox(height: 24),

                        // 2. Personal Greeting (YOUR DAILY EDIT, Good morning, [User])
                        _buildGreetingHeader(theme, _displayName),
                        const SizedBox(height: 28),

                        // 3. Today's Look (Hero Outfit with actions)
                        _buildTodaysLookSlot(context),

                        // Optional: Contextual assistance for established user with 0 items
                        if (learningService.wardrobe.isEmpty && !isGuestUser) ...[
                          const SizedBox(height: 24),
                          ZeroWardrobeContextCard(
                            onAddWardrobeItem: () =>
                                context.pushNamed(RouteNames.wardrobeAddItem),
                          ),
                        ],
                        const SizedBox(height: 24),

                        // 4. Style Score
                        _buildScoreSlot(),
                        const SizedBox(height: 24),

                        // 5. AI Insight
                        _buildAIInsight(),
                        const SizedBox(height: 24),

                        // 6. Upcoming Event
                        _buildUpcomingSlot(),
                        const SizedBox(height: 24),

                        // 7. AI Stylist (2x2 Grid)
                        _buildAiStylist(context, learningService),
                        const SizedBox(height: 28),

                        // 8. Curated For You (asymmetric Pinterest grid)
                        ExistingUserCuratedForYou(
                          onLookTap: (title) =>
                              context.pushNamed(RouteNames.discover),
                        ),
                        const SizedBox(height: 28),

                        // 9. Trending For You
                        ExistingUserTrending(
                          onTrendingTap: () =>
                              context.pushNamed(RouteNames.discover),
                        ),
                        const SizedBox(height: 28),

                        // 10. Style Journey (Progress visualization & streaks)
                        _buildStyleJourney(),
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

  Widget _buildGreetingHeader(ThemeData theme, String? displayName) {
    return ExistingUserGreeting(displayName: displayName);
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
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ExistingUserStyleScoreCard(
            score: service.styleScore,
            scoreChange: 'DEVICE ONLY',
            rankingLabel: 'LOCAL',
            supportingText: '$pieces ${pieces == 1 ? 'piece' : 'pieces'} · '
                '$favorites ${favorites == 1 ? 'favorite' : 'favorites'} on this device — grows as you add clothes.',
          ),
          const SizedBox(height: 8),
          FansiButton.tertiary(
            label: 'Sign in to sync & back up',
            onPressed: () => promptGuestSignIn(context),
          ),
        ],
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

  Widget _buildAiStylist(
    BuildContext context,
    LearningService learningService,
  ) {
    return ExistingUserAiStylistGrid(
      onScanMyOutfit: () => context.pushNamed(RouteNames.scanOutfit),
      onBuildFromWardrobe: () => context.pushNamed(RouteNames.buildOutfit),
      onPlanEvent: () => context.pushNamed(RouteNames.events),
      onHairstyle: () => context.pushNamed(RouteNames.hairstyle),
    );
  }

  Widget _buildAIInsight() {
    // Backend-first wardrobe insight (P2-8): live backend insight renders
    // verbatim via [ExistingUserAiInsightCard]. When unavailable (204 empty
    // wardrobe, loading, or network error), renders the editorial guidance
    // card matching the visual reference.
    return FutureBuilder<WardrobeInsightData?>(
      future: _insightFuture,
      builder: (context, snapshot) {
        final insight = snapshot.data;
        if (insight != null) {
          return ExistingUserAiInsightCard(
            quote: insight.title,
            supportingText: insight.insight,
            onExploreTap: () => context.pushNamed(RouteNames.discover),
          );
        }
        return ExistingUserAiInsightCard(
          quote:
              '“Your recent looks are leaning toward structured silhouettes and neutral palettes.”',
          supportingText:
              'Try introducing one warmer accent this week to create dynamic visual depth.',
          onExploreTap: () => context.pushNamed(RouteNames.discover),
        );
      },
    );
  }

  Widget _buildUpcomingSlot() {
    if (isGuestUser || !AuthSession.isAuthenticated) {
      return ExistingUserUpcomingCard(
        hasEvent: false,
        onCreateEvent: () => context.pushNamed(RouteNames.eventAdd),
      );
    }
    return FutureBuilder<EventListPage?>(
      future: _eventsFuture,
      builder: (context, snapshot) {
        final page = snapshot.data;
        if (page != null && page.items.isNotEmpty) {
          final event = page.items.first;
          final timeOrDate = event.eventTime ?? event.displayDate;
          final locationStr = event.location ?? 'Fansivibe Atelier';
          return ExistingUserUpcomingCard(
            hasEvent: true,
            title: event.title,
            occasion: event.eventType.toUpperCase(),
            locationAndTime: '$locationStr • $timeOrDate',
            onPlanMyLook: () => context.pushNamed(
              RouteNames.buildOutfit,
              extra: {
                'eventId': event.id,
                'eventTitle': event.title,
                'occasion': event.eventType,
              },
            ),
          );
        }
        return ExistingUserUpcomingCard(
          hasEvent: false,
          onCreateEvent: () => context.pushNamed(RouteNames.eventAdd),
        );
      },
    );
  }

  Widget _buildStyleJourney() {
    // 30-day overview is server-tracked across weeks — guests have no
    // account history so the slot hides rather than posing historical data.
    if (isGuestUser) return const SizedBox.shrink();
    return FutureBuilder<LearningSummary?>(
      future: _summaryFuture,
      builder: (context, snapshot) {
        final summary = snapshot.data;
        final score = summary?.styleScore ?? 86;
        final streak = summary?.streak ?? 0;
        return Column(
          children: [
            ExistingUserStyleJourney(
              currentScore: score,
              streakDays: streak,
            ),
            const SizedBox(height: 16),
            _buildStreakSlot(),
          ],
        );
      },
    );
  }
}
