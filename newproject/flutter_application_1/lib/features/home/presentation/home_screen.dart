import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/events/data/event_models.dart';
import 'package:fansivibe/features/events/data/events_repository.dart';
import 'package:fansivibe/features/home/data/home_mock_data.dart';
import 'package:fansivibe/features/home/presentation/first_time_home_screen.dart';
import 'package:fansivibe/features/home/presentation/widgets/backend_summary_cards.dart';
import 'package:fansivibe/features/home/presentation/widgets/existing_user_home_widgets.dart';
import 'package:fansivibe/features/home/today_look.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart'
    show WardrobeInsightData;
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
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

  /// Account-scoped classification answer. Null until the learning-summary
  /// future resolves. This is a cache of the async server answer for the
  /// current session — not user state: it is cleared on every auth change
  /// and re-proven after local history changes. Local device flags alone
  /// can never prove established here because they may belong to a
  /// previous account on this device.
  ({bool established})? _serverClassification;

  /// Request outcome for the classification fetch above (not user state).
  /// True once the summary provably failed; reset on every new fetch and
  /// every auth change. A failed fetch with device-local history present
  /// renders the neutral error shell (that history may be another
  /// account's); a failed fetch with no history keeps today's Old-shell
  /// error shape (nothing untrusted is involved).
  bool _summaryFailed = false;

  void _initEstablishedFuturesIfNeeded() {
    if (_summaryFuture != null) return;
    _summaryRepository =
        widget.summaryRepository ?? LearningSummaryRepositoryImpl();
    _fetchSummary();
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

  /// Fetches the account-scoped learning summary and records what it
  /// proves about THIS authenticated account: any server-side wardrobe
  /// points, saved-look points, streak, or signals mean an established
  /// account; a zero summary (or an unreachable backend, which keeps
  /// today's offline shape) resolves through the device-local fallback.
  /// Stale completions from a previous session are ignored via the
  /// identical-future guard.
  void _fetchSummary() {
    _summaryFailed = false;
    final pending = _summaryFuture = _summaryRepository.getSummary();
    unawaited(
      pending.then(
        (summary) {
          if (!mounted || !identical(_summaryFuture, pending)) return;
          if (summary != null && _summaryShowsHistory(summary)) {
            _serverClassification = (established: true);
          } else if (summary != null) {
            _serverClassification = (established: false);
          } else {
            // Unreachable backend: mark the failure so the branch below
            // can fail safe (neutral error when untrusted history exists,
            // today's Old-shell error shape when it does not).
            _summaryFailed = true;
          }
          setState(() {});
        },
        onError: (_) {
          if (!mounted || !identical(_summaryFuture, pending)) return;
          _summaryFailed = true;
          setState(() {});
        },
      ),
    );
  }

  /// Whether the backend summary carries any account history (M10).
  /// A fresh account answers the documented zero summary (base score 60,
  /// zero points, zero streak, no signals).
  static bool _summaryShowsHistory(LearningSummary summary) {
    return summary.breakdown.wardrobePoints > 0 ||
        summary.breakdown.savedPoints > 0 ||
        summary.streak > 0 ||
        summary.recentSignals.isNotEmpty;
  }

  @override
  void initState() {
    super.initState();
    LearningService.instance.addListener(_onLocalChanged);
    UserSession.savedWardrobeItemNotifier.addListener(_onLocalChanged);
    // React to sign-in/sign-out (and account switches) while Home is
    // mounted: cached backend futures belong to the previous session and
    // must be dropped so the newly resolved session re-derives its own.
    AuthSession.authVersion.addListener(_onAuthChanged);

    if (isGuestUser) {
      LearningService.instance.load().then((_) {
        if (mounted) setState(() {});
      });
    }
    if (_needsBackendFutures) {
      _initEstablishedFuturesIfNeeded();
    }
  }

  /// Drops every cached backend future, the server classification, and the
  /// fetch outcome so the next resolution belongs to the current session.
  void _resetBackendState() {
    _summaryFuture = null;
    _todayLookFuture = null;
    _insightFuture = null;
    _eventsFuture = null;
    _serverClassification = null;
    _summaryFailed = false;
  }

  @override
  void didUpdateWidget(covariant HomeScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    // A new navigation extra is a new handoff (e.g. post-auth landing):
    // drop the previous resolution so the sync fast path re-decides from
    // the current extra instead of a stale server answer.
    if (!identical(widget.onboardingData, oldWidget.onboardingData)) {
      _resetBackendState();
      if (_needsBackendFutures) {
        _initEstablishedFuturesIfNeeded();
      }
      setState(() {});
    }
  }

  void _onAuthChanged() {
    if (!mounted) return;
    // Drop every cached future and the server classification: a signed-out
    // Home must not retain old account data, and a newly signed-in account
    // must not inherit the previous account's look/score/insight/events or
    // its new/old classification.
    _resetBackendState();
    if (isGuestUser) {
      LearningService.instance.load().then((_) {
        if (mounted) setState(() {});
      });
    }
    if (_needsBackendFutures) {
      _initEstablishedFuturesIfNeeded();
    }
    setState(() {});
  }

  /// Manual retry for the neutral classification-error shell below:
  /// re-resolves from the current session's account-scoped summary.
  void _retryClassification() {
    if (!mounted) return;
    _resetBackendState();
    if (_needsBackendFutures) {
      _initEstablishedFuturesIfNeeded();
    }
    setState(() {});
  }

  void _retrySummary() {
    if (isGuestUser) return;
    _initEstablishedFuturesIfNeeded();
    setState(() {
      _fetchSummary();
    });
  }

  @override
  void dispose() {
    LearningService.instance.removeListener(_onLocalChanged);
    UserSession.savedWardrobeItemNotifier.removeListener(_onLocalChanged);
    AuthSession.authVersion.removeListener(_onAuthChanged);
    super.dispose();
  }

  void _onLocalChanged() {
    if (!mounted) return;
    // A fresh-account proof is void the moment on-device history appears:
    // re-ask the server so a genuinely established account promotes to the
    // Old Home while a local-only addition keeps the New Home. Bounded to
    // the proven-fresh case — established Homes never refetch here.
    if (_serverClassification?.established == false &&
        AuthSession.isAuthenticated) {
      _serverClassification = null;
      _fetchSummary();
    }
    if (_needsBackendFutures) {
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
        'analysis_cached': LocalStorage.onboardingPhotoCaptured,
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

  /// Backend futures are needed whenever the Old Home may render: the
  /// sync-Old branch and the ambiguous branch (which the account-scoped
  /// summary then confirms). Sync-New Homes (signed out, fresh onboarding
  /// handoff) fetch nothing.
  bool get _needsBackendFutures =>
      AuthSession.isAuthenticated &&
      !isGuestUser &&
      _syncIsNew != true;

  /// Synchronous fast path. Null means ambiguous: no explicit handoff, so
  /// device-local history must NOT decide (it may belong to a previous
  /// account on this device) — the account-scoped summary decides instead.
  /// Deliberately ignores [UserSession.isReturningUser]: every sign-in sets
  /// it, including a first-ever login of a genuinely new account, so it
  /// cannot distinguish new from old (Discover/Profile keep consuming it).
  /// There is deliberately no `is_login` shortcut: verified across
  /// `lib/` — no production call site passes that extra (only tests), so
  /// it cannot mean "existing returning account". A data-empty login
  /// resolves New unless the server proves history.
  bool? get _syncIsNew {
    if (!AuthSession.isAuthenticated) return true;
    final extra = widget.onboardingData;
    if (extra != null) {
      // Explicit onboarding/registration handoff on this flow: history
      // built here is live and belongs to this user.
      return !_hasEstablishedHistory;
    }
    // No handoff (cold start, post-login landing, tab revisit): stored
    // onboarding markers with no history still mean New; anything else
    // waits for the server below.
    final stored = _onboardingDataFromLocalStorage();
    if (stored != null && !_hasEstablishedHistory) return true;
    return null;
  }

  String? get _displayName {
    // Display names are account identity: never resolve one while signed
    // out, no matter what local leftovers exist.
    if (!AuthSession.isAuthenticated) return null;
    final raw = widget.onboardingData?['display_name'] as String? ??
        _onboardingDataFromLocalStorage()?['display_name'] as String? ??
        LocalStorage.displayName;
    if (raw == null || raw.trim().isEmpty) return null;
    return raw.trim();
  }

  /// Single authoritative New-vs-Old decision for /home.
  ///
  /// Only two experiences exist: the New User Home ([FirstTimeHomeScreen])
  /// and the established Old User Home (this screen's backend-fed body).
  /// The sync fast path decides explicit handoffs; otherwise the
  /// account-scoped learning summary decides (a zero summary proves a
  /// fresh account even when another account's leftovers sit on this
  /// device). Null means still resolving — the neutral loading shell
  /// below renders, never Old content pre-proof. Display names, cached UI
  /// state, and recommendation payloads never influence this.
  bool? get _resolvedIsNew {
    final sync = _syncIsNew;
    if (sync != null) return sync;
    final server = _serverClassification;
    if (server != null) return !server.established;
    // Unreachable backend with no device history at all: nothing untrusted
    // is involved — keep today's Old-shell error shape for this bare case.
    if (_summaryFailed && !_hasEstablishedHistory) return false;
    return null;
  }

  /// True only when classification is blocked: the summary failed and
  /// device-local history exists, which may belong to a previous account.
  /// That history must not classify — the neutral error shell renders.
  bool get _classificationBlocked =>
      _syncIsNew == null &&
      _serverClassification == null &&
      _summaryFailed &&
      _hasEstablishedHistory;

  /// Neutral resolving state: plain surface + spinner. No Home content of
  /// either experience renders before the account is classified.
  Widget _buildResolving() {
    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      body: const SafeArea(
        child: Center(child: CircularProgressIndicator()),
      ),
    );
  }

  /// Neutral classification-error state: honest retry, no classification
  /// from untrusted device history. Reuses the shared summary error card.
  Widget _buildClassificationError() {
    final theme = Theme.of(context);
    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: SummaryErrorCard(
              title: 'Home',
              message:
                  "Couldn't load your Home. Please check your connection.",
              onRetry: _retryClassification,
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final learningService = LearningService.instance;

    if (_needsBackendFutures) {
      _initEstablishedFuturesIfNeeded();
    }

    final resolved = _resolvedIsNew;
    final String chosenWidget;
    if (resolved == null) {
      chosenWidget =
          _classificationBlocked ? 'HomeClassificationError' : 'HomeResolving';
    } else if (resolved) {
      chosenWidget = 'FirstTimeHomeScreen';
    } else {
      chosenWidget = 'HomeScreen';
    }

    debugPrint(
      'FIRST_TIME_HOME_RUNTIME:\n'
      'route=/home\n'
      'widget=$chosenWidget\n'
      'auth=${AuthSession.isAuthenticated}\n'
      'sync=${_syncIsNew}\n'
      'server=${_serverClassification}\n'
      'failed=$_summaryFailed\n'
      'preferences=${LocalStorage.vibe != null}\n'
      'displayName=$_displayName\n'
      'onboardingData=${widget.onboardingData}',
    );

    if (resolved == null) {
      return _classificationBlocked
          ? _buildClassificationError()
          : _buildResolving();
    }
    if (resolved) {
      return FirstTimeHomeScreen(displayName: _displayName);
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
                        if (learningService.wardrobe.isEmpty &&
                            AuthSession.isAuthenticated) ...[
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
    // Auth boundary: the style score is personal data. While signed out
    // it must not render at all — neither the backend value nor a
    // locally computed one relabeled "device only". Same hide pattern as
    // the streak slot below.
    if (!AuthSession.isAuthenticated) return const SizedBox.shrink();
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
    // Same for any signed-out state (stale local data is not a session).
    if (!AuthSession.isAuthenticated) return const SizedBox.shrink();
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
    // instead of a 401-backed error card. Applies to every signed-out
    // state, not just the guest flag (stale flags are not a session).
    if (!AuthSession.isAuthenticated) {
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
        return ExistingUserHeroCard(
          data: _todayLookCardData(look),
          onWearThisLook: () => context.pushNamed(RouteNames.dailyOutfit),
          onSwapItem: () => context.pushNamed(RouteNames.buildOutfit),
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
    // Same for any signed-out state.
    if (!AuthSession.isAuthenticated) return const SizedBox.shrink();
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
