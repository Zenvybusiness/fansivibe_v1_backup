import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// Standard tonal image well used as the hero placeholder inside card
/// families when no real photo is available yet.
///
/// The well is a colour-tinted gradient with a centred category icon and an
/// optional label. It is the "image" slot of the card system — the image is
/// always the hero, so the well fills the full image area of its card.
class FansiImageWell extends StatelessWidget {
  const FansiImageWell({
    required this.icon,
    required this.color,
    this.label,
    this.iconSize = 48,
    this.showLabel = true,
    super.key,
  });

  /// Category / product icon shown in the centre of the well.
  final IconData icon;

  /// Tint used for the gradient and icon.
  final Color color;

  /// Optional label under the icon (e.g. "Outfit Image").
  final String? label;

  /// Size of the central icon.
  final double iconSize;

  /// Whether to render [label] under the icon.
  final bool showLabel;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            color.withValues(alpha: 0.22),
            color.withValues(alpha: 0.38),
          ],
        ),
      ),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: iconSize, color: color.withValues(alpha: 0.6)),
            if (showLabel && label != null) ...[
              const SizedBox(height: 8),
              Text(
                label!,
                textAlign: TextAlign.center,
                style: FansivibeTypography.labelSmallWithFamily.copyWith(
                  color: FansivibeColors.secondary,
                  letterSpacing: 0.4,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
