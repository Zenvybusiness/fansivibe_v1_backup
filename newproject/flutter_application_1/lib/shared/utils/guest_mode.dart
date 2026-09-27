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
