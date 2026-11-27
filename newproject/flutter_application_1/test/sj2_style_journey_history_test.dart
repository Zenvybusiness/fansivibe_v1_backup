import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/features/home/presentation/home_screen.dart';
import 'package:fansivibe/features/home/presentation/widgets/existing_user_home_widgets.dart';
import 'package:fansivibe/features/learning/data/style_journey_client.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

Map<String, dynamic> _sampleHistoryJson({
  bool includeHistory = true,
  bool includeGap = false,
  int currentScore = 78,
  int previousScore = 73,
  int bestScore = 82,
  int? scoreDelta = 5,
  String? trend = 'up',
  int currentRank = 2,
  int totalRanked = 3,
  bool isTiedWithBest = false,
}) {
  final currentWeek = <String, dynamic>{
    'weekStart': '2026-11-23',
    'weekEnd': '2026-11-29',
    'timezone': 'Asia/Karachi',
    'styleScore': currentScore,
    'breakdown': {
      'base': 60,
      'wardrobePoints': 10,
      'savedPoints': currentScore - 70,
      'total': currentScore,
    },
    'styledDaysCount': 4,
    'signalsCount': 9,
    'isCurrent': true,
    'personalRank': currentRank,
    'recordedAt': null,
    'aggregationPolicy': 'end_of_week_score_v1',
  };

  if (!includeHistory) {
    return {
      'timezone': 'Asia/Karachi',
      'aggregationPolicy': 'end_of_week_score_v1',
      'currentWeek': currentWeek,
      'previousWeek': null,
      'bestHistoricalWeek': null,
      'comparison': {
        'scoreDelta': null,
        'trend': null,
        'currentWeekRank': 1,
        'totalRankedWeeks': 1,
        'isTiedWithBest': false,
      },
      'weeks': [currentWeek],
      'hasHistory': false,
    };
  }

  final prevWeek = <String, dynamic>{
    'weekStart': includeGap ? '2026-11-09' : '2026-11-16',
    'weekEnd': includeGap ? '2026-11-15' : '2026-11-22',
    'timezone': 'Asia/Karachi',
    'styleScore': previousScore,
    'breakdown': {
      'base': 60,
      'wardrobePoints': 8,
      'savedPoints': previousScore - 68,
      'total': previousScore,
    },
    'styledDaysCount': 3,
    'signalsCount': 6,
    'isCurrent': false,
    'personalRank': 3,
    'recordedAt': '2026-11-23T00:05:00Z',
    'aggregationPolicy': 'end_of_week_score_v1',
  };

  final bestWeek = <String, dynamic>{
    'weekStart': '2026-11-02',
    'weekEnd': '2026-11-08',
    'timezone': 'Asia/Karachi',
    'styleScore': bestScore,
    'breakdown': {
      'base': 60,
      'wardrobePoints': 12,
      'savedPoints': bestScore - 72,
      'total': bestScore,
    },
    'styledDaysCount': 6,
    'signalsCount': 14,
    'isCurrent': false,
    'personalRank': 1,
    'recordedAt': '2026-11-09T00:05:00Z',
    'aggregationPolicy': 'end_of_week_score_v1',
  };

  return {
    'timezone': 'Asia/Karachi',
    'aggregationPolicy': 'end_of_week_score_v1',
    'currentWeek': currentWeek,
    'previousWeek': includeGap ? null : prevWeek,
    'bestHistoricalWeek': bestWeek,
    'comparison': {
      'scoreDelta': includeGap ? null : scoreDelta,
      'trend': includeGap ? null : trend,
      'currentWeekRank': currentRank,
      'totalRankedWeeks': totalRanked,
      'isTiedWithBest': isTiedWithBest,
    },
    'weeks': includeGap
        ? [currentWeek, bestWeek]
        : [currentWeek, prevWeek, bestWeek],
    'hasHistory': true,
  };
}

class _FakeSummaryRepo implements LearningSummaryRepository {
  _FakeSummaryRepo({this.styleScore = 78, this.streak = 4});

  final int styleScore;
  final int streak;

  @override
  Future<LearningSummary?> getSummary() async => LearningSummary(
    styleScore: styleScore,
    breakdown: LearningSummaryBreakdown(
      base: 60,
      wardrobePoints: 10,
      savedPoints: styleScore - 70,
      total: styleScore,
    ),
    streak: streak,
    recentSignals: const ['Look saved'],
  );
}

class _FakeHistoryRepo implements StyleJourneyRepository {
  _FakeHistoryRepo({required List<StyleJourneyHistoryResult> results})
    : _results = results;

  final List<StyleJourneyHistoryResult> _results;
  int calls = 0;

  @override
  Future<StyleJourneyHistoryResult> getHistory({
    String? timezone,
    int limit = 12,
  }) async {
    final index = calls < _results.length ? calls : _results.length - 1;
    calls++;
    return _results[index];
  }
}

class _HangingHistoryRepo implements StyleJourneyRepository {
  @override
  Future<StyleJourneyHistoryResult> getHistory({
    String? timezone,
    int limit = 12,
  }) => Completer<StyleJourneyHistoryResult>().future;
}

Widget _wrapHome({
  required LearningSummaryRepository summaryRepo,
  required StyleJourneyRepository historyRepo,
}) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: HomeScreen(
      summaryRepository: summaryRepo,
      styleJourneyRepository: historyRepo,
    ),
  );
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    LearningService.instance.resetForTest();
    AuthSession.resetForTest();
    await AuthSession.saveSession('sj2-test-token');
  });

  tearDown(() async {
    LearningService.instance.resetForTest();
    AuthSession.resetForTest();
    await AuthSession.clearSession();
  });

  group('SJ2 Style Journey history models & client', () {
    test(
      'parses exact backend history response and orders chart chronologically',
      () {
        final json = _sampleHistoryJson();
        final history = StyleJourneyHistory.fromJson(json);

        expect(history.timezone, 'Asia/Karachi');
        expect(history.aggregationPolicy, 'end_of_week_score_v1');
        expect(history.hasHistory, isTrue);
        expect(history.currentWeek.styleScore, 78);
        expect(history.currentWeek.shortRangeLabel, 'Nov 23–29');
        expect(history.currentWeek.recordedAt, isNull);
        expect(history.previousWeek?.styleScore, 73);
        expect(
          history.previousWeek?.recordedAt,
          DateTime.parse('2026-11-23T00:05:00Z'),
        );
        expect(history.bestHistoricalWeek?.styleScore, 82);
        expect(history.comparison.scoreDelta, 5);
        expect(history.comparison.trend, 'up');
        expect(history.comparison.currentWeekRank, 2);
        expect(history.comparison.totalRankedWeeks, 3);
        expect(history.comparison.isTiedWithBest, isFalse);

        final ordered = history.chronologicalWeeks;
        expect(ordered.map((w) => w.shortStartLabel).toList(), [
          'Nov 2',
          'Nov 16',
          'Nov 23',
        ]);
        expect(ordered.last.isCurrent, isTrue);
        expect(history.toJson()['timezone'], 'Asia/Karachi');
      },
    );

    test('client handles 401 auth expiry by notifying AuthSession', () async {
      final client = StyleJourneyClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/learning/journey/history');
          expect(request.headers['Authorization'], 'Bearer sj2-test-token');
          return http.Response('{"detail":"unauthorized"}', 401);
        }),
      );

      final result = await client.getHistory();
      expect(result.isFailure, isTrue);
      expect(result.failure, StyleJourneyFailure.unauthorized);
      expect(AuthSession.isAuthenticated, isFalse);
    });

    test('client classifies network SocketException as networkError', () async {
      final client = StyleJourneyClient(
        client: MockClient(
          (_) async => throw const SocketException('Network unreachable'),
        ),
      );

      final result = await client.getHistory();
      expect(result.isFailure, isTrue);
      expect(result.failure, StyleJourneyFailure.networkError);
    });
  });

  group('SJ2 Style Journey UI states', () {
    testWidgets(
      'renders weekly chart, previous week comparison, ranking, best week, and activity',
      (WidgetTester tester) async {
        final history = StyleJourneyHistory.fromJson(_sampleHistoryJson());
        final historyRepo = _FakeHistoryRepo(
          results: [StyleJourneyHistoryResult.success(history)],
        );

        await tester.pumpWidget(
          _wrapHome(summaryRepo: _FakeSummaryRepo(), historyRepo: historyRepo),
        );
        await tester.pumpAndSettle();

        await tester.scrollUntilVisible(find.text('STYLE JOURNEY'), 500.0);
        await tester.pumpAndSettle();

        expect(find.text('Week of Nov 23–29'), findsOneWidget);
        expect(find.text('Last week (Nov 16–22): 73'), findsOneWidget);
        expect(find.text('+5 pts vs last week'), findsOneWidget);
        expect(find.text('NOW'), findsOneWidget);
        expect(find.text('Nov 16'), findsOneWidget);
        expect(find.text('Nov 2'), findsOneWidget);
        expect(find.text('Rank #2 of 3 weeks'), findsOneWidget);
        expect(find.text('Personal best: 82 (Nov 2–8)'), findsOneWidget);
        expect(
          find.text('4/7 styled days • 9 style actions this week'),
          findsOneWidget,
        );
        expect(historyRepo.calls, 1);
      },
    );

    testWidgets(
      'renders tied-with-best and negative delta accurately without percentages',
      (WidgetTester tester) async {
        final history = StyleJourneyHistory.fromJson(
          _sampleHistoryJson(
            currentScore: 70,
            previousScore: 74,
            bestScore: 70,
            scoreDelta: -4,
            trend: 'down',
            currentRank: 1,
            totalRanked: 3,
            isTiedWithBest: true,
          ),
        );
        await tester.pumpWidget(
          MaterialApp(
            theme: ThemeData.dark(),
            home: Scaffold(
              body: SingleChildScrollView(
                child: ExistingUserStyleJourney(
                  currentScore: 70,
                  streakDays: 2,
                  history: history,
                ),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text('-4 pts vs last week'), findsOneWidget);
        expect(
          find.text('Personal best: 70 (Nov 2–8) • Tied with best'),
          findsOneWidget,
        );
        expect(find.textContaining('%'), findsNothing);
      },
    );

    testWidgets(
      'renders empty history state for new user without fabricating weeks',
      (WidgetTester tester) async {
        final history = StyleJourneyHistory.fromJson(
          _sampleHistoryJson(includeHistory: false, currentScore: 72),
        );
        final historyRepo = _FakeHistoryRepo(
          results: [StyleJourneyHistoryResult.success(history)],
        );

        await tester.pumpWidget(
          _wrapHome(
            summaryRepo: _FakeSummaryRepo(styleScore: 72, streak: 1),
            historyRepo: historyRepo,
          ),
        );
        await tester.pumpAndSettle();

        await tester.scrollUntilVisible(find.text('STYLE JOURNEY'), 500.0);
        await tester.pumpAndSettle();

        expect(find.text('Rank #1 of 1 week'), findsOneWidget);
        expect(
          find.text(
            'First week in progress — past weeks and personal bests will appear here once recorded.',
          ),
          findsOneWidget,
        );
        expect(find.textContaining('Personal best:'), findsNothing);
        expect(find.textContaining('%'), findsNothing);
      },
    );

    testWidgets('does not render missing historical weeks as zero-score weeks', (
      WidgetTester tester,
    ) async {
      final history = StyleJourneyHistory.fromJson(
        _sampleHistoryJson(includeGap: true, currentRank: 2, totalRanked: 2),
      );
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: SingleChildScrollView(
              child: ExistingUserStyleJourney(
                currentScore: 78,
                streakDays: 4,
                history: history,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Nov 2'), findsOneWidget);
      expect(find.text('NOW'), findsOneWidget);
      // Missing week (Nov 9 / Nov 16) is not synthesized and 0 is not rendered.
      expect(find.text('Nov 9'), findsNothing);
      expect(find.text('Nov 16'), findsNothing);
      expect(find.text('0'), findsNothing);
      expect(find.textContaining('vs last week'), findsNothing);
    });

    testWidgets('shows loading state while history future is pending', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrapHome(
          summaryRepo: _FakeSummaryRepo(),
          historyRepo: _HangingHistoryRepo(),
        ),
      );
      await tester.pump();
      await tester.pump();

      await tester.scrollUntilVisible(find.text('STYLE JOURNEY'), 500.0);
      await tester.pump();

      expect(find.text('Loading weekly history...'), findsOneWidget);
    });

    testWidgets(
      'shows error state on failure and retries + refreshes cleanly',
      (WidgetTester tester) async {
        final loaded = StyleJourneyHistory.fromJson(_sampleHistoryJson());
        final updated = StyleJourneyHistory.fromJson(
          _sampleHistoryJson(currentScore: 84, scoreDelta: 11, currentRank: 1),
        );
        final historyRepo = _FakeHistoryRepo(
          results: [
            const StyleJourneyHistoryResult.failure(
              StyleJourneyFailure.networkError,
            ),
            StyleJourneyHistoryResult.success(loaded),
            StyleJourneyHistoryResult.success(updated),
          ],
        );

        await tester.pumpWidget(
          _wrapHome(summaryRepo: _FakeSummaryRepo(), historyRepo: historyRepo),
        );
        await tester.pumpAndSettle();

        await tester.scrollUntilVisible(find.text('STYLE JOURNEY'), 500.0);
        await tester.pumpAndSettle();

        expect(
          find.text(
            'Couldn\'t load weekly history. Please check your connection.',
          ),
          findsOneWidget,
        );
        expect(historyRepo.calls, 1);

        // Retry loads history
        await tester.tap(find.byKey(const Key('style_journey_retry_button')));
        await tester.pumpAndSettle();

        expect(historyRepo.calls, 2);
        expect(find.text('Rank #2 of 3 weeks'), findsOneWidget);

        // Refresh button fetches updated history
        await tester.tap(find.byKey(const Key('style_journey_refresh_button')));
        await tester.pumpAndSettle();

        expect(historyRepo.calls, 3);
        expect(find.text('+11 pts vs last week'), findsOneWidget);
        expect(find.text('Rank #1 of 3 weeks'), findsOneWidget);
      },
    );
  });
}
