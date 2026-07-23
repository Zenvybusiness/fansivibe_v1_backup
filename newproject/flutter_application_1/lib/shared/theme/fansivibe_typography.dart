import 'package:flutter/material.dart';
import 'fansivibe_colors.dart';

/// Typography tokens following the Digital Atelier editorial system.
///
/// Pairing: Noto Serif (editorial headings) + Inter (functional text).
/// Font files must be added under assets/fonts/ and declared in pubspec.yaml.
///
/// Fallback: system serif / sans-serif until custom fonts are bundled.
abstract final class FansivibeTypography {
  FansivibeTypography._();

  // ── Font families (swap strings when fonts are bundled) ──
  static const String displayFamily = 'Noto Serif';
  static const String textFamily = 'Inter';
  static const String _displayFallback = 'serif';
  static const String _textFallback = 'sans-serif';

  static String get _display => displayFamily;
  static String get _text => textFamily;

  // ── Text styles ──

  /// Editorial hero / statements – 56 px, w400.
  static const TextStyle displayLarge = TextStyle(
    fontFamily: _displayFallback,
    fontSize: 56,
    fontWeight: FontWeight.w400,
    color: FansivibeColors.onSurface,
  );

  /// Section headers – 28 px, w500.
  static const TextStyle headlineMedium = TextStyle(
    fontFamily: _displayFallback,
    fontSize: 28,
    fontWeight: FontWeight.w500,
    color: FansivibeColors.onSurface,
  );

  /// Card titles / nav – 22 px, w600.
  static const TextStyle titleLarge = TextStyle(
    fontFamily: _textFallback,
    fontSize: 22,
    fontWeight: FontWeight.w600,
    color: FansivibeColors.onSurface,
  );

  /// General reading – 16 px, w400.
  static const TextStyle bodyLarge = TextStyle(
    fontFamily: _textFallback,
    fontSize: 16,
    fontWeight: FontWeight.w400,
    color: FansivibeColors.onSurface,
  );

  /// Metadata / all-caps tags – 12 px, w500, +10% letter-spacing.
  static const TextStyle labelMedium = TextStyle(
    fontFamily: _textFallback,
    fontSize: 12,
    fontWeight: FontWeight.w500,
    color: FansivibeColors.secondary,
    letterSpacing: 1.2,
  );

  /// Small metadata – 10 px, w500.
  static const TextStyle labelSmall = TextStyle(
    fontFamily: _textFallback,
    fontSize: 10,
    fontWeight: FontWeight.w500,
    color: FansivibeColors.secondary,
  );

  /// Body secondary – 14 px, w400, muted colour.
  static const TextStyle bodyMedium = TextStyle(
    fontFamily: _textFallback,
    fontSize: 14,
    fontWeight: FontWeight.w400,
    color: FansivibeColors.secondary,
  );

  // ── Shortcut extensions ──

  static TextStyle displayLargeWithFamily = displayLarge.copyWith(
    fontFamily: _display,
  );
  static TextStyle headlineMediumWithFamily = headlineMedium.copyWith(
    fontFamily: _display,
  );
  static TextStyle titleLargeWithFamily = titleLarge.copyWith(
    fontFamily: _text,
  );
  static TextStyle bodyLargeWithFamily = bodyLarge.copyWith(fontFamily: _text);
  static TextStyle labelMediumWithFamily = labelMedium.copyWith(
    fontFamily: _text,
  );
  static TextStyle labelSmallWithFamily = labelSmall.copyWith(
    fontFamily: _text,
  );
  static TextStyle bodyMediumWithFamily = bodyMedium.copyWith(
    fontFamily: _text,
  );
}
