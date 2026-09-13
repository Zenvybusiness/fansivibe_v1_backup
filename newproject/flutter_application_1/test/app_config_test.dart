import 'package:flutter_test/flutter_test.dart';

import 'package:fansivibe/core/config/app_config.dart';
import 'package:fansivibe/features/assistant/data/assistant_client.dart';
import 'package:fansivibe/features/auth/data/auth_client.dart';
import 'package:fansivibe/features/discover/data/discover_client.dart';
import 'package:fansivibe/features/events/data/events_client.dart';
import 'package:fansivibe/features/feedback/data/feedback_client.dart';
import 'package:fansivibe/features/grooming/data/grooming_client.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_client.dart';
import 'package:fansivibe/features/home/data/today_look_client.dart';
import 'package:fansivibe/features/knowledge/data/knowledge_client.dart';
import 'package:fansivibe/features/learning/data/learning_summary_client.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_client.dart';
import 'package:fansivibe/features/outfit_scan/data/outfit_scan_client.dart';
import 'package:fansivibe/features/profile/data/saved_looks_client.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_client.dart';

/// P0-4 — centralized Flutter production API configuration.
///
/// One authoritative base URL ([AppConfig.apiBaseUrl]); every API client
/// resolves through it. Development keeps localhost; production fails
/// clearly on missing/localhost/non-HTTPS instead of silent bad requests.
void main() {
  group('P0-4 AppConfig', () {
    test('development default uses localhost and validates', () {
      // Default compile-time config (no dart-define): dev localhost.
      expect(AppConfig.apiBaseUrl, contains('localhost'));
      expect(AppConfig.isProduction, isFalse);
      expect(AppConfig.isLocalhost, isTrue);
      // Non-production never throws — local dev keeps working.
      expect(
        () => AppConfig.validateOrThrow(
          baseUrl: 'http://localhost:8000',
          production: false,
        ),
        returnsNormally,
      );
    });

    test('configured production HTTPS URL validates', () {
      expect(
        () => AppConfig.validateOrThrow(
          baseUrl: 'https://api.example.com',
          production: true,
        ),
        returnsNormally,
      );
      expect(
        AppConfig.isHttpsUrl('https://api.example.com'),
        isTrue,
      );
      expect(
        AppConfig.isLocalhostUrl('https://api.example.com'),
        isFalse,
      );
    });

    test('production + localhost is rejected clearly', () {
      expect(
        () => AppConfig.validateOrThrow(
          baseUrl: 'http://localhost:8000',
          production: true,
        ),
        throwsA(isA<StateError>()),
      );
      expect(
        () => AppConfig.validateOrThrow(
          baseUrl: 'http://127.0.0.1:8000',
          production: true,
        ),
        throwsA(isA<StateError>()),
      );
    });

    test('production + plain HTTP is rejected clearly', () {
      expect(
        () => AppConfig.validateOrThrow(
          baseUrl: 'http://api.example.com',
          production: true,
        ),
        throwsA(isA<StateError>()),
      );
    });

    test('production + missing or invalid URL is rejected clearly', () {
      expect(
        () => AppConfig.validateOrThrow(baseUrl: '', production: true),
        throwsA(isA<StateError>()),
      );
      expect(
        () => AppConfig.validateOrThrow(
          baseUrl: 'not-a-url',
          production: true,
        ),
        throwsA(isA<StateError>()),
      );
    });

    test('no real production domain is hardcoded', () {
      // The default must remain the dev loopback — a real backend host
      // is supplied at build time via dart-define, never hardcoded.
      expect(AppConfig.apiBaseUrl, 'http://localhost:8000');
    });

    test('all API clients use the centralized configuration', () {
      final clients = <String, String>{
        'AssistantClient': AssistantClient.baseUrl,
        'AuthClient': AuthClient.baseUrl,
        'DiscoverClient': DiscoverClient.baseUrl,
        'EventsClient': EventsClient.baseUrl,
        'FeedbackClient': FeedbackClient.baseUrl,
        'GroomingClient': GroomingClient.baseUrl,
        'HairstyleClient': HairstyleClient.baseUrl,
        'TodayLookClient': TodayLookClient.baseUrl,
        'KnowledgeClient': KnowledgeClient.baseUrl,
        'LearningSummaryClient': LearningSummaryClient.baseUrl,
        'OutfitClient': OutfitBuilderClient.baseUrl,
        'OutfitScanClient': OutfitScanClient.baseUrl,
        'SavedLooksClient': SavedLooksClient.baseUrl,
        'WardrobeClient': WardrobeClient.baseUrl,
      };
      expect(clients.length, 14);
      for (final entry in clients.entries) {
        expect(
          entry.value,
          AppConfig.apiBaseUrl,
          reason: '${entry.key}.baseUrl must equal AppConfig.apiBaseUrl',
        );
      }
    });
  });
}
