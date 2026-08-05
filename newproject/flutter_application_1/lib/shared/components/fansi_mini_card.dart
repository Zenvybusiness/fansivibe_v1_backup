import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// Mini card — compact product/wardrobe card family.
///
/// Vertical split of **75% image / 25% content** (enforced with `Expanded`
/// flex, so the image can never be shrunk to fit more text).
///
/// Used for: Wardrobe Items, Shoes, Accessories, Products.
///
/// Rules:
/// - The image is the hero. Content is a single name line plus optional
///   meta line, both ellipsized.
/// - Additional information belongs on a detail page, not in a taller card.
/// - Tonal surface, `md` corner radius, no borders, no divider lines,
///   no drop shadows.
class FansiMiniCard extends StatelessWidget {
  const FansiMiniCard({
    required this.image,
    required this.title,
    this.meta,
    this.badge,
    this.onTap,
    this.imageRatio = 75,
    super.key,
  });

  /// The image area (typically a [FansiImageWell] or a real photo).
  final Widget image;

  /// Item name.
  final String title;

  /// One-line meta (colour, price, material).
  final String? meta;

  /// Optional floating indicator over the image (e.g. favourite heart).
  final Widget? badge;

  /// Whole-card tap.
  final VoidCallback? onTap;

  /// Percentage of card height dedicated to the image (default 75).
  final int imageRatio;

  @override
  Widget build(BuildContext context) {
    final contentRatio = 100 - imageRatio;

    return Semantics(
      button: onTap != null,
      child: ClipRRect(
        borderRadius: FansivibeRadius.mdBorder,
        child: Material(
          color: FansivibeColors.surfaceContainer,
          child: InkWell(
            onTap: onTap,
            child: LayoutBuilder(
              builder: (context, constraints) {
                final isBounded = constraints.maxHeight.isFinite;
                if (isBounded) {
                  return Column(
                    children: [
                      Expanded(flex: imageRatio, child: _buildImage(context)),
                      Expanded(
                        flex: contentRatio,
                        child: _buildContent(context, bounded: true),
                      ),
                    ],
                  );
                }
                // Fallback for unbounded heights (e.g. inside a scroll view):
                // the image keeps a square aspect so it is never shrunk.
                return Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    AspectRatio(aspectRatio: 1, child: _buildImage(context)),
                    _buildContent(context, bounded: false),
                  ],
                );
              },
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildImage(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        image,
        if (badge != null)
          Positioned(
            top: FansivibeSpacing.sm,
            right: FansivibeSpacing.sm,
            child: badge!,
          ),
      ],
    );
  }

  Widget _buildContent(BuildContext context, {required bool bounded}) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(
        FansivibeSpacing.sm + 2,
        FansivibeSpacing.sm,
        FansivibeSpacing.sm + 2,
        FansivibeSpacing.sm,
      ),
      decoration: const BoxDecoration(color: FansivibeColors.surfaceContainer),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          _bounded(
            bounded,
            Text(
              title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: FansivibeTypography.labelMediumWithFamily.copyWith(
                color: FansivibeColors.onSurface,
                fontSize: 11,
              ),
            ),
          ),
          if (meta != null) ...[
            const SizedBox(height: FansivibeSpacing.xs),
            _bounded(
              bounded,
              Text(
                meta!,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: FansivibeTypography.labelSmallWithFamily.copyWith(
                  fontSize: 9,
                  color: FansivibeColors.secondary,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _bounded(bool bounded, Text text) {
    return bounded ? Flexible(child: text) : text;
  }
}
