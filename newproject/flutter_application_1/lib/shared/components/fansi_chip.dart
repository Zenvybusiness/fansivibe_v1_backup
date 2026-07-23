import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// A garment-tag-style chip built with `surface-container-highest` and
/// `sm` radius as specified in the design system.
///
/// Use [FansiChip.selected] for the active/filtered state (gold tint).
class FansiChip extends StatelessWidget {
  const FansiChip({
    required this.label,
    this.icon,
    this.onTap,
    this.selected = false,
    super.key,
  });

  final String label;
  final IconData? icon;
  final VoidCallback? onTap;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    final bgColor = selected
        ? FansivibeColors.primary.withValues(alpha: 0.2)
        : FansivibeColors.surfaceContainerHighest;
    final fgColor = selected
        ? FansivibeColors.primary
        : FansivibeColors.secondary;

    final chip = Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: FansivibeRadius.smBorder,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 14, color: fgColor),
            const SizedBox(width: 6),
          ],
          Text(
            label,
            style: FansivibeTypography.labelSmallWithFamily.copyWith(
              color: fgColor,
              fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
            ),
          ),
        ],
      ),
    );

    if (onTap != null) {
      return InkWell(
        onTap: onTap,
        borderRadius: FansivibeRadius.smBorder,
        child: chip,
      );
    }
    return chip;
  }
}
