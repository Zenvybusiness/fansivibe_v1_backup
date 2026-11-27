import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/discover/discover.dart';
import 'package:fansivibe/features/events/data/event_mock_data.dart';
import 'package:fansivibe/features/events/data/event_models.dart';
import 'package:fansivibe/features/events/data/events_repository.dart';
import 'package:fansivibe/features/home/data/home_mock_data.dart';
import 'package:fansivibe/features/home/data/home_recommendation_models.dart';
import 'package:fansivibe/features/home/data/home_vibe_mapping.dart';
import 'package:fansivibe/features/home/data/today_look_client.dart';
import 'package:fansivibe/features/home/presentation/first_time_home_screen.dart';
import 'package:fansivibe/features/home/presentation/widgets/backend_summary_cards.dart';
import 'package:fansivibe/features/home/presentation/widgets/existing_user_home_widgets.dart';
import 'package:fansivibe/features/home/today_look.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/features/profile/data/saved_looks_models.dart';
import 'package:fansivibe/features/profile/data/saved_looks_repository.dart';
import 'package:fansivibe/features/trending/data/trending_repository.dart';
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

  /// Backend saved-looks source (DEC-013). Defaults to live repository;
  /// tests inject a fake.
  final SavedLooksRepository? savedLooksRepository;

  /// Backend Discover / For-You recommendation source (H4.1).
  final DiscoverRepository? discoverRepository;

  /// Backend Trending source (H4.1).
  final TrendingRepository? trendingRepository;

  /// Backend Style Journey history source (SJ2).
  final StyleJourneyRepository? styleJourneyRepository;

  const HomeScreen({
    super.key,
    this.onboardingData,
    this.summaryRepository,
    this.todayLookRepository,
    this.wardrobeRepository,
    this.eventsRepository,
    this.savedLooksRepository,
    this.discoverRepository,
    this.trendingRepository,
    this.styleJourneyRepository,
  });

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late LearningSummaryRepository _summaryRepository;
  Future<LearningSummary?>? _summaryFuture;
  late TodayLookRepository _todayLookRepository;
  Future<TodayLookResult>? _todayLookFuture;
  late WardrobeRepository _wardrobeRepository;
  Future<WardrobeInsightData?>? _insightFuture;
  late EventsRepository _eventsRepository;
  EventListResult? _eventsResult;
  bool _eventsLoading = false;
  int _eventsGeneration = 0;
  late SavedLooksRepository _savedLooksRepository;
  List<SavedLookItem>? _savedLooks;
  bool _isLoadingSavedLooks = false;
  bool _isSavingTodayLook = false;
  int _savedLookSyncGeneration = 0;
  bool _ignoringNextSavedLooksNotification = false;

  late DiscoverRepository _discoverRepository;
  List<HomeCuratedLookItem>? _curatedItems;
  bool _curatedLoading = false;
  int _curatedGeneration = 0;

  late TrendingRepository _trendingRepository;
  List<HomeTrendingItem>? _trendingItems;
  bool _trendingLoading = false;
  bool _trendingIsStale = false;
  int _trendingGeneration = 0;

  late StyleJourneyRepository _styleJourneyRepository;
  StyleJourneyHistoryResult? _historyResult;
  bool _historyLoading = false;
  int _historyGeneration = 0;

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
    _wardrobeRepository = widget.wardrobeRepository ?? WardrobeRepositoryImpl();
    _insightFuture = _wardrobeRepository.getInsight();
    _eventsRepository = widget.eventsRepository ?? EventsRepositoryImpl();
    _discoverRepository = widget.discoverRepository ?? DiscoverRepositoryImpl();
    _trendingRepository = widget.trendingRepository ?? TrendingRepositoryImpl();
    _styleJourneyRepository =
        widget.styleJourneyRepository ?? StyleJourneyRepositoryImpl();
    if (AuthSession.isAuthenticated && !isGuestUser) {
      _fetchEvents(notify: false);
      _savedLooksRepository =
          widget.savedLooksRepository ?? SavedLooksRepositoryImpl();
      _loadSavedLooks();
      _fetchCuratedLooks(notify: false);
      _fetchTrending(notify: false);
      _fetchStyleJourneyHistory(notify: false);
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
    LocalStorage.weatherLocationVersion.addListener(_onWeatherLocationChanged);
    LocalStorage.vibeVersion.addListener(_onVibeChanged);
    UserSession.savedLooksVersion.addListener(_onSavedLooksChanged);
    UserSession.eventsVersion.addListener(_onEventsChanged);

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
    _eventsGeneration++;
    _eventsLoading = false;
    _eventsResult = null;
    _savedLooks = null;
    _isLoadingSavedLooks = false;
    _isSavingTodayLook = false;
    _savedLookSyncGeneration++;
    _serverClassification = null;
    _summaryFailed = false;
    _curatedGeneration++;
    _curatedLoading = false;
    _curatedItems = null;
    _trendingGeneration++;
    _trendingLoading = false;
    _trendingIsStale = false;
    _trendingItems = null;
    _historyGeneration++;
    _historyLoading = false;
    _historyResult = null;
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
    _fetchStyleJourneyHistory(force: true);
  }

  Future<void> _fetchStyleJourneyHistory({
    bool notify = true,
    bool force = false,
  }) async {
    if (isGuestUser || !AuthSession.isAuthenticated) return;
    if (_historyLoading && !force) return;
    final gen = ++_historyGeneration;
    _historyLoading = true;
    if (notify && mounted) setState(() {});

    final result = await _styleJourneyRepository.getHistory();
    if (!mounted || gen != _historyGeneration) return;
    setState(() {
      _historyResult = result;
      _historyLoading = false;
    });
  }

  void _retryStyleJourneyHistory() {
    if (isGuestUser || !AuthSession.isAuthenticated) return;
    _initEstablishedFuturesIfNeeded();
    _fetchStyleJourneyHistory(force: true);
  }

  Future<void> _refreshHome() async {
    if (isGuestUser || !AuthSession.isAuthenticated) return;
    _initEstablishedFuturesIfNeeded();
    setState(() {
      _fetchSummary();
      _todayLookFuture = _todayLookRepository.getTodayLook();
      _insightFuture = _wardrobeRepository.getInsight();
    });
    _fetchEvents();
    await Future.wait<void>([
      _fetchStyleJourneyHistory(force: true),
      _loadSavedLooks(),
    ]);
  }

  @override
  void dispose() {
    _eventsGeneration++;
    _savedLookSyncGeneration++;
    _curatedGeneration++;
    _trendingGeneration++;
    _historyGeneration++;
    LearningService.instance.removeListener(_onLocalChanged);
    UserSession.savedWardrobeItemNotifier.removeListener(_onLocalChanged);
    AuthSession.authVersion.removeListener(_onAuthChanged);
    LocalStorage.weatherLocationVersion.removeListener(
      _onWeatherLocationChanged,
    );
    LocalStorage.vibeVersion.removeListener(_onVibeChanged);
    UserSession.savedLooksVersion.removeListener(_onSavedLooksChanged);
    UserSession.eventsVersion.removeListener(_onEventsChanged);
    super.dispose();
  }

  void _onEventsChanged() {
    if (!mounted || isGuestUser || !AuthSession.isAuthenticated) return;
    _initEstablishedFuturesIfNeeded();
    _fetchEvents();
  }

  void _onSavedLooksChanged() {
    if (!mounted) return;
    if (_ignoringNextSavedLooksNotification) {
      _ignoringNextSavedLooksNotification = false;
      return;
    }
    if (!AuthSession.isAuthenticated || isGuestUser) return;
    _initEstablishedFuturesIfNeeded();
    _loadSavedLooks();
  }

  void _notifySavedLooksChangedFromHome() {
    _ignoringNextSavedLooksNotification = true;
    UserSession.notifySavedLooksChanged();
  }

  Future<void> _loadSavedLooks() async {
    if (!AuthSession.isAuthenticated || isGuestUser) return;
    final gen = ++_savedLookSyncGeneration;
    _isLoadingSavedLooks = true;
    const pageSize = 100;
    const maxPages = 50;
    final loaded = <SavedLookItem>[];
    final seenIds = <String>{};

    for (var page = 1; page <= maxPages; page++) {
      final result = await _savedLooksRepository.listSavedLooks(
        page: page,
        pageSize: pageSize,
      );
      if (!mounted || gen != _savedLookSyncGeneration) return;
      if (result == null) {
        _isLoadingSavedLooks = false;
        setState(() {});
        return;
      }
      var addedThisPage = 0;
      for (final item in result.items) {
        if (seenIds.add(item.id)) {
          loaded.add(item);
          addedThisPage++;
        }
      }
      if (result.items.isEmpty ||
          result.items.length < pageSize ||
          loaded.length >= result.total ||
          (page > 1 && addedThisPage == 0)) {
        break;
      }
    }

    if (!mounted || gen != _savedLookSyncGeneration) return;
    setState(() {
      _savedLooks = loaded;
      _isLoadingSavedLooks = false;
    });
  }

  static bool _sameIdSet(List<String> a, List<String> b) {
    if (a.length != b.length) return false;
    final setA = a.toSet();
    final setB = b.toSet();
    return setA.length == setB.length && setA.containsAll(setB);
  }

  SavedLookItem? _findMatchingSavedLook(TodayLook look) {
    final saved = _savedLooks;
    if (saved == null || saved.isEmpty) return null;
    final targetTitle = look.title.trim();
    for (final item in saved) {
      if (item.sourceContext != 'daily') continue;
      if (item.title.trim() != targetTitle) continue;
      if (_sameIdSet(item.selectedItemIds, look.selectedItemIds)) {
        return item;
      }
    }
    return null;
  }

  void _showHomeSnackBar(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), behavior: SnackBarBehavior.floating),
    );
  }

  Future<void> _toggleTodayLookSave(TodayLook look) async {
    if (isGuestUser || !AuthSession.isAuthenticated) {
      promptGuestSignIn(
        context,
        action: 'Sign in to save looks. Browsing stays free.',
      );
      return;
    }
    if (_isSavingTodayLook || _isLoadingSavedLooks) return;

    final existing = _findMatchingSavedLook(look);
    final gen = _savedLookSyncGeneration;
    setState(() => _isSavingTodayLook = true);

    if (existing == null) {
      final title = look.title.trim();
      if (title.isEmpty || title.length > 200) {
        setState(() => _isSavingTodayLook = false);
        _showHomeSnackBar('This look can\'t be saved (invalid title).');
        return;
      }
      final saved = await _todayLookRepository.saveTodayLook(
        title: look.title,
        snapshot: look.snapshot,
        idempotencyKey: newTodayLookIdempotencyKey(),
      );
      if (!mounted || gen != _savedLookSyncGeneration) return;
      if (saved != null) {
        final newItem = SavedLookItem(
          id: saved.id,
          lookId: saved.lookId,
          title: saved.title,
          sourceContext: saved.sourceContext ?? 'daily',
          snapshot: saved.snapshot ?? look.snapshot,
          sourceRunId: saved.sourceRunId,
          createdAt: saved.createdAt,
        );
        setState(() {
          final current = List<SavedLookItem>.from(_savedLooks ?? const []);
          if (!current.any((item) => item.id == newItem.id)) {
            current.insert(0, newItem);
          }
          _savedLooks = current;
          _isSavingTodayLook = false;
        });
        _notifySavedLooksChangedFromHome();
        _showHomeSnackBar('Today\'s look saved');
      } else {
        setState(() => _isSavingTodayLook = false);
        if (AuthSession.isAuthenticated) {
          _showHomeSnackBar('Couldn\'t save this look. Please try again.');
        }
      }
    } else {
      final outcome = await _savedLooksRepository.deleteSavedLook(
        id: existing.id,
      );
      if (!mounted || gen != _savedLookSyncGeneration) return;
      if (outcome == SavedLookDeleteOutcome.deleted ||
          outcome == SavedLookDeleteOutcome.alreadyGone) {
        setState(() {
          final current = List<SavedLookItem>.from(_savedLooks ?? const []);
          current.removeWhere((item) => item.id == existing.id);
          _savedLooks = current;
          _isSavingTodayLook = false;
        });
        _notifySavedLooksChangedFromHome();
        _showHomeSnackBar(
          outcome == SavedLookDeleteOutcome.deleted
              ? 'Removed from saved looks'
              : 'Look was already removed',
        );
      } else {
        setState(() => _isSavingTodayLook = false);
        if (AuthSession.isAuthenticated) {
          _showHomeSnackBar('Couldn\'t remove saved look. Please try again.');
        }
      }
    }
  }

  /// Refetch the look after a successful city change so the card never
  /// keeps showing weather derived for the previous location.
  void _onWeatherLocationChanged() {
    if (!mounted || _todayLookFuture == null) return;
    setState(() {
      _todayLookFuture = _todayLookRepository.getTodayLook();
    });
  }

  void _onVibeChanged() {
    if (!mounted) return;
    if (_todayLookFuture != null) {
      setState(() {
        _todayLookFuture = _todayLookRepository.getTodayLook();
      });
    }
    if (AuthSession.isAuthenticated && !isGuestUser) {
      _fetchCuratedLooks();
    } else {
      setState(() {});
    }
  }

  String? get _effectiveVibe =>
      LocalStorage.vibe ?? LearningService.instance.styleType;

  void _fetchCuratedLooks({bool notify = true}) {
    if (isGuestUser || !AuthSession.isAuthenticated) return;
    if (widget.discoverRepository == null) {
      // Without an explicit DiscoverRepository, avoid firing live network
      // requests in tests; use vibe-matched editorial curations cleanly.
      return;
    }
    final gen = ++_curatedGeneration;
    if (notify) {
      setState(() => _curatedLoading = true);
    } else {
      _curatedLoading = true;
    }
    final vibeAtFetch = _effectiveVibe;
    unawaited(
      _discoverRepository
          .getForYouRecommendations(page: 1, pageSize: 4)
          .then(
            (result) {
              if (!mounted || gen != _curatedGeneration) return;
              if (result.isSuccess && result.response != null) {
                final resp = result.response!;
                final mapped = <HomeCuratedLookItem>[];
                for (var i = 0; i < resp.items.length && i < 4; i++) {
                  final item = resp.items[i];
                  final imageUrl = item.imageUrls.isNotEmpty
                      ? item.imageUrls.first
                      : (resp.isPersonalized
                            ? ''
                            : HomeVibeMapping.heroImageFor(vibe: vibeAtFetch));
                  mapped.add(
                    HomeCuratedLookItem(
                      id: item.id,
                      title: item.title,
                      category: (item.brand ?? item.category ?? 'CURATED')
                          .toUpperCase(),
                      imageRef: imageUrl,
                      height: i.isEven ? 230 : 210,
                      provenance: HomeRecommendationProvenance(
                        recommendationId: item.id,
                        sourceType: resp.isPersonalized
                            ? HomeRecommendationSourceType.backendPersonalized
                            : HomeRecommendationSourceType.backendCurated,
                        selectedVibe:
                            resp.appliedContext.styleType ?? vibeAtFetch,
                        imageRef: imageUrl.isNotEmpty ? imageUrl : null,
                        contentKind: resp.isPersonalized
                            ? 'personalized'
                            : 'curated',
                        isPersonalized: resp.isPersonalized,
                      ),
                    ),
                  );
                }
                setState(() {
                  _curatedLoading = false;
                  _curatedItems = mapped;
                });
              } else {
                setState(() {
                  _curatedLoading = false;
                  _curatedItems = null;
                });
              }
            },
            onError: (_) {
              if (!mounted || gen != _curatedGeneration) return;
              setState(() {
                _curatedLoading = false;
                _curatedItems = null;
              });
            },
          ),
    );
  }

  void _fetchTrending({bool notify = true}) {
    if (isGuestUser || !AuthSession.isAuthenticated) return;
    if (widget.trendingRepository == null) {
      return;
    }
    final gen = ++_trendingGeneration;
    if (notify) {
      setState(() => _trendingLoading = true);
    } else {
      _trendingLoading = true;
    }
    unawaited(
      _trendingRepository
          .getTrendingFeed(limit: 2)
          .then(
            (result) {
              if (!mounted || gen != _trendingGeneration) return;
              final feed = result.feed;
              if (feed != null) {
                final mapped = <HomeTrendingItem>[];
                for (final trend in feed.items.take(2)) {
                  final matchedImg = trend.matchedProducts
                      .map((p) => p.imageUrl)
                      .whereType<String>()
                      .firstWhere((u) => u.isNotEmpty, orElse: () => '');
                  final imageRef = matchedImg;
                  mapped.add(
                    HomeTrendingItem(
                      id: trend.trendId,
                      title: trend.displayName,
                      subtitle: feed.isStale
                          ? 'Cached • ${trend.region}'
                          : 'Trending • ${trend.region}',
                      imageRef: imageRef,
                      provenance: HomeRecommendationProvenance(
                        recommendationId: trend.trendId,
                        sourceType:
                            HomeRecommendationSourceType.backendTrending,
                        selectedVibe: _effectiveVibe,
                        imageRef: imageRef.isNotEmpty ? imageRef : null,
                        contentKind: 'trending',
                        isPersonalized: false,
                        isStale: feed.isStale,
                      ),
                    ),
                  );
                }
                setState(() {
                  _trendingLoading = false;
                  _trendingIsStale = feed.isStale;
                  _trendingItems = mapped;
                });
              } else {
                setState(() {
                  _trendingLoading = false;
                  _trendingItems = null;
                });
              }
            },
            onError: (_) {
              if (!mounted || gen != _trendingGeneration) return;
              setState(() {
                _trendingLoading = false;
                _trendingItems = null;
              });
            },
          ),
    );
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
      if (_todayLookFuture != null) {
        _todayLookFuture = _todayLookRepository.getTodayLook();
      }
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

  void _retryInsight() {
    if (isGuestUser) return;
    _initEstablishedFuturesIfNeeded();
    setState(() {
      _insightFuture = _wardrobeRepository.getInsight();
    });
  }

  void _fetchEvents({bool notify = true}) {
    if (isGuestUser || !AuthSession.isAuthenticated) return;
    final gen = ++_eventsGeneration;
    if (notify) {
      setState(() {
        _eventsLoading = true;
        _eventsResult = null;
      });
    } else {
      _eventsLoading = true;
      _eventsResult = null;
    }
    unawaited(
      _eventsRepository
          .listEventsResult(page: 1, pageSize: 5, fromDate: localTodayIsoDate())
          .then(
            (result) {
              if (!mounted || gen != _eventsGeneration) return;
              setState(() {
                _eventsLoading = false;
                _eventsResult = result;
              });
            },
            onError: (Object error) {
              if (!mounted || gen != _eventsGeneration) return;
              setState(() {
                _eventsLoading = false;
                _eventsResult = EventListResult.failure(
                  _classifyEventsError(error),
                );
              });
            },
          ),
    );
  }

  EventListFailure _classifyEventsError(Object error) {
    if (error is SocketException ||
        error is TimeoutException ||
        error is http.ClientException) {
      return EventListFailure.networkError;
    }
    return EventListFailure.unknown;
  }

  void _retryEvents() {
    if (isGuestUser || !AuthSession.isAuthenticated) return;
    _initEstablishedFuturesIfNeeded();
    _fetchEvents();
  }

  Map<String, dynamic>? _onboardingDataFromLocalStorage() {
    if (widget.onboardingData != null) return null;
    final hasCompleted = LocalStorage.onboardingComplete;
    final storedDisplayName = LocalStorage.displayName;
    final storedVibe = LocalStorage.vibe;
    if (hasCompleted || (!AuthSession.isAuthenticated && storedVibe != null)) {
      return <String, dynamic>{
        'onboarding_complete': hasCompleted,
        'display_name': storedDisplayName,
        'vibe': storedVibe,
        'analysis_cached': hasCachedOutfitPreview(),
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
      AuthSession.isAuthenticated && !isGuestUser && _syncIsNew != true;

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
    final raw =
        widget.onboardingData?['display_name'] as String? ??
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
      body: const SafeArea(child: Center(child: CircularProgressIndicator())),
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
              message: "Couldn't load your Home. Please check your connection.",
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
      chosenWidget = _classificationBlocked
          ? 'HomeClassificationError'
          : 'HomeResolving';
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
      'sync=$_syncIsNew\n'
      'server=$_serverClassification\n'
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

            return RefreshIndicator(
              onRefresh: _refreshHome,
              child: SingleChildScrollView(
                physics: const AlwaysScrollableScrollPhysics(
                  parent: BouncingScrollPhysics(),
                ),
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
                            onAvatarTap: () =>
                                context.goNamed(RouteNames.profile),
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
                            items: _curatedItems,
                            selectedVibe: _effectiveVibe,
                            isLoading: _curatedLoading,
                            onLookTap: (title) =>
                                context.pushNamed(RouteNames.discover),
                          ),
                          const SizedBox(height: 28),

                          // 9. Trending For You
                          ExistingUserTrending(
                            items: _trendingItems,
                            isLoading: _trendingLoading,
                            isStale: _trendingIsStale,
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
        final isSaved = _findMatchingSavedLook(look) != null;
        final resolvedVibe =
            look.selectedVibe ?? look.styleDna?.styleType ?? _effectiveVibe;
        final componentImg = look.components
            .map((c) => c.imageUrl)
            .whereType<String>()
            .map((u) => u.trim())
            .firstWhere((u) => u.isNotEmpty, orElse: () => '');
        final explicitLookImage =
            (look.imageUrl != null && look.imageUrl!.trim().isNotEmpty)
            ? look.imageUrl!.trim()
            : (componentImg.isNotEmpty ? componentImg : null);
        // Never attach unrelated generic stock images to personalized outfits.
        final heroImage = look.isPersonalized
            ? (explicitLookImage ?? '')
            : HomeVibeMapping.heroImageFor(
                lookImageUrl: explicitLookImage,
                vibe: resolvedVibe,
                occasion: look.occasion,
              );
        final provenance = HomeRecommendationProvenance(
          recommendationId:
              look.recommendationId ??
              (look.selectedItemIds.isNotEmpty
                  ? look.selectedItemIds.join('-')
                  : look.title),
          sourceType: HomeRecommendationSourceType.wardrobeDerived,
          associatedPreferences: [
            if (look.occasion != null && look.occasion!.isNotEmpty)
              look.occasion!,
            if (resolvedVibe != null && resolvedVibe.isNotEmpty) resolvedVibe,
          ],
          selectedVibe: resolvedVibe,
          occasion: look.occasion,
          imageRef: heroImage.isNotEmpty ? heroImage : null,
          contentKind: look.isPersonalized ? 'personalized' : 'curated',
          isPersonalized: look.isPersonalized,
        );
        return ExistingUserHeroCard(
          data: _todayLookCardData(look),
          imageAsset: heroImage,
          provenance: provenance,
          isSaved: isSaved,
          isSaving: _isSavingTodayLook,
          onToggleSave: () => _toggleTodayLookSave(look),
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
  /// fetched again here). The card's match badge shows the derivation's
  /// own `matchScore` (never the style score, never a local default).
  /// `occasion` shows only when the backend derived one — the static
  /// 'Everyday' fallback is presentation copy, never an event
  /// recalculation (no event fetch happens in this layer).
  TodaysLookData _todayLookCardData(TodayLook look) {
    return TodaysLookData(
      title: look.title,
      occasion: look.occasion ?? 'Everyday',
      weather: look.weather?.summary ?? '',
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
      styleScore: look.matchScore,
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
    // Backend-first wardrobe insight (P2-8): the live backend insight
    // renders verbatim via [ExistingUserAiInsightCard]. The repository
    // returns null for empty (204), unreachable, and error states alike,
    // so a null slot hides instead of inventing advice — the same contract
    // the Wardrobe screen honors. No editorial fallback is posed as AI
    // output.
    return FutureBuilder<WardrobeInsightData?>(
      future: _insightFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const SummaryLoadingCard(title: 'AI Insight');
        }
        final insight = snapshot.data;
        if (insight != null) {
          return ExistingUserAiInsightCard(
            quote: insight.title,
            supportingText: insight.insight,
            onExploreTap: () => context.pushNamed(RouteNames.discover),
          );
        }
        if (snapshot.hasError) {
          return SummaryErrorCard(
            title: 'AI Insight',
            message:
                'Couldn\'t load wardrobe insight. Please check your connection.',
            onRetry: _retryInsight,
          );
        }
        return const SizedBox.shrink();
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
    if (_eventsLoading || _eventsResult == null) {
      return const SummaryLoadingCard(title: 'Upcoming');
    }
    final result = _eventsResult!;
    if (result.isError) {
      final message = switch (result.failure) {
        EventListFailure.networkError =>
          'Couldn\'t load upcoming events. Please check your connection.',
        EventListFailure.unauthorized =>
          'Your session expired. Please sign in again.',
        _ => 'Couldn\'t load upcoming events. Please try again.',
      };
      return SummaryErrorCard(
        title: 'Upcoming',
        message: message,
        onRetry: _retryEvents,
      );
    }
    final events = deduplicateEvents(
      result.page!.items,
    ).where((e) => isUpcomingEvent(e)).toList();
    if (events.isEmpty) {
      return ExistingUserUpcomingCard(
        hasEvent: false,
        onCreateEvent: () => context.pushNamed(RouteNames.eventAdd),
      );
    }
    final event = events.first;
    final rawLocation = event.location?.trim();
    final locationAndTime = (rawLocation != null && rawLocation.isNotEmpty)
        ? '$rawLocation • ${event.eventTime ?? event.displayDate}'
        : (event.displayTime != null
              ? '${event.displayDate} • ${event.displayTime}'
              : event.displayDate);
    final occasionLabel =
        (EventType.byCodeOrNull(event.eventType)?.name ?? event.eventType)
            .toUpperCase();
    return ExistingUserUpcomingCard(
      hasEvent: true,
      isCalendarSynced: false,
      title: event.title,
      occasion: occasionLabel,
      locationAndTime: locationAndTime,
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

  Widget _buildStyleJourney() {
    // 30-day overview is server-tracked across weeks — guests have no
    // account history so the slot hides rather than posing historical data.
    // Same for any signed-out state. Authenticated users render the live
    // backend score only: loading and error states keep the slot title
    // with no value — there is deliberately no score fallback here.
    if (!AuthSession.isAuthenticated) return const SizedBox.shrink();
    return FutureBuilder<LearningSummary?>(
      future: _summaryFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const SummaryLoadingCard(title: 'Style Journey');
        }
        final summary = snapshot.data;
        if (snapshot.hasError || summary == null) {
          return Column(
            children: [
              SummaryErrorCard(
                title: 'Style Journey',
                message:
                    'Couldn\'t load style summary. Please check your connection.',
                onRetry: _retrySummary,
              ),
              const SizedBox(height: 16),
              _buildStreakSlot(),
            ],
          );
        }
        return Column(
          children: [
            ExistingUserStyleJourney(
              currentScore: summary.styleScore,
              streakDays: summary.streak,
              history: _historyResult?.history,
              isHistoryLoading: _historyLoading,
              historyFailure: _historyResult?.failure,
              onRetryHistory: _retryStyleJourneyHistory,
              onRefreshHistory: _retryStyleJourneyHistory,
            ),
            const SizedBox(height: 16),
            _buildStreakSlot(),
          ],
        );
      },
    );
  }
}
