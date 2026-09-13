import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';

@pragma('vm:entry-point')
class FansivibeApp extends StatelessWidget {
  const FansivibeApp({super.key, this.router});

  final GoRouter? router;

  @override
  Widget build(BuildContext context) {
    // D-AUTH-1: any authenticated client that receives a 401 clears the
    // dead session and lands back on entry (sign-in). The session token
    // itself restores from platform storage via LocalStorage, so a
    // relaunch resumes the account until the server rejects it.
    AuthSession.onSessionExpired = () {
      (router ?? appRouter).goNamed(RouteNames.entry);
    };
    // P0-3: persistent auth/onboarding state is initialized in main()
    // (SharedPreferences + LocalStorage) BEFORE runApp(), so EntryScreen
    // evaluates the restored session on cold start. No lazy/post-frame
    // init here — no duplicate initialization, no startup race.

    return MaterialApp.router(
      title: 'Fansivibe',
      debugShowCheckedModeBanner: false,
      theme: FansivibeTheme.darkTheme,
      routerConfig: router ?? appRouter,
    );
  }
}