import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/pending_auth_intent.dart';

/// Phase 2 guest mode (read-only browsing, no token, no backend writes).
///
/// Mirrors the Phase 1 router's `isGuest` computation
/// (`!isAuthenticated && savedLocally`): explicit guests chose
/// "Continue Without Account" (persisted `savedLocally`, no session
/// token). Tests with injected fakes never set `savedLocally`, so they
/// keep exercising the authenticated backend path.
bool get isGuestUser =>
    !AuthSession.isAuthenticated && LocalStorage.savedLocally;

/// Honest sign-in prompt at the button: tells the user the action needs
/// an account, then routes to account creation. Never fakes a save,
/// analysis, or authentication.
///
/// Conversion behavior (Flow 1B): records a pending-auth intent for the
/// current location (best-effort — a failure here must never break the
/// prompt, so it is swallowed) so post-auth success can return to this
/// origin. Every current call site is class D (return-to-origin +
/// guidance; see `pending_auth_intent.dart`): no guest flow holds a
/// replayable server payload, so nothing is auto-POSTed after login.
/// Guest wardrobe/preferences travel via the explicit Merge/Keep/Discard
/// dialog instead — never silently.
void promptGuestSignIn(BuildContext context, {String? action}) {
  try {
    final path = GoRouterState.of(context).uri.path;
    recordPendingAuthIntent(
      PendingAuthIntent(
        action: action ?? 'save',
        route: path,
        createdAt: DateTime.now(),
      ),
    );
  } catch (_) {
    // No router in scope (tests) or unreadable location: the prompt
    // below still works; post-auth just falls back to /home.
  }
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(
        action ??
            'Sign in to use this feature. Browsing stays free.',
      ),
      backgroundColor: FansivibeColors.accentGold,
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(
        borderRadius: FansivibeRadius.smdBorder,
      ),
    ),
  );
  context.pushNamed(RouteNames.signIn);
}

/// Honest guest placeholder for an account-backed slot: names the slot,
/// says plainly it needs an account, and offers Sign In. No fake data.
class GuestSignInCard extends StatelessWidget {
  const GuestSignInCard({
    required this.title,
    required this.message,
    this.actionLabel = 'Sign In',
    super.key,
  });

  final String title;
  final String message;
  final String actionLabel;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return FansivibeCard(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: FansivibeColors.accentGold.withValues(alpha: 0.12),
                  borderRadius: FansivibeRadius.smBorder,
                ),
                child: const Icon(
                  Icons.lock_outline_rounded,
                  color: FansivibeColors.accentGold,
                  size: 20,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  title,
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: FansivibeColors.textPrimary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            message,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: FansivibeColors.textSecondary,
            ),
          ),
          const SizedBox(height: 16),
          FansiButton.primary(
            label: actionLabel,
            icon: Icons.login_rounded,
            onPressed: () => promptGuestSignIn(context),
          ),
        ],
      ),
    );
  }
}

/// Feature keys for the pending ephemeral result slot (D-01).
///
/// Only pipelines whose guest save crosses the account boundary stash a
/// result (hairstyle/outfit/grooming). Garment saves persist device-local
/// through `LocalWardrobeRepository`, so garment stashes nothing.
class EphemeralFeature {
  EphemeralFeature._();

  static const hairstyle = 'hairstyle';
  static const outfit = 'outfit';
  static const grooming = 'grooming';
}

/// Stashes one guest analysis snapshot for a later Save → sign-in replay.
///
/// Written at guest analysis time (last analysis wins, mirroring the
/// single-slot `PendingAuthIntent` design). The transient `sourceRunId`
/// correlation id is stripped (top level + `appearance` sub-map) so a
/// restored snapshot can never carry a nonexistent run id into an
/// FK-backed save. Device-local only; failures never break analysis.
void stashPendingEphemeralResult({
  required String feature,
  required Map<String, dynamic> snapshot,
}) {
  try {
    final clean = Map<String, dynamic>.from(snapshot)..remove('sourceRunId');
    final appearance = clean['appearance'];
    if (appearance is Map<String, dynamic>) {
      clean['appearance'] = Map<String, dynamic>.from(appearance)
        ..remove('sourceRunId');
    }
    LocalStorage.pendingEphemeralResult = jsonEncode({
      'feature': feature,
      'snapshot': clean,
      'savedAt': DateTime.now().toIso8601String(),
    });
  } catch (_) {
    // Stash must never break the analysis flow itself.
  }
}

/// Reads (without consuming) the stashed guest result, or null when
/// absent, malformed, or older than 24h (stale slots fail closed to null
/// and are cleared, mirroring `PendingAuthIntent` expiry).
({String feature, Map<String, dynamic> snapshot})?
peekPendingEphemeralResult() {
  final raw = LocalStorage.pendingEphemeralResult;
  if (raw == null || raw.isEmpty) return null;
  try {
    final decoded = jsonDecode(raw);
    if (decoded is! Map<String, dynamic>) return null;
    final feature = decoded['feature'];
    final snapshot = decoded['snapshot'];
    final savedAt = decoded['savedAt'];
    if (feature is! String ||
        snapshot is! Map<String, dynamic> ||
        savedAt is! String) {
      return null;
    }
    if (DateTime.now().difference(DateTime.parse(savedAt)) >
        const Duration(hours: 24)) {
      LocalStorage.pendingEphemeralResult = null;
      return null;
    }
    return (
      feature: feature,
      snapshot: Map<String, dynamic>.from(snapshot),
    );
  } catch (_) {
    return null;
  }
}

/// Drops the stashed guest result (after a completed save, an explicit
/// dismiss, or a superseding analysis).
void clearPendingEphemeralResult() {
  LocalStorage.pendingEphemeralResult = null;
}

/// Resume banner for a stashed guest analysis result (D-01).
///
/// Rendered by the feature origin screen when [peekPendingEphemeralResult]
/// holds its feature: an explicit View action restores the exact result
/// for replay (class-D: nothing auto-POSTs), Dismiss clears the slot.
/// Reuses the Digital Atelier card/button components only.
class PendingEphemeralResultBanner extends StatelessWidget {
  const PendingEphemeralResultBanner({
    required this.title,
    required this.message,
    required this.onView,
    required this.onDismiss,
    super.key,
  });

  final String title;
  final String message;
  final VoidCallback onView;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return FansivibeCard(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: FansivibeColors.accentGold.withValues(alpha: 0.12),
                  borderRadius: FansivibeRadius.smBorder,
                ),
                child: const Icon(
                  Icons.history_rounded,
                  color: FansivibeColors.accentGold,
                  size: 20,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  title,
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: FansivibeColors.textPrimary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            message,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: FansivibeColors.textSecondary,
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: FansiButton.primary(
                  label: 'View Result',
                  icon: Icons.visibility_outlined,
                  onPressed: onView,
                ),
              ),
              const SizedBox(width: 12),
              FansiButton.tertiary(label: 'Dismiss', onPressed: onDismiss),
            ],
          ),
        ],
      ),
    );
  }
}
