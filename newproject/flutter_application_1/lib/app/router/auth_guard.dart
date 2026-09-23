/// Declarative router authentication guard (21.2, M1).
///
/// Pure redirect decision — no network, no storage I/O on navigation:
/// the caller passes the already-known [AuthSession.isAuthenticated]
/// value, so every navigation stays synchronous and offline-safe.
///
/// Contract (deliberately one-directional to avoid redirect loops):
/// - Unauthenticated navigation to an authenticated route
///   (`/home`, `/discover`, `/stylist`, `/wardrobe`, `/profile` and any
///   nested path beneath them) redirects to `/entry`.
/// - Explicit guests (chose "Continue Without Account", persisted as
///   `savedLocally` with no session token) may browse the whole shell:
///   all 5 tabs plus their nested read screens (Phase 1 guest scope).
///   Account-required writes (analysis submit, saves, wears, event
///   mutations, preference sync, feedback) are gated at their buttons,
///   not here. Guest access mints no token and bypasses no backend
///   auth: authenticated API clients keep resolving tokens through
///   `AuthSession` and 401 honestly.
/// - Guests stay blocked from `/assistant` and `/reasoning` (redirect to
///   `/entry`), even though `/assistant` is public for everyone else.
/// - Authenticated users are NEVER forced away from public routes: entry,
///   onboarding, login/register, and `/assistant` (frozen-public chat)
///   stay reachable so onboarding, Maybe-Later, and sign-in flows keep
///   working, including cold start (EntryScreen performs its own
///   returning-user hop to home after the launch animation).
/// - Unknown paths return null (error handling owns them; the guard
///   invents no destinations).
///
/// Reactivity note: the guard re-evaluates on every navigation. Login,
/// logout, and session-expiry already navigate explicitly (`goNamed`),
/// so no `refreshListenable` is attached — `AuthSession` is static state
/// and a listenable would only add rebuild churn for zero new coverage.
String? authRedirect(
  String location, {
  required bool isAuthenticated,
  bool isGuest = false,
}) {
  if (isAuthenticated) return null;
  // Phase 1 guest scope: reasoning + assistant stay blocked for guests
  // (checked before the public list, since /assistant is public for
  // everyone else).
  if (isGuest && _isGuestBlocked(location)) return '/entry';
  if (_isPublic(location)) return null;
  // Guests may browse the whole shell (all 5 tabs + nested read
  // screens). Account-required writes stay gated at their buttons.
  if (isGuest && _isGuestSafe(location)) return null;
  if (_isAuthenticatedRoute(location)) return '/entry';
  return null;
}

/// Public flows: launch, entry, all onboarding steps, account
/// creation/login, and the (optionally-authenticated) assistant chat.
bool _isPublic(String location) {
  if (location == '/splash' || location == '/entry') return true;
  if (location == '/onboarding/account') return true;
  if (location.startsWith('/onboarding/') || location == '/onboarding') {
    return true;
  }
  if (location == '/assistant') return true;
  return false;
}

/// Routes that stay blocked for explicit guests (Phase 1): the assistant
/// chat and the reasoning screen. Both bundle account-only actions and
/// shared model budget, so guests are sent back to `/entry`.
bool _isGuestBlocked(String location) {
  return location == '/assistant' ||
      location.startsWith('/assistant/') ||
      location == '/reasoning' ||
      location.startsWith('/reasoning/');
}

/// Shell routes a guest may browse (Phase 1 guest scope).
///
/// Deliberately identical to [_isAuthenticatedRoute]: every nested route
/// in `appRoutes` under the 5 tabs is a guest-safe read screen
/// (home/daily-outfit, discover/look-details, all stylist flows,
/// all wardrobe flows, all profile flows — verified against
/// `app_router.dart`). Writes stay gated at their buttons, not here.
bool _isGuestSafe(String location) => _isAuthenticatedRoute(location);

/// Shell branches that require a session (including nested routes).
bool _isAuthenticatedRoute(String location) {
  return location == '/home' ||
      location.startsWith('/home/') ||
      location == '/discover' ||
      location.startsWith('/discover/') ||
      location == '/stylist' ||
      location.startsWith('/stylist/') ||
      location == '/wardrobe' ||
      location.startsWith('/wardrobe/') ||
      location == '/profile' ||
      location.startsWith('/profile/');
}
