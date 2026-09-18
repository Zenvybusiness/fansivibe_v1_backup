import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:fansivibe/shared/crash_reporting/crash_reporting_service.dart';
import 'package:fansivibe/shared/crash_reporting/error_sanitizer.dart';
import 'package:fansivibe/shared/crash_reporting/global_error_handler.dart';
import 'package:fansivibe/shared/crash_reporting/global_error_widget.dart';

class _TestCrashSink implements CrashReportSink {
  final List<CrashReport> reports = [];

  @override
  void recordError(CrashReport report) {
    reports.add(report);
  }
}

class _ThrowingCrashSink implements CrashReportSink {
  @override
  void recordError(CrashReport report) {
    throw Exception('Sink delivery failed intentionally');
  }
}

void main() {
  group('P2-10 ErrorSanitizer', () {
    test('sanitizes Bearer tokens in strings', () {
      const message = 'Failed request: Bearer eyJ123.abc_456.def789 rejected';
      final sanitized = ErrorSanitizer.sanitizeString(message);
      expect(sanitized, isNot(contains('eyJ123')));
      expect(sanitized, contains('Bearer [REDACTED]'));
    });

    test('sanitizes raw JWT tokens in strings', () {
      const message = 'JWT token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgN leaked';
      final sanitized = ErrorSanitizer.sanitizeString(message);
      expect(sanitized, isNot(contains('dozjgN')));
      expect(sanitized, contains('[REDACTED_JWT]'));
    });

    test('sanitizes password query params in strings', () {
      const url = 'https://api.example.com/login?user=alex&password=SuperSecret123&other=val';
      final sanitized = ErrorSanitizer.sanitizeString(url);
      expect(sanitized, isNot(contains('SuperSecret123')));
      expect(sanitized, contains('password=[REDACTED]'));
    });

    test('sanitizes json secret keys in strings', () {
      const jsonStr = '{"user": "alex", "password": "SuperSecret123", "token": "tok_xyz"}';
      final sanitized = ErrorSanitizer.sanitizeString(jsonStr);
      expect(sanitized, isNot(contains('SuperSecret123')));
      expect(sanitized, isNot(contains('tok_xyz')));
      expect(sanitized, contains('"password": "[REDACTED]"'));
      expect(sanitized, contains('"token": "[REDACTED]"'));
    });

    test('sanitizes sensitive keys in metadata map', () {
      final metadata = <String, dynamic>{
        'authorization': 'Bearer raw-token-12345',
        'access_token': 'secret-access-token',
        'refresh_token': 'secret-refresh-token',
        'password': 'user-cleartext-pass',
        'api_key': 'ak_live_abcdef123456',
        'wardrobe_photo': 'https://storage.internal/user/wardrobe/private_item.jpg',
        'face_profile': {'shape': 'oval', 'features': [1, 2, 3]},
        'email': 'user@example.com',
        'screen': 'WardrobeScreen',
        'item_count': 42,
      };

      final sanitized = ErrorSanitizer.sanitizeMap(metadata);

      // Sensitive entries must be completely redacted
      expect(sanitized['authorization'], equals('[REDACTED]'));
      expect(sanitized['access_token'], equals('[REDACTED]'));
      expect(sanitized['refresh_token'], equals('[REDACTED]'));
      expect(sanitized['password'], equals('[REDACTED]'));
      expect(sanitized['api_key'], equals('[REDACTED]'));
      expect(sanitized['wardrobe_photo'], equals('[REDACTED]'));
      expect(sanitized['face_profile'], equals('[REDACTED]'));
      expect(sanitized['email'], equals('[REDACTED]'));

      // Non-sensitive entries must remain intact
      expect(sanitized['screen'], equals('WardrobeScreen'));
      expect(sanitized['item_count'], equals(42));
    });

    test('sanitizes image and binary bytes', () {
      final rawBytes = Uint8List.fromList([0xFF, 0xD8, 0xFF, 0xE0, 0x00]);
      final byteList = [1, 2, 3, 4, 5, 6];

      final metadata = <String, dynamic>{
        'image_bytes': rawBytes,
        'raw_stream': byteList,
      };

      final sanitized = ErrorSanitizer.sanitizeMap(metadata);
      expect(sanitized['image_bytes'], equals('[REDACTED]')); // key has image_bytes
      expect(sanitized['raw_stream'], equals('[BYTES: 6 items]'));
    });

    test('recursively sanitizes nested maps and lists', () {
      final nested = <String, dynamic>{
        'context': {
          'headers': {
            'authorization': 'Bearer secret-nested-token',
            'host': 'api.fansivibe.com',
          },
          'history': [
            {'action': 'click', 'target': 'save_button'},
            {'action': 'auth', 'token': 'tok_nested_123'},
          ],
        },
      };

      final sanitized = ErrorSanitizer.sanitizeMap(nested);
      final headers = (sanitized['context'] as Map<String, dynamic>)['headers'] as Map<String, dynamic>;
      expect(headers['authorization'], equals('[REDACTED]'));
      expect(headers['host'], equals('api.fansivibe.com'));

      final history = (sanitized['context'] as Map<String, dynamic>)['history'] as List<dynamic>;
      expect((history[1] as Map<String, dynamic>)['token'], equals('[REDACTED]'));
    });
  });

  group('P2-10 CrashReportingService', () {
    late CrashReportingService service;

    setUp(() {
      service = CrashReportingService.instance;
      service.clearReports();
      service.clearSinks();
    });

    tearDown(() {
      service.clearReports();
      service.clearSinks();
    });

    test('records sanitized error and notifies sinks', () {
      final sink = _TestCrashSink();
      service.addSink(sink);

      service.reportError(
        Exception('Network failure with Bearer raw_token_xyz'),
        StackTrace.current,
        reason: 'Failed to fetch items with token=secret123',
        metadata: {
          'screen': 'HomeScreen',
          'access_token': 'leaked_access_token',
        },
        fatal: false,
      );

      expect(service.recentReports.length, equals(1));
      expect(sink.reports.length, equals(1));

      final report = sink.reports.first;
      expect(report.error, isNot(contains('raw_token_xyz')));
      expect(report.error, contains('Bearer [REDACTED]'));
      expect(report.reason, isNot(contains('secret123')));
      expect(report.metadata['screen'], equals('HomeScreen'));
      expect(report.metadata['access_token'], equals('[REDACTED]'));
      expect(report.fatal, isFalse);
    });

    test('safely isolates failing sinks without throwing', () {
      final badSink = _ThrowingCrashSink();
      final goodSink = _TestCrashSink();
      service.addSink(badSink);
      service.addSink(goodSink);

      expect(
        () => service.reportError('Some error', null),
        returnsNormally,
      );

      expect(goodSink.reports.length, equals(1));
    });

    test('bounds recent reports to maxRecentReports', () {
      for (var i = 0; i < 60; i++) {
        service.reportError('Error number $i', null);
      }

      expect(service.recentReports.length, equals(CrashReportingService.maxRecentReports));
      expect(service.recentReports.last.error, contains('Error number 59'));
    });

    test('reportFlutterError extracts and sanitizes library and context', () {
      final sink = _TestCrashSink();
      service.addSink(sink);

      final flutterError = FlutterErrorDetails(
        exception: Exception('Rendering overflow with password=12345'),
        library: 'widgets library',
        context: ErrorDescription('during layout for user token abc'),
      );

      service.reportFlutterError(flutterError);

      expect(sink.reports.length, equals(1));
      final report = sink.reports.first;
      expect(report.error, isNot(contains('12345')));
      expect(report.metadata['library'], equals('widgets library'));
    });
  });

  group('P2-10 GlobalErrorHandler & GlobalErrorWidget', () {
    setUp(() {
      GlobalErrorHandler.reset();
      CrashReportingService.instance.clearReports();
    });

    tearDown(() {
      GlobalErrorHandler.reset();
      CrashReportingService.instance.clearReports();
    });

    test('initializes and configures framework and platform handlers', () {
      expect(GlobalErrorHandler.isInitialized, isFalse);

      GlobalErrorHandler.initialize();
      expect(GlobalErrorHandler.isInitialized, isTrue);

      expect(FlutterError.onError, isNotNull);
      expect(PlatformDispatcher.instance.onError, isNotNull);

      // Test PlatformDispatcher.onError invocation
      final handled = PlatformDispatcher.instance.onError!(
        Exception('Uncaught platform async failure'),
        StackTrace.current,
      );
      expect(handled, isTrue);
      expect(CrashReportingService.instance.recentReports.length, equals(1));
      expect(CrashReportingService.instance.recentReports.first.fatal, isTrue);
    });

    testWidgets('GlobalErrorWidget renders truthful generic UI without raw exception text', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: GlobalErrorWidget(
            details: FlutterErrorDetails(
              exception: Exception('CRITICAL_INTERNAL_DB_CRASH: table missing at /root/var/db'),
              stack: StackTrace.current,
            ),
          ),
        ),
      );

      // Verify truthful, generic error message
      expect(find.text('Something went wrong'), findsOneWidget);
      expect(find.text('An unexpected error occurred. Please try again shortly.'), findsOneWidget);

      // Verify sensitive exception details and paths are NOT exposed to normal users
      expect(find.textContaining('CRITICAL_INTERNAL_DB_CRASH'), findsNothing);
      expect(find.textContaining('/root/var/db'), findsNothing);
    });
  });
}
