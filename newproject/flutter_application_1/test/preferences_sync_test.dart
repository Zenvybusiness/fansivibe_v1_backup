import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/features/assistant/data/assistant_client.dart';
import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/profile/presentation/preferences_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

/// Scriptable preferences backend: canned GET list, recorded PATCHes.
class ScriptedPreferencesBackend {
  ScriptedPreferencesBackend({List<String>? serverOccasions})
    : serverOccasions = serverOccasions ?? [];

  List<String> serverOccasions;
  int patchStatus = 200;
  bool failGet = false;
  bool throwOnPatch = false;
  final List<http.Request> patchRequests = [];
  Completer<http.Response>? patchCompleter;

  Future<http.Response> handle(http.Request request) async {
    if (request.method == 'GET') {
      if (failGet) return http.Response('boom', 500);
      return http.Response(
        jsonEncode({
          'preferences': {'preferredOccasions': serverOccasions},
        }),
        200,
      );
    }
    patchRequests.add(request);
    if (throwOnPatch) throw Exception('offline');
    if (patchCompleter != null) return patchCompleter!.future;
    return http.Response('{"displayName":"Dev User"}', patchStatus);
  }

  AssistantClient client() => AssistantClient(client: MockClient(handle));
}

void main() {
  group('occasionLabelToCode (P1-2)', () {
    test('maps exact backend vocabulary counterparts', () {
      expect(occasionLabelToCode, {
        'Casual': 'casual',
        'Business': 'business',
        'Formal': 'formal',
      });
    });

    test('labels without a backend code have no entry (no invention)', () {
      expect(occasionLabelToCode.containsKey('Smart Casual'), isFalse);
      expect(occasionLabelToCode.containsKey('Streetwear'), isFalse);
    });
  });

  group('syncPreferredOccasion client (P1-2)', () {
    test('PATCH is sent with merged list + Authorization', () async {
      final backend = ScriptedPreferencesBackend(serverOccasions: ['date']);
      final client = backend.client();
      final result = await client.syncPreferredOccasion(code: 'casual');
      expect(result, PreferenceSyncResult.synced);
      expect(backend.patchRequests, hasLength(1));
      final patch = backend.patchRequests.single;
      expect(patch.method, 'PATCH');
      expect(patch.url.path, '/v1/users/me');
      expect(patch.headers['Authorization'], 'Bearer dev');
      // R36-derived values preserved, new code appended (no dupes).
      expect(patch.body, '{"preferredOccasions":["date","casual"]}');
      client.dispose();
    });

    test('already-present code sends no PATCH', () async {
      final backend = ScriptedPreferencesBackend(serverOccasions: ['casual']);
      final client = backend.client();
      final result = await client.syncPreferredOccasion(code: 'casual');
      expect(result, PreferenceSyncResult.alreadySynced);
      expect(backend.patchRequests, isEmpty);
      client.dispose();
    });

    test('empty code fails closed with zero requests', () async {
      var calls = 0;
      final client = AssistantClient(
        client: MockClient((_) async {
          calls++;
          return http.Response('{}', 200);
        }),
      );
      expect(
        await client.syncPreferredOccasion(code: ''),
        PreferenceSyncResult.invalidInput,
      );
      expect(calls, 0);
      client.dispose();
    });

    test('unreadable server list fails without writing', () async {
      final backend = ScriptedPreferencesBackend()..failGet = true;
      final client = backend.client();
      expect(
        await client.syncPreferredOccasion(code: 'casual'),
        PreferenceSyncResult.networkError,
      );
      expect(backend.patchRequests, isEmpty);
      client.dispose();
    });

    test('PATCH statuses map truthfully', () async {
      final cases = {
        401: PreferenceSyncResult.unauthorized,
        422: PreferenceSyncResult.invalidInput,
        429: PreferenceSyncResult.rateLimited,
        500: PreferenceSyncResult.unknown,
      };
      for (final entry in cases.entries) {
        final backend = ScriptedPreferencesBackend()..patchStatus = entry.key;
        final client = backend.client();
        expect(
          await client.syncPreferredOccasion(code: 'casual'),
          entry.value,
          reason: 'status ${entry.key}',
        );
        client.dispose();
      }
    });

    test('offline PATCH maps to networkError without throwing', () async {
      final backend = ScriptedPreferencesBackend()..throwOnPatch = true;
      final client = backend.client();
      expect(
        await client.syncPreferredOccasion(code: 'casual'),
        PreferenceSyncResult.networkError,
      );
      client.dispose();
    });

    test('updatePreferredOccasions bool parity holds (200→true)', () async {
      final backend = ScriptedPreferencesBackend();
      final client = backend.client();
      expect(await client.updatePreferredOccasions(['casual']), isTrue);
      backend.patchStatus = 401;
      expect(await client.updatePreferredOccasions(['casual']), isFalse);
      client.dispose();
    });
  });

  group('PreferencesScreen sync (P1-2 & P2-6)', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      LocalStorage.init(prefs: await SharedPreferences.getInstance());
      AuthSession.resetForTest();
      LearningService.instance.resetForTest();
    });

    Widget harness(AssistantClient client) => MaterialApp(
      theme: ThemeData.dark(),
      home: PreferencesScreen(preferencesClient: client),
    );

    bool isChipSelected(WidgetTester tester, String label) {
      final container = tester.widget<Container>(
        find.ancestor(
          of: find.text(label),
          matching: find.byType(Container),
        ).first,
      );
      final decoration = container.decoration as BoxDecoration?;
      return decoration?.color == FansivibeColors.accentGold;
    }

    testWidgets('mappable tap syncs and reports success', (
      WidgetTester tester,
    ) async {
      final backend = ScriptedPreferencesBackend();
      await tester.pumpWidget(harness(backend.client()));
      await tester.pumpAndSettle();

      final chip = find.text('Formal');
      await tester.ensureVisible(chip);
      await tester.tap(chip);
      await tester.pumpAndSettle();

      expect(find.text('Synced: Formal'), findsOneWidget);
      expect(
        backend.patchRequests.single.body,
        '{"preferredOccasions":["formal"]}',
      );
      // Local behavior preserved alongside the sync.
      expect(LearningService.instance.preferredOccasions, contains('Formal'));
    });

    testWidgets('unmappable tap stays local with zero PATCH', (
      WidgetTester tester,
    ) async {
      final backend = ScriptedPreferencesBackend();
      await tester.pumpWidget(harness(backend.client()));
      await tester.pumpAndSettle();

      final chip = find.text('Streetwear');
      await tester.ensureVisible(chip);
      await tester.tap(chip);
      await tester.pumpAndSettle();

      expect(find.textContaining('this device only'), findsOneWidget);
      expect(backend.patchRequests, isEmpty);
      expect(
        LearningService.instance.preferredOccasions,
        contains('Streetwear'),
      );
    });

    testWidgets('auth failure is reported truthfully', (
      WidgetTester tester,
    ) async {
      final backend = ScriptedPreferencesBackend()..patchStatus = 401;
      await tester.pumpWidget(harness(backend.client()));
      await tester.pumpAndSettle();

      final chip = find.text('Casual');
      await tester.ensureVisible(chip);
      await tester.tap(chip);
      await tester.pumpAndSettle();

      expect(find.textContaining('Session expired'), findsOneWidget);
    });

    testWidgets('pending tap is ignored (single PATCH)', (
      WidgetTester tester,
    ) async {
      final backend = ScriptedPreferencesBackend();
      await tester.pumpWidget(harness(backend.client()));
      await tester.pumpAndSettle();

      final chip = find.text('Casual');
      await tester.ensureVisible(chip);
      await tester.tap(chip);
      await tester.tap(chip);
      await tester.pumpAndSettle();

      expect(backend.patchRequests, hasLength(1));
      expect(find.text('Synced: Casual'), findsOneWidget);
    });

    testWidgets('selected chip highlight reflects initial and updated state (P2-6)', (
      WidgetTester tester,
    ) async {
      // Pre-seed an existing preference
      LearningService.instance.addPreferredOccasion('Formal');

      final backend = ScriptedPreferencesBackend();
      await tester.pumpWidget(harness(backend.client()));
      await tester.pumpAndSettle();

      // Initially 'Formal' is selected, others are not
      expect(isChipSelected(tester, 'Formal'), isTrue);
      expect(isChipSelected(tester, 'Casual'), isFalse);
      expect(isChipSelected(tester, 'Business'), isFalse);

      // Tap 'Business'
      final businessChip = find.text('Business');
      await tester.ensureVisible(businessChip);
      await tester.tap(businessChip);
      await tester.pumpAndSettle();

      // Now 'Business' is selected, 'Formal' is unselected
      expect(isChipSelected(tester, 'Business'), isTrue);
      expect(isChipSelected(tester, 'Formal'), isFalse);
      expect(find.text('Synced: Business'), findsOneWidget);
    });

    testWidgets('conflicting rapid taps cannot produce silent state divergence (P2-6)', (
      WidgetTester tester,
    ) async {
      final backend = ScriptedPreferencesBackend();
      await tester.pumpWidget(harness(backend.client()));
      await tester.pumpAndSettle();

      final formalChip = find.text('Formal');
      final businessChip = find.text('Business');
      await tester.ensureVisible(formalChip);
      await tester.tap(formalChip);
      // Conflicting tap while sync is pending
      await tester.tap(businessChip);
      await tester.pumpAndSettle();

      // Exactly 1 patch request sent (for formal, not business)
      expect(backend.patchRequests, hasLength(1));
      expect(backend.patchRequests.single.body, '{"preferredOccasions":["formal"]}');

      // Local state does NOT silently contain Business
      expect(LearningService.instance.preferredOccasions, contains('Formal'));
      expect(LearningService.instance.preferredOccasions, isNot(contains('Business')));

      // Selection reflects Formal
      expect(isChipSelected(tester, 'Formal'), isTrue);
      expect(isChipSelected(tester, 'Business'), isFalse);
      expect(find.text('Synced: Formal'), findsOneWidget);
    });

    testWidgets('in-progress sync shows truthful syncing state and chip highlight (P2-6)', (
      WidgetTester tester,
    ) async {
      final backend = ScriptedPreferencesBackend();
      final patchCompleter = Completer<http.Response>();
      backend.patchCompleter = patchCompleter;

      await tester.pumpWidget(harness(backend.client()));
      await tester.pumpAndSettle();

      final chip = find.text('Formal');
      await tester.ensureVisible(chip);
      await tester.tap(chip);
      // Observe immediate state during sync
      await tester.pump();

      expect(find.text('Syncing Formal…'), findsOneWidget);
      expect(isChipSelected(tester, 'Formal'), isTrue);

      // Complete the pending request
      patchCompleter.complete(http.Response('{"displayName":"Dev User"}', 200));

      // Settle completion
      await tester.pumpAndSettle();
      expect(find.text('Synced: Formal'), findsOneWidget);
      expect(isChipSelected(tester, 'Formal'), isTrue);
    });

    testWidgets('failed sync rolls back chip selection and does not record local preference (P2-6)', (
      WidgetTester tester,
    ) async {
      // Pre-seed 'Formal' as initial state
      LearningService.instance.addPreferredOccasion('Formal');

      final backend = ScriptedPreferencesBackend()..patchStatus = 401;
      await tester.pumpWidget(harness(backend.client()));
      await tester.pumpAndSettle();

      expect(isChipSelected(tester, 'Formal'), isTrue);

      final casualChip = find.text('Casual');
      await tester.ensureVisible(casualChip);
      await tester.tap(casualChip);
      await tester.pumpAndSettle();

      // Error reported truthfully
      expect(find.textContaining('Session expired'), findsOneWidget);

      // Reverted to Formal: Casual is NOT selected, Formal is selected
      expect(isChipSelected(tester, 'Casual'), isFalse);
      expect(isChipSelected(tester, 'Formal'), isTrue);

      // LearningService does not pretend Casual was accepted
      expect(LearningService.instance.preferredOccasions, isNot(contains('Casual')));
      expect(LearningService.instance.preferredOccasions, contains('Formal'));
    });

    testWidgets('401 during preference sync triggers AuthSession unauthorized notification (P2-6)', (
      WidgetTester tester,
    ) async {
      await AuthSession.saveSession('tok-pref-sync');
      var expiredNotified = false;
      AuthSession.onSessionExpired = () {
        expiredNotified = true;
      };

      final backend = ScriptedPreferencesBackend()..patchStatus = 401;
      await tester.pumpWidget(harness(backend.client()));
      await tester.pumpAndSettle();

      final chip = find.text('Casual');
      await tester.ensureVisible(chip);
      await tester.tap(chip);
      await tester.pumpAndSettle();

      expect(expiredNotified, isTrue);
      AuthSession.onSessionExpired = null;
      await AuthSession.clearSession();
    });
  });
}
