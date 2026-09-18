import 'package:flutter/material.dart';
import 'package:fansivibe/features/discover/data/discover_mock_data.dart';
import 'package:fansivibe/features/discover/discover.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart'
    show WardrobeItemData;
import 'package:fansivibe/shared/components/fansi_badge.dart';
import 'package:fansivibe/shared/components/fansi_chip.dart';
import 'package:fansivibe/shared/components/fansi_hero_card.dart';
import 'package:fansivibe/shared/components/fansi_image_well.dart';
import 'package:fansivibe/shared/components/fansi_mini_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

/// A tab button for Discover tabs (For You / Trending).
class DiscoverTabButton extends StatelessWidget {
  const DiscoverTabButton({
    required this.data,
    required this.isSelected,
    required this.onTap,
    this.badge,
    super.key,
  });

  final DiscoverTabData data;
  final bool isSelected;
  final VoidCallback onTap;
  final Widget? badge;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Semantics(
      button: true,
      label: data.label,
      child: InkWell(
        onTap: onTap,
        borderRadius: FansivibeRadius.smdBorder,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
          decoration: BoxDecoration(
            color: isSelected
                ? FansivibeColors.accentGold.withValues(alpha: 0.15)
                : Colors.transparent,
            borderRadius: FansivibeRadius.smdBorder,
            border: Border.all(
              color: isSelected
                  ? FansivibeColors.accentGold.withValues(alpha: 0.4)
                  : FansivibeColors.accentGold.withValues(alpha: 0.08),
              width: 1,
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                data.icon,
                size: 18,
                color: isSelected
                    ? FansivibeColors.accentGold
                    : FansivibeColors.textSecondary,
              ),
              const SizedBox(width: 8),
              Flexible(
                child: Text(
                  data.label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: isSelected
                        ? FansivibeColors.accentGold
                        : FansivibeColors.textSecondary,
                  ),
                ),
              ),
              if (badge != null) ...[const SizedBox(width: 6), badge!],
            ],
          ),
        ),
      ),
    );
  }
}

/// A horizontal filter chips row for Discover.
class DiscoverFilterChipsRow extends StatelessWidget {
  const DiscoverFilterChipsRow({
    required this.options,
    required this.onOptionChanged,
    this.title,
    super.key,
  });

  final List<FilterOption> options;
  final void Function(FilterOption) onOptionChanged;
  final String? title;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (title != null) ...[
          Text(
            title!,
            style: theme.textTheme.bodySmall?.copyWith(
              fontWeight: FontWeight.w600,
              color: FansivibeColors.textSecondary,
              letterSpacing: 0.5,
            ),
          ),
          const SizedBox(height: 8),
        ],
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: options.map((option) {
              return Padding(
                padding: const EdgeInsets.only(right: 8),
                child: FansiChip(
                  label: option.label,
                  icon: option.icon,
                  selected: option.isSelected,
                  onTap: () => onOptionChanged(option),
                ),
              );
            }).toList(),
          ),
        ),
      ],
    );
  }
}

/// Look card widget for Discover grid.
/// A backend-fed look card (M14).
///
/// Renders one ranked [LookSummary] verbatim: title, description, and the
/// backend match score. The catalog carries no image, occasion, style/fit
/// tags, or trending signal, so the visual area is the neutral well and
/// no tag/trending chrome is rendered (AI-0 honesty — never fabricated).
/// Card proportions follow the shared [FansiHeroCard] default (65/35).
class LookCard extends StatelessWidget {
  const LookCard({
    required this.data,
    this.onTap,
    this.showMatchBadge = true,
    super.key,
  });

  /// Ranked backend row (catalog code id, verbatim fields).
  final LookSummary data;
  final VoidCallback? onTap;
  final bool showMatchBadge;

  @override
  Widget build(BuildContext context) {
    return FansiHeroCard(
      onTap: onTap,
      image: const Stack(
        fit: StackFit.expand,
        children: [
          FansiImageWell(
            icon: Icons.checkroom_rounded,
            color: FansivibeColors.accentGold,
          ),
        ],
      ),
      title: data.title,
      subtitle: data.description,
      badge: showMatchBadge
          ? FansiBadge(score: data.matchScore, size: BadgeSize.compact)
          : null,
    );
  }
}

/// Wardrobe-item card for the Discover Clothes tab (M12 P3).
///
/// Discover-owned presentation over the backend `WardrobeItemData`
/// (same shared primitives as the wardrobe surface): neutral
/// [FansiImageWell] placeholder — wardrobe rows carry no servable
/// photo (image_ref is provenance, never a URL), so no photo is ever
/// invented here. Taps route to the existing wardrobe detail surface.
class ClothesItemCard extends StatelessWidget {
  const ClothesItemCard({required this.item, this.onTap, super.key});

  /// Persisted backend wardrobe row, verbatim (never a mock product).
  final WardrobeItemData item;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return FansiMiniCard(
      onTap: onTap,
      image: const Stack(
        fit: StackFit.expand,
        children: [
          FansiImageWell(
            icon: Icons.checkroom_rounded,
            color: FansivibeColors.accentGold,
          ),
        ],
      ),
      title: item.name,
      meta: item.color,
    );
  }
}
