import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

/// A tonal card that uses background colour shifts instead of borders or
/// drop shadows to define its boundary against the parent surface.
///
/// - [variant] selects the surface-container tier (default = `container`).
/// - [onTap] promotes the card to `container-high` on press.
/// - No borders and no shadows (per the "No-Line" and tonal-layering rules).
///
/// [borderColor] is accepted for backward compatibility but NOT rendered.
class FansivibeCard extends StatelessWidget {
  const FansivibeCard({
    required this.child,
    this.variant = CardVariant.container,
    this.padding = const EdgeInsets.all(20),
    this.margin = EdgeInsets.zero,
    this.onTap,
    // ignore: unused_element
    this.borderColor,
    super.key,
  });

  final Widget child;
  final CardVariant variant;
  final EdgeInsetsGeometry padding;
  final EdgeInsetsGeometry margin;
  final VoidCallback? onTap;
  final Color? borderColor;

  @override
  Widget build(BuildContext context) {
    final bgColor = switch (variant) {
      CardVariant.low => FansivibeColors.surfaceContainerLow,
      CardVariant.container => FansivibeColors.surfaceContainer,
      CardVariant.high => FansivibeColors.surfaceContainerHigh,
      CardVariant.highest => FansivibeColors.surfaceContainerHighest,
    };

    Widget card = Container(
      margin: margin,
      padding: padding,
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: FansivibeRadius.mdBorder,
      ),
      child: child,
    );

    if (onTap != null) {
      card = Semantics(
        button: true,
        child: InkWell(
          onTap: onTap,
          borderRadius: FansivibeRadius.mdBorder,
          splashColor: FansivibeColors.primary.withValues(alpha: 0.08),
          highlightColor: FansivibeColors.primary.withValues(alpha: 0.04),
          child: card,
        ),
      );
    }

    return card;
  }
}

enum CardVariant { low, container, high, highest }
