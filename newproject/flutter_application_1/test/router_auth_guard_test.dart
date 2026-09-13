import 'package:flutter_test/flutter_test.dart';

import 'package:fansivibe/app/router/auth_guard.dart';

/// 21.2 (M1) — declarative router auth guard.
///
/// Pure-function matrix: no widgets, no network, no storage I/O.
/// Widget-level cold-start behavior stays covered by
/// `app_cold_start_test.dart` (which builds its own guard-free router
/// from `appRoutes`, so this guard cannot break it).
void main() {
  group('unauthenticated', () {
    test('public flows stay reachable', () {
      for (final location in [
        '/splash',
        '/entry',
        '/onboarding/vibe',
        '/onboarding/camera-permission',
        '/onboarding/photo-capture',
        '/onboarding/analysis',
        '/onboarding/result',
        '/onboarding/account',
        '/assistant',
      ]) {
        expect(
          authRedirect(location, isAuthenticated: false),
          isNull,
          reason: location,
        );
      }
    });

    test('shell routes redirect to entry', () {
      for (final location in [
        '/home',
        '/home/daily-outfit',
        '/discover',
        '/discover/look-details',
        '/stylist',
        '/stylist/scan-outfit',
        '/stylist/build-outfit/generation',
        '/stylist/hairstyle/processing/result',
        '/stylist/grooming/processing/result/details',
        '/stylist/events/add',
        '/wardrobe',
        '/wardrobe/add-item',
        '/wardrobe/item-details',
        '/profile',
        '/profile/preferences',
        '/profile/saved-looks',
        '/profile/subscription',
        '/profile/support',
        '/profile/settings',
      ]) {
        expect(
          authRedirect(location, isAuthenticated: false),
          '/entry',
          reason: location,
        );
      }
    });

    test('unknown paths are left alone (no invented destinations)', () {
      expect(
        authRedirect('/nope', isAuthenticated: false),
        isNull,
      );
    });
  });

  group('authenticated', () {
    test('never forced away from any route (no loops)', () {
      for (final location in [
        '/entry',
        '/splash',
        '/onboarding/account',
        '/assistant',
        '/home',
        '/discover',
        '/stylist/scan-outfit',
        '/wardrobe',
        '/profile/settings',
        '/nope',
      ]) {
        expect(
          authRedirect(location, isAuthenticated: true),
          isNull,
          reason: location,
        );
      }
    });
  });
}
