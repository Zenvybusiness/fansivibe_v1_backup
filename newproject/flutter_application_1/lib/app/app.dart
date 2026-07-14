import 'package:flutter/material.dart';
import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';

class FansivibeApp extends StatelessWidget {
  const FansivibeApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'Fansivibe',
      debugShowCheckedModeBanner: false,
      theme: FansivibeTheme.darkTheme,
      routerConfig: appRouter,
    );
  }
}
