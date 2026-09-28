import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/grooming/data/grooming_models.dart';
import 'package:fansivibe/features/grooming/data/grooming_service.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_result_screen.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/domain/hairstyle_service.dart';
import 'package:fansivibe/features/hairstyle/presentation/hairstyle_result_screen.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_analysis_screen.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart'
    show AddItemConfig;
import 'package:fansivibe/features/wardrobe/presentation/add_wardrobe_item_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/pending_auth_intent.dart';

import 'support/controllable_hairstyle_service.dart';

/// D-02: authenticated save continuation.
///
/// Guest analysis → result → Save → sign-in → authenticated session →
/// persistence, reusing `PendingAuthIntent` + the D-01 ephemeral slot.
/// No new auth state, no second continuation, no migrations.

Map<String, dynamic> _hairstyleSnapshot() => {
  'appearance': {
    'faceShape': 'Oval',
    'skinTone': 'Warm Medium',
    'bodyType': '',
    'styleType': 'Modern Classic',
    'sourceRunId': 'ephemeral-test-id',
  },
  'confidence': 0.9,
  'needs_more_data': false,
  'recommendations': {
    'top': {
      'id': 'textured_quiff',
      'name': 'Textured Quiff',
      'description': 'A test recommendation.',
      'matchScore': 0.94,
      'reasons': ['Grounded reason'],
      'stylingTips': 'Tips',
      'maintenance': 'Low',
      'bestFor': 'Oval',
    },
    'alternatives': [],
  },
};

Map<String, dynamic> _groomingSnapshot() => {
  'appearance': {
    'faceShape': 'oval',
    'skinTone': '',
    'bodyType': '',
    'styleType': '',
    'sourceRunId': 'ephemeral-test-id',
  },
  'confidence': 0.88,
  'needs_more_data': true,
  'recommendations': {
    'top': {
      'id': 'structured_goatee',
      'name': 'Structured Goatee',
      'description': 'A test recommendation.',
      'matchScore': 0.92,
      'reasons': ['Grounded reason'],
      'stylingTips': 'Tips',
      'maintenance': 'Medium',
      'bestFor': 'Oval',
    },
    'alternatives': [],
  },
};

Map<String, dynamic> _outfitSnapshot() => {
  'appearance': {
    'faceShape': 'Oval',
    'skinTone': 'Warm Medium',
    'bodyType': '',
    'styleType': 'Modern Classic',
    'sourceRunId': 'ephemeral-test-id',
  },
  'confidence': 0.9,
  'needs_more_data': false,
  'recommendations': {
    'top': {
      'id': 'office_outfit',
      'name': 'Office Outfit',
      'description': 'A test recommendation.',
      'matchScore': 0.9,
      'reasons': ['Grounded reason'],
      'stylingTips': 'Tips',
      'maintenance': 'Low',
      'bestFor': 'Office',
    },
    'alternatives': [],
  },
};

class _StubSaveGroomingService extends GroomingService {
  _StubSaveGroomingService({this.saveResult = true});

  bool saveResult;
  int saveCalls = 0;

  @override
  Future<bool> saveGroomingLook({
    required GroomingRecommendation recommendation,
    required String title,
  }) async {
    saveCalls++;
    return saveResult;
  }
}

Future<void> _initPrefs() async {
  SharedPreferences.setMockInitialValues({});
  LocalStorage.init(prefs: await SharedPreferences.getInstance());
  AuthSession.resetForTest();
}

void _asGuest() {
  LocalStorage.savedLocally = true;
}

void _asAuthenticated() {
  LocalStorage.savedLocally = false;
  LocalStorage.authToken = 'test-token';
}

Future<void> _tapSave(WidgetTester tester, String label) async {
  await tester.scrollUntilVisible(
    find.text(label),
    300.0,
    scrollable: find.byType(Scrollable).first,
  );
  await tester.pumpAndSettle();
  await tester.tap(find.text(label));
  await tester.pumpAndSettle();
}

void main() {
  setUp(() async {
    await _initPrefs();
  });

  tearDown(() {
    AuthSession.resetForTest();
    LocalStorage.resetForTest();
    LearningService.instance.resetForTest();
  });

  group('hairstyle save continuation', () {
    testWidgets('authenticated Save persists once and clears the stash', (
      tester,
    ) async {
      _asAuthenticated();
      final service = StubSaveHairstyleService();
      final result = HairstyleAnalysisResult.fromRunResult(
        _hairstyleSnapshot(),
      );
      stashPendingEphemeralResult(
        feature: EphemeralFeature.hairstyle,
        snapshot: _hairstyleSnapshot(),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: HairstyleResultScreen(result: result, service: service),
        ),
      );
      await tester.pumpAndSettle();

      await _tapSave(tester, 'Save Style');

      expect(service.saveCalls, 1);
      expect(find.text('sign-in-marker'), findsNothing);
      expect(find.text('Hairstyle saved to profile'), findsOneWidget);
      expect(peekPendingEphemeralResult(), isNull);
      expect(AuthSession.isAuthenticated, isTrue);
    });

    testWidgets('duplicate Save taps never duplicate persistence', (
      tester,
    ) async {
      _asAuthenticated();
      final service = StubSaveHairstyleService();
      final result = HairstyleAnalysisResult.fromRunResult(
        _hairstyleSnapshot(),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: HairstyleResultScreen(result: result, service: service),
        ),
      );
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(
        find.text('Save Style'),
        300.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save Style'));
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(find.text('Save Style'));
      await tester.pumpAndSettle();

      expect(service.saveCalls, 1);
    });

    testWidgets('failed save keeps the result recoverable and the stash', (
      tester,
    ) async {
      _asAuthenticated();
      final service = StubSaveHairstyleService(saveResult: false);
      final result = HairstyleAnalysisResult.fromRunResult(
        _hairstyleSnapshot(),
      );
      stashPendingEphemeralResult(
        feature: EphemeralFeature.hairstyle,
        snapshot: _hairstyleSnapshot(),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: HairstyleResultScreen(result: result, service: service),
        ),
      );
      await tester.pumpAndSettle();

      await _tapSave(tester, 'Save Style');

      expect(service.saveCalls, 1);
      expect(find.text('Could not save hairstyle'), findsOneWidget);
      expect(find.text('Textured Quiff'), findsOneWidget);
      expect(peekPendingEphemeralResult(), isNotNull);
    });

    testWidgets('guest Save records intent and never persists', (
      tester,
    ) async {
      _asGuest();
      final service = StubSaveHairstyleService();
      final result = HairstyleAnalysisResult.fromRunResult(
        _hairstyleSnapshot(),
      );
      stashPendingEphemeralResult(
        feature: EphemeralFeature.hairstyle,
        snapshot: _hairstyleSnapshot(),
      );
      final router = GoRouter(
        initialLocation: '/result',
        routes: [
          GoRoute(
            path: '/result',
            builder: (_, __) =>
                HairstyleResultScreen(result: result, service: service),
          ),
          GoRoute(
            path: '/sign-in',
            name: RouteNames.signIn,
            builder: (_, __) => const Text('sign-in-marker'),
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      await _tapSave(tester, 'Save Style');

      expect(find.text('sign-in-marker'), findsOneWidget);
      expect(service.saveCalls, 0);
      expect(takePendingAuthIntent(), isNotNull);
      expect(peekPendingEphemeralResult(), isNotNull);
    });

    testWidgets('missing result renders the truthful error, never a save', (
      tester,
    ) async {
      _asAuthenticated();
      await tester.pumpWidget(
        const MaterialApp(home: HairstyleResultScreen()),
      );
      await tester.pumpAndSettle();

      expect(
        find.text('No hairstyle analysis available. Please run a scan first.'),
        findsOneWidget,
      );
      expect(find.text('Save Style'), findsNothing);
    });
  });

  group('grooming save continuation', () {
    GroomingAnalysisResult result() =>
        GroomingAnalysisResult.fromSnapshot(_groomingSnapshot());

    Widget screen(_StubSaveGroomingService service) => MaterialApp(
      home: GroomingResultScreen(
        faceShape: 'oval',
        beardStyle: 'goatee',
        beardDensity: 'medium',
        beardColor: 'black',
        result: result(),
        service: service,
      ),
    );

    testWidgets('authenticated Save persists once and clears the stash', (
      tester,
    ) async {
      _asAuthenticated();
      final service = _StubSaveGroomingService();
      stashPendingEphemeralResult(
        feature: EphemeralFeature.grooming,
        snapshot: _groomingSnapshot(),
      );
      await tester.pumpWidget(screen(service));
      await tester.pumpAndSettle();

      await _tapSave(tester, 'Save Look');

      expect(service.saveCalls, 1);
      expect(find.text('sign-in-marker'), findsNothing);
      expect(find.text('Look saved to profile'), findsOneWidget);
      expect(peekPendingEphemeralResult(), isNull);
      expect(AuthSession.isAuthenticated, isTrue);
    });

    testWidgets('duplicate Save taps never duplicate persistence', (
      tester,
    ) async {
      _asAuthenticated();
      final service = _StubSaveGroomingService();
      await tester.pumpWidget(screen(service));
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(
        find.text('Save Look'),
        300.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save Look'));
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(find.text('Save Look'));
      await tester.pumpAndSettle();

      expect(service.saveCalls, 1);
    });

    testWidgets('failed save keeps the result recoverable and the stash', (
      tester,
    ) async {
      _asAuthenticated();
      final service = _StubSaveGroomingService(saveResult: false);
      stashPendingEphemeralResult(
        feature: EphemeralFeature.grooming,
        snapshot: _groomingSnapshot(),
      );
      await tester.pumpWidget(screen(service));
      await tester.pumpAndSettle();

      await _tapSave(tester, 'Save Look');

      expect(service.saveCalls, 1);
      expect(find.text('Could not save look'), findsOneWidget);
      expect(find.text('Structured Goatee'), findsOneWidget);
      expect(peekPendingEphemeralResult(), isNotNull);
    });

    testWidgets('missing result renders the truthful error, never a save', (
      tester,
    ) async {
      _asAuthenticated();
      await tester.pumpWidget(
        const MaterialApp(
          home: GroomingResultScreen(
            faceShape: '',
            beardStyle: '',
            beardDensity: '',
            beardColor: '',
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text('No grooming analysis available. Please run a scan first.'),
        findsOneWidget,
      );
      expect(find.text('Save Look'), findsNothing);
    });
  });

  group('outfit scan save continuation', () {
    testWidgets('guest Save prompts sign-in and keeps the stash', (
      tester,
    ) async {
      _asGuest();
      stashPendingEphemeralResult(
        feature: EphemeralFeature.outfit,
        snapshot: _outfitSnapshot(),
      );
      final router = GoRouter(
        initialLocation: '/analysis',
        routes: [
          GoRoute(
            path: '/analysis',
            builder: (_, __) =>
                OutfitAnalysisScreen(analysisResult: _outfitSnapshot()),
          ),
          GoRoute(
            path: '/sign-in',
            name: RouteNames.signIn,
            builder: (_, __) => const Text('sign-in-marker'),
          ),
        ],
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      await _tapSave(tester, 'Save Profile');

      expect(find.text('sign-in-marker'), findsOneWidget);
      expect(takePendingAuthIntent(), isNotNull);
      expect(peekPendingEphemeralResult(), isNotNull);
    });
  });

  group('garment save continuation', () {
    testWidgets('guest Save persists device-local with no sign-in prompt', (
      tester,
    ) async {
      _asGuest();
      final category = AddItemConfig.categories.firstWhere(
        (c) => c.id == 'tops',
      );
      await tester.pumpWidget(
        MaterialApp(home: AddWardrobeItemScreen(category: category)),
      );
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(
        find.text('T-Shirt'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('T-Shirt'));
      await tester.pump();
      await tester.scrollUntilVisible(
        find.text('Black'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Black'));
      await tester.pump();
      await tester.scrollUntilVisible(
        find.text('Save Item'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Save Item'));
      await tester.pumpAndSettle();

      expect(find.text('sign-in-marker'), findsNothing);
      expect(
        find.textContaining('Saved', findRichText: true),
        findsWidgets,
      );
      // Device-local ids ride the post-auth Merge continuation, so the
      // guest stash slot stays out of the garment flow by design.
      expect(peekPendingEphemeralResult(), isNull);
    });
  });

  group('ephemeral slot hygiene', () {
    test('stash strips the transient run id and peek restores the snapshot',
        () async {
      stashPendingEphemeralResult(
        feature: EphemeralFeature.hairstyle,
        snapshot: _hairstyleSnapshot(),
      );
      final pending = peekPendingEphemeralResult();
      expect(pending, isNotNull);
      expect(pending!.feature, EphemeralFeature.hairstyle);
      expect(pending.snapshot.containsKey('sourceRunId'), isFalse);
      final appearance =
          pending.snapshot['appearance'] as Map<String, dynamic>;
      expect(appearance.containsKey('sourceRunId'), isFalse);
      expect(appearance['faceShape'], 'Oval');
    });

    test('malformed slot fails closed to null', () async {
      LocalStorage.pendingEphemeralResult = 'not-json';
      expect(peekPendingEphemeralResult(), isNull);
    });

    test('expired slot fails closed and is cleared', () async {
      final stale = jsonEncode({
        'feature': EphemeralFeature.grooming,
        'snapshot': _groomingSnapshot(),
        'savedAt': DateTime.now()
            .subtract(const Duration(hours: 25))
            .toIso8601String(),
      });
      LocalStorage.pendingEphemeralResult = stale;
      expect(peekPendingEphemeralResult(), isNull);
      expect(LocalStorage.pendingEphemeralResult, isNull);
    });

    test('clear drops the slot', () async {
      stashPendingEphemeralResult(
        feature: EphemeralFeature.outfit,
        snapshot: _outfitSnapshot(),
      );
      clearPendingEphemeralResult();
      expect(peekPendingEphemeralResult(), isNull);
    });
  });
}
