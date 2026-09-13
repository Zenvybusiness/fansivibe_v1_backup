import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/auth/secure_token_storage.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// 21.2 (H2) — secure token storage.
///
/// The platform channel `plugins.it_nomads.com/flutter_secure_storage`
/// is mocked with an in-memory map so the secure path is deterministic;
/// a separate group proves the no-platform fallback keeps every existing
/// behavior (all historical tests run that path).
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel =
      MethodChannel('plugins.it_nomads.com/flutter_secure_storage');
  final Map<String, String> vault = {};

  Future<void> coldStart({Map<String, Object> seed = const {}}) async {
    SharedPreferences.setMockInitialValues(seed);
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
  }

  setUp(() async {
    vault.clear();
    SecureTokenStorage.resetForTest();
    AuthSession.resetForTest();
    await coldStart();
  });

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
    AuthSession.resetForTest();
    SecureTokenStorage.resetForTest();
    await AuthSession.clearSession();
    LocalStorage.resetForTest();
  });

  void mockVault() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (MethodCall call) async {
      final args = (call.arguments as Map?)?.cast<String, dynamic>() ?? {};
      switch (call.method) {
        case 'read':
          return vault[args['key'] as String?];
        case 'write':
          vault[args['key'] as String] = args['value'] as String;
          return null;
        case 'delete':
          vault.remove(args['key'] as String?);
          return null;
        case 'containsKey':
          return vault.containsKey(args['key'] as String?);
        case 'readAll':
          return Map<String, String>.from(vault);
        case 'deleteAll':
          vault.clear();
          return null;
        default:
          return null;
      }
    });
  }

  group('fallback without platform (historical behavior preserved)', () {
    test('write/read/delete round-trips through app storage', () async {
      await SecureTokenStorage.writeToken('fallback-token');
      expect(SecureTokenStorage.currentToken, 'fallback-token');
      expect(AuthSession.isAuthenticated, isTrue);
      await SecureTokenStorage.deleteToken();
      expect(SecureTokenStorage.currentToken, isNull);
      expect(AuthSession.isAuthenticated, isFalse);
    });

    test('init without platform never throws and keeps prefs token',
        () async {
      LocalStorage.authToken = 'legacy-token';
      await SecureTokenStorage.init();
      expect(SecureTokenStorage.currentToken, 'legacy-token');
    });

    test('AuthSession save/clear/expiry behavior preserved', () async {
      await AuthSession.saveSession('session-abc');
      expect(AuthSession.token, 'session-abc');
      expect(AuthSession.effectiveToken('dev'), 'session-abc');

      var expired = 0;
      AuthSession.onSessionExpired = () => expired++;
      AuthSession.notifyUnauthorized();
      AuthSession.notifyUnauthorized();
      expect(AuthSession.token, isNull);
      expect(expired, 1);
      expect(AuthSession.effectiveToken('dev'), 'dev');

      await AuthSession.saveSession('session-xyz');
      await AuthSession.clearSession();
      expect(AuthSession.token, isNull);
    });
  });

  group('mocked secure platform', () {
    test('init migrates a legacy prefs token and drops the copy',
        () async {
      mockVault();
      LocalStorage.authToken = 'legacy-token';
      await SecureTokenStorage.init();

      expect(SecureTokenStorage.isInitialized, isTrue);
      expect(SecureTokenStorage.currentToken, 'legacy-token');
      expect(vault['fansivibe_auth_token'], 'legacy-token');
      expect(LocalStorage.authToken, isNull);
    });

    test('writeToken leaves no plaintext duplication', () async {
      mockVault();
      await SecureTokenStorage.init();
      await SecureTokenStorage.writeToken('secured-123');

      expect(vault['fansivibe_auth_token'], 'secured-123');
      expect(LocalStorage.authToken, isNull);
      expect(SecureTokenStorage.currentToken, 'secured-123');
    });

    test('secured token wins over a stale prefs copy', () async {
      mockVault();
      vault['fansivibe_auth_token'] = 'secured-winner';
      LocalStorage.authToken = 'stale-copy';
      await SecureTokenStorage.init();

      expect(SecureTokenStorage.currentToken, 'secured-winner');
      expect(LocalStorage.authToken, isNull);
    });

    test('deleteToken clears secure vault, cache, and prefs', () async {
      mockVault();
      await SecureTokenStorage.init();
      await SecureTokenStorage.writeToken('to-delete');
      await SecureTokenStorage.deleteToken();

      expect(vault.containsKey('fansivibe_auth_token'), isFalse);
      expect(SecureTokenStorage.currentToken, isNull);
      expect(LocalStorage.authToken, isNull);
      expect(AuthSession.isAuthenticated, isFalse);
    });

    test('AuthSession end-to-end over secure storage', () async {
      mockVault();
      await SecureTokenStorage.init();

      await AuthSession.saveSession('jwt-1');
      expect(AuthSession.token, 'jwt-1');
      expect(AuthSession.isAuthenticated, isTrue);

      AuthSession.notifyUnauthorized();
      expect(AuthSession.token, isNull);
      // The async secure delete settles without error.
      await Future<void>.delayed(const Duration(milliseconds: 50));
      expect(vault.containsKey('fansivibe_auth_token'), isFalse);
    });
  });
}
