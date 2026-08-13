import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

@pragma('vm:entry-point')
class FansivibeApp extends StatelessWidget {
  const FansivibeApp({super.key, this.router});

  final GoRouter? router;

  @override
  Widget build(BuildContext context) {
    // Initialize local storage early via post-frame callback
    // SharedPreferences.getInstance() is async, so we use addPostFrameCallback
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final prefs = await SharedPreferences.getInstance();
      LocalStorage.init(prefs: prefs);
    });

    return MaterialApp.router(
      title: 'Fansivibe',
      debugShowCheckedModeBanner: false,
      theme: FansivibeTheme.darkTheme,
      routerConfig: router ?? appRouter,
    );
  }
}