import 'package:flutter/material.dart';

abstract final class FansivibeColors {
  FansivibeColors._();

  // ── Base layers ──
  static const Color surface = Color(0xFF131313);
  static const Color surfaceContainerLowest = Color(0xFF0E0E0E);

  // ── Section / card layers ──
  static const Color surfaceContainerLow = Color(0xFF1C1B1B);
  static const Color surfaceContainer = Color(0xFF201F1F);
  static const Color surfaceContainerHigh = Color(0xFF2A2A2A);
  static const Color surfaceContainerHighest = Color(0xFF353534);

  // ── Brand palette ──
  static const Color primary = Color(0xFFE3C373);
  static const Color primaryContainer = Color(0xFFC6A85B);
  static const Color onPrimary = Color(0xFF3E2E00);

  // ── Text ──
  static const Color onSurface = Color(0xFFE5E2E1);
  static const Color secondary = Color(0xFFC6C6CB);

  // ── Utility ──
  static const Color outlineVariant = Color(0xFF4C4638);

  // ── Semantic ──
  static const Color success = Color(0xFF4CAF50);
  static const Color warning = Color(0xFFFF9800);
  static const Color error = Color(0xFFF44336);

  // ── Legacy aliases (kept for backward compatibility; prefer new names) ──
  static const Color accentGold = primary;
  static const Color textPrimary = onSurface;
  static const Color textSecondary = secondary;
  static const Color background = surface;
}
