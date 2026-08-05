import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// Hero card — the flagship editorial card family.
///
/// Vertical split of **65% image / 35% content** (the ratio is enforced with
/// `Expanded` flex, so the image can never be shrunk to fit more text).
///
/// Used for: Today's Look, Outfit Recommendations, Saved Looks, Discover
/// Stories, Hairstyle Recommendations.
///
/// Rules:
/// - The image is the hero. Content stays concise and ellipsized.
/// - Additional information belongs on a detail page, not in a taller card.
/// - Tonal surface, `md` corner radius, no borders, no divider lines,
///   no drop shadows (tonal layering only).
class FansiHeroCard extends StatelessWidget {
  const FansiHeroCard({
    required this.image,
    required this.title,
    this.eyebrow,
    this.subtitle,
    this.badge,
    this.tags = const [],
    this.footer,
    this.onTap,
    this.imageRatio = 65,
    super.key,
  });

  /// The image area (typically a [FansiImageWell] or a real photo).
  final Widget image;

  /// Editorial headline (serif).
  final String title;

  /// Small all-caps eyebrow shown over the image (e.g. "TODAY'S LOOK").
  final String? eyebrow;

  /// One-line supporting description.
  final String? subtitle;

  /// Optional floating badge over the image top-right (e.g. a [FansiBadge]).
  final Widget? badge;

  /// Concise garment tags shown in the content strip.
  final List<String> tags;

  /// Optional extra content rendered below the content strip (e.g. actions).
  final Widget? footer;

  /// Whole-card tap.
  final VoidCallback? onTap;

  /// Percentage of card height dedicated to the image (default 65).
  final int imageRatio;

  @override
  Widget build(BuildContext context) {
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
                return isBounded
                    ? _buildFlexColumn()
                    : _buildIntrinsicColumn();
              },
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildFlexColumn() {
    final contentRatio = 100 - imageRatio;
    return Column(
      children: [
        Expanded(flex: imageRatio, child: _buildImage()),
        Expanded(flex: contentRatio, child: _buildContent(bounded: true)),
        if (footer != null) footer!,
      ],
    );
  }

  /// Fallback for unbounded heights (e.g. inside a scroll view): the image
  /// keeps a square aspect so it is never shrunk to fit the content.
  Widget _buildIntrinsicColumn() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        AspectRatio(aspectRatio: 1, child: _buildImage()),
        _buildContent(bounded: false),
        if (footer != null) footer!,
      ],
    );
  }

  Widget _buildImage() {
    return Stack(
      fit: StackFit.expand,
      children: [
        image,
        if (eyebrow != null)
          Positioned(
            top: FansivibeSpacing.md,
            left: FansivibeSpacing.md,
            child: _eyebrowTag(eyebrow!),
          ),
        if (badge != null)
          Positioned(
            top: FansivibeSpacing.md,
            right: FansivibeSpacing.md,
            child: badge!,
          ),
        Positioned(
          left: 0,
          right: 0,
          bottom: 0,
          height: 64,
          child: IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.bottomCenter,
                  end: Alignment.topCenter,
                  colors: [
                    FansivibeColors.surfaceContainer.withValues(alpha: 0.7),
                    Colors.transparent,
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildContent({required bool bounded}) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(
        FansivibeSpacing.lg,
        FansivibeSpacing.md,
        FansivibeSpacing.lg,
        FansivibeSpacing.md,
      ),
      decoration: const BoxDecoration(color: FansivibeColors.surfaceContainer),
      child: Column(
        mainAxisSize: bounded ? MainAxisSize.max : MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Flexible(
            child: Text(
              title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: FansivibeTypography.titleLargeWithFamily,
            ),
          ),
          if (subtitle != null) ...[
            const SizedBox(height: FansivibeSpacing.xs),
            Flexible(
              child: Text(
                subtitle!,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: FansivibeTypography.bodyMediumWithFamily,
              ),
            ),
          ],
          if (tags.isNotEmpty) ...[
            const SizedBox(height: FansivibeSpacing.sm + 2),
            Row(
              children: [
                for (var i = 0; i < tags.length && i < 2; i++) ...[
                  if (i > 0) const SizedBox(width: FansivibeSpacing.xs),
                  Flexible(child: _tagPill(tags[i])),
                ],
              ],
            ),
          ],
        ],
      ),
    );
  }

  Widget _eyebrowTag(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: FansivibeSpacing.sm + 2,
        vertical: 5,
      ),
      decoration: BoxDecoration(
        color: FansivibeColors.accentGold.withValues(alpha: 0.15),
        borderRadius: FansivibeRadius.xsBorder,
      ),
      child: Text(
        label.toUpperCase(),
        style: FansivibeTypography.labelSmallWithFamily.copyWith(
          color: FansivibeColors.accentGold,
          fontWeight: FontWeight.w700,
          letterSpacing: 1.8,
          fontSize: 11,
        ),
      ),
    );
  }

  Widget _tagPill(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: FansivibeSpacing.sm,
        vertical: 4,
      ),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerHighest,
        borderRadius: FansivibeRadius.smBorder,
      ),
      child: Text(
        label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: FansivibeTypography.labelSmallWithFamily.copyWith(
          color: FansivibeColors.secondary,
          fontWeight: FontWeight.w500,
          fontSize: 10,
        ),
      ),
    );
  }
}
