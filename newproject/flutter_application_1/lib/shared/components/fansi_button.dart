import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// Three button variants defined in the Digital Atelier design system.
///
/// | Variant  | Background              | Text colour | Radius | When |
/// |----------|-------------------------|-------------|--------|------|
/// | primary  | `primary` (gold)        | `onPrimary` | full   | main CTA |
/// | secondary| `surface-container-high` | `onSurface` | full   | alternatives |
/// | tertiary | none (text only)        | `primary`   | n/a    | editorial links |
class FansiButton extends StatelessWidget {
  const FansiButton.primary({
    required this.label,
    this.icon,
    this.onPressed,
    this.expanded = true,
    super.key,
  }) : variant = FansiButtonVariant.primary;

  const FansiButton.secondary({
    required this.label,
    this.icon,
    this.onPressed,
    this.expanded = true,
    super.key,
  }) : variant = FansiButtonVariant.secondary;

  const FansiButton.tertiary({required this.label, this.onPressed, super.key})
    : variant = FansiButtonVariant.tertiary,
      icon = null,
      expanded = false;

  final FansiButtonVariant variant;
  final String label;
  final IconData? icon;
  final VoidCallback? onPressed;
  final bool expanded;

  @override
  Widget build(BuildContext context) {
    final Widget button = switch (variant) {
      FansiButtonVariant.primary => _primary(context),
      FansiButtonVariant.secondary => _secondary(context),
      FansiButtonVariant.tertiary => _tertiary(context),
    };

    if (expanded) {
      return SizedBox(width: double.infinity, child: button);
    }
    return button;
  }

  Widget _primary(BuildContext context) {
    return FilledButton.icon(
      onPressed: onPressed,
      icon: icon != null ? Icon(icon, size: 18) : const SizedBox.shrink(),
      label: Text(label),
    );
  }

  Widget _secondary(BuildContext context) {
    final theme = Theme.of(context);
    return FilledButton.icon(
      onPressed: onPressed,
      icon: icon != null ? Icon(icon, size: 18) : const SizedBox.shrink(),
      label: Text(label),
      style: FilledButton.styleFrom(
        backgroundColor: FansivibeColors.surfaceContainerHigh,
        foregroundColor: FansivibeColors.onSurface,
        disabledBackgroundColor: FansivibeColors.surfaceContainerHigh
            .withValues(alpha: 0.4),
        disabledForegroundColor: FansivibeColors.secondary.withValues(
          alpha: 0.5,
        ),
        shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.fullBorder),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
        textStyle: theme.textTheme.bodyLarge?.copyWith(
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }

  Widget _tertiary(BuildContext context) {
    return GestureDetector(
      onTap: onPressed,
      child: Text(
        label,
        style: FansivibeTypography.labelMediumWithFamily.copyWith(
          color: FansivibeColors.primary,
          decoration: TextDecoration.underline,
          decorationColor: FansivibeColors.primary,
          decorationThickness: 1,
        ),
      ),
    );
  }
}

enum FansiButtonVariant { primary, secondary, tertiary }
