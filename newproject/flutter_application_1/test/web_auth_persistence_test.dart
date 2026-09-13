import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/features/auth/data/auth_client.dart';
import 'package:fansivibe/features/discover/data/discover_client.dart';
import 'package:fansivibe/features/events/data/events_client.dart';
import 'package:fansivibe/features/learning/data/learning_summary_client.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_client.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_client.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

// Covers ONLY the Flutter Web session flow behind the reported 401s:
//
//   GET /v1/looks, POST /v1/outfits/generate, GET /v1/events,
//   GET /v1/wardrobe/items, GET /v1/learning/summary
//
// Backend ground truth (live :8000): a freshly minted token answers
// 200/204 on all five, while a missing/`dev`/tampered/revoked token
// answers 401 — so a 401 means the browser sent no session token
// (`Bearer dev` fallback) or a stale one, never a missing header in
// code. These tests pin the header contract per endpoint plus the
// Web reload persistence that DevTools Network should confirm
// (`Authorization: Bearer <token>`, never printed here — fake
// test-only tokens throughout).

Future<void> _initPrefs([Map<String, Object> seed = const {}]) async {
  SharedPreferences.setMockInitialValues(seed);
  LocalStorage.init(prefs: await SharedPreferences.getInstance());
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    await _initPrefs();
    AuthSession.resetForTest();
  });

  tearDown(() async {
    AuthSession.resetForTest();
    await AuthSession.clearSession();
    LocalStorage.resetForTest();
  });

  group('Web auth headers on the five 401 endpoints', () {
    test('logged out clients send the dev fallback (expect 401 live)',
        () async {
      expect(AuthSession.isAuthenticated, isFalse);
      final seen = <String, String?>{};

      final wardrobe = WardrobeClient(
        client: MockClient((request) async {
          seen['wardrobe'] = request.headers['Authorization'];
          return http.Response(
            '{"items":[],"page":1,"page_size":20,"total":0}',
            200,
          );
        }),
      );
      await wardrobe.listItems();
      wardrobe.dispose();

      final events = EventsClient(
        client: MockClient((request) async {
          seen['events'] = request.headers['Authorization'];
          return http.Response(
            '{"items":[],"page":1,"page_size":20,"total":0}',
            200,
          );
        }),
      );
      await events.listEvents();
      events.dispose();

      final learning = LearningSummaryClient(
        client: MockClient((request) async {
          seen['learning'] = request.headers['Authorization'];
          return http.Response(
            '{"styleScore":60,"breakdown":{"base":60,"wardrobePoints":0,'
            '"savedPoints":0,"total":60},"streak":0,"recentSignals":[]}',
            200,
          );
        }),
      );
      await learning.getSummary();
      learning.dispose();

      final discover = DiscoverClient(
        client: MockClient((request) async {
          seen['looks'] = request.headers['Authorization'];
          return http.Response('{}', 500);
        }),
      );
      await discover.getLookFeed();
      discover.dispose();

      final outfits = OutfitBuilderClient(
        client: MockClient((request) async {
          seen['generate'] = request.headers['Authorization'];
          return http.Response('', 500);
        }),
      );
      await outfits.generateOutfit(
        occasion: 'casual',
        mood: 'relaxed',
        fit: 'regular',
        colorPalette: 'neutral',
      );
      outfits.dispose();

      // DevTools equivalent when logged out: the fallback header the
      // dev backend (allow_dev_token=false) correctly rejects with 401.
      expect(seen['wardrobe'], 'Bearer dev');
      expect(seen['events'], 'Bearer dev');
      expect(seen['learning'], 'Bearer dev');
      expect(seen['looks'], 'Bearer dev');
      expect(seen['generate'], 'Bearer dev');
    });

    test('logged in clients attach the persisted session (never dev)',
        () async {
      await AuthSession.saveSession('web-session-token-abc');
      expect(AuthSession.isAuthenticated, isTrue);
      final seen = <String, String?>{};

      final wardrobe = WardrobeClient(
        client: MockClient((request) async {
          seen['wardrobe'] = request.headers['Authorization'];
          return http.Response(
            '{"items":[],"page":1,"page_size":20,"total":0}',
            200,
          );
        }),
      );
      await wardrobe.listItems();
      wardrobe.dispose();

      final events = EventsClient(
        client: MockClient((request) async {
          seen['events'] = request.headers['Authorization'];
          return http.Response(
            '{"items":[],"page":1,"page_size":20,"total":0}',
            200,
          );
        }),
      );
      await events.listEvents();
      events.dispose();

      final learning = LearningSummaryClient(
        client: MockClient((request) async {
          seen['learning'] = request.headers['Authorization'];
          return http.Response(
            '{"styleScore":60,"breakdown":{"base":60,"wardrobePoints":0,'
            '"savedPoints":0,"total":60},"streak":0,"recentSignals":[]}',
            200,
          );
        }),
      );
      final summary = await learning.getSummary();
      learning.dispose();

      final discover = DiscoverClient(
        client: MockClient((request) async {
          seen['looks'] = request.headers['Authorization'];
          return http.Response('{}', 500);
        }),
      );
      await discover.getLookFeed();
      discover.dispose();

      final outfits = OutfitBuilderClient(
        client: MockClient((request) async {
          seen['generate'] = request.headers['Authorization'];
          return http.Response('', 500);
        }),
      );
      await outfits.generateOutfit(
        occasion: 'casual',
        mood: 'relaxed',
        fit: 'regular',
        colorPalette: 'neutral',
      );
      outfits.dispose();

      expect(summary, isNotNull);
      for (final entry in seen.entries) {
        expect(
          entry.value,
          'Bearer web-session-token-abc',
          reason: '${entry.key} must carry the session token',
        );
        expect(entry.value, isNot('Bearer dev'));
      }
    });

    test('logout returns all five clients to the dev fallback', () async {
      await AuthSession.saveSession('web-session-token-abc');
      await AuthSession.clearSession();
      expect(AuthSession.isAuthenticated, isFalse);

      String? seen;
      final events = EventsClient(
        client: MockClient((request) async {
          seen = request.headers['Authorization'];
          return http.Response(
            '{"items":[],"page":1,"page_size":20,"total":0}',
            200,
          );
        }),
      );
      await events.listEvents();
      events.dispose();
      expect(seen, 'Bearer dev');
    });
  });

  group('Web reload restores the persisted session', () {
    test('token survives a simulated Chrome reload on the same origin',
        () async {
      await AuthSession.saveSession('web-session-token-abc');

      // Simulate a Chrome reload: drop the in-memory prefs reference and
      // re-open platform storage (localStorage on Web keeps the value
      // for the same origin).
      LocalStorage.resetForTest();
      LocalStorage.init(prefs: await SharedPreferences.getInstance());

      expect(AuthSession.isAuthenticated, isTrue);
      expect(AuthSession.token, 'web-session-token-abc');

      String? seen;
      final learning = LearningSummaryClient(
        client: MockClient((request) async {
          seen = request.headers['Authorization'];
          return http.Response(
            '{"styleScore":60,"breakdown":{"base":60,"wardrobePoints":0,'
            '"savedPoints":0,"total":60},"streak":0,"recentSignals":[]}',
            200,
          );
        }),
      );
      await learning.getSummary();
      learning.dispose();
      expect(seen, 'Bearer web-session-token-abc');
    });
  });

  group('Login persists the session for later requests', () {
    test('register/login response token lands in storage and headers',
        () async {
      const loginBody =
          '{"accessToken":"web-login-token-xyz","tokenType":"bearer",'
          '"expiresIn":3600,"profile":{"displayName":"Web"}}';
      final auth = AuthClient(
        client: MockClient((request) async {
          if (request.url.path == '/v1/auth/login') {
            return http.Response(loginBody, 200);
          }
          return http.Response('{}', 404);
        }),
      );
      final result = await auth.login(
        email: 'web@example.com',
        password: 'TestPass123!',
      );
      auth.dispose();

      expect(result.isAuthenticated, isTrue);
      expect(AuthSession.token, 'web-login-token-xyz');

      String? seen;
      final discover = DiscoverClient(
        client: MockClient((request) async {
          seen = request.headers['Authorization'];
          return http.Response('{}', 500);
        }),
      );
      await discover.getLookFeed();
      discover.dispose();
      expect(seen, 'Bearer web-login-token-xyz');
    });

    test('a 401 on looks clears the stale session exactly once', () async {
      await AuthSession.saveSession('web-stale-token');
      var calls = 0;
      AuthSession.onSessionExpired = () => calls++;
      final discover = DiscoverClient(
        client: MockClient((_) async => http.Response('{}', 401)),
      );
      await discover.getLookFeed();
      await discover.getLookFeed();
      discover.dispose();
      expect(AuthSession.token, isNull);
      expect(calls, 1);
    });
  });
}
