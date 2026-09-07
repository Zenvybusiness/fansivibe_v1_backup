import 'dart:async';

import 'package:flutter/material.dart';

import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/app/router/route_names.dart';

String _resolveCategory(String category) {
  switch (category.toLowerCase()) {
    case 'tops':
      return 'Top';
    case 'bottoms':
      return 'Bottom';
    case 'outerwear':
      return 'Outerwear';
    case 'footwear':
      return 'Footwear';
    case 'accessories':
      return 'Accessories';
    default:
      return category.substring(0).toUpperCase();
  }
}

List<String> _categoryNames() => [
  'tops',
  'bottoms',
  'outerwear',
  'footwear',
  'accessories',
];

String _dataAvailabilityString(String? dataAvailability) {
  switch (dataAvailability) {
    case 'full':
      return 'Full wardrobe data';
    case 'partial':
      return 'Partial wardrobe data';
    case 'sparse':
      return 'Limited wardrobe data';
    default:
      return 'Wardrobe data available';
  }
}

class OutfitRecommendationCard extends StatelessWidget {
  const OutfitRecommendationCard({
    required this.outfitIntelligence,
    required this.wardrobeItems,
    super.key,
  });

  final OutfitIntelligence outfitIntelligence;
  final List<WardrobeItemData> wardrobeItems;

  @override
  Widget build(BuildContext context) {
    return _OutfitRecommendationCardView(
      outfitIntelligence: outfitIntelligence,
      wardrobeItems: wardrobeItems,
    );
  }
}

class _OutfitRecommendationCardView extends StatefulWidget {
  const _OutfitRecommendationCardView({
    required this.outfitIntelligence,
    required this.wardrobeItems,
    super.key,
  });

  final OutfitIntelligence outfitIntelligence;
  final List<WardrobeItemData> wardrobeItems;

  @override
  State<_OutfitRecommendationCardView> createState() =>
      _OutfitRecommendationCardViewState();
}

class _OutfitRecommendationCardViewState
    extends State<_OutfitRecommendationCardView> {
  late final ThemeData _theme;
  late final bool _isDark;

  @override
  void initState() {
    super.initState();
    _theme = Theme.of(context);
    _isDark = _theme.brightness == Brightness.dark;
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: FansivibeColors.surfaceContainer,
      child: Padding(
        padding: const EdgeInsets.all(FansivibeSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildHeader(context),

            const SizedBox(height: FansivibeSpacing.md),

            _buildComposition(widget.wardrobeItems),

            const SizedBox(height: FansivibeSpacing.md),

            _buildStyleScore(context),

            const SizedBox(height: FansivibeSpacing.md),

            _buildWhyItWorks(context),

            const SizedBox(height: FansivibeSpacing.md),

            _buildDataAvailability(context),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Your Outfit',
                style: FansivibeTypography.titleLargeWithFamily.copyWith(
                  color: FansivibeColors.onSurface,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: FansivibeSpacing.xs),
              Text(
                widget.outfitIntelligence.occasion,
                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                  color: FansivibeColors.secondary,
                  height: 1.4,
                ),
              ),
            ],
          ),
        ),
        Container(
          padding: const EdgeInsets.symmetric(
            horizontal: FansivibeSpacing.sm,
            vertical: FansivibeSpacing.xs,
          ),
          decoration: BoxDecoration(
            color: FansivibeColors.primary.withValues(alpha: 0.12),
            borderRadius: FansivibeRadius.fullBorder,
          ),
          child: Text(
            '${(widget.outfitIntelligence.confidence * 100).round()}% confident',
            style: FansivibeTypography.labelSmallWithFamily.copyWith(
              color: FansivibeColors.primary,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildComposition(List<WardrobeItemData>? items) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Outfit composition',
          style: FansivibeTypography.titleLargeWithFamily.copyWith(
            color: FansivibeColors.onSurface,
            fontWeight: FontWeight.w600,
            fontSize: 18,
          ),
        ),
        const SizedBox(height: FansivibeSpacing.sm),

        ..._categoryNames().map((category) {
          final categoryItems =
              (items ?? []).where((item) => item.category == category).toList();
          final categoryLabel = _resolveCategory(category);

          if (categoryItems.isEmpty) {
            return const SizedBox.shrink();
          }

          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(bottom: FansivibeSpacing.xs),
                child: Text(
                  categoryLabel,
                  style: FansivibeTypography.bodyLargeWithFamily.copyWith(
                    color: FansivibeColors.primary,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              ...categoryItems.take(2).map((item) => _buildItemChip(context, item)),
              if (categoryItems.length > 2)
                Padding(
                  padding: const EdgeInsets.only(top: FansivibeSpacing.xs),
                  child: Text(
                    '+ ${categoryItems.length - 2} more',
                    style: FansivibeTypography.labelSmallWithFamily.copyWith(
                      color: FansivibeColors.secondary,
                    ),
                  ),
                ),
            ],
          );
        }).toList(),
      ],
    );
  }

  Widget _buildItemChip(BuildContext context, WardrobeItemData item) {
    final colorSwatch = _colorFromName(item.color);

    return Padding(
      padding: const EdgeInsets.only(bottom: FansivibeSpacing.xs),
      child: ChoiceChip(
        label: Text(
          item.name,
          style: FansivibeTypography.bodyMediumWithFamily.copyWith(
            color: _isDark ? FansivibeColors.onSurface : Colors.white,
          ),
        ),
        selected: false,
        backgroundColor: FansivibeColors.surfaceContainerHighest,
        side: BorderSide(
          color: colorSwatch,
          width: 1,
        ),
        padding: const EdgeInsets.symmetric(
          horizontal: FansivibeSpacing.sm,
          vertical: FansivibeSpacing.xs,
        ),
        labelPadding: const EdgeInsets.symmetric(
          horizontal: FansivibeSpacing.sm,
          vertical: 0,
        ),
        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
        onSelected: (_) {
          if (!context.mounted) return;
          Navigator.of(context).pushNamed(
            RouteNames.wardrobeItemDetails,
            arguments: item.id,
          );
        },
      ),
    );
  }

  Color _colorFromName(String colorName) {
    switch (colorName.toLowerCase()) {
      case 'charcoal':
        return const Color(0xFF444444);
      case 'black':
        return Colors.black;
      case 'white':
      case 'off-white':
      case 'cream':
        return const Color(0xFFE5E5E5);
      case 'navy':
      case 'indigo':
        return const Color(0xFF1A237E);
      case 'blush':
      case 'beige':
      case 'khaki':
      case 'stone':
      case 'tan':
        return const Color(0xFFD7CCC8);
      case 'light wash':
        return const Color(0xFFB5D2E0);
      case 'light blue':
        return const Color(0xFF81D4FA);
      case 'burgundy':
        return const Color(0xFF880E4F);
      case 'brown':
        return const Color(0xFF795548);
      case 'silver':
        return const Color(0xFFBDBDBD);
      default:
        return FansivibeColors.textSecondary;
    }
  }

  Widget _buildStyleScore(BuildContext context) {
    return Row(
      children: [
        const Icon(
          Icons.star_rounded,
          size: 16,
          color: FansivibeColors.primary,
        ),
        const SizedBox(width: FansivibeSpacing.xs),
        Text(
          'Style Score: ${widget.outfitIntelligence.outfitComposition.styleScore}',
          style: FansivibeTypography.bodyMediumWithFamily.copyWith(
            color: FansivibeColors.onSurface,
            height: 1.3,
          ),
        ),
      ],
    );
  }

  Widget _buildWhyItWorks(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Why it works',
          style: FansivibeTypography.titleLargeWithFamily.copyWith(
            color: FansivibeColors.onSurface,
            fontWeight: FontWeight.w600,
            fontSize: 18,
          ),
        ),
        const SizedBox(height: FansivibeSpacing.sm),
        Text(
          widget.outfitIntelligence.stylingRationale,
          style: FansivibeTypography.bodyMediumWithFamily.copyWith(
            color: FansivibeColors.secondary,
            height: 1.4,
          ),
        ),
        const SizedBox(height: FansivibeSpacing.sm),
        Text(
          widget.outfitIntelligence.compatibilityRationale,
          style: FansivibeTypography.bodyMediumWithFamily.copyWith(
            color: FansivibeColors.secondary,
            height: 1.4,
          ),
        ),
      ],
    );
  }

  Widget _buildDataAvailability(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(top: FansivibeSpacing.md),
      padding: const EdgeInsets.all(FansivibeSpacing.sm),
      decoration: BoxDecoration(
        color: FansivibeColors.primary.withValues(alpha: 0.08),
        borderRadius: FansivibeRadius.smBorder,
      ),
      child: Row(
        children: [
          Icon(
            Icons.info_outlined,
            size: 16,
            color: FansivibeColors.primary,
          ),
          const SizedBox(width: FansivibeSpacing.xs),
          Expanded(
            child: Text(
              _dataAvailabilityString(widget.outfitIntelligence.dataAvailability),
              style: FansivibeTypography.labelSmallWithFamily.copyWith(
                color: FansivibeColors.primary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
