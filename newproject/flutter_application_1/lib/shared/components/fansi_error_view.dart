import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// A centered error state with icon, message, and optional retry button.
class FansiErrorView extends StatelessWidget {
  const FansiErrorView({
    this.message = 'Something went wrong',
    this.onRetry,
    super.key,
  });

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(FansivibeSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.error_outline_rounded,
              size: 48,
              color: FansivibeColors.error.withValues(alpha: 0.6),
            ),
            const SizedBox(height: FansivibeSpacing.md),
            Text(
              message,
              style: FansivibeTypography.bodyMediumWithFamily,
              textAlign: TextAlign.center,
            ),
            if (onRetry != null) ...[
              const SizedBox(height: FansivibeSpacing.lg),
              FilledButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh_rounded, size: 18),
                label: const Text('Try Again'),
                style: FilledButton.styleFrom(
                  shape: RoundedRectangleBorder(
                    borderRadius: FansivibeRadius.fullBorder,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
