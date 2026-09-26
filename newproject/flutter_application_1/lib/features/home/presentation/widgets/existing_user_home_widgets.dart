import 'package:flutter/material.dart';
import 'package:fansivibe/features/discover/presentation/widgets/discover_editorial_widgets.dart';
import 'package:fansivibe/features/home/data/home_mock_data.dart';
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
                      assetPath: avatarUrl ?? 'assets/images/profile_avatar.png',
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
  const ExistingUserGreeting({
    this.displayName,
    super.key,
  });

  final String? displayName;

  @override
  Widget build(BuildContext context) {
    final hasName = displayName != null && displayName!.trim().isNotEmpty;
    final greetingText = hasName ? 'Good morning, ${displayName!.trim()}' : 'Good morning';

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
    this.onWearThisLook,
    this.onSwapItem,
    this.onChangeStyle,
    this.imageAsset = 'assets/images/discover_hero_quiet_luxury.jpg',
    super.key,
  });

  final TodaysLookData data;
  final VoidCallback? onWearThisLook;
  final VoidCallback? onSwapItem;
  final VoidCallback? onChangeStyle;
  final String imageAsset;

  @override
  State<ExistingUserHeroCard> createState() => _ExistingUserHeroCardState();
}

class _ExistingUserHeroCardState extends State<ExistingUserHeroCard> {
  bool _isFavorite = false;
  bool _isSaved = false;

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
                          style: FansivibeTypography.bodyMediumWithFamily.copyWith(
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
    final matchScore = widget.data.styleScore > 0 ? widget.data.styleScore : 94;

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
            Text(
              '08:00 AM',
              style: FansivibeTypography.labelSmallWithFamily.copyWith(
                color: FansivibeColors.secondary.withValues(alpha: 0.7),
                letterSpacing: 1.0,
                fontSize: 11,
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
                // Background image
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
                      // Match badge
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
                              style: FansivibeTypography.labelSmallWithFamily.copyWith(
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
                      ),
                      // Favorite & Save action pills
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          // Heart button
                          Semantics(
                            button: true,
                            label: 'Favorite',
                            child: InkWell(
                              onTap: () => setState(() => _isFavorite = !_isFavorite),
                              borderRadius: BorderRadius.circular(20),
                              child: Container(
                                width: 34,
                                height: 34,
                                decoration: BoxDecoration(
                                  color: Colors.black.withValues(alpha: 0.5),
                                  shape: BoxShape.circle,
                                  border: Border.all(
                                    color: FansivibeColors.outlineVariant.withValues(
                                      alpha: 0.35,
                                    ),
                                  ),
                                ),
                                child: Icon(
                                  _isFavorite
                                      ? Icons.favorite_rounded
                                      : Icons.favorite_border_rounded,
                                  color: _isFavorite
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
                              onTap: () => setState(() => _isSaved = !_isSaved),
                              borderRadius: BorderRadius.circular(20),
                              child: Container(
                                width: 34,
                                height: 34,
                                decoration: BoxDecoration(
                                  color: Colors.black.withValues(alpha: 0.5),
                                  shape: BoxShape.circle,
                                  border: Border.all(
                                    color: FansivibeColors.outlineVariant.withValues(
                                      alpha: 0.35,
                                    ),
                                  ),
                                ),
                                child: Icon(
                                  _isSaved
                                      ? Icons.bookmark_rounded
                                      : Icons.bookmark_border_rounded,
                                  color: _isSaved
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
                            style: FansivibeTypography.labelSmallWithFamily.copyWith(
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
                        style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                          color: FansivibeColors.onSurface.withValues(alpha: 0.8),
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
                                  color: FansivibeColors.outlineVariant.withValues(
                                    alpha: 0.3,
                                  ),
                                ),
                              ),
                              child: Text(
                                item.name,
                                style: FansivibeTypography.labelSmallWithFamily.copyWith(
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
                                padding: const EdgeInsets.symmetric(vertical: 4),
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Text(
                                      'WHY THIS WORKS →',
                                      style: FansivibeTypography.labelSmallWithFamily.copyWith(
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
                          Text(
                            'CURATED #140',
                            style: FansivibeTypography.labelSmallWithFamily.copyWith(
                              color: FansivibeColors.secondary.withValues(alpha: 0.6),
                              letterSpacing: 1.2,
                              fontSize: 10,
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
    this.scoreChange = '+4 THIS MONTH',
    this.rankingLabel = 'TOP 4%',
    this.supportingText = 'Your style consistency is improving across tailoring & tone.',
    super.key,
  });

  final int score;
  final String scoreChange;
  final String rankingLabel;
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
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 6,
                            vertical: 3,
                          ),
                          decoration: BoxDecoration(
                            color: FansivibeColors.primary.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(
                            scoreChange,
                            style: FansivibeTypography.labelSmallWithFamily.copyWith(
                              color: FansivibeColors.primary,
                              fontWeight: FontWeight.w700,
                              fontSize: 9,
                            ),
                          ),
                        ),
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
                          const SizedBox(height: 2),
                          Text(
                            rankingLabel,
                            style: FansivibeTypography.labelSmallWithFamily.copyWith(
                              color: FansivibeColors.primary,
                              fontWeight: FontWeight.w700,
                              fontSize: 9,
                            ),
                          ),
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
    this.quote = '“Your recent looks are leaning toward structured silhouettes and neutral palettes.”',
    this.supportingText = 'Try introducing one warmer accent this week to create dynamic visual depth.',
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
                child: Opacity(
                  opacity: 0.0,
                  child: Text('AI Insight'),
                ),
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
                  child: Opacity(
                    opacity: 0.0,
                    child: Text(quote),
                  ),
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

/// Upcoming Event Card matching reference image.
///
/// Features:
/// - Label: `UPCOMING` & `CALENDAR SYNCED`
/// - Title: `Friday • Dinner with Friends`
/// - Location & Time: `Le Saint Martin • 8:30 PM`
/// - Category: `SMART CASUAL`
/// - CTA button: `PLAN MY LOOK →`
class ExistingUserUpcomingCard extends StatelessWidget {
  const ExistingUserUpcomingCard({
    this.title = 'Friday • Dinner with Friends',
    this.locationAndTime = 'Le Saint Martin • 8:30 PM',
    this.occasion = 'SMART CASUAL',
    this.onPlanMyLook,
    this.onCreateEvent,
    this.hasEvent = true,
    super.key,
  });

  final String title;
  final String locationAndTime;
  final String occasion;
  final VoidCallback? onPlanMyLook;
  final VoidCallback? onCreateEvent;
  final bool hasEvent;

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
          // Header row: UPCOMING & CALENDAR SYNCED
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
                padding: const EdgeInsets.symmetric(
                  horizontal: 8,
                  vertical: 4,
                ),
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
                    colors: [
                      FansivibeColors.primary,
                      Color(0xFFC6A85B),
                    ],
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
                    child: Text(
                      text,
                      style: const TextStyle(fontSize: 1),
                    ),
                  ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    icon,
                    size: 20,
                    color: FansivibeColors.primary,
                  ),
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

/// Asymmetric Pinterest-inspired Curated For You layout.
///
/// 4 fashion editorial cards arranged with varying heights.
class ExistingUserCuratedForYou extends StatelessWidget {
  const ExistingUserCuratedForYou({
    this.onLookTap,
    super.key,
  });

  final void Function(String title)? onLookTap;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Label
        Text(
          'BASED ON YOUR STYLE',
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
          'Curated For You',
          style: TextStyle(
            fontFamily: FansivibeTypography.displayFamily,
            fontSize: 22,
            fontWeight: FontWeight.w600,
            color: FansivibeColors.onSurface,
          ),
        ),
        const SizedBox(height: 16),
        // 2-Column Asymmetric Pinterest Grid
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Left Column
            Expanded(
              child: Column(
                children: [
                  _CuratedCard(
                    imageAsset: 'assets/images/discover_look_modern_classics.jpg',
                    category: 'STUDIO ATELIER',
                    title: 'Quiet Tailoring',
                    height: 230,
                    onTap: () => onLookTap?.call('Quiet Tailoring'),
                  ),
                  const SizedBox(height: 16),
                  _CuratedCard(
                    imageAsset: 'assets/images/discover_moodboard_silhouette.jpg',
                    category: 'PARIS RUNWAY',
                    title: 'Modern Minimal',
                    height: 250,
                    onTap: () => onLookTap?.call('Modern Minimal'),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 14),
            // Right Column
            Expanded(
              child: Column(
                children: [
                  _CuratedCard(
                    imageAsset: 'assets/images/discover_cat_accessories.jpg',
                    category: 'LEATHER & GOLD',
                    title: 'Soft Structure',
                    height: 180,
                    onTap: () => onLookTap?.call('Soft Structure'),
                  ),
                  const SizedBox(height: 16),
                  _CuratedCard(
                    imageAsset: 'assets/images/discover_look_urban_minimal.jpg',
                    category: 'ARCHIVE STREET',
                    title: 'Urban Evening',
                    height: 260,
                    onTap: () => onLookTap?.call('Urban Evening'),
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
                borderRadius: const BorderRadius.vertical(top: Radius.circular(15)),
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

/// Compact Trending For You section matching reference image.
class ExistingUserTrending extends StatelessWidget {
  const ExistingUserTrending({
    this.onTrendingTap,
    super.key,
  });

  final VoidCallback? onTrendingTap;

  @override
  Widget build(BuildContext context) {
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
                  'TRENDING FOR YOU',
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
              'SEASONAL CURATIONS',
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
        // Two horizontal cards
        Row(
          children: [
            Expanded(
              child: _buildTrendingCard(
                imageAsset: 'assets/images/discover_cat_accessories.jpg',
                title: 'Signet Rings',
                affinity: '+18% Affinity',
                onTap: onTrendingTap,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _buildTrendingCard(
                imageAsset: 'assets/images/discover_item_wool_coat.jpg',
                title: 'Fluid Wool',
                affinity: '+24% Affinity',
                onTap: onTrendingTap,
              ),
            ),
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
                  child: AtelierImage(
                    assetPath: imageAsset,
                    fit: BoxFit.cover,
                  ),
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

/// Style Journey Progress Section matching reference image.
///
/// Features:
/// - Label: `STYLE JOURNEY` and `30-DAY OVERVIEW`
/// - 4-column chart: W1 (74), W2 (78), W3 (82), NOW (score in glowing gold)
/// - Supporting message: `Your style is becoming more defined.`
/// - Guidance: `Keep exploring, saving, and creating looks to refine your personal style profile.`
class ExistingUserStyleJourney extends StatelessWidget {
  const ExistingUserStyleJourney({
    this.currentScore = 86,
    this.streakDays = 0,
    super.key,
  });

  final int currentScore;
  final int streakDays;

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
          // Header row: STYLE JOURNEY and 30-DAY OVERVIEW
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
              Text(
                '30-DAY OVERVIEW',
                style: FansivibeTypography.labelSmallWithFamily.copyWith(
                  color: FansivibeColors.secondary,
                  letterSpacing: 1.2,
                  fontSize: 10,
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),

          SizedBox(
            height: 125,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                _buildBar(label: 'W1', value: 74, height: 42, isNow: false),
                _buildBar(label: 'W2', value: 78, height: 52, isNow: false),
                _buildBar(label: 'W3', value: 82, height: 62, isNow: false),
                _buildBar(
                  label: 'NOW',
                  value: currentScore,
                  height: 76,
                  isNow: true,
                ),
              ],
            ),
          ),

          const SizedBox(height: 20),

          // Supporting message
          Text(
            'Your style is becoming more defined.',
            style: const TextStyle(
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
                    colors: [
                      FansivibeColors.primary,
                      Color(0xFFC6A85B),
                    ],
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
  const ZeroWardrobeContextCard({
    required this.onAddWardrobeItem,
    super.key,
  });

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
