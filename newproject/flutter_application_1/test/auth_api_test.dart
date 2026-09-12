import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/features/auth/auth.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_client.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

const String _authBody = '{"accessToken":"tok-abc-123","tokenType":"bearer",'
    '"expiresIn":3600,"profile":{"displayName":"Alex","styleProfile":{},'
    '"preferences":{},"settings":{},"flags":{},"version":0}}';

Future<void> _initPrefs() async {
  SharedPreferences.setMockInitialValues({});
  LocalStorage.init(prefs: await SharedPreferences.getInstance());
}

void main() {
  setUp(() async {
    await _initPrefs();
    AuthSession.resetForTest();
  });

  tearDown(() async {
    AuthSession.resetForTest();
    await AuthSession.clearSession();
  });

  group('AuthClient register/login paths', () {
    test('register posts the exact wire map with key and persists session',
        () async {
      late Uri seen;
      late Map<String, String> headers;
      late Map<String, dynamic> body;
      final client = AuthClient(
        client: MockClient((request) async {
          seen = request.url;
          headers = request.headers;
          body = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(_authBody, 201);
        }),
      );

      final result = await client.register(
        email: 'Alex@Example.com',
        password: 'Passw0rd1',
        displayName: 'Alex',
        idempotencyKey: 'reg-key-1',
      );

      expect(seen.path, '/v1/auth/register');
      expect(headers['Idempotency-Key'], 'reg-key-1');
      expect(
        body,
        {'email': 'Alex@Example.com', 'password': 'Passw0rd1', 'displayName': 'Alex'},
      );
      expect(result.isAuthenticated, isTrue);
      expect(result.status, AuthStatus.authenticated);
      expect(result.displayName, 'Alex');
      expect(result.expiresIn, 3600);
      expect(AuthSession.token, 'tok-abc-123');
      expect(AuthSession.isAuthenticated, isTrue);
      client.dispose();
    });

    test('register omits displayName when null and fails closed on empty key',
        () async {
      var calls = 0;
      final client = AuthClient(
        client: MockClient((request) async {
          calls++;
          return http.Response(_authBody, 201);
        }),
      );

      final result = await client.register(
        email: 'a@b.co',
        password: 'Passw0rd1',
        idempotencyKey: '',
      );

      expect(result.isAuthenticated, isFalse);
      expect(result.status, AuthStatus.invalidInput);
      expect(calls, 0);
      expect(AuthSession.token, isNull);
      client.dispose();
    });

    test('login posts credentials and persists the session on 200', () async {
      late Map<String, dynamic> body;
      final client = AuthClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/auth/login');
          body = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(_authBody, 200);
        }),
      );

      final result = await client.login(
        email: 'alex@example.com',
        password: 'Passw0rd1',
      );

      expect(body, {'email': 'alex@example.com', 'password': 'Passw0rd1'});
      expect(result.isAuthenticated, isTrue);
      expect(AuthSession.token, 'tok-abc-123');
      client.dispose();
    });

    test('status table: 401 invalidCredentials, 409 emailTaken, 422 invalidInput',
        () async {
      final cases = {
        401: AuthStatus.invalidCredentials,
        409: AuthStatus.emailTaken,
        422: AuthStatus.invalidInput,
        502: AuthStatus.providerUnavailable,
        500: AuthStatus.networkError,
      };
      for (final entry in cases.entries) {
        final client = AuthClient(
          client: MockClient((_) async => http.Response('{}', entry.key)),
        );
        final login = await client.login(
          email: 'a@b.co',
          password: 'Passw0rd1',
        );
        expect(login.isAuthenticated, isFalse, reason: '${entry.key}');
        expect(login.status, entry.value, reason: '${entry.key}');
        expect(AuthSession.token, isNull, reason: '${entry.key}');
        final register = await client.register(
          email: 'a@b.co',
          password: 'Passw0rd1',
          idempotencyKey: 'k-${entry.key}',
        );
        expect(register.status, entry.value, reason: 'register ${entry.key}');
        client.dispose();
      }
    });

    test('offline register/login are networkError with no persisted session',
        () async {
      final client = AuthClient(
        client: MockClient((_) async => throw Exception('down')),
      );
      expect(
        (await client.login(email: 'a@b.co', password: 'Passw0rd1')).status,
        AuthStatus.networkError,
      );
      expect(
        (await client.register(
          email: 'a@b.co',
          password: 'Passw0rd1',
          idempotencyKey: 'k',
        )).status,
        AuthStatus.networkError,
      );
      expect(AuthSession.token, isNull);
      client.dispose();
    });

    test('social is honestly providerUnavailable and mints nothing', () async {
      final client = AuthClient(
        client: MockClient((_) async => http.Response('{}', 502)),
      );
      final result = await client.socialSignIn(
        provider: 'google',
        providerToken: 'tok',
      );
      expect(result.isAuthenticated, isFalse);
      expect(result.status, AuthStatus.providerUnavailable);
      expect(AuthSession.token, isNull);
      client.dispose();
    });

    test('malformed success body clears any session (no fake auth)', () async {
      final client = AuthClient(
        client: MockClient((_) async => http.Response('{"nope":true}', 200)),
      );
      final result = await client.login(
        email: 'a@b.co',
        password: 'Passw0rd1',
      );
      expect(result.isAuthenticated, isFalse);
      expect(AuthSession.token, isNull);
      client.dispose();
    });
  });

  group('AuthClient logout + validateSession', () {
    test('logout revokes server-side then clears local session', () async {
      await AuthSession.saveSession('tok-out');
      late Map<String, String> headers;
      final client = AuthClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/auth/logout');
          headers = request.headers;
          return http.Response('', 204);
        }),
      );

      expect(await client.logout(), AuthStatus.signedOut);
      expect(headers['Authorization'], 'Bearer tok-out');
      expect(AuthSession.token, isNull);
      client.dispose();
    });

    test('logout clears locally even when the server 401s or is down',
        () async {
      for (final status in [401, 500]) {
        await AuthSession.saveSession('tok-dead');
        final client = AuthClient(
          client: MockClient((_) async => http.Response('', status)),
        );
        expect(await client.logout(), AuthStatus.signedOut);
        expect(AuthSession.token, isNull);
        client.dispose();
      }
      await AuthSession.saveSession('tok-down');
      final offline = AuthClient(
        client: MockClient((_) async => throw Exception('down')),
      );
      expect(await offline.logout(), AuthStatus.signedOut);
      expect(AuthSession.token, isNull);
      offline.dispose();
    });

    test('validateSession is true only on 200 (restoration probe)', () async {
      await AuthSession.saveSession('tok-restore');
      final ok = AuthClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/users/me');
          expect(
            request.headers['Authorization'],
            'Bearer tok-restore',
          );
          return http.Response('{}', 200);
        }),
      );
      expect(await ok.validateSession(), isTrue);
      expect(AuthSession.token, 'tok-restore');
      ok.dispose();

      final dead = AuthClient(
        client: MockClient((_) async => http.Response('{}', 401)),
      );
      expect(await dead.validateSession(), isFalse);
      // A 401 restoration probe drops the dead session.
      expect(AuthSession.token, isNull);
      dead.dispose();
    });

    test('validateSession is false without a token and makes zero calls',
        () async {
      var calls = 0;
      final client = AuthClient(
        client: MockClient((_) async {
          calls++;
          return http.Response('{}', 200);
        }),
      );
      expect(await client.validateSession(), isFalse);
      expect(calls, 0);
      client.dispose();
    });
  });

  group('Canonical session token injection', () {
    test('clients fall back to the dart-define token without a session',
        () async {
      late Map<String, String> headers;
      final client = WardrobeClient(
        client: MockClient((request) async {
          headers = request.headers;
          return http.Response('{"items":[],"page":1,"page_size":20,"total":0}', 200);
        }),
      );
      await client.listItems();
      expect(headers['Authorization'], 'Bearer dev');
      client.dispose();
    });

    test('session token wins over the dev default (no leakage)', () async {
      await AuthSession.saveSession('real-user-token');
      late Map<String, String> headers;
      final client = WardrobeClient(
        client: MockClient((request) async {
          headers = request.headers;
          return http.Response('{"items":[],"page":1,"page_size":20,"total":0}', 200);
        }),
      );
      await client.listItems();
      expect(headers['Authorization'], 'Bearer real-user-token');
      expect(headers['Authorization'], isNot('Bearer dev'));
      client.dispose();
    });

    test('multi-user sessions stay separated per stored token', () async {
      final seen = <String?>[];
      final client = WardrobeClient(
        client: MockClient((request) async {
          seen.add(request.headers['Authorization']);
          return http.Response('{"items":[],"page":1,"page_size":20,"total":0}', 200);
        }),
      );
      await AuthSession.saveSession('token-user-a');
      await client.listItems();
      await AuthSession.saveSession('token-user-b');
      await client.listItems();
      await AuthSession.clearSession();
      await client.listItems();
      expect(seen, [
        'Bearer token-user-a',
        'Bearer token-user-b',
        'Bearer dev',
      ]);
      client.dispose();
    });

    test('a 401 clears the session and fires the expiry callback once',
        () async {
      await AuthSession.saveSession('tok-stale');
      var calls = 0;
      AuthSession.onSessionExpired = () => calls++;
      final client = WardrobeClient(
        client: MockClient((_) async => http.Response('{}', 401)),
      );
      await client.listItems();
      await client.listItems();
      expect(AuthSession.token, isNull);
      expect(calls, 1);
      client.dispose();
    });
  });

  group('AuthRepository passthrough + key helper', () {
    test('repository delegates register/login/logout/validate', () async {
      final repo = AuthRepositoryImpl(
        client: AuthClient(
          client: MockClient((request) async {
            if (request.url.path == '/v1/auth/register') {
              return http.Response(_authBody, 201);
            }
            if (request.url.path == '/v1/auth/login') {
              return http.Response(_authBody, 200);
            }
            if (request.url.path == '/v1/auth/logout') {
              return http.Response('', 204);
            }
            return http.Response('{}', 200);
          }),
        ),
      );
      final registered = await repo.register(
        email: 'a@b.co',
        password: 'Passw0rd1',
        idempotencyKey: 'k1',
      );
      expect(registered.isAuthenticated, isTrue);
      expect(AuthSession.token, 'tok-abc-123');

      await AuthSession.clearSession();
      final loggedIn = await repo.login(
        email: 'a@b.co',
        password: 'Passw0rd1',
      );
      expect(loggedIn.isAuthenticated, isTrue);
      expect(await repo.validateSession(), isTrue);
      expect(await repo.logout(), AuthStatus.signedOut);
      expect(AuthSession.token, isNull);
    });

    test('idempotency keys are fresh UUID-shaped strings', () {
      final first = newAuthIdempotencyKey();
      final second = newAuthIdempotencyKey();
      expect(first, isNot(second));
      final uuid = RegExp(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
      );
      expect(uuid.hasMatch(first), isTrue);
      expect(uuid.hasMatch(second), isTrue);
    });
  });
}
