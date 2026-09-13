import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/features/outfit_scan/data/outfit_scan_client.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

Future<void> _initPrefs() async {
  SharedPreferences.setMockInitialValues({});
  LocalStorage.init(prefs: await SharedPreferences.getInstance());
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    await _initPrefs();
    AuthSession.resetForTest();
    await AuthSession.clearSession();
  });

  tearDown(() async {
    AuthSession.resetForTest();
    await AuthSession.clearSession();
  });

  group('OutfitScanClient Canonical Configuration & D-AUTH-1 Auth', () {
    test('baseUrl uses canonical configuration with fallback', () {
      expect(OutfitScanClient.baseUrl, isNotEmpty);
      expect(
        OutfitScanClient.baseUrl,
        anyOf(
          equals('http://localhost:8000'),
          contains('http'),
        ),
      );
    });

    test('devToken falls back to canonical default when logged out', () {
      expect(AuthSession.isAuthenticated, isFalse);
      expect(OutfitScanClient.devToken, equals('dev'));
    });

    test('devToken resolves session token when authenticated (D-AUTH-1)',
        () async {
      await AuthSession.saveSession('user-session-token-xyz');
      expect(AuthSession.isAuthenticated, isTrue);
      expect(OutfitScanClient.devToken, equals('user-session-token-xyz'));
    });
  });

  group('OutfitScanClient.submitOutfitAnalysis', () {
    test('submits multipart request with canonical url and auth header',
        () async {
      await AuthSession.saveSession('active-jwt-token');

      // Web-safe: XFile backed by temp bytes (client reads bytes, no dart:io
      // File in lib). Temp dir creation stays test-only (VM).
      final tempDir = Directory.systemTemp.createTempSync('scan_test_');
      final testFile = File('${tempDir.path}/test_outfit.jpg')
        ..writeAsBytesSync([1, 2, 3, 4]);
      final xFile = XFile(testFile.path);

      final client = OutfitScanClient(
        client: MockClient((request) async {
          expect(request.url.path, equals('/v1/analysis/outfit'));
          expect(
            request.headers['Authorization'],
            equals('Bearer active-jwt-token'),
          );
          expect(
            request.headers['content-type'],
            contains('multipart/form-data'),
          );
          return http.Response(
            jsonEncode({'run_id': 'run-outfit-abc'}),
            202,
          );
        }),
      );

      final runId = await client.submitOutfitAnalysis(xFile);
      expect(runId, equals('run-outfit-abc'));

      // Web-safe bytes path also works (Chrome Web upload).
      final bytesRunId = await client.submitOutfitAnalysisBytes(
        Uint8List.fromList([1, 2, 3, 4]),
        filename: 'test_outfit.jpg',
      );
      expect(bytesRunId, equals('run-outfit-abc'));

      // Empty bytes fail closed without network.
      final emptyRunId = await client.submitOutfitAnalysisBytes(
        Uint8List(0),
        filename: 'empty.jpg',
      );
      expect(emptyRunId, isNull);

      // Cleanup
      tempDir.deleteSync(recursive: true);
    });

    test('returns null gracefully on rejection or network failure', () async {
      final tempDir = Directory.systemTemp.createTempSync('scan_test_');
      final testFile = File('${tempDir.path}/test_outfit.jpg')
        ..writeAsBytesSync([1, 2, 3, 4]);
      final xFile = XFile(testFile.path);

      final errorClient = OutfitScanClient(
        client: MockClient((request) async {
          return http.Response(jsonEncode({'error': 'invalid media'}), 422);
        }),
      );

      final runId = await errorClient.submitOutfitAnalysis(xFile);
      expect(runId, isNull);

      tempDir.deleteSync(recursive: true);
    });
  });

  group('OutfitScanClient.getAnalysisRun', () {
    test('polls analysis run with canonical url and auth header', () async {
      await AuthSession.saveSession('poll-jwt-token');

      final client = OutfitScanClient(
        client: MockClient((request) async {
          expect(
            request.url.path,
            equals('/v1/analysis/runs/test-run-123'),
          );
          expect(
            request.headers['Authorization'],
            equals('Bearer poll-jwt-token'),
          );
          return http.Response(
            jsonEncode({
              'run_id': 'test-run-123',
              'status': 'completed',
              'result': {'score': 95},
            }),
            200,
          );
        }),
      );

      final result = await client.getAnalysisRun('test-run-123');
      expect(result.statusCode, equals(200));
      expect(result.isCompleted, isTrue);
      expect(result.data?['result']?['score'], equals(95));
    });

    test('handles 401 unauthorized canonically through AuthSession', () async {
      await AuthSession.saveSession('expired-jwt-token');
      expect(AuthSession.isAuthenticated, isTrue);

      var expiredFired = false;
      AuthSession.onSessionExpired = () {
        expiredFired = true;
      };

      final client = OutfitScanClient(
        client: MockClient((request) async {
          return http.Response(
            jsonEncode({'detail': 'Token expired'}),
            401,
          );
        }),
      );

      final result = await client.getAnalysisRun('expired-run');
      expect(result.statusCode, equals(401));
      expect(AuthSession.isAuthenticated, isFalse);
      expect(expiredFired, isTrue);
    });
  });

  group('Outfit-Scan Implementation Hygiene', () {
    test('no hardcoded localhost or raw dev-token in screens', () {
      final scanScreenFile =
          File('lib/features/outfit_scan/presentation/outfit_scan_screen.dart');
      final procScreenFile = File(
          'lib/features/outfit_scan/presentation/outfit_processing_screen.dart');

      if (scanScreenFile.existsSync()) {
        final content = scanScreenFile.readAsStringSync();
        expect(content.contains('http://localhost'), isFalse);
        expect(content.contains('http://127.0.0.1'), isFalse);
        expect(content.contains("effectiveToken('dev')"), isFalse);
      }

      if (procScreenFile.existsSync()) {
        final content = procScreenFile.readAsStringSync();
        expect(content.contains('http://localhost'), isFalse);
        expect(content.contains('http://127.0.0.1'), isFalse);
        expect(content.contains("effectiveToken('dev')"), isFalse);
        expect(content.contains("static const _baseUrl"), isFalse);
      }
    });
  });
}
