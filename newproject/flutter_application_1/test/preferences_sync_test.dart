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

/// Scriptable preferences backend: canned GET list, recorded PATCHes.
class ScriptedPreferencesBackend {
  ScriptedPreferencesBackend({List<String>? serverOccasions})
    : serverOccasions = serverOccasions ?? [];

  List<String> serverOccasions;
  int patchStatus = 200;
  bool failGet = false;
  bool throwOnPatch = false;
  final List<http.Request> patchRequests = [];

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

  group('PreferencesScreen sync (P1-2)', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
      LearningService.instance.resetForTest();
    });

    Widget harness(AssistantClient client) => MaterialApp(
      theme: ThemeData.dark(),
      home: PreferencesScreen(preferencesClient: client),
    );

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
  });
}
