import 'package:flutter/material.dart';
import 'fansivibe_colors.dart';

/// Design system theme definition for Fansivibe.
///
/// Configures a cohesive dark theme using design system colors and fonts.
abstract final class FansivibeTheme {
  /// The official dark theme configuration for Fansivibe.
  static ThemeData get darkTheme {
    return ThemeData(
      brightness: Brightness.dark,
      primaryColor: FansivibeColors.accentGold,
      scaffoldBackgroundColor: FansivibeColors.background,
      cardColor: FansivibeColors.surface,
      colorScheme: const ColorScheme.dark(
        primary: FansivibeColors.accentGold,
        secondary: FansivibeColors.accentGold,
        surface: FansivibeColors.surface,
        error: Colors.redAccent,
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: FansivibeColors.background,
        elevation: 0,
        centerTitle: true,
        titleTextStyle: TextStyle(
          fontFamily: 'serif',
          fontSize: 20,
          fontWeight: FontWeight.bold,
          color: FansivibeColors.textPrimary,
        ),
      ),
      textTheme: const TextTheme(
        displayLarge: TextStyle(
          fontFamily: 'serif',
          fontSize: 32,
          fontWeight: FontWeight.bold,
          color: FansivibeColors.textPrimary,
        ),
        headlineMedium: TextStyle(
          fontFamily: 'serif',
          fontSize: 24,
          fontWeight: FontWeight.w600,
          color: FansivibeColors.textPrimary,
        ),
        bodyLarge: TextStyle(
          fontFamily: 'sans-serif',
          fontSize: 16,
          color: FansivibeColors.textPrimary,
        ),
        bodyMedium: TextStyle(
          fontFamily: 'sans-serif',
          fontSize: 14,
          color: FansivibeColors.textSecondary,
        ),
      ),
    );
  }
}
