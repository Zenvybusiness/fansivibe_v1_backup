import 'package:flutter/material.dart';
import 'fansivibe_colors.dart';
import 'fansivibe_radius.dart';
import 'fansivibe_typography.dart';

abstract final class FansivibeTheme {
  FansivibeTheme._();

  static ThemeData get darkTheme {
    final colorScheme = ColorScheme.dark(
      primary: FansivibeColors.primary,
      onPrimary: FansivibeColors.onPrimary,
      primaryContainer: FansivibeColors.primaryContainer,
      surface: FansivibeColors.surface,
      onSurface: FansivibeColors.onSurface,
      secondary: FansivibeColors.secondary,
      error: FansivibeColors.error,
      outlineVariant: FansivibeColors.outlineVariant,
    );

    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: colorScheme,
      primaryColor: FansivibeColors.primary,
      scaffoldBackgroundColor: FansivibeColors.surface,
      cardColor: FansivibeColors.surfaceContainer,

      appBarTheme: AppBarTheme(
        backgroundColor: FansivibeColors.surface,
        surfaceTintColor: FansivibeColors.surface,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: true,
        titleTextStyle: FansivibeTypography.titleLargeWithFamily,
        iconTheme: const IconThemeData(color: FansivibeColors.onSurface),
      ),

      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: FansivibeColors.surfaceContainerHigh,
        indicatorColor: FansivibeColors.primary.withValues(alpha: 0.2),
        surfaceTintColor: FansivibeColors.surface,
        elevation: 0,
        labelTextStyle: WidgetStatePropertyAll(
          FansivibeTypography.labelSmallWithFamily,
        ),
        iconTheme: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return const IconThemeData(
              color: FansivibeColors.primary,
              size: 24,
            );
          }
          return const IconThemeData(
            color: FansivibeColors.secondary,
            size: 24,
          );
        }),
      ),

      textTheme: const TextTheme(
        displayLarge: FansivibeTypography.displayLarge,
        headlineMedium: FansivibeTypography.headlineMedium,
        titleLarge: FansivibeTypography.titleLarge,
        bodyLarge: FansivibeTypography.bodyLarge,
        bodyMedium: FansivibeTypography.bodyMedium,
        labelMedium: FansivibeTypography.labelMedium,
        labelSmall: FansivibeTypography.labelSmall,
      ),

      dividerColor: Colors.transparent,

      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: FansivibeColors.primary,
          foregroundColor: FansivibeColors.onPrimary,
          disabledBackgroundColor: FansivibeColors.primary.withValues(
            alpha: 0.3,
          ),
          disabledForegroundColor: FansivibeColors.secondary.withValues(
            alpha: 0.5,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: FansivibeRadius.fullBorder,
          ),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          textStyle: FansivibeTypography.bodyLargeWithFamily.copyWith(
            fontWeight: FontWeight.w600,
          ),
        ),
      ),

      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: FansivibeColors.primary,
          side: BorderSide(
            color: FansivibeColors.primary.withValues(alpha: 0.4),
          ),
          shape: RoundedRectangleBorder(
            borderRadius: FansivibeRadius.fullBorder,
          ),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          textStyle: FansivibeTypography.bodyLargeWithFamily.copyWith(
            fontWeight: FontWeight.w600,
          ),
        ),
      ),

      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: FansivibeColors.primary,
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          textStyle: FansivibeTypography.labelMediumWithFamily.copyWith(
            color: FansivibeColors.primary,
          ),
        ),
      ),

      inputDecorationTheme: InputDecorationTheme(
        filled: false,
        fillColor: Colors.transparent,
        contentPadding: const EdgeInsets.symmetric(vertical: 14, horizontal: 4),
        hintStyle: FansivibeTypography.bodyLargeWithFamily.copyWith(
          color: FansivibeColors.secondary.withValues(alpha: 0.5),
        ),
        labelStyle: FansivibeTypography.bodyLargeWithFamily.copyWith(
          color: FansivibeColors.secondary,
        ),
        border: const UnderlineInputBorder(
          borderSide: BorderSide(color: FansivibeColors.outlineVariant),
        ),
        enabledBorder: const UnderlineInputBorder(
          borderSide: BorderSide(color: FansivibeColors.outlineVariant),
        ),
        focusedBorder: UnderlineInputBorder(
          borderSide: const BorderSide(
            color: FansivibeColors.primary,
            width: 2,
          ),
        ),
        errorBorder: UnderlineInputBorder(
          borderSide: BorderSide(
            color: FansivibeColors.error.withValues(alpha: 0.6),
          ),
        ),
        focusedErrorBorder: UnderlineInputBorder(
          borderSide: BorderSide(color: FansivibeColors.error, width: 2),
        ),
      ),

      snackBarTheme: SnackBarThemeData(
        backgroundColor: FansivibeColors.surfaceContainerHighest,
        contentTextStyle: FansivibeTypography.bodyLargeWithFamily,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.mdBorder),
      ),
    );
  }
}
