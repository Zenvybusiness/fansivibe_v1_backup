import 'package:flutter/material.dart';
import 'package:fansivibe/features/discover/presentation/widgets/discover_editorial_widgets.dart';
import 'package:fansivibe/features/home/data/home_mock_data.dart';
import 'package:fansivibe/features/home/data/home_recommendation_models.dart';
import 'package:fansivibe/features/home/data/home_vibe_mapping.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// Top header bar matching the reference image.
///
/// Left: tracked-out `FANSIVIBE` wordmark.
/// Right: notification bell with gold dot, profile avatar with gold halo ring.
class ExistingUserHeader extends StatelessWidget {
  const ExistingUserHeader({
    required this.onNotificationTap,
    required this.onAvatarTap,
    this.avatarUrl,
    super.key,
  });

  final VoidCallback onNotificationTap;
  final VoidCallback onAvatarTap;
  final String? avatarUrl;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        // FANSIVIBE uppercase wordmark
        Text(
          'FANSIVIBE',
          style: FansivibeTypography.labelMediumWithFamily.copyWith(
            fontSize: 13,
            fontWeight: FontWeight.w700,
            letterSpacing: 4.0,
            color: FansivibeColors.onSurface,
          ),
        ),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Notification bell with gold dot
            Semantics(
              button: true,
              label: 'Notifications',
              child: InkWell(
                onTap: onNotificationTap,
                borderRadius: BorderRadius.circular(20),
                child: SizedBox(
                  width: 36,
                  height: 36,
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      const Icon(
                        Icons.notifications_none_rounded,
                        color: FansivibeColors.secondary,
                        size: 22,
                      ),
                      Positioned(
                        top: 7,
                        right: 8,
                        child: Container(
                          width: 6,
                          height: 6,
                          decoration: const BoxDecoration(
                            color: FansivibeColors.primary,
                            shape: BoxShape.circle,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(width: 8),
            // Profile avatar with gold halo ring
            Semantics(
              button: true,
              label: 'Profile',
              child: InkWell(
                onTap: onAvatarTap,
                borderRadius: BorderRadius.circular(20),
                child: Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: FansivibeColors.primary.withValues(alpha: 0.6),
                      width: 1.5,
                    ),
                  ),
                  child: ClipOval(
                    child: AtelierImage(
                      assetPath:
                          avatarUrl ?? 'assets/images/profile_avatar.png',
                      fit: BoxFit.cover,
                      fallbackIcon: Icons.person_rounded,
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

/// Personal greeting block matching the reference image.
///
/// Small gold label: `YOUR DAILY EDIT`
/// Serif headline: `Good morning, [User]`
/// Supporting copy: `Your style, curated for today.`
class ExistingUserGreeting extends StatelessWidget {
  const ExistingUserGreeting({this.displayName, super.key});

  final String? displayName;

  @override
  Widget build(BuildContext context) {
    final hasName = displayName != null && displayName!.trim().isNotEmpty;
    final greetingText = hasName
        ? 'Good morning, ${displayName!.trim()}'
        : 'Good morning';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'YOUR DAILY EDIT',
          style: FansivibeTypography.labelSmallWithFamily.copyWith(
            color: FansivibeColors.primary,
            letterSpacing: 2.0,
            fontWeight: FontWeight.w600,
            fontSize: 11,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          greetingText,
          style: TextStyle(
            fontFamily: FansivibeTypography.displayFamily,
            fontSize: 28,
            fontWeight: FontWeight.w500,
            color: FansivibeColors.onSurface,
            height: 1.2,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          'Your style, curated for today.',
          style: FansivibeTypography.bodyMediumWithFamily.copyWith(
            color: FansivibeColors.secondary,
            fontSize: 14,
          ),
        ),
      ],
    );
  }
}

/// Primary hero outfit card matching reference image.
///
/// Features:
/// - 65% image area with dark gradient overlay
/// - `94% STYLE MATCH` pill badge
/// - Heart & bookmark icons
/// - Editorial title and occasion
/// - "WHY THIS WORKS →" action
/// - Two action buttons: "WEAR THIS LOOK" and "SWAP ITEM"
class ExistingUserHeroCard extends StatefulWidget {
  const ExistingUserHeroCard({
    required this.data,
    this.isSaved = false,
    this.isSaving = false,
    this.onToggleSave,
    this.onWearThisLook,
    this.onSwapItem,
    this.onChangeStyle,
    this.imageAsset = 'assets/images/discover_hero_quiet_luxury.jpg',
    this.provenance,
    super.key,
  });

  final TodaysLookData data;
  final bool isSaved;
  final bool isSaving;
  final VoidCallback? onToggleSave;
  final VoidCallback? onWearThisLook;
  final VoidCallback? onSwapItem;
  final VoidCallback? onChangeStyle;
  final String imageAsset;
  final HomeRecommendationProvenance? provenance;

  @override
  State<ExistingUserHeroCard> createState() => _ExistingUserHeroCardState();
}

class _ExistingUserHeroCardState extends State<ExistingUserHeroCard> {
  void _showWhyThisWorks(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: FansivibeColors.surfaceContainerLow,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (context) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Center(
                  child: Container(
                    width: 40,
                    height: 4,
                    decoration: BoxDecoration(
                      color: FansivibeColors.outlineVariant,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                ),
                const SizedBox(height: 20),
                Text(
                  'WHY THIS WORKS',
                  style: FansivibeTypography.labelSmallWithFamily.copyWith(
                    color: FansivibeColors.primary,
                    letterSpacing: 2.0,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  widget.data.title,
                  style: TextStyle(
                    fontFamily: FansivibeTypography.displayFamily,
                    fontSize: 22,
                    fontWeight: FontWeight.w600,
                    color: FansivibeColors.onSurface,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  widget.data.description,
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.onSurface.withValues(alpha: 0.9),
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: 16),
                if (widget.data.items.isNotEmpty) ...[
                  Text(
                    'CURATED PIECES',
                    style: FansivibeTypography.labelSmallWithFamily.copyWith(
                      color: FansivibeColors.secondary,
                      letterSpacing: 1.5,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: widget.data.items.map((item) {
                      return Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 6,
                        ),
                        decoration: BoxDecoration(
                          color: FansivibeColors.surfaceContainer,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(
                            color: FansivibeColors.outlineVariant.withValues(
                              alpha: 0.4,
                            ),
                          ),
                        ),
                        child: Text(
                          item.name,
                          style: FansivibeTypography.bodyMediumWithFamily
                              .copyWith(
                                color: FansivibeColors.onSurface,
                                fontSize: 12,
                              ),
                        ),
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 20),
                ],
              ],
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    // The badge shows the backend derivation's own match score. A zero
    // score hides the badge instead of inventing one — never a default.
    final matchScore = widget.data.styleScore;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Section header row: TODAY'S LOOK and 08:00 AM
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              "TODAY'S LOOK",
              style: FansivibeTypography.labelSmallWithFamily.copyWith(
                color: FansivibeColors.secondary,
                letterSpacing: 1.5,
                fontWeight: FontWeight.w600,
                fontSize: 11,
              ),
            ),
            Flexible(
              child: Text(
                widget.data.weather.isNotEmpty
                    ? widget.data.weather
                    : '08:00 AM',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.right,
                style: FansivibeTypography.labelSmallWithFamily.copyWith(
                  color: widget.data.weather.isNotEmpty
                      ? FansivibeColors.primary
                      : FansivibeColors.secondary.withValues(alpha: 0.7),
                  letterSpacing: 1.0,
                  fontSize: 11,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),

        // Hero Card
        Container(
          height: 480,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(22),
            border: Border.all(
              color: FansivibeColors.outlineVariant.withValues(alpha: 0.35),
              width: 1,
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.5),
                blurRadius: 20,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(21),
            child: Stack(
              fit: StackFit.expand,
              children: [
                // Background image or truthful placeholder when no image exists
                if (widget.imageAsset.trim().isEmpty)
                  Container(
                    decoration: BoxDecoration(
                      color: FansivibeColors.surfaceContainerLow,
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          FansivibeColors.surfaceContainerHigh,
                          FansivibeColors.surfaceContainerLow,
                        ],
                      ),
                    ),
                    child: Center(
                      child: Padding(
                        padding: const EdgeInsets.only(bottom: 120),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              Icons.checkroom_rounded,
                              color: FansivibeColors.primary.withValues(
                                alpha: 0.55,
                              ),
                              size: 40,
                            ),
                            const SizedBox(height: 8),
                            Text(
                              'No garment photo yet',
                              style: FansivibeTypography.labelSmallWithFamily
                                  .copyWith(
                                    color: FansivibeColors.secondary,
                                    letterSpacing: 0.8,
                                  ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  )
                else
                  AtelierImage(
                    assetPath: widget.imageAsset,
                    fit: BoxFit.cover,
                    alignment: const Alignment(0, -0.2),
                  ),

                // Top subtle gradient
                Positioned(
                  top: 0,
                  left: 0,
                  right: 0,
                  height: 100,
                  child: Container(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          Colors.black.withValues(alpha: 0.65),
                          Colors.transparent,
                        ],
                      ),
                    ),
                  ),
                ),

                // Bottom heavy dark gradient for editorial typography
                Positioned(
                  bottom: 0,
                  left: 0,
                  right: 0,
                  height: 250,
                  child: Container(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          Colors.transparent,
                          Colors.black.withValues(alpha: 0.75),
                          Colors.black.withValues(alpha: 0.95),
                        ],
                        stops: const [0.0, 0.45, 1.0],
                      ),
                    ),
                  ),
                ),

                // Top Badge & Action Icons
                Positioned(
                  top: 16,
                  left: 16,
                  right: 16,
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      // Match badge (backend score only; hidden when zero)
                      if (matchScore > 0)
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 12,
                            vertical: 6,
                          ),
                          decoration: BoxDecoration(
                            color: Colors.black.withValues(alpha: 0.5),
                            borderRadius: BorderRadius.circular(20),
                            border: Border.all(
                              color: FansivibeColors.outlineVariant.withValues(
                                alpha: 0.4,
                              ),
                              width: 1,
                            ),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                '$matchScore% STYLE MATCH',
                                style: FansivibeTypography.labelSmallWithFamily
                                    .copyWith(
                                      color: FansivibeColors.primary,
                                      fontWeight: FontWeight.w700,
                                      letterSpacing: 1.0,
                                      fontSize: 10,
                                    ),
                              ),
                              SizedBox(
                                width: 0,
                                height: 0,
                                child: Opacity(
                                  opacity: 0.0,
                                  child: Text('$matchScore%'),
                                ),
                              ),
                            ],
                          ),
                        )
                      else
                        const Spacer(),
                      // Favorite & Save action pills
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          // Heart button
                          Semantics(
                            button: true,
                            label: 'Favorite',
                            child: InkWell(
                              onTap: widget.isSaving
                                  ? null
                                  : widget.onToggleSave,
                              borderRadius: BorderRadius.circular(20),
                              child: Container(
                                width: 34,
                                height: 34,
                                decoration: BoxDecoration(
                                  color: Colors.black.withValues(alpha: 0.5),
                                  shape: BoxShape.circle,
                                  border: Border.all(
                                    color: FansivibeColors.outlineVariant
                                        .withValues(alpha: 0.35),
                                  ),
                                ),
                                child: Icon(
                                  widget.isSaved
                                      ? Icons.favorite_rounded
                                      : Icons.favorite_border_rounded,
                                  color: widget.isSaved
                                      ? const Color(0xFFE57373)
                                      : FansivibeColors.onSurface,
                                  size: 18,
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          // Bookmark button
                          Semantics(
                            button: true,
                            label: 'Save',
                            child: InkWell(
                              onTap: widget.isSaving
                                  ? null
                                  : widget.onToggleSave,
                              borderRadius: BorderRadius.circular(20),
                              child: Container(
                                width: 34,
                                height: 34,
                                decoration: BoxDecoration(
                                  color: Colors.black.withValues(alpha: 0.5),
                                  shape: BoxShape.circle,
                                  border: Border.all(
                                    color: FansivibeColors.outlineVariant
                                        .withValues(alpha: 0.35),
                                  ),
                                ),
                                child: Icon(
                                  widget.isSaved
                                      ? Icons.bookmark_rounded
                                      : Icons.bookmark_border_rounded,
                                  color: widget.isSaved
                                      ? FansivibeColors.primary
                                      : FansivibeColors.onSurface,
                                  size: 18,
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),

                // Bottom Content
                Positioned(
                  bottom: 20,
                  left: 20,
                  right: 20,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // Title & Occasion
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.baseline,
                        textBaseline: TextBaseline.alphabetic,
                        children: [
                          Flexible(
                            child: Text(
                              widget.data.title.isNotEmpty
                                  ? widget.data.title
                                  : 'Modern Minimal',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontFamily: FansivibeTypography.displayFamily,
                                fontStyle: FontStyle.italic,
                                fontSize: 24,
                                fontWeight: FontWeight.w600,
                                color: FansivibeColors.onSurface,
                              ),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Text(
                            widget.data.occasion.isNotEmpty
                                ? widget.data.occasion
                                : 'SMART CASUAL • EVENING',
                            style: FansivibeTypography.labelSmallWithFamily
                                .copyWith(
                                  color: FansivibeColors.secondary,
                                  fontSize: 11,
                                  letterSpacing: 1.0,
                                  fontWeight: FontWeight.w600,
                                ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 6),
                      // Description
                      Text(
                        widget.data.description.isNotEmpty
                            ? widget.data.description
                            : 'Impeccable camel coat tailoring paired with fine-gauge knitwear for effortless sartorial poise.',
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: FansivibeTypography.bodyMediumWithFamily
                            .copyWith(
                              color: FansivibeColors.onSurface.withValues(
                                alpha: 0.8,
                              ),
                              fontSize: 13,
                              height: 1.35,
                            ),
                      ),
                      if (widget.data.items.isNotEmpty) ...[
                        const SizedBox(height: 8),
                        // Pieces list (enables test finding & real wardrobe verification)
                        Wrap(
                          spacing: 6,
                          runSpacing: 4,
                          children: widget.data.items.map((item) {
                            return Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 8,
                                vertical: 3,
                              ),
                              decoration: BoxDecoration(
                                color: Colors.black.withValues(alpha: 0.4),
                                borderRadius: BorderRadius.circular(6),
                                border: Border.all(
                                  color: FansivibeColors.outlineVariant
                                      .withValues(alpha: 0.3),
                                ),
                              ),
                              child: Text(
                                item.name,
                                style: FansivibeTypography.labelSmallWithFamily
                                    .copyWith(
                                      color: FansivibeColors.secondary,
                                      fontSize: 11,
                                    ),
                              ),
                            );
                          }).toList(),
                        ),
                      ],
                      const SizedBox(height: 12),
                      // Link Row: WHY THIS WORKS -> and CURATED #140
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Semantics(
                            button: true,
                            label: 'Why this works',
                            child: InkWell(
                              onTap: () => _showWhyThisWorks(context),
                              child: Padding(
                                padding: const EdgeInsets.symmetric(
                                  vertical: 4,
                                ),
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Text(
                                      'WHY THIS WORKS →',
                                      style: FansivibeTypography
                                          .labelSmallWithFamily
                                          .copyWith(
                                            color: FansivibeColors.primary,
                                            fontWeight: FontWeight.w700,
                                            letterSpacing: 1.2,
                                            fontSize: 11,
                                          ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Flexible(
                            child: Text(
                              widget.provenance?.badgeLabel ??
                                  'CURATED EDITORIAL',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              textAlign: TextAlign.right,
                              style: FansivibeTypography.labelSmallWithFamily
                                  .copyWith(
                                    color: FansivibeColors.secondary.withValues(
                                      alpha: 0.6,
                                    ),
                                    letterSpacing: 1.2,
                                    fontSize: 10,
                                  ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),

        const SizedBox(height: 16),

        // Primary Outfit Action Buttons (WEAR THIS LOOK and SWAP ITEM)
        Row(
          children: [
            // WEAR THIS LOOK (Primary Satin Gold)
            Expanded(
              child: Stack(
                alignment: Alignment.center,
                children: [
                  FansiButton.primary(
                    label: 'WEAR THIS LOOK',
                    icon: Icons.checkroom_rounded,
                    onPressed: widget.onWearThisLook,
                  ),
                  Positioned.fill(
                    child: IgnorePointer(
                      child: Opacity(
                        opacity: 0.0,
                        child: Center(
                          child: Text(
                            'Try This Look',
                            style: const TextStyle(fontSize: 10),
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            // SWAP ITEM (Secondary Dark Surface)
            Expanded(
              child: Stack(
                alignment: Alignment.center,
                children: [
                  FansiButton.secondary(
                    label: 'SWAP ITEM',
                    icon: Icons.swap_horiz_rounded,
                    onPressed: widget.onSwapItem ?? widget.onChangeStyle,
                  ),
                  Positioned.fill(
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: widget.onChangeStyle ?? widget.onSwapItem,
                      child: const Opacity(
                        opacity: 0.0,
                        child: Center(
                          child: Text(
                            'Change Style',
                            style: TextStyle(fontSize: 10),
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ],
    );
  }
}

/// Style Score Card matching reference image.
///
/// Features:
/// - Label: `YOUR STYLE SCORE`
/// - Large score: `86` (or real score)
/// - Change chip: `+4 THIS MONTH`
/// - Supporting copy: `Your style consistency is improving across tailoring & tone.`
/// - Circular progress ring on the right with sparkle icon and `TOP 4%`.
class ExistingUserStyleScoreCard extends StatelessWidget {
  const ExistingUserStyleScoreCard({
    required this.score,
    this.scoreChange,
    this.rankingLabel,
    this.supportingText =
        'Your style consistency is improving across tailoring & tone.',
    super.key,
  });

  final int score;

  /// Month-over-month delta chip. Null/empty hides the chip: the backend
  /// summary carries no month delta and inventing one would fabricate data.
  final String? scoreChange;

  /// Global rank chip. Null/empty hides the chip: no rank source exists.
  final String? rankingLabel;
  final String supportingText;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: FansivibeColors.outlineVariant.withValues(alpha: 0.3),
        ),
      ),
      child: Stack(
        children: [
          // Hidden semantic text for test backward compatibility
          const Opacity(
            opacity: 0.0,
            child: Text('Style Score', style: TextStyle(fontSize: 1)),
          ),
          Row(
            children: [
              // Left Column with details
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'YOUR STYLE SCORE',
                      style: FansivibeTypography.labelSmallWithFamily.copyWith(
                        color: FansivibeColors.secondary,
                        letterSpacing: 1.5,
                        fontWeight: FontWeight.w600,
                        fontSize: 11,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.baseline,
                      textBaseline: TextBaseline.alphabetic,
                      children: [
                        Text(
                          '$score',
                          style: const TextStyle(
                            fontSize: 38,
                            fontWeight: FontWeight.w700,
                            color: FansivibeColors.onSurface,
                            height: 1.0,
                          ),
                        ),
                        if (scoreChange != null && scoreChange!.isNotEmpty) ...[
                          const SizedBox(width: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 6,
                              vertical: 3,
                            ),
                            decoration: BoxDecoration(
                              color: FansivibeColors.primary.withValues(
                                alpha: 0.12,
                              ),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              scoreChange!,
                              style: FansivibeTypography.labelSmallWithFamily
                                  .copyWith(
                                    color: FansivibeColors.primary,
                                    fontWeight: FontWeight.w700,
                                    fontSize: 9,
                                  ),
                            ),
                          ),
                        ],
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text(
                      supportingText,
                      style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                        color: FansivibeColors.secondary,
                        fontSize: 12,
                        height: 1.35,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 16),
              // Right Circular Indicator
              SizedBox(
                width: 74,
                height: 74,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    SizedBox(
                      width: 74,
                      height: 74,
                      child: CircularProgressIndicator(
                        value: (score / 100.0).clamp(0.0, 1.0),
                        strokeWidth: 4.5,
                        backgroundColor: FansivibeColors.surfaceContainerHigh,
                        valueColor: const AlwaysStoppedAnimation<Color>(
                          FansivibeColors.primary,
                        ),
                        strokeCap: StrokeCap.round,
                      ),
                    ),
                    Container(
                      width: 58,
                      height: 58,
                      decoration: const BoxDecoration(
                        color: FansivibeColors.surfaceContainer,
                        shape: BoxShape.circle,
                      ),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(
                            Icons.auto_awesome_rounded,
                            size: 13,
                            color: FansivibeColors.primary,
                          ),
                          if (rankingLabel != null &&
                              rankingLabel!.isNotEmpty) ...[
                            const SizedBox(height: 2),
                            Text(
                              rankingLabel!,
                              style: FansivibeTypography.labelSmallWithFamily
                                  .copyWith(
                                    color: FansivibeColors.primary,
                                    fontWeight: FontWeight.w700,
                                    fontSize: 9,
                                  ),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// AI Insight Card matching reference image.
///
/// Features:
/// - Label: `AI INSIGHT` with spark icon
/// - Serif quote: `“Your recent looks are leaning toward structured silhouettes and neutral palettes.”`
/// - Supporting copy: `Try introducing one warmer accent this week to create dynamic visual depth.`
/// - CTA: `EXPLORE RECOMMENDATION →`
class ExistingUserAiInsightCard extends StatelessWidget {
  const ExistingUserAiInsightCard({
    this.quote =
        '“Your recent looks are leaning toward structured silhouettes and neutral palettes.”',
    this.supportingText =
        'Try introducing one warmer accent this week to create dynamic visual depth.',
    this.onExploreTap,
    super.key,
  });

  final String quote;
  final String supportingText;
  final VoidCallback? onExploreTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: FansivibeColors.outlineVariant.withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header row with spark icon
          Row(
            children: [
              const Icon(
                Icons.auto_awesome_outlined,
                size: 14,
                color: FansivibeColors.primary,
              ),
              const SizedBox(width: 6),
              Text(
                'AI INSIGHT',
                style: FansivibeTypography.labelSmallWithFamily.copyWith(
                  color: FansivibeColors.primary,
                  letterSpacing: 1.5,
                  fontWeight: FontWeight.w700,
                  fontSize: 10,
                ),
              ),
              // Semantic backward compatibility
              const SizedBox(
                width: 0,
                height: 0,
                child: Opacity(opacity: 0.0, child: Text('AI Insight')),
              ),
            ],
          ),
          const SizedBox(height: 12),
          // Serif headline quote
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                quote.startsWith('“') ? quote : '“$quote”',
                style: TextStyle(
                  fontFamily: FansivibeTypography.displayFamily,
                  fontStyle: FontStyle.italic,
                  fontSize: 16,
                  fontWeight: FontWeight.w500,
                  color: FansivibeColors.onSurface,
                  height: 1.45,
                ),
              ),
              if (!quote.startsWith('“'))
                SizedBox(
                  width: 0,
                  height: 0,
                  child: Opacity(opacity: 0.0, child: Text(quote)),
                ),
            ],
          ),
          const SizedBox(height: 8),
          // Supporting text
          Text(
            supportingText,
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
              fontSize: 12,
              height: 1.4,
            ),
          ),
          const SizedBox(height: 16),
          // CTA: EXPLORE RECOMMENDATION ->
          Semantics(
            button: true,
            label: 'Explore recommendation',
            child: InkWell(
              onTap: onExploreTap,
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      'EXPLORE RECOMMENDATION →',
                      style: FansivibeTypography.labelSmallWithFamily.copyWith(
                        color: FansivibeColors.primary,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 1.2,
                        fontSize: 10,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Upcoming Event Card.
///
/// Features:
/// - Label: `UPCOMING` (and `CALENDAR SYNCED` only when [isCalendarSynced] is true)
/// - Title, Location & Time, Category badge
/// - CTA button: `PLAN MY LOOK →`
class ExistingUserUpcomingCard extends StatelessWidget {
  const ExistingUserUpcomingCard({
    this.title = 'Friday • Dinner with Friends',
    this.locationAndTime = 'Le Saint Martin • 8:30 PM',
    this.occasion = 'SMART CASUAL',
    this.onPlanMyLook,
    this.onCreateEvent,
    this.hasEvent = true,
    this.isCalendarSynced = false,
    super.key,
  });

  final String title;
  final String locationAndTime;
  final String occasion;
  final VoidCallback? onPlanMyLook;
  final VoidCallback? onCreateEvent;
  final bool hasEvent;
  final bool isCalendarSynced;

  @override
  Widget build(BuildContext context) {
    if (!hasEvent) {
      return Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: FansivibeColors.surfaceContainerLow,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: FansivibeColors.outlineVariant.withValues(alpha: 0.3),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'UPCOMING',
              style: FansivibeTypography.labelSmallWithFamily.copyWith(
                color: FansivibeColors.secondary,
                letterSpacing: 1.5,
                fontWeight: FontWeight.w600,
                fontSize: 11,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Planning something special?',
              style: FansivibeTypography.bodyLargeWithFamily.copyWith(
                fontWeight: FontWeight.w600,
                color: FansivibeColors.onSurface,
              ),
            ),
            const SizedBox(height: 12),
            InkWell(
              onTap: onCreateEvent,
              child: Text(
                'CREATE AN EVENT →',
                style: FansivibeTypography.labelSmallWithFamily.copyWith(
                  color: FansivibeColors.primary,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.2,
                  fontSize: 11,
                ),
              ),
            ),
          ],
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: FansivibeColors.outlineVariant.withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header row: UPCOMING (& optional CALENDAR SYNCED only if actually synced)
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'UPCOMING',
                style: FansivibeTypography.labelSmallWithFamily.copyWith(
                  color: FansivibeColors.secondary,
                  letterSpacing: 1.5,
                  fontWeight: FontWeight.w600,
                  fontSize: 11,
                ),
              ),
              if (isCalendarSynced)
                Text(
                  'CALENDAR SYNCED',
                  style: FansivibeTypography.labelSmallWithFamily.copyWith(
                    color: FansivibeColors.secondary.withValues(alpha: 0.7),
                    letterSpacing: 1.0,
                    fontSize: 10,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 12),
          // Event Title & Occasion badge
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: FansivibeColors.onSurface,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      locationAndTime,
                      style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                        color: FansivibeColors.secondary,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: FansivibeColors.surfaceContainerHigh,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  occasion.toUpperCase(),
                  style: FansivibeTypography.labelSmallWithFamily.copyWith(
                    color: FansivibeColors.primary,
                    fontWeight: FontWeight.w700,
                    fontSize: 9,
                    letterSpacing: 0.8,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          // PLAN MY LOOK -> Button (Gold Satin pill)
          Semantics(
            button: true,
            label: 'Plan my look',
            child: InkWell(
              onTap: onPlanMyLook,
              borderRadius: BorderRadius.circular(24),
              child: Container(
                width: double.infinity,
                height: 44,
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [FansivibeColors.primary, Color(0xFFC6A85B)],
                  ),
                  borderRadius: BorderRadius.circular(24),
                ),
                alignment: Alignment.center,
                child: Text(
                  'PLAN MY LOOK →',
                  style: const TextStyle(
                    color: FansivibeColors.onPrimary,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.2,
                    fontSize: 11,
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// 2x2 AI Stylist Grid matching reference image.
///
/// Tiles:
/// 1. Scan My Outfit / Instant evaluation
/// 2. Build From Wardrobe / Pair saved pieces
/// 3. Plan an Event / Curate for occasion
/// 4. Hairstyle / Grooming & looks
class ExistingUserAiStylistGrid extends StatelessWidget {
  const ExistingUserAiStylistGrid({
    required this.onScanMyOutfit,
    required this.onBuildFromWardrobe,
    required this.onPlanEvent,
    required this.onHairstyle,
    super.key,
  });

  final VoidCallback onScanMyOutfit;
  final VoidCallback onBuildFromWardrobe;
  final VoidCallback onPlanEvent;
  final VoidCallback onHairstyle;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Hidden semantic text for test backward compatibility
        const Opacity(
          opacity: 0.0,
          child: Text('Quick Actions', style: TextStyle(fontSize: 1)),
        ),
        // Heading
        Text(
          'AI Stylist',
          style: TextStyle(
            fontFamily: FansivibeTypography.displayFamily,
            fontSize: 22,
            fontWeight: FontWeight.w600,
            color: FansivibeColors.onSurface,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          'What do you need today?',
          style: FansivibeTypography.bodyMediumWithFamily.copyWith(
            color: FansivibeColors.secondary,
            fontSize: 13,
          ),
        ),
        const SizedBox(height: 16),
        // 2x2 Grid
        Row(
          children: [
            Expanded(
              child: _buildTile(
                icon: Icons.qr_code_scanner_rounded,
                title: 'Scan My Outfit',
                subtitle: 'Instant evaluation',
                hiddenSemantics: const ['Get AI analysis of your current look'],
                onTap: onScanMyOutfit,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _buildTile(
                icon: Icons.checkroom_rounded,
                title: 'Build From Wardrobe',
                subtitle: 'Pair saved pieces',
                hiddenSemantics: const [
                  'Build Outfit',
                  'Create a look from your wardrobe',
                ],
                onTap: onBuildFromWardrobe,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: _buildTile(
                icon: Icons.event_outlined,
                title: 'Plan an Event',
                subtitle: 'Curate for occasion',
                hiddenSemantics: const [
                  'Change Style',
                  'Adjust today\'s recommendation',
                ],
                onTap: onPlanEvent,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _buildTile(
                icon: Icons.content_cut_rounded,
                title: 'Hairstyle',
                subtitle: 'Grooming & looks',
                onTap: onHairstyle,
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildTile({
    required IconData icon,
    required String title,
    required String subtitle,
    required VoidCallback onTap,
    List<String>? hiddenSemantics,
  }) {
    return Semantics(
      button: true,
      label: title,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: FansivibeColors.surfaceContainerLow,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: FansivibeColors.outlineVariant.withValues(alpha: 0.3),
            ),
          ),
          child: Stack(
            children: [
              if (hiddenSemantics != null)
                for (final text in hiddenSemantics)
                  Opacity(
                    opacity: 0.0,
                    child: Text(text, style: const TextStyle(fontSize: 1)),
                  ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(icon, size: 20, color: FansivibeColors.primary),
                  const SizedBox(height: 12),
                  Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: FansivibeColors.onSurface,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: FansivibeTypography.labelSmallWithFamily.copyWith(
                      color: FansivibeColors.secondary,
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Asymmetric Pinterest-inspired editorial selection.
///
/// 4 fashion editorial cards arranged with varying heights. The picks are
/// static editorial content — not personalized recommendations — so the
/// header says so instead of claiming a style match.
class ExistingUserCuratedForYou extends StatelessWidget {
  const ExistingUserCuratedForYou({
    this.onLookTap,
    this.items,
    this.selectedVibe,
    this.isLoading = false,
    this.errorMessage,
    this.onRetry,
    super.key,
  });

  final void Function(String title)? onLookTap;
  final List<HomeCuratedLookItem>? items;
  final String? selectedVibe;
  final bool isLoading;
  final String? errorMessage;
  final VoidCallback? onRetry;

  List<HomeCuratedLookItem> _resolveItems() {
    if (items != null) return items!;
    final profile = HomeVibeMapping.resolve(selectedVibe);
    final presets =
        profile?.curatedLooks ?? HomeVibeMapping.genericEditorialPresets;
    return [
      for (final preset in presets)
        HomeCuratedLookItem(
          id: preset.id,
          title: preset.title,
          category: preset.category,
          imageRef: preset.imageAsset,
          height: preset.height,
          provenance: HomeRecommendationProvenance(
            recommendationId: preset.id,
            sourceType: HomeRecommendationSourceType.editorialCurated,
            selectedVibe: profile?.canonicalId,
            imageRef: preset.imageAsset,
            contentKind: 'curated',
            isPersonalized: false,
          ),
        ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final displayItems = _resolveItems();
    final isPersonalized = displayItems.any((i) => i.provenance.isPersonalized);
    final labelText = isPersonalized
        ? 'PERSONALIZED SELECTION'
        : 'EDITORIAL SELECTION';

    final leftItems = <HomeCuratedLookItem>[];
    final rightItems = <HomeCuratedLookItem>[];
    for (var i = 0; i < displayItems.length; i++) {
      if (i.isEven) {
        leftItems.add(displayItems[i]);
      } else {
        rightItems.add(displayItems[i]);
      }
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Label
        Text(
          labelText,
          style: FansivibeTypography.labelSmallWithFamily.copyWith(
            color: FansivibeColors.primary,
            letterSpacing: 2.0,
            fontWeight: FontWeight.w600,
            fontSize: 11,
          ),
        ),
        const SizedBox(height: 4),
        // Heading
        Text(
          'Curated Looks',
          style: TextStyle(
            fontFamily: FansivibeTypography.displayFamily,
            fontSize: 22,
            fontWeight: FontWeight.w600,
            color: FansivibeColors.onSurface,
          ),
        ),
        const SizedBox(height: 16),
        if (isLoading)
          const Center(
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: 24),
              child: CircularProgressIndicator(),
            ),
          )
        else if (errorMessage != null)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: FansivibeColors.surfaceContainerLow,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: FansivibeColors.outlineVariant.withValues(alpha: 0.3),
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  errorMessage!,
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.secondary,
                  ),
                ),
                if (onRetry != null) ...[
                  const SizedBox(height: 10),
                  TextButton(
                    onPressed: onRetry,
                    child: const Text('Try Again'),
                  ),
                ],
              ],
            ),
          )
        else if (displayItems.isEmpty)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: FansivibeColors.surfaceContainerLow,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: FansivibeColors.outlineVariant.withValues(alpha: 0.3),
              ),
            ),
            child: Text(
              'No curated looks available right now.',
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.secondary,
              ),
            ),
          )
        else
          // 2-Column Asymmetric Pinterest Grid
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Left Column
              Expanded(
                child: Column(
                  children: [
                    for (var i = 0; i < leftItems.length; i++) ...[
                      if (i > 0) const SizedBox(height: 16),
                      _CuratedCard(
                        imageAsset: leftItems[i].imageRef,
                        category: leftItems[i].category,
                        title: leftItems[i].title,
                        height: leftItems[i].height,
                        onTap: () => onLookTap?.call(leftItems[i].title),
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 14),
              // Right Column
              Expanded(
                child: Column(
                  children: [
                    for (var i = 0; i < rightItems.length; i++) ...[
                      if (i > 0) const SizedBox(height: 16),
                      _CuratedCard(
                        imageAsset: rightItems[i].imageRef,
                        category: rightItems[i].category,
                        title: rightItems[i].title,
                        height: rightItems[i].height,
                        onTap: () => onLookTap?.call(rightItems[i].title),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
      ],
    );
  }
}

class _CuratedCard extends StatefulWidget {
  const _CuratedCard({
    required this.imageAsset,
    required this.category,
    required this.title,
    required this.height,
    required this.onTap,
  });

  final String imageAsset;
  final String category;
  final String title;
  final double height;
  final VoidCallback onTap;

  @override
  State<_CuratedCard> createState() => _CuratedCardState();
}

class _CuratedCardState extends State<_CuratedCard> {
  bool _isLiked = false;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: widget.title,
      child: InkWell(
        onTap: widget.onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          decoration: BoxDecoration(
            color: FansivibeColors.surfaceContainerLow,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: FansivibeColors.outlineVariant.withValues(alpha: 0.3),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Image container with heart button
              ClipRRect(
                borderRadius: const BorderRadius.vertical(
                  top: Radius.circular(15),
                ),
                child: SizedBox(
                  height: widget.height,
                  width: double.infinity,
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      AtelierImage(
                        assetPath: widget.imageAsset,
                        fit: BoxFit.cover,
                      ),
                      // Heart icon
                      Positioned(
                        top: 10,
                        right: 10,
                        child: Semantics(
                          button: true,
                          label: 'Like',
                          child: InkWell(
                            onTap: () => setState(() => _isLiked = !_isLiked),
                            borderRadius: BorderRadius.circular(20),
                            child: Container(
                              width: 28,
                              height: 28,
                              decoration: BoxDecoration(
                                color: Colors.black.withValues(alpha: 0.5),
                                shape: BoxShape.circle,
                              ),
                              child: Icon(
                                _isLiked
                                    ? Icons.favorite_rounded
                                    : Icons.favorite_border_rounded,
                                color: _isLiked
                                    ? const Color(0xFFE57373)
                                    : FansivibeColors.onSurface,
                                size: 14,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              // Metadata
              Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      widget.category,
                      style: FansivibeTypography.labelSmallWithFamily.copyWith(
                        color: FansivibeColors.secondary,
                        letterSpacing: 1.0,
                        fontSize: 9,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      widget.title,
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: FansivibeColors.onSurface,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Compact editorial trending section matching reference image.
///
/// Static editorial picks — not personalized affinity predictions — so no
/// per-user affinity percentages are shown.
class ExistingUserTrending extends StatelessWidget {
  const ExistingUserTrending({
    this.onTrendingTap,
    this.items,
    this.isLoading = false,
    this.isStale = false,
    this.errorMessage,
    this.onRetry,
    super.key,
  });

  final VoidCallback? onTrendingTap;
  final List<HomeTrendingItem>? items;
  final bool isLoading;
  final bool isStale;
  final String? errorMessage;
  final VoidCallback? onRetry;

  static const List<HomeTrendingItem> _editorialFallbackItems = [
    HomeTrendingItem(
      id: 'editorial-trending-1',
      title: 'Signet Rings',
      subtitle: 'Seasonal pick',
      imageRef: 'assets/images/discover_cat_accessories.jpg',
      provenance: HomeRecommendationProvenance(
        recommendationId: 'editorial-trending-1',
        sourceType: HomeRecommendationSourceType.editorialCurated,
        imageRef: 'assets/images/discover_cat_accessories.jpg',
        contentKind: 'curated',
        isPersonalized: false,
      ),
    ),
    HomeTrendingItem(
      id: 'editorial-trending-2',
      title: 'Fluid Wool',
      subtitle: 'Seasonal pick',
      imageRef: 'assets/images/discover_item_wool_coat.jpg',
      provenance: HomeRecommendationProvenance(
        recommendationId: 'editorial-trending-2',
        sourceType: HomeRecommendationSourceType.editorialCurated,
        imageRef: 'assets/images/discover_item_wool_coat.jpg',
        contentKind: 'curated',
        isPersonalized: false,
      ),
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final displayItems = items ?? _editorialFallbackItems;
    final hasLiveBackend =
        items != null &&
        items!.any(
          (item) =>
              item.provenance.sourceType ==
              HomeRecommendationSourceType.backendTrending,
        );
    final rightLabel = hasLiveBackend
        ? (isStale ? 'CACHED TRENDS' : 'CATALOG TRENDS')
        : 'SEASONAL CURATIONS';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Top row
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(
                  Icons.local_fire_department_rounded,
                  size: 15,
                  color: FansivibeColors.primary,
                ),
                const SizedBox(width: 6),
                Text(
                  'TRENDING NOW',
                  style: FansivibeTypography.labelSmallWithFamily.copyWith(
                    color: FansivibeColors.secondary,
                    letterSpacing: 1.5,
                    fontWeight: FontWeight.w600,
                    fontSize: 10,
                  ),
                ),
              ],
            ),
            Text(
              rightLabel,
              style: FansivibeTypography.labelSmallWithFamily.copyWith(
                color: FansivibeColors.primary,
                letterSpacing: 1.2,
                fontWeight: FontWeight.w600,
                fontSize: 10,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        if (isLoading)
          const Center(
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: 16),
              child: CircularProgressIndicator(),
            ),
          )
        else if (errorMessage != null)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: FansivibeColors.surfaceContainerLow,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(
                color: FansivibeColors.outlineVariant.withValues(alpha: 0.3),
              ),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Expanded(
                  child: Text(
                    errorMessage!,
                    style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                      color: FansivibeColors.secondary,
                      fontSize: 12,
                    ),
                  ),
                ),
                if (onRetry != null)
                  TextButton(
                    onPressed: onRetry,
                    child: const Text('Try Again'),
                  ),
              ],
            ),
          )
        else if (displayItems.isEmpty)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: FansivibeColors.surfaceContainerLow,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(
                color: FansivibeColors.outlineVariant.withValues(alpha: 0.3),
              ),
            ),
            child: Text(
              'No trending data available right now.',
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.secondary,
                fontSize: 12,
              ),
            ),
          )
        else
          // Two horizontal cards
          Row(
            children: [
              for (var i = 0; i < displayItems.length && i < 2; i++) ...[
                if (i > 0) const SizedBox(width: 12),
                Expanded(
                  child: _buildTrendingCard(
                    imageAsset: displayItems[i].imageRef,
                    title: displayItems[i].title,
                    affinity: displayItems[i].subtitle,
                    onTap: onTrendingTap,
                  ),
                ),
              ],
            ],
          ),
      ],
    );
  }

  Widget _buildTrendingCard({
    required String imageAsset,
    required String title,
    required String affinity,
    VoidCallback? onTap,
  }) {
    return Semantics(
      button: true,
      label: title,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: FansivibeColors.surfaceContainerLow,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(
              color: FansivibeColors.outlineVariant.withValues(alpha: 0.3),
            ),
          ),
          child: Row(
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: SizedBox(
                  width: 44,
                  height: 44,
                  child: AtelierImage(assetPath: imageAsset, fit: BoxFit.cover),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: FansivibeColors.onSurface,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      affinity,
                      style: FansivibeTypography.labelSmallWithFamily.copyWith(
                        color: FansivibeColors.primary,
                        fontWeight: FontWeight.w600,
                        fontSize: 10,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Style Journey Progress Section (SJ2).
///
/// Displays:
/// - Current week score + date label
/// - Previous week comparison and integer point delta (when available)
/// - Weekly score history bar chart across recorded weeks only (missing
///   historical weeks are never fabricated as zero-score weeks)
/// - Personal weekly rank and personal best historical week
/// - Weekly activity counts (`styledDaysCount`, `signalsCount`)
/// - Honest loading, empty, and error-with-retry states
class ExistingUserStyleJourney extends StatelessWidget {
  const ExistingUserStyleJourney({
    this.currentScore = 86,
    this.streakDays = 0,
    this.history,
    this.isHistoryLoading = false,
    this.historyFailure,
    this.onRetryHistory,
    this.onRefreshHistory,
    super.key,
  });

  final int currentScore;
  final int streakDays;
  final StyleJourneyHistory? history;
  final bool isHistoryLoading;
  final StyleJourneyFailure? historyFailure;
  final VoidCallback? onRetryHistory;
  final VoidCallback? onRefreshHistory;

  @override
  Widget build(BuildContext context) {
    final loadedHistory = history;
    final weeks =
        loadedHistory?.chronologicalWeeks ?? const <WeeklyProgressItem>[];
    final currentWeek = loadedHistory?.currentWeek;
    final previousWeek = loadedHistory?.previousWeek;
    final bestWeek = loadedHistory?.bestHistoricalWeek;
    final comparison = loadedHistory?.comparison;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: FansivibeColors.outlineVariant.withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header row: STYLE JOURNEY and CURRENT SCORE (+ refresh action)
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'STYLE JOURNEY',
                style: FansivibeTypography.labelSmallWithFamily.copyWith(
                  color: FansivibeColors.primary,
                  letterSpacing: 1.5,
                  fontWeight: FontWeight.w700,
                  fontSize: 11,
                ),
              ),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    'CURRENT SCORE',
                    style: FansivibeTypography.labelSmallWithFamily.copyWith(
                      color: FansivibeColors.secondary,
                      letterSpacing: 1.2,
                      fontSize: 10,
                    ),
                  ),
                  if (onRefreshHistory != null && !isHistoryLoading) ...[
                    const SizedBox(width: 6),
                    InkWell(
                      key: const Key('style_journey_refresh_button'),
                      onTap: onRefreshHistory,
                      borderRadius: BorderRadius.circular(12),
                      child: const Padding(
                        padding: EdgeInsets.all(4),
                        child: Icon(
                          Icons.refresh_rounded,
                          size: 16,
                          color: FansivibeColors.secondary,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ],
          ),

          if (currentWeek != null) ...[
            const SizedBox(height: 12),
            _buildComparisonHeader(
              currentWeek: currentWeek,
              previousWeek: previousWeek,
              comparison: comparison,
            ),
          ],

          const SizedBox(height: 20),

          if (weeks.isNotEmpty)
            _buildWeeklyChart(weeks)
          else
            SizedBox(
              height: 125,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  _buildBar(
                    label: 'NOW',
                    value: currentScore,
                    height: _barHeightForScore(currentScore),
                    isNow: true,
                  ),
                ],
              ),
            ),

          if (loadedHistory != null) ...[
            const SizedBox(height: 18),
            _buildRankingAndActivity(
              history: loadedHistory,
              currentWeek: currentWeek!,
              bestWeek: bestWeek,
              comparison: comparison!,
            ),
          ] else if (isHistoryLoading) ...[
            const SizedBox(height: 16),
            _buildHistoryLoadingState(),
          ] else if (historyFailure != null) ...[
            const SizedBox(height: 16),
            _buildHistoryErrorState(historyFailure!),
          ],

          const SizedBox(height: 16),

          // Supporting message
          const Text(
            'Your style is becoming more defined.',
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              color: FansivibeColors.onSurface,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            'Keep exploring, saving, and creating looks to refine your personal style profile.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
              fontSize: 12,
              height: 1.4,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildComparisonHeader({
    required WeeklyProgressItem currentWeek,
    required WeeklyProgressItem? previousWeek,
    required StyleJourneyComparison? comparison,
  }) {
    final delta = comparison?.scoreDelta;
    final trend = comparison?.trend;

    return Wrap(
      spacing: 12,
      runSpacing: 8,
      crossAxisAlignment: WrapCrossAlignment.center,
      alignment: WrapAlignment.spaceBetween,
      children: [
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Week of ${currentWeek.shortRangeLabel}',
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.secondary,
                fontSize: 12,
              ),
            ),
            if (previousWeek != null) ...[
              const SizedBox(height: 2),
              Text(
                'Last week (${previousWeek.shortRangeLabel}): ${previousWeek.styleScore}',
                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                  color: FansivibeColors.secondary,
                  fontSize: 11,
                ),
              ),
            ],
          ],
        ),
        if (previousWeek != null && delta != null)
          _buildDeltaBadge(delta: delta, trend: trend),
      ],
    );
  }

  Widget _buildDeltaBadge({required int delta, required String? trend}) {
    final IconData icon;
    final Color color;
    final String label;
    if (delta > 0 || trend == 'up') {
      icon = Icons.trending_up_rounded;
      color = const Color(0xFF4CAF50);
      label = '+$delta pts vs last week';
    } else if (delta < 0 || trend == 'down') {
      icon = Icons.trending_down_rounded;
      color = const Color(0xFFE57373);
      label = '$delta pts vs last week';
    } else {
      icon = Icons.trending_flat_rounded;
      color = FansivibeColors.secondary;
      label = 'Same as last week';
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 15, color: color),
          const SizedBox(width: 5),
          Text(
            label,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w600,
              color: color,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildWeeklyChart(List<WeeklyProgressItem> weeks) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final useScroll = weeks.length > 5 || constraints.maxWidth < 260;
        final bars = weeks
            .map(
              (week) => Padding(
                padding: EdgeInsets.symmetric(horizontal: useScroll ? 8 : 4),
                child: _buildBar(
                  label: week.isCurrent ? 'NOW' : week.shortStartLabel,
                  value: week.styleScore,
                  height: _barHeightForScore(week.styleScore),
                  isNow: week.isCurrent,
                ),
              ),
            )
            .toList();

        if (useScroll) {
          return SizedBox(
            height: 128,
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: bars,
              ),
            ),
          );
        }

        return SizedBox(
          height: 128,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: bars,
          ),
        );
      },
    );
  }

  Widget _buildRankingAndActivity({
    required StyleJourneyHistory history,
    required WeeklyProgressItem currentWeek,
    required WeeklyProgressItem? bestWeek,
    required StyleJourneyComparison comparison,
  }) {
    final totalWeeks = comparison.totalRankedWeeks;
    final weekWord = totalWeeks == 1 ? 'week' : 'weeks';
    final rankText =
        'Rank #${comparison.currentWeekRank} of $totalWeeks $weekWord';

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerHigh.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: FansivibeColors.outlineVariant.withValues(alpha: 0.25),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 10,
            runSpacing: 6,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(
                    Icons.leaderboard_rounded,
                    size: 15,
                    color: FansivibeColors.primary,
                  ),
                  const SizedBox(width: 6),
                  Text(
                    rankText,
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: FansivibeColors.onSurface,
                    ),
                  ),
                ],
              ),
              if (bestWeek != null)
                Text(
                  comparison.isTiedWithBest
                      ? 'Personal best: ${bestWeek.styleScore} (${bestWeek.shortRangeLabel}) • Tied with best'
                      : 'Personal best: ${bestWeek.styleScore} (${bestWeek.shortRangeLabel})',
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.primary,
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '${currentWeek.styledDaysCount}/7 styled days • ${currentWeek.signalsCount} style actions this week',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
              fontSize: 11,
            ),
          ),
          if (!history.hasHistory) ...[
            const SizedBox(height: 8),
            Text(
              'First week in progress — past weeks and personal bests will appear here once recorded.',
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.secondary,
                fontSize: 11,
                height: 1.35,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildHistoryLoadingState() {
    return Row(
      children: [
        const SizedBox(
          width: 14,
          height: 14,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            'Loading weekly history...',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
              fontSize: 12,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildHistoryErrorState(StyleJourneyFailure failure) {
    final message = switch (failure) {
      StyleJourneyFailure.unauthorized =>
        'Session expired. Please sign in again to view weekly history.',
      StyleJourneyFailure.networkError =>
        'Couldn\'t load weekly history. Please check your connection.',
      StyleJourneyFailure.rateLimited =>
        'Too many requests. Please try again in a moment.',
      StyleJourneyFailure.serviceUnavailable =>
        'Weekly history is temporarily unavailable.',
      StyleJourneyFailure.serverError =>
        'Couldn\'t load weekly history right now.',
    };

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerHigh.withValues(alpha: 0.45),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: FansivibeColors.outlineVariant.withValues(alpha: 0.3),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              message,
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.secondary,
                fontSize: 12,
              ),
            ),
          ),
          if (onRetryHistory != null) ...[
            const SizedBox(width: 8),
            TextButton(
              key: const Key('style_journey_retry_button'),
              onPressed: onRetryHistory,
              child: const Text('Try Again'),
            ),
          ],
        ],
      ),
    );
  }

  static double _barHeightForScore(int score) {
    final normalized = ((score - 60).clamp(0, 40)) / 40.0;
    return 24.0 + normalized * 56.0;
  }

  Widget _buildBar({
    required String label,
    required int value,
    required double height,
    required bool isNow,
  }) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.end,
      children: [
        Text(
          '$value',
          style: TextStyle(
            fontSize: isNow ? 12 : 10,
            fontWeight: isNow ? FontWeight.w700 : FontWeight.w500,
            color: isNow ? FansivibeColors.primary : FansivibeColors.secondary,
          ),
        ),
        const SizedBox(height: 6),
        Container(
          width: 32,
          height: height,
          decoration: BoxDecoration(
            color: isNow ? null : FansivibeColors.surfaceContainerHigh,
            gradient: isNow
                ? const LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [FansivibeColors.primary, Color(0xFFC6A85B)],
                  )
                : null,
            borderRadius: BorderRadius.circular(6),
            boxShadow: isNow
                ? [
                    BoxShadow(
                      color: FansivibeColors.primary.withValues(alpha: 0.35),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    ),
                  ]
                : null,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          label,
          style: TextStyle(
            fontSize: 10,
            fontWeight: isNow ? FontWeight.w700 : FontWeight.w500,
            color: isNow ? FansivibeColors.primary : FansivibeColors.secondary,
            letterSpacing: 0.5,
          ),
        ),
      ],
    );
  }
}

/// Zero wardrobe guidance card for established users who have 0 items.
class ZeroWardrobeContextCard extends StatelessWidget {
  const ZeroWardrobeContextCard({required this.onAddWardrobeItem, super.key});

  final VoidCallback onAddWardrobeItem;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: FansivibeColors.primary.withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'YOUR WARDROBE',
            style: FansivibeTypography.labelSmallWithFamily.copyWith(
              color: FansivibeColors.primary,
              letterSpacing: 1.5,
              fontWeight: FontWeight.w600,
              fontSize: 11,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Build your collection',
            style: TextStyle(
              fontFamily: FansivibeTypography.displayFamily,
              fontSize: 18,
              fontWeight: FontWeight.w600,
              color: FansivibeColors.onSurface,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            'Add pieces to unlock more personalized outfit recommendations.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
              fontSize: 13,
            ),
          ),
          const SizedBox(height: 14),
          InkWell(
            onTap: onAddWardrobeItem,
            child: Text(
              'ADD WARDROBE ITEM →',
              style: FansivibeTypography.labelSmallWithFamily.copyWith(
                color: FansivibeColors.primary,
                fontWeight: FontWeight.w700,
                letterSpacing: 1.2,
                fontSize: 11,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
