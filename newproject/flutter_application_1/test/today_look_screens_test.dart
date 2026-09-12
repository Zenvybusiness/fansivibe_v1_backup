import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/home/data/today_look_client.dart';
import 'package:fansivibe/features/home/data/today_look_models.dart';
import 'package:fansivibe/features/home/data/today_look_repository.dart';
import 'package:fansivibe/features/home/presentation/daily_outfit_screen.dart';
import 'package:fansivibe/features/home/presentation/home_screen.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

const String _uuid1 = '78ff3686-c950-4cd6-84c3-7e18d6634dfa';
const String _uuid2 = '4412f646-56a9-4afa-8717-b330da03b3d0';
const String _uuid3 = '9d8f2c1a-3b4e-4f5a-8c6d-7e8f9a0b1c2d';
const String _uuidAlt = '3fa85f64-5717-4562-b3fc-2c963f66afa6';
const String _staleId = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const String _savedId = 'b3e1a2c4-5d6f-47a8-b9c0-d1e2f3a4b5c6';

Map<String, dynamic> _wire({
  String title = "Today's Look",
  Object? occasion = 'formal',
  List<Map<String, dynamic>>? components,
  List<String>? selectedItemIds,
}) {
  final comps =
      components ??
      [
        {
          'id': _uuid1,
          'name': 'Navy Blazer',
          'category': 'outerwear',
          'color': 'navy',
          'material': 'wool',
        },
        {
          'id': _uuid2,
          'name': 'White Tee',
          'category': 'tops',
          'color': 'white',
        },
        {
          'id': _uuid3,
          'name': 'Dark Jeans',
          'category': 'bottoms',
          'color': 'indigo',
          'material': 'denim',
        },
      ];
  return {
    'title': title,
    if (occasion != null) 'occasion': occasion,
    'description': 'Sharp tailoring grounded in owned staples.',
    'matchScore': 87,
    'styleScore': 87,
    'components': comps,
    'reasons': [
      'Picked for a formal occasion',
      'Covers 3 owned wardrobe staples',
    ],
    'wardrobeContext': {'totalItems': 3, 'matchingItems': 3},
    'alternatives': [
      {'id': _uuidAlt, 'matchScore': 81},
    ],
    'selectedItemIds':
        selectedItemIds ?? comps.map((c) => c['id'] as String).toList(),
  };
}

Map<String, dynamic> _savedWire(Map<String, dynamic> snapshot) => {
  'id': _savedId,
  'lookId': null,
  'title': "Today's Look",
  'sourceContext': 'daily',
  'snapshot': snapshot,
  'sourceRunId': null,
  'createdAt': '2030-08-15T10:00:00.000Z',
};

TodayLook _look(Map<String, dynamic> wire) => TodayLook.fromJson(wire);

/// Scriptable fake: scripted results, full call accounting, no network.
class ScriptedTodayLookRepository implements TodayLookRepository {
  ScriptedTodayLookRepository();

  Future<TodayLookResult> Function()? getHandler;
  Future<TodayLookResult> Function(String? seed)? regenHandler;
  Future<SavedTodayLook?> Function()? saveHandler;

  int getCalls = 0;
  int regenCalls = 0;
  int saveCalls = 0;
  final List<String?> regenSeeds = [];
  final List<String> saveTitles = [];
  final List<Map<String, dynamic>> saveSnapshots = [];
  final List<String> saveKeys = [];

  @override
  Future<TodayLookResult> getTodayLook() {
    getCalls += 1;
    return getHandler!();
  }

  @override
  Future<TodayLookResult> regenerateTodayLook({String? seed}) {
    regenCalls += 1;
    regenSeeds.add(seed);
    return regenHandler!(seed);
  }

  @override
  Future<SavedTodayLook?> saveTodayLook({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) {
    saveCalls += 1;
    saveTitles.add(title);
    saveSnapshots.add(snapshot);
    saveKeys.add(idempotencyKey);
    return saveHandler!();
  }
}

/// Zero summary source so M10 slots render success cards (never their own
/// retry buttons) in today-look tests.
class _NullSummaryRepository implements LearningSummaryRepository {
  @override
  Future<LearningSummary?> getSummary() async => const LearningSummary(
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
}

Widget _homeWith(ScriptedTodayLookRepository repo) {
  return MaterialApp(
    theme: ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: FansivibeColors.background,
      colorScheme: const ColorScheme.dark(surface: FansivibeColors.surface),
    ),
    home: HomeScreen(
      todayLookRepository: repo,
      summaryRepository: _NullSummaryRepository(),
    ),
  );
}

Widget _dailyWith(TodayLookRepository repo) {
  return MaterialApp(
    theme: ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: FansivibeColors.background,
      colorScheme: const ColorScheme.dark(surface: FansivibeColors.surface),
    ),
    home: DailyOutfitScreen(todayLookRepository: repo),
  );
}

void main() {
  group('F–I, X. Home Today\'s Look slot', () {
    testWidgets('F. successful look renders backend data verbatim', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedTodayLookRepository()
        ..getHandler = () async => TodayLookResult.available(_look(_wire()));

      await tester.pumpWidget(_homeWith(repo));
      await tester.pumpAndSettle();

      expect(repo.getCalls, 1);
      expect(find.text("Today's Look"), findsWidgets);
      expect(find.text('formal'), findsOneWidget);
      expect(find.text('Navy Blazer'), findsOneWidget);
      expect(find.text('White Tee'), findsOneWidget);
      expect(find.text('Dark Jeans'), findsOneWidget);
      expect(find.text('Try This Look'), findsOneWidget);
      expect(find.text('Change Style'), findsWidgets);
      // No mock leftovers posing as data.
      expect(find.text('Modern Minimalist'), findsNothing);
      expect(find.text('Your Look'), findsNothing);
      expect(find.text('Building Your Look'), findsNothing);
      expect(find.text('Unstructured Blazer'), findsNothing);
      expect(find.text('Merino Crew Neck'), findsNothing);
    });

    testWidgets('G. loading state shows no fake content', (
      WidgetTester tester,
    ) async {
      final gate = Completer<TodayLookResult>();
      final repo = ScriptedTodayLookRepository()
        ..getHandler = () => gate.future;

      await tester.pumpWidget(_homeWith(repo));
      await tester.pump();

      expect(find.text("Today's Look"), findsWidgets);
      expect(find.byType(CircularProgressIndicator), findsWidgets);
      expect(find.text('Navy Blazer'), findsNothing);
      expect(find.text('Modern Minimalist'), findsNothing);
      expect(find.text('Your Look'), findsNothing);

      gate.complete(TodayLookResult.available(_look(_wire())));
      await tester.pumpAndSettle();
      expect(find.text('Navy Blazer'), findsOneWidget);
    });

    testWidgets('H. 404 renders a friendly no-look state', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedTodayLookRepository()
        ..getHandler = () async => const TodayLookResult.noneAvailable();

      await tester.pumpWidget(_homeWith(repo));
      await tester.pumpAndSettle();

      expect(find.text("Today's Look"), findsWidgets);
      expect(find.textContaining('No today\'s look available'), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);
      // No fake successful content.
      expect(find.text('Navy Blazer'), findsNothing);
      expect(find.text('Modern Minimalist'), findsNothing);
      expect(find.text('Try This Look'), findsNothing);
    });

    testWidgets('I. error state is truthful with retry', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedTodayLookRepository()
        ..getHandler = () async =>
            const TodayLookResult.failure(TodayLookFailure.networkError);

      await tester.pumpWidget(_homeWith(repo));
      await tester.pumpAndSettle();

      expect(find.text("Today's Look"), findsWidgets);
      expect(
        find.textContaining('Couldn\'t load today\'s look'),
        findsOneWidget,
      );
      expect(find.text('Try Again'), findsOneWidget);
      // A failed look never fakes success elsewhere on Home.
      expect(find.text('Navy Blazer'), findsNothing);
      expect(find.text('Modern Minimalist'), findsNothing);
      expect(find.text('84'), findsNothing);
    });

    testWidgets('X. retry refetches and renders the look', (
      WidgetTester tester,
    ) async {
      var calls = 0;
      final repo = ScriptedTodayLookRepository()
        ..getHandler = () async {
          calls += 1;
          if (calls == 1) {
            return const TodayLookResult.failure(TodayLookFailure.networkError);
          }
          return TodayLookResult.available(_look(_wire()));
        };

      await tester.pumpWidget(_homeWith(repo));
      await tester.pumpAndSettle();
      expect(
        find.textContaining('Couldn\'t load today\'s look'),
        findsOneWidget,
      );

      await tester.tap(find.text('Try Again'));
      await tester.pumpAndSettle();

      expect(calls, 2);
      expect(find.text('Navy Blazer'), findsOneWidget);
      expect(find.textContaining('Couldn\'t load today\'s look'), findsNothing);
    });
  });

  group('Daily outfit loading/empty/error states', () {
    testWidgets('loading keeps chrome with no mock content', (
      WidgetTester tester,
    ) async {
      final gate = Completer<TodayLookResult>();
      final repo = ScriptedTodayLookRepository()
        ..getHandler = () => gate.future;

      await tester.pumpWidget(_dailyWith(repo));
      await tester.pump();

      expect(find.text('TODAY\'S LOOK'), findsWidgets);
      expect(find.byType(CircularProgressIndicator), findsWidgets);
      expect(find.text('Modern Minimalist'), findsNothing);
      expect(find.text('Wear This Look'), findsNothing);

      gate.complete(TodayLookResult.available(_look(_wire())));
      await tester.pumpAndSettle();
      expect(find.text("Today's Look"), findsOneWidget);
    });

    testWidgets('empty state offers retry', (WidgetTester tester) async {
      final empty = ScriptedTodayLookRepository()
        ..getHandler = () async => const TodayLookResult.noneAvailable();
      await tester.pumpWidget(_dailyWith(empty));
      await tester.pumpAndSettle();
      expect(find.text('No today\'s look available'), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);
      expect(find.text('Wear This Look'), findsNothing);
    });

    testWidgets('error state offers retry', (WidgetTester tester) async {
      final failing = ScriptedTodayLookRepository()
        ..getHandler = () async =>
            const TodayLookResult.failure(TodayLookFailure.serviceUnavailable);
      await tester.pumpWidget(_dailyWith(failing));
      await tester.pumpAndSettle();
      expect(find.text('Couldn\'t load today\'s look'), findsOneWidget);
      expect(find.textContaining('Style service unavailable'), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);
    });
  });

  group('J–K. regenerate', () {
    testWidgets('J. regenerate calls backend with a deterministic seed', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedTodayLookRepository()
        ..getHandler = () async {
          return TodayLookResult.available(_look(_wire()));
        }
        ..regenHandler = (_) async =>
            TodayLookResult.available(_look(_wire(title: 'Second Look')));

      await tester.pumpWidget(_dailyWith(repo));
      await tester.pumpAndSettle();
      expect(find.text("Today's Look"), findsOneWidget);

      await tester.ensureVisible(find.text('Generate Another Look'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Generate Another Look'));
      await tester.pumpAndSettle();

      expect(repo.regenCalls, 1);
      expect(repo.regenSeeds, ['look-1']);
      expect(find.text('Second Look'), findsOneWidget);
      expect(find.text("Today's Look"), findsNothing);
    });

    testWidgets('K. regenerate pending guard ignores repeated taps', (
      WidgetTester tester,
    ) async {
      final gate = Completer<TodayLookResult>();
      final repo = ScriptedTodayLookRepository()
        ..getHandler = () async {
          return TodayLookResult.available(_look(_wire()));
        }
        ..regenHandler = (_) => gate.future;

      await tester.pumpWidget(_dailyWith(repo));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Generate Another Look'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Generate Another Look'));
      await tester.pump();
      // Button is disabled while pending: the label flips and taps no-op.
      expect(find.text('Generating…'), findsOneWidget);
      await tester.tap(find.text('Generating…'));
      await tester.pump();
      expect(repo.regenCalls, 1);

      gate.complete(TodayLookResult.available(_look(_wire(title: 'Fresh'))));
      await tester.pumpAndSettle();
      expect(find.text('Fresh'), findsOneWidget);
      expect(repo.regenCalls, 1);
    });

    testWidgets('failed regenerate keeps the look with feedback', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedTodayLookRepository()
        ..getHandler = () async {
          return TodayLookResult.available(_look(_wire()));
        }
        ..regenHandler = (_) async =>
            const TodayLookResult.failure(TodayLookFailure.serviceUnavailable);

      await tester.pumpWidget(_dailyWith(repo));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Generate Another Look'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Generate Another Look'));
      await tester.pumpAndSettle();

      expect(find.text("Today's Look"), findsOneWidget);
      expect(
        find.text('Style service unavailable. Please try again.'),
        findsOneWidget,
      );
    });
  });

  group('L–O. save', () {
    testWidgets('L/N. save calls backend then shows success feedback', (
      WidgetTester tester,
    ) async {
      final wire = _wire();
      SavedTodayLook? savedResult;
      final repo = ScriptedTodayLookRepository()
        ..getHandler = () async {
          return TodayLookResult.available(_look(wire));
        }
        ..saveHandler = () async {
          savedResult = SavedTodayLook.fromJson(_savedWire(wire));
          return savedResult;
        };

      await tester.pumpWidget(_dailyWith(repo));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Save Look'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save Look'));
      await tester.pumpAndSettle();

      expect(repo.saveCalls, 1);
      // P. sourceContext is daily; title obeys the backend requirement.
      expect(repo.saveTitles.single, "Today's Look");
      // Q. snapshot preserved verbatim.
      expect(jsonEncode(repo.saveSnapshots.single), jsonEncode(wire));
      expect(repo.saveKeys.single, isNotEmpty);
      // N. truthful success feedback, no duplicate affordance.
      expect(find.text('Today\'s look saved'), findsOneWidget);
      expect(find.text('Saved'), findsOneWidget);
      expect(savedResult, isNotNull);
      expect(savedResult!.sourceContext, 'daily');
    });

    testWidgets('M. save pending guard ignores repeated taps', (
      WidgetTester tester,
    ) async {
      final gate = Completer<SavedTodayLook?>();
      final repo = ScriptedTodayLookRepository()
        ..getHandler = () async {
          return TodayLookResult.available(_look(_wire()));
        }
        ..saveHandler = () => gate.future;

      await tester.pumpWidget(_dailyWith(repo));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Save Look'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save Look'));
      await tester.pump();
      expect(find.text('Saving…'), findsOneWidget);
      await tester.tap(find.text('Saving…'));
      await tester.pump();
      expect(repo.saveCalls, 1);

      gate.complete(null);
      await tester.pumpAndSettle();
      expect(repo.saveCalls, 1);
    });

    testWidgets('O. failed save keeps the look visible with retry feedback', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedTodayLookRepository()
        ..getHandler = () async {
          return TodayLookResult.available(_look(_wire()));
        }
        ..saveHandler = () async => null;

      await tester.pumpWidget(_dailyWith(repo));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Save Look'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save Look'));
      await tester.pumpAndSettle();

      expect(find.text("Today's Look"), findsOneWidget);
      expect(find.text('Navy Blazer'), findsOneWidget);
      expect(
        find.text('Couldn\'t save this look. Please try again.'),
        findsOneWidget,
      );
      // Still unsaved: retry stays available, never a fake 'Saved'.
      expect(find.text('Save Look'), findsOneWidget);
      expect(find.text('Saved'), findsNothing);
    });
  });

  group('R–W. safety properties on the detail surface', () {
    testWidgets('R. saving is never confused with wearing', (
      WidgetTester tester,
    ) async {
      final wire = _wire();
      final repo = ScriptedTodayLookRepository()
        ..getHandler = () async {
          return TodayLookResult.available(_look(wire));
        }
        ..saveHandler = () async => SavedTodayLook.fromJson(_savedWire(wire));

      await tester.pumpWidget(_dailyWith(repo));
      await tester.pumpAndSettle();

      expect(find.text('Wear This Look'), findsNothing);
      expect(find.text('Wearing this look!'), findsNothing);

      await tester.ensureVisible(find.text('Save Look'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save Look'));
      await tester.pumpAndSettle();

      expect(find.text('Wearing this look!'), findsNothing);
      expect(find.text('Today\'s look saved'), findsOneWidget);
    });

    testWidgets('T/U. UUID components render verbatim; stale IDs never crash', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedTodayLookRepository()
        ..getHandler = () async => TodayLookResult.available(
          _look(
            _wire(
              components: [
                {
                  'id': _uuid1,
                  'name': 'Navy Blazer',
                  'category': 'outerwear',
                  'color': 'navy',
                },
                {
                  'id': _staleId,
                  'name': 'Mystery Top',
                  'category': 'tops',
                  'color': 'grey',
                },
              ],
              selectedItemIds: [_uuid1, _staleId, _uuid2],
            ),
          ),
        );

      await tester.pumpWidget(_dailyWith(repo));
      await tester.pumpAndSettle();

      // Backend names shown as-is — never translated, never invented.
      expect(find.text('Navy Blazer'), findsOneWidget);
      expect(find.text('Mystery Top'), findsOneWidget);
      expect(find.text('Unknown Item'), findsNothing);
      // A selectedItemId with no component row never crashes the screen.
      expect(find.text("Today's Look"), findsOneWidget);
    });

    testWidgets('V. weather absence is normal; occasion shows only when set', (
      WidgetTester tester,
    ) async {
      final repo = ScriptedTodayLookRepository()
        ..getHandler = () async => TodayLookResult.available(_look(_wire()));

      await tester.pumpWidget(_dailyWith(repo));
      await tester.pumpAndSettle();

      expect(find.textContaining('°F'), findsNothing);
      expect(find.textContaining('Cloudy'), findsNothing);
      expect(find.text('formal'), findsOneWidget);

      // Flush element state so the second pump builds a fresh screen.
      await tester.pumpWidget(const MaterialApp(home: SizedBox()));
      final noOccasion = ScriptedTodayLookRepository()
        ..getHandler = () async =>
            TodayLookResult.available(_look(_wire(occasion: null)));
      await tester.pumpWidget(_dailyWith(noOccasion));
      await tester.pumpAndSettle();

      expect(find.text("Today's Look"), findsOneWidget);
      expect(find.text('formal'), findsNothing);
      expect(find.textContaining('°F'), findsNothing);
    });

    testWidgets('W. occasion is displayed, never recalculated over events', (
      WidgetTester tester,
    ) async {
      final paths = <String>[];
      final wire = _wire();
      final repo = TodayLookRepositoryImpl(
        client: TodayLookClient(
          client: MockClient((request) async {
            paths.add(request.url.path);
            if (request.url.path.endsWith('/save')) {
              return http.Response(jsonEncode(_savedWire(wire)), 201);
            }
            return http.Response(jsonEncode(wire), 200);
          }),
        ),
      );

      await tester.pumpWidget(_dailyWith(repo));
      await tester.pumpAndSettle();

      expect(find.text('formal'), findsOneWidget);
      expect(paths, ['/v1/looks/today']);
      expect(paths.any((p) => p.contains('event')), isFalse);

      await tester.ensureVisible(find.text('Save Look'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save Look'));
      await tester.pumpAndSettle();

      expect(paths, ['/v1/looks/today', '/v1/looks/today/save']);
      expect(paths.any((p) => p.contains('wear')), isFalse);
    });
  });
}
