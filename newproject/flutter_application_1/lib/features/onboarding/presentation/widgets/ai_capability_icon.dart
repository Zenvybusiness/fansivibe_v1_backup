import 'package:flutter/material.dart';
import 'package:fansivibe/features/onboarding/data/onboarding_data.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

class AiCapabilityIcon extends StatelessWidget {
  final AiCapability capability;
  final double size;

  const AiCapabilityIcon({required this.capability, this.size = 48, super.key});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: capability.active ? null : () => _showHint(context),
      child: Container(
        width: size + 16,
        margin: EdgeInsets.only(right: FansivibeSpacing.sm),
        child: Column(
          mainAxisSize: MainAxisSize.max,
          children: [
            Container(
              width: size,
              height: size,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: capability.active
                    ? FansivibeColors.primary.withValues(alpha: 0.12)
                    : FansivibeColors.surfaceContainerHighest,
                border: capability.active
                    ? Border.all(
                        color: FansivibeColors.primary.withValues(alpha: 0.3),
                        width: 1.5,
                      )
                    : null,
              ),
              child: Center(
                child: Icon(
                  capability.active
                      ? Icons.check_circle_rounded
                      : Icons.lock_rounded,
                  size: size * 0.45,
                  color: capability.active
                      ? FansivibeColors.primary
                      : FansivibeColors.secondary.withValues(alpha: 0.5),
                ),
              ),
            ),
            SizedBox(height: FansivibeSpacing.xs),
            Flexible(
              child: Text(
                capability.name,
                style: FansivibeTypography.labelSmallWithFamily.copyWith(
                  color: capability.active
                      ? FansivibeColors.primary
                      : FansivibeColors.secondary.withValues(alpha: 0.6),
                  fontSize: 9,
                ),
                textAlign: TextAlign.center,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            if (!capability.active && capability.unlockHint != null)
              Flexible(
                child: Padding(
                  padding: EdgeInsets.only(top: FansivibeSpacing.xs),
                  child: Text(
                    capability.unlockHint!,
                    style: FansivibeTypography.labelSmallWithFamily.copyWith(
                      fontSize: 7,
                      color: FansivibeColors.secondary.withValues(alpha: 0.4),
                    ),
                    textAlign: TextAlign.center,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  void _showHint(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          '${capability.name}: ${capability.unlockHint ?? "Coming soon"}',
        ),
        backgroundColor: FansivibeColors.surfaceContainerHighest,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.smBorder),
        duration: const Duration(seconds: 2),
      ),
    );
  }
}
