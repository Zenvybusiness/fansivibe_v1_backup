import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

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
    // Initialize local storage fallback if not already initialized before runApp
    if (!LocalStorage.isInitialized) {
      WidgetsBinding.instance.addPostFrameCallback((_) async {
        if (!LocalStorage.isInitialized) {
          final prefs = await SharedPreferences.getInstance();
          LocalStorage.init(prefs: prefs);
        }
      });
    }


    return MaterialApp.router(
      title: 'Fansivibe',
      debugShowCheckedModeBanner: false,
      theme: FansivibeTheme.darkTheme,
      routerConfig: router ?? appRouter,
    );
  }
}