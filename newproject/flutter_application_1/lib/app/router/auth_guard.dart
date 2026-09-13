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
String? authRedirect(String location, {required bool isAuthenticated}) {
  if (isAuthenticated) return null;
  if (_isPublic(location)) return null;
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
