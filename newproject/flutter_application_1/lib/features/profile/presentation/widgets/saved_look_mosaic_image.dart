import 'package:flutter/material.dart';

import 'package:fansivibe/features/profile/data/saved_looks_models.dart';
import 'package:fansivibe/features/wardrobe/presentation/widgets/wardrobe_widgets.dart';
import 'package:fansivibe/shared/components/fansi_image_well.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// Multi-garment thumbnail mosaic for saved-look hero cards (Stage 2 P1-2).
///
/// Replaces generic placeholder icons with real wardrobe thumbnails while
/// strictly preserving the 65% image / 35% content card balance in [FansiHeroCard].
///
/// Dynamically arranges 1 to 4 garments into a clean, balanced grid.
/// Gracefully falls back to [FansiImageWell] for looks without garments or images.
class SavedLookMosaicImage extends StatelessWidget {
  const SavedLookMosaicImage({
    required this.items,
    required this.fallbackIcon,
    required this.fallbackColor,
    super.key,
  });

  /// Hydrated garments belonging to the saved look.
  final List<HydratedGarmentItem> items;

  /// Fallback icon when no garment thumbnails are available.
  final IconData fallbackIcon;

  /// Fallback accent color for the image well.
  final Color fallbackColor;

  Widget _buildArchivedBadge() {
    return Positioned(
      bottom: 4,
      left: 4,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
        decoration: BoxDecoration(
          color: FansivibeColors.surfaceContainerHighest.withValues(alpha: 0.9),
          borderRadius: FansivibeRadius.xsBorder,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.archive_outlined,
              size: 10,
              color: FansivibeColors.accentGold,
            ),
            const SizedBox(width: 3),
            Text(
              'Archived',
              style: FansivibeTypography.labelSmallWithFamily.copyWith(
                fontSize: 9,
                color: FansivibeColors.accentGold,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTile(HydratedGarmentItem item) {
    return Stack(
      fit: StackFit.expand,
      children: [
        WardrobeItemImage(item: item.toWardrobeItemData(), iconSize: 24),
        if (item.isArchived) _buildArchivedBadge(),
      ],
    );
  }

  Widget _buildDivider({bool vertical = true}) {
    return Container(
      width: vertical ? 1 : null,
      height: vertical ? null : 1,
      color: FansivibeColors.surfaceContainerLow,
    );
  }

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return FansiImageWell(icon: fallbackIcon, color: fallbackColor);
    }

    final count = items.length;

    if (count == 1) {
      return _buildTile(items[0]);
    }

    if (count == 2) {
      return Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(child: _buildTile(items[0])),
          _buildDivider(vertical: true),
          Expanded(child: _buildTile(items[1])),
        ],
      );
    }

    if (count == 3) {
      return Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(flex: 1, child: _buildTile(items[0])),
          _buildDivider(vertical: true),
          Expanded(
            flex: 1,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(child: _buildTile(items[1])),
                _buildDivider(vertical: false),
                Expanded(child: _buildTile(items[2])),
              ],
            ),
          ),
        ],
      );
    }

    // 4 or more garments: 2x2 grid (first 4 items)
    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(child: _buildTile(items[0])),
              _buildDivider(vertical: false),
              Expanded(child: _buildTile(items[1])),
            ],
          ),
        ),
        _buildDivider(vertical: true),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(child: _buildTile(items[2])),
              _buildDivider(vertical: false),
              Expanded(child: _buildTile(items[3])),
            ],
          ),
        ),
      ],
    );
  }
}
