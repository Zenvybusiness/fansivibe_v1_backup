import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/home/presentation/home_screen.dart';
import 'package:fansivibe/features/home/presentation/widgets/backend_summary_cards.dart';
import 'package:fansivibe/features/learning/data/learning_summary_client.dart';
import 'package:fansivibe/features/learning/data/learning_summary_models.dart';
import 'package:fansivibe/features/learning/data/learning_summary_repository.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/learning/learning_summary.dart'
    as public_contract;
import 'package:fansivibe/features/profile/presentation/profile_screen.dart';

/// M10-C tests (STEP 19.16, DEC-019/DEC-020/DEC-021).
///
/// A. DTO parses exact backend response
/// B. DTO preserves breakdown fields
/// C. client requests /v1/learning/summary
/// D. repository maps response correctly
/// E. style score is not recalculated locally
/// F. streak is not recalculated locally
/// G. recentSignals are preserved
/// H. Profile renders backend score
/// I. Profile renders backend streak
/// J. Profile renders breakdown
/// K. Profile renders recent signals
/// L. Home renders backend score/streak
/// M. loading state
/// N. error state does not show fake score
/// O. zero summary renders correctly
/// P. no hardcoded/mock score is used by the new M10 surface

const Map<String, dynamic> _backendJson = {
  'styleScore': 73,
  'breakdown': {'base': 60, 'wardrobePoints': 5, 'savedPoints': 8, 'total': 73},
  'streak': 5,
  'recentSignals': ['backend-signal-1', 'backend-signal-2'],
};

const LearningSummary _backendSummary = LearningSummary(
  styleScore: 73,
  breakdown: LearningSummaryBreakdown(
    base: 60,
    wardrobePoints: 5,
    savedPoints: 8,
    total: 73,
  ),
  streak: 5,
  recentSignals: ['backend-signal-1', 'backend-signal-2'],
);

const LearningSummary _zeroSummary = LearningSummary(
  styleScore: 60,
  breakdown: LearningSummaryBreakdown(
    base: 60,
    wardrobePoints: 0,
    savedPoints: 0,
    total: 60,
  ),
  streak: 0,
  recentSignals: [],
);

/// In-memory [LearningSummaryRepository] double (no network).
class FakeSummaryRepository implements LearningSummaryRepository {
  FakeSummaryRepository({LearningSummary? summary})
    : _summary = summary,
      _hang = false;

  FakeSummaryRepository.hanging() : _summary = null, _hang = true;

  final LearningSummary? _summary;
  final bool _hang;
  int calls = 0;

  @override
  Future<LearningSummary?> getSummary() async {
    calls++;
    if (_hang) {
      await Completer<void>().future;
    }
    return _summary;
  }
}

Widget _wrapHome(LearningSummaryRepository repo) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: HomeScreen(summaryRepository: repo),
  );
}

Widget _wrapProfile(LearningSummaryRepository repo) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: ProfileScreen(summaryRepository: repo),
  );
}

void main() {
  setUp(() => LearningService.instance.resetForTest());
  tearDown(() => LearningService.instance.resetForTest());

  group('LearningSummary DTO', () {
    test('A. parses exact backend response and roundtrips', () {
      final summary = LearningSummary.fromJson(_backendJson);
      expect(summary.styleScore, 73);
      expect(summary.streak, 5);
      expect(summary.recentSignals, ['backend-signal-1', 'backend-signal-2']);
      expect(summary.toJson(), _backendJson);
      expect(summary.copyWith(streak: 6).streak, 6);
    });

    test('B. preserves breakdown fields and roundtrips', () {
      final breakdown = LearningSummaryBreakdown.fromJson(
        _backendJson['breakdown'] as Map<String, dynamic>,
      );
      expect(breakdown.base, 60);
      expect(breakdown.wardrobePoints, 5);
      expect(breakdown.savedPoints, 8);
      expect(breakdown.total, 73);
      expect(
        breakdown.toJson(),
        _backendJson['breakdown'] as Map<String, dynamic>,
      );
      expect(breakdown.copyWith(total: 74).total, 74);
    });

    test('DTO throws on wrong types into the client null path', () {
      expect(
        () => LearningSummary.fromJson({
          'styleScore': '73',
          'breakdown': _backendJson['breakdown'],
          'streak': 5,
          'recentSignals': <String>[],
        }),
        throwsA(isA<TypeError>()),
      );
    });

    test('public contract exposes the summary types', () {
      // Screens must import only the feature-root contract, never
      // `learning/data/` internals (DEC-002).
      const viaContract = public_contract.LearningSummary(
        styleScore: 73,
        breakdown: public_contract.LearningSummaryBreakdown(
          base: 60,
          wardrobePoints: 5,
          savedPoints: 8,
          total: 73,
        ),
        streak: 5,
        recentSignals: <String>[],
      );
      expect(viaContract.styleScore, 73);
    });
  });

  group('LearningSummaryClient', () {
    test('C. requests exact path with auth; 200 parses; else null', () async {
      final client = LearningSummaryClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/learning/summary');
          expect(request.headers['Authorization'], 'Bearer dev');
          return http.Response(jsonEncode(_backendJson), 200);
        }),
      );
      final summary = await client.getSummary();
      expect(summary?.styleScore, 73);
      expect(summary?.breakdown.total, 73);
      expect(summary?.streak, 5);
      expect(summary?.recentSignals, hasLength(2));
      client.dispose();
    });

    test('C. non-200, exception, and malformed 200 all yield null', () async {
      final statusClient = LearningSummaryClient(
        client: MockClient((_) async => http.Response('nope', 500)),
      );
      expect(await statusClient.getSummary(), isNull);

      final offlineClient = LearningSummaryClient(
        client: MockClient((_) async => throw Exception('offline')),
      );
      expect(await offlineClient.getSummary(), isNull);

      final malformedClient = LearningSummaryClient(
        client: MockClient(
          (_) async => http.Response(jsonEncode({'styleScore': 'x'}), 200),
        ),
      );
      expect(await malformedClient.getSummary(), isNull);
    });
  });

  group('LearningSummaryRepository', () {
    test('D. maps response correctly and passes null through', () async {
      final okRepo = LearningSummaryRepositoryImpl(
        client: LearningSummaryClient(
          client: MockClient(
            (_) async => http.Response(jsonEncode(_backendJson), 200),
          ),
        ),
      );
      final summary = await okRepo.getSummary();
      expect(summary?.styleScore, 73);
      expect(summary?.breakdown.wardrobePoints, 5);
      expect(summary?.recentSignals.first, 'backend-signal-1');

      final nullRepo = LearningSummaryRepositoryImpl(
        client: LearningSummaryClient(
          client: MockClient((_) async => http.Response('x', 500)),
        ),
      );
      expect(await nullRepo.getSummary(), isNull);
    });
  });

  group('M10 surfaces use backend truth', () {
    testWidgets('E. style score is not recalculated locally', (
      WidgetTester tester,
    ) async {
      // Local singleton math yields 80 (24 seeded items, no saves);
      // the backend says 73. The surface must show 73, never 80.
      expect(LearningService.instance.styleScore, 80);
      await tester.pumpWidget(
        _wrapHome(FakeSummaryRepository(summary: _backendSummary)),
      );
      await tester.pumpAndSettle();
      expect(find.text('73'), findsWidgets);
      expect(find.text('80'), findsNothing);
    });

    testWidgets('F. streak is not recalculated locally', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrapHome(FakeSummaryRepository(summary: _backendSummary)),
      );
      await tester.pumpAndSettle();
      expect(find.text('5-day streak'), findsOneWidget);
      // The mock week (12-day streak, Mon–Sun cells) is gone.
      expect(find.text('12-day streak'), findsNothing);
      expect(find.text('Mon'), findsNothing);
    });

    testWidgets('G. recentSignals are preserved verbatim', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrapProfile(FakeSummaryRepository(summary: _backendSummary)),
      );
      await tester.pumpAndSettle();
      expect(find.text('backend-signal-1'), findsOneWidget);
      expect(find.text('backend-signal-2'), findsOneWidget);
    });

    testWidgets('H. Profile renders backend score in hero', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrapProfile(FakeSummaryRepository(summary: _backendSummary)),
      );
      await tester.pumpAndSettle();
      expect(find.text('73'), findsWidgets);
      expect(find.text('Style Score'), findsWidgets);
    });

    testWidgets('I. Profile renders backend streak', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrapProfile(FakeSummaryRepository(summary: _backendSummary)),
      );
      await tester.pumpAndSettle();
      expect(find.text('5-day streak'), findsOneWidget);
      expect(find.text('Consecutive styled days'), findsOneWidget);
    });

    testWidgets('J. Profile renders frozen breakdown rows', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrapProfile(FakeSummaryRepository(summary: _backendSummary)),
      );
      await tester.pumpAndSettle();
      expect(find.text('Style Summary'), findsOneWidget);
      expect(find.text('Score breakdown'), findsOneWidget);
      expect(find.text('Base'), findsOneWidget);
      expect(find.text('Wardrobe'), findsOneWidget);
      expect(find.text('Saved looks'), findsOneWidget);
      expect(find.text('Total'), findsOneWidget);
      // No invented interpretations.
      expect(find.textContaining('balanced'), findsNothing);
      expect(find.textContaining('neglected'), findsNothing);
      expect(find.textContaining('needs improvement'), findsNothing);
    });

    testWidgets('K. Profile renders recent signals section', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrapProfile(FakeSummaryRepository(summary: _backendSummary)),
      );
      await tester.pumpAndSettle();
      expect(find.text('Recent activity'), findsOneWidget);
      expect(find.text('backend-signal-1'), findsOneWidget);
      expect(find.text('backend-signal-2'), findsOneWidget);
    });

    testWidgets('L. Home renders backend score and streak', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrapHome(FakeSummaryRepository(summary: _backendSummary)),
      );
      await tester.pumpAndSettle();
      // Scoped to the backend slots: Today's Look owns its own score
      // badge text elsewhere on the screen.
      expect(
        find.descendant(
          of: find.byType(BackendStyleScoreCard),
          matching: find.text('Style Score'),
        ),
        findsOneWidget,
      );
      expect(find.text('73'), findsWidgets);
      expect(find.text('Style Streak'), findsOneWidget);
      expect(find.text('5-day streak'), findsOneWidget);
    });

    testWidgets('M. loading state shows progress, no score', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_wrapHome(FakeSummaryRepository.hanging()));
      await tester.pump();
      // Slot titles stay visible; bodies spin without posing values.
      expect(find.text('Style Score'), findsWidgets);
      expect(find.text('Style Streak'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsWidgets);
      expect(find.text('73'), findsNothing);
    });

    testWidgets('N. error state shows retry, never a fake score', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_wrapHome(FakeSummaryRepository(summary: null)));
      await tester.pumpAndSettle();
      expect(
        find.text(
          'Couldn\'t load style summary. Please check your connection.',
        ),
        findsWidgets,
      );
      expect(find.text('Try Again'), findsWidgets);
      expect(find.text('73'), findsNothing);
      expect(find.text('80'), findsNothing);
      expect(find.text('84'), findsNothing);
    });

    testWidgets('O. zero summary renders truthfully', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrapProfile(FakeSummaryRepository(summary: _zeroSummary)),
      );
      await tester.pumpAndSettle();
      expect(find.text('60'), findsWidgets);
      expect(find.text('0-day streak'), findsOneWidget);
      expect(find.text('No recent activity yet.'), findsOneWidget);
    });

    testWidgets('P. no hardcoded or mock score on the M10 surfaces', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrapHome(FakeSummaryRepository(summary: _backendSummary)),
      );
      await tester.pumpAndSettle();
      // Mock score card values and banned breakdown categories.
      expect(find.text('84'), findsNothing);
      expect(find.text('+3 pts'), findsNothing);
      expect(find.text('Fit'), findsNothing);
      expect(find.text('Excellent proportions'), findsNothing);
      expect(find.text('Occasion'), findsNothing);
      expect(find.text('Creativity'), findsNothing);
    });
  });
}
