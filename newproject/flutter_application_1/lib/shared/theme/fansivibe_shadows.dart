import 'package:flutter/material.dart';
import 'fansivibe_colors.dart';

/// Shadow tokens for the Fansivibe design system.
///
/// Cards on the background must NOT use shadows – use tonal shifts instead
/// (see FansivibeColors surface-container-* hierarchy).
///
/// Shadows are reserved for truly floating elements (modals, FABs, sheets).
abstract final class FansivibeShadows {
  FansivibeShadows._();

  /// Extra-diffused ambient shadow for floating overlays.
  ///
  /// Value: 0px 24px 48px, tinted with the background colour.
  static List<BoxShadow> get ambient => [
    BoxShadow(
      color: FansivibeColors.surface.withValues(alpha: 0.7),
      blurRadius: 48,
      offset: const Offset(0, 24),
    ),
  ];
}
