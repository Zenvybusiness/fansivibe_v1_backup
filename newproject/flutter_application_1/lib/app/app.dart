import 'package:flutter/material.dart';
import '../shared/theme/fansivibe_theme.dart';
import 'main_shell.dart';

/// The root widget of the Fansivibe application.
class FansivibeApp extends StatelessWidget {
  /// Creates a [FansivibeApp].
  const FansivibeApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Fansivibe',
      debugShowCheckedModeBanner: false,
      theme: FansivibeTheme.darkTheme,
      home: const MainShell(),
    );
  }
}
