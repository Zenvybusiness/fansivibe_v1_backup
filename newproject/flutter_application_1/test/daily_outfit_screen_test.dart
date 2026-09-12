import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/home/data/today_look_models.dart';
import 'package:fansivibe/features/home/data/today_look_repository.dart';
import 'package:fansivibe/features/home/presentation/daily_outfit_screen.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

// Backend-first DailyOutfitScreen tests (STEP 19.25): the screen renders
// the M9 derivation verbatim via an injected repository. The mock-only
// surface (weather, AI notes, insights, style tips, Wear CTA) is gone by
// contract — see today_look_screens_test.dart for the full A–X matrix.

const String _uuid1 = '78ff3686-c950-4cd6-84c3-7e18d6634dfa';
const String _uuid2 = '4412f646-56a9-4afa-8717-b330da03b3d0';
const String _uuid3 = '9d8f2c1a-3b4e-4f5a-8c6d-7e8f9a0b1c2d';

Map<String, dynamic> _wire({String title = 'Evening Polish'}) => {
  'title': title,
  'occasion': 'date',
  'description': 'Clean lines meet relaxed sophistication for an evening out.',
  'matchScore': 91,
  'styleScore': 91,
  'components': [
    {
      'id': _uuid1,
      'name': 'Charcoal Unstructured Blazer',
      'category': 'outerwear',
      'color': 'Charcoal',
      'material': 'Wool Blend',
    },
    {
      'id': _uuid2,
      'name': 'Merino Wool Crewneck',
      'category': 'tops',
      'color': 'Off-White',
      'material': 'Merino Wool',
    },
    {
      'id': _uuid3,
      'name': 'Tapered Wool Trousers',
      'category': 'bottoms',
      'color': 'Charcoal',
      'material': 'Wool',
    },
  ],
  'reasons': ['Picked for a date occasion', 'Covers 3 owned wardrobe staples'],
  'wardrobeContext': {'totalItems': 12, 'matchingItems': 3},
  'alternatives': [
    {'id': _uuid3, 'matchScore': 88},
  ],
  'selectedItemIds': [_uuid1, _uuid2, _uuid3],
};

class _FakeTodayLookRepository implements TodayLookRepository {
  _FakeTodayLookRepository({
    TodayLookResult? getResult,
    TodayLookResult? regenResult,
    SavedTodayLook? saveResult,
  }) : _getResult = getResult,
       _regenResult = regenResult,
       _saveResult = saveResult;

  final TodayLookResult? _getResult;
  final TodayLookResult? _regenResult;
  final SavedTodayLook? _saveResult;
  int regenCalls = 0;
  int saveCalls = 0;

  @override
  Future<TodayLookResult> getTodayLook() async =>
      _getResult ?? TodayLookResult.available(TodayLook.fromJson(_wire()));

  @override
  Future<TodayLookResult> regenerateTodayLook({String? seed}) async {
    regenCalls += 1;
    return _regenResult ??
        TodayLookResult.available(TodayLook.fromJson(_wire()));
  }

  @override
  Future<SavedTodayLook?> saveTodayLook({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async {
    saveCalls += 1;
    return _saveResult;
  }
}

Widget _buildTestApp({TodayLookRepository? repository}) {
  return MaterialApp(
    theme: ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: FansivibeColors.background,
      colorScheme: const ColorScheme.dark(surface: FansivibeColors.surface),
    ),
    home: DailyOutfitScreen(
      todayLookRepository: repository ?? _FakeTodayLookRepository(),
    ),
  );
}

void main() {
  group('DailyOutfitScreen (Today\'s Look) Widget Tests', () {
    testWidgets('renders hero section with TODAY\'S LOOK label', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('TODAY\'S LOOK'), findsOneWidget);
    });

    testWidgets('renders backend match score in hero', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('91%'), findsOneWidget);
    });

    testWidgets('renders backend occasion with no weather chip', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('date'), findsOneWidget);
      expect(find.textContaining('°F'), findsNothing);
      expect(find.textContaining('Cloudy'), findsNothing);
    });

    testWidgets('renders back button in hero', (WidgetTester tester) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
    });

    testWidgets('renders editorial summary with backend title', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('Evening Polish'), findsOneWidget);
      expect(
        find.textContaining('Clean lines meet relaxed sophistication'),
        findsOneWidget,
      );
    });

    testWidgets('renders outfit breakdown section', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('The Ensemble'), findsOneWidget);
      expect(find.text('3 pieces'), findsOneWidget);
    });

    testWidgets('renders component names in breakdown', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('Charcoal Unstructured Blazer'), findsOneWidget);
      expect(find.text('Merino Wool Crewneck'), findsOneWidget);
      expect(find.text('Tapered Wool Trousers'), findsOneWidget);
    });

    testWidgets('renders Why It Works section with backend reasons', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('Why It Works'), findsOneWidget);
      expect(find.text('Picked for a date occasion'), findsOneWidget);
      expect(find.text('Covers 3 owned wardrobe staples'), findsOneWidget);
    });

    testWidgets('renders Alternatives section from backend', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('Alternatives'), findsOneWidget);
      expect(find.text('Alternative 1'), findsOneWidget);
      expect(find.text('88%'), findsOneWidget);
    });

    testWidgets('renders backend quick actions without any wear CTA', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('Generate Another Look'), findsOneWidget);
      expect(find.text('Save Look'), findsOneWidget);
      expect(find.text('Share'), findsOneWidget);
      expect(find.text('Wear This Look'), findsNothing);
    });

    testWidgets('Generate Another Look swaps in the regenerated look', (
      WidgetTester tester,
    ) async {
      final repo = _FakeTodayLookRepository(
        regenResult: TodayLookResult.available(
          TodayLook.fromJson(_wire(title: 'Fresh Rotation')),
        ),
      );
      await tester.pumpWidget(_buildTestApp(repository: repo));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Generate Another Look'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Generate Another Look'));
      await tester.pumpAndSettle();

      expect(repo.regenCalls, 1);
      expect(find.text('Fresh Rotation'), findsOneWidget);
    });

    testWidgets('Save Look shows success feedback without wear logging', (
      WidgetTester tester,
    ) async {
      final repo = _FakeTodayLookRepository(
        saveResult: SavedTodayLook.fromJson({
          'id': 'b3e1a2c4-5d6f-47a8-b9c0-d1e2f3a4b5c6',
          'title': 'Evening Polish',
          'sourceContext': 'daily',
          'snapshot': _wire(),
          'createdAt': '2030-08-15T10:00:00.000Z',
        }),
      );
      await tester.pumpWidget(_buildTestApp(repository: repo));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Save Look'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save Look'));
      await tester.pumpAndSettle();

      expect(repo.saveCalls, 1);
      expect(find.text('Today\'s look saved'), findsOneWidget);
      expect(find.text('Wearing this look!'), findsNothing);
    });

    testWidgets('empty backend renders retry without mock content', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _buildTestApp(
          repository: _FakeTodayLookRepository(
            getResult: const TodayLookResult.noneAvailable(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('No today\'s look available'), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);
      expect(find.text('Modern Minimalist'), findsNothing);
    });

    testWidgets('DailyOutfitScreen is scrollable', (WidgetTester tester) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('The Ensemble'), findsOneWidget);
      expect(find.text('Why It Works'), findsOneWidget);
    });
  });
}
