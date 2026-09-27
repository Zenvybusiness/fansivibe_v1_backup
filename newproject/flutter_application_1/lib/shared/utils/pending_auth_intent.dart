import 'dart:convert';

import 'package:fansivibe/shared/utils/local_storage.dart';

/// Pending authenticated-action intent (guest → auth conversion).
///
/// Single-slot, LocalStorage-backed mechanism — no database, no new
/// persistence architecture. When a guest hits an account-required action,
/// [promptGuestSignIn] records where they came from; the post-auth success
/// handlers consume it once and return there (falling back to `/home`).
///
/// Gate classification (audited, Flow 1B):
/// - A (auto-resume): NOTHING today. No guest flow holds a replayable
///   server payload (analysis submits are gated before any run exists;
///   wardrobe/prefs go through explicit migration instead). Auto-POSTing
///   would fabricate saves.
/// - B (form restore): event forms hold typed input in screen state that
///   dies on navigation and is not serializable — not restorable without
///   a form-persistence layer (deferred, documented).
/// - C (explicit confirmation): guest wardrobe + preferences, handled by
///   the Merge/Keep/Discard dialog in the auth feature (never silent).
/// - D (return to origin + guidance): EVERY current gate. The user lands
///   back where they tapped Save with a "tap Save again" hint and
///   replays explicitly — no duplicate POST, no fake success.
class PendingAuthIntent {
  const PendingAuthIntent({
    required this.action,
    required this.route,
    this.params = const {},
    required this.createdAt,
  });

  /// Short machine label for the gated action (`save`, `save_progress`,
  /// `browse`). Shown back to the user only via the fixed guidance copy
  /// in the post-auth flow — never executed or POSTed automatically.
  final String action;

  /// Concrete location path where the gate fired (e.g. `/stylist`).
  /// Query strings are never stored ([recordPendingAuthIntent] keeps
  /// `uri.path` only).
  final String route;

  /// String-only extras for future use. Never carries images, tokens, or
  /// non-serializable objects (those die with their screens by design).
  final Map<String, String> params;

  final DateTime createdAt;

  /// Stale intents (older than 24h, e.g. abandoned sign-in) are treated
  /// as absent so a days-old tap cannot yank the user somewhere odd.
  bool get isExpired =>
      DateTime.now().difference(createdAt) > const Duration(hours: 24);

  Map<String, dynamic> toJson() => {
    'action': action,
    'route': route,
    'params': params,
    'createdAt': createdAt.toIso8601String(),
  };

  /// Null on any malformed input (missing keys, wrong types, bad date) —
  /// a poisoned slot fails closed to "no intent".
  static PendingAuthIntent? fromJson(Map<String, dynamic> json) {
    try {
      final action = json['action'];
      final route = json['route'];
      final createdAt = json['createdAt'];
      if (action is! String ||
          action.isEmpty ||
          route is! String ||
          route.isEmpty ||
          createdAt is! String) {
        return null;
      }
      final params = <String, String>{};
      final rawParams = json['params'];
      if (rawParams is Map) {
        for (final entry in rawParams.entries) {
          if (entry.key is String && entry.value is String) {
            params[entry.key as String] = entry.value as String;
          }
        }
      }
      return PendingAuthIntent(
        action: action,
        route: route,
        params: params,
        createdAt: DateTime.parse(createdAt),
      );
    } catch (_) {
      return null;
    }
  }
}

/// Records (overwrites) the single pending intent. Last gate wins.
void recordPendingAuthIntent(PendingAuthIntent intent) {
  try {
    LocalStorage.pendingAuthIntent = jsonEncode(intent.toJson());
  } catch (_) {
    // Intent capture must never break the sign-in prompt itself.
  }
}

/// Reads and clears the slot (single-use). Returns null when absent,
/// malformed (slot cleared to avoid poisoning), or expired.
PendingAuthIntent? takePendingAuthIntent() {
  final raw = LocalStorage.pendingAuthIntent;
  LocalStorage.pendingAuthIntent = null;
  if (raw == null || raw.isEmpty) return null;
  try {
    final decoded = jsonDecode(raw);
    if (decoded is! Map<String, dynamic>) return null;
    final intent = PendingAuthIntent.fromJson(decoded);
    if (intent == null || intent.isExpired) return null;
    return intent;
  } catch (_) {
    return null;
  }
}

/// Resolves where post-auth success navigates.
///
/// Only routes renderable without caller-held objects are allowed (see
/// the class doc): exact safe paths pass through, deeper paths walk up
/// to their nearest safe parent (e.g. `/discover/look-details` needs a
/// `lookId` extra → `/discover`), auth-looping paths (`/sign-in`,
/// `/create-account`) and anything unknown fall back to `/home` —
/// preserving today's default when no intent exists (null → `/home`).
String resolvePostAuthDestination(PendingAuthIntent? intent) {
  const home = '/home';
  if (intent == null) return home;
  var candidate = intent.route.trim();
  if (!candidate.startsWith('/')) return home;
  // Auth screens must never be a "return" destination (infinite loop).
  if (candidate == '/sign-in' ||
      candidate == '/create-account' ||
      candidate.startsWith('/sign-in/') ||
      candidate.startsWith('/create-account/')) {
    return home;
  }
  if (_safePostAuthRoutes.contains(candidate)) return candidate;
  // Walk up to the nearest safe parent.
  final segments =
      candidate.split('/').where((s) => s.isNotEmpty).toList();
  while (segments.length > 1) {
    segments.removeLast();
    candidate = '/${segments.join('/')}';
    if (_safePostAuthRoutes.contains(candidate)) return candidate;
  }
  if (segments.length == 1 && _safePostAuthRoutes.contains('/${segments.first}')) {
    return '/${segments.first}';
  }
  return home;
}

/// Shell roots + first-level screens whose builders need no caller-held
/// `extra` (nullable-extra builders verified in `app_router.dart`).
/// Onboarding paths are deliberately absent: post-auth users belong in
/// the product shell, so they resolve to `/home` below.
const _safePostAuthRoutes = {
  '/home',
  '/home/daily-outfit',
  '/discover',
  '/stylist',
  '/stylist/scan-outfit',
  '/stylist/build-outfit',
  '/stylist/hairstyle',
  '/stylist/grooming',
  '/stylist/events',
  '/wardrobe',
  '/wardrobe/add-category',
  '/profile',
  '/profile/preferences',
  '/profile/saved-looks',
  '/profile/subscription',
  '/profile/support',
  '/profile/settings',
  '/assistant',
  '/entry',
};
