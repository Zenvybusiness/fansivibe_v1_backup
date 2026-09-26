import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// Editorial image widget with smooth loading and resilient fallback.
class AtelierImage extends StatelessWidget {
  const AtelierImage({
    required this.assetPath,
    this.fit = BoxFit.cover,
    this.alignment = Alignment.center,
    this.fallbackIcon = Icons.checkroom_rounded,
    this.height,
    this.width,
    super.key,
  });

  final String assetPath;
  final BoxFit fit;
  final Alignment alignment;
  final IconData fallbackIcon;
  final double? height;
  final double? width;

  @override
  Widget build(BuildContext context) {
    return Image.asset(
      assetPath,
      fit: fit,
      alignment: alignment,
      width: width,
      height: height,
      errorBuilder: (context, error, stackTrace) => Container(
        width: width,
        height: height,
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
          child: Icon(
            fallbackIcon,
            color: FansivibeColors.primary.withValues(alpha: 0.5),
            size: 28,
          ),
        ),
      ),
    );
  }
}

/// The editorial top brand bar matching Trending.jpg and ForYou.jpg.
class DiscoverBrandHeader extends StatelessWidget {
  const DiscoverBrandHeader({
    required this.onNotificationTap,
    required this.onAvatarTap,
    this.displayName,
    super.key,
  });

  final VoidCallback onNotificationTap;
  final VoidCallback onAvatarTap;
  final String? displayName;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        // FANSIVIBE brand wordmark
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
            // Notification bell with badge dot
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
                      assetPath: 'assets/images/profile_avatar.png',
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

/// Editorial Monograph title block: EDITORIAL MONOGRAPH / Discover / subtitle.
class DiscoverMonographTitle extends StatelessWidget {
  const DiscoverMonographTitle({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'EDITORIAL MONOGRAPH',
          style: FansivibeTypography.labelMediumWithFamily.copyWith(
            fontSize: 11,
            fontWeight: FontWeight.w700,
            letterSpacing: 2.0,
            color: FansivibeColors.primary,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          'Discover',
          style: FansivibeTypography.headlineMediumWithFamily.copyWith(
            fontSize: 34,
            fontWeight: FontWeight.w500,
            color: FansivibeColors.onSurface,
            height: 1.15,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          'Fashion inspiration for your next chapter.',
          style: FansivibeTypography.bodyMediumWithFamily.copyWith(
            fontSize: 14,
            color: FansivibeColors.secondary,
            height: 1.4,
          ),
        ),
      ],
    );
  }
}

/// Tonal fashion discovery search bar with filter button.
class DiscoverSearchBarWidget extends StatelessWidget {
  const DiscoverSearchBarWidget({
    required this.controller,
    required this.onChanged,
    required this.onFilterTap,
    this.activeFilterCount = 0,
    this.onClear,
    super.key,
  });

  final TextEditingController controller;
  final ValueChanged<String> onChanged;
  final VoidCallback onFilterTap;
  final int activeFilterCount;
  final VoidCallback? onClear;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 50,
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainer,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.05),
          width: 1,
        ),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 14),
      child: Row(
        children: [
          const Icon(
            Icons.search_rounded,
            color: FansivibeColors.secondary,
            size: 20,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: TextField(
              controller: controller,
              onChanged: onChanged,
              style: FansivibeTypography.bodyLargeWithFamily.copyWith(
                fontSize: 14,
                color: FansivibeColors.onSurface,
              ),
              cursorColor: FansivibeColors.primary,
              decoration: InputDecoration(
                hintText: 'Search outfits, styles, brands...',
                hintStyle: FansivibeTypography.bodyMediumWithFamily.copyWith(
                  fontSize: 14,
                  color: FansivibeColors.secondary.withValues(alpha: 0.65),
                ),
                border: InputBorder.none,
                isDense: true,
                contentPadding: EdgeInsets.zero,
              ),
            ),
          ),
          if (controller.text.isNotEmpty)
            IconButton(
              icon: const Icon(
                Icons.clear_rounded,
                color: FansivibeColors.secondary,
                size: 18,
              ),
              onPressed: onClear,
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
            ),
          const SizedBox(width: 6),
          // Filter control with subtle gold tint
          Semantics(
            button: true,
            label: 'Filter',
            child: InkWell(
              onTap: onFilterTap,
              borderRadius: BorderRadius.circular(10),
              child: Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: FansivibeColors.surfaceContainerHigh,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                    color: activeFilterCount > 0
                        ? FansivibeColors.primary
                        : FansivibeColors.primary.withValues(alpha: 0.25),
                    width: 1,
                  ),
                ),
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    Icon(
                      Icons.tune_rounded,
                      color: activeFilterCount > 0
                          ? FansivibeColors.primary
                          : FansivibeColors.secondary,
                      size: 18,
                    ),
                    if (activeFilterCount > 0)
                      Positioned(
                        top: 5,
                        right: 5,
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
        ],
      ),
    );
  }
}

/// The Discover tab selector: TRENDING vs FOR YOU with gold glowing underline.
class DiscoverEditorialTabBar extends StatelessWidget {
  const DiscoverEditorialTabBar({
    required this.selectedTab,
    required this.onTrendingTap,
    required this.onForYouTap,
    super.key,
  });

  final String selectedTab; // 'trending' or 'forYou'
  final VoidCallback onTrendingTap;
  final VoidCallback onForYouTap;

  @override
  Widget build(BuildContext context) {
    final isTrending = selectedTab == 'trending';

    return Row(
      children: [
        // Trending Tab
        Expanded(
          child: Semantics(
            button: true,
            selected: isTrending,
            label: 'Trending',
            child: InkWell(
              onTap: onTrendingTap,
              splashColor: Colors.transparent,
              highlightColor: Colors.transparent,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Text(
                      'Trending',
                      style: TextStyle(
                        fontFamily: 'Noto Serif',
                        fontSize: 16,
                        fontWeight: isTrending ? FontWeight.w600 : FontWeight.w400,
                        color: isTrending
                            ? FansivibeColors.primary
                            : FansivibeColors.secondary,
                      ),
                    ),
                  ),
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 250),
                    curve: Curves.easeOutCubic,
                    height: 2.5,
                    width: isTrending ? 64 : 0,
                    decoration: BoxDecoration(
                      color: FansivibeColors.primary,
                      borderRadius: BorderRadius.circular(2),
                      boxShadow: isTrending
                          ? [
                              BoxShadow(
                                color: FansivibeColors.primary.withValues(alpha: 0.7),
                                blurRadius: 6,
                                offset: const Offset(0, 1),
                              ),
                            ]
                          : null,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        // For You Tab
        Expanded(
          child: Semantics(
            button: true,
            selected: !isTrending,
            label: 'For You',
            child: InkWell(
              onTap: onForYouTap,
              splashColor: Colors.transparent,
              highlightColor: Colors.transparent,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Text(
                      'For You',
                      style: TextStyle(
                        fontFamily: 'Noto Serif',
                        fontSize: 16,
                        fontWeight: !isTrending ? FontWeight.w600 : FontWeight.w400,
                        color: !isTrending
                            ? FansivibeColors.primary
                            : FansivibeColors.secondary,
                      ),
                    ),
                  ),
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 250),
                    curve: Curves.easeOutCubic,
                    height: 2.5,
                    width: !isTrending ? 64 : 0,
                    decoration: BoxDecoration(
                      color: FansivibeColors.primary,
                      borderRadius: BorderRadius.circular(2),
                      boxShadow: !isTrending
                          ? [
                              BoxShadow(
                                color: FansivibeColors.primary.withValues(alpha: 0.7),
                                blurRadius: 6,
                                offset: const Offset(0, 1),
                              ),
                            ]
                          : null,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

/// Editorial Section Header: [TAG] on left, [ACTION] on right, Title, Subtitle.
class EditorialSectionHeader extends StatelessWidget {
  const EditorialSectionHeader({
    required this.tag,
    required this.title,
    required this.subtitle,
    this.actionLabel = 'SEE ALL →',
    this.onActionTap,
    super.key,
  });

  final String tag;
  final String title;
  final String subtitle;
  final String actionLabel;
  final VoidCallback? onActionTap;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              tag,
              style: FansivibeTypography.labelMediumWithFamily.copyWith(
                fontSize: 11,
                fontWeight: FontWeight.w700,
                letterSpacing: 1.5,
                color: FansivibeColors.primary,
              ),
            ),
            if (actionLabel.isNotEmpty)
              InkWell(
                onTap: onActionTap,
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2, horizontal: 4),
                  child: Text(
                    actionLabel,
                    style: FansivibeTypography.labelMediumWithFamily.copyWith(
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.2,
                      color: FansivibeColors.primary,
                    ),
                  ),
                ),
              ),
          ],
        ),
        const SizedBox(height: 4),
        Text(
          title,
          style: FansivibeTypography.headlineMediumWithFamily.copyWith(
            fontSize: 22,
            fontWeight: FontWeight.w500,
            color: FansivibeColors.onSurface,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          subtitle,
          style: FansivibeTypography.bodyMediumWithFamily.copyWith(
            fontSize: 13,
            color: FansivibeColors.secondary,
            height: 1.35,
          ),
        ),
      ],
    );
  }
}

/// Hero Spotlight Directive Card (Quiet Luxury hero in Trending.jpg).
class SpotlightHeroCard extends StatelessWidget {
  const SpotlightHeroCard({
    required this.onTap,
    super.key,
  });

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: 'Spotlight Directive Quiet Luxury',
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: Container(
          height: 400,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            color: FansivibeColors.surfaceContainerLow,
            border: Border.all(
              color: Colors.white.withValues(alpha: 0.08),
              width: 1,
            ),
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(20),
            child: Stack(
              fit: StackFit.expand,
              children: [
                // Hero fashion photography
                const AtelierImage(
                  assetPath: 'assets/images/discover_hero_quiet_luxury.jpg',
                  fit: BoxFit.cover,
                  alignment: Alignment(0, -0.2),
                ),
                // Top vignette
                Positioned(
                  top: 0,
                  left: 0,
                  right: 0,
                  height: 90,
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          Colors.black.withValues(alpha: 0.6),
                          Colors.transparent,
                        ],
                      ),
                    ),
                  ),
                ),
                // Top trending pill badge
                Positioned(
                  top: 16,
                  left: 16,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 6,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.black.withValues(alpha: 0.55),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                        color: Colors.white.withValues(alpha: 0.15),
                        width: 1,
                      ),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          width: 8,
                          height: 8,
                          decoration: const BoxDecoration(
                            color: FansivibeColors.primary,
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 6),
                        Text(
                          'TRENDING',
                          style: FansivibeTypography.labelSmallWithFamily.copyWith(
                            fontSize: 10,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 1.5,
                            color: Colors.white,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                // Bottom content vignette & details
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  height: 180,
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          Colors.transparent,
                          Colors.black.withValues(alpha: 0.85),
                          Colors.black.withValues(alpha: 0.95),
                        ],
                      ),
                    ),
                    child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Expanded(
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.end,
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'BRUTALIST EDIT',
                                  style: FansivibeTypography.labelSmallWithFamily.copyWith(
                                    fontSize: 10,
                                    fontWeight: FontWeight.w600,
                                    letterSpacing: 1.6,
                                    color: Colors.white70,
                                  ),
                                ),
                                const SizedBox(height: 3),
                                Text(
                                  'SPOTLIGHT DIRECTIVE',
                                  style: FansivibeTypography.labelSmallWithFamily.copyWith(
                                    fontSize: 10,
                                    fontWeight: FontWeight.w700,
                                    letterSpacing: 1.5,
                                    color: FansivibeColors.primary,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  'Quiet Luxury',
                                  style: TextStyle(
                                    fontFamily: 'Noto Serif',
                                    fontSize: 26,
                                    fontWeight: FontWeight.w600,
                                    color: Colors.white,
                                    height: 1.15,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  'Timeless pieces. Modern everyday...',
                                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                                    fontSize: 13,
                                    color: Colors.white.withValues(alpha: 0.85),
                                  ),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(width: 12),
                          // Gold circular action button
                          Container(
                            width: 44,
                            height: 44,
                            decoration: BoxDecoration(
                              color: FansivibeColors.primary,
                              shape: BoxShape.circle,
                              boxShadow: [
                                BoxShadow(
                                  color: FansivibeColors.primary.withValues(alpha: 0.35),
                                  blurRadius: 10,
                                  offset: const Offset(0, 3),
                                ),
                              ],
                            ),
                            child: const Icon(
                              Icons.arrow_forward_rounded,
                              color: Color(0xFF131313),
                              size: 20,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Circular visual category tile for the Atelier Rail.
class CircularCategoryTile extends StatelessWidget {
  const CircularCategoryTile({
    required this.name,
    required this.assetPath,
    required this.onTap,
    this.isSelected = false,
    super.key,
  });

  final String name;
  final String assetPath;
  final VoidCallback onTap;
  final bool isSelected;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: isSelected,
      label: name,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(40),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 68,
                height: 68,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: isSelected
                        ? FansivibeColors.primary
                        : Colors.white.withValues(alpha: 0.15),
                    width: isSelected ? 2 : 1,
                  ),
                  boxShadow: isSelected
                      ? [
                          BoxShadow(
                            color: FansivibeColors.primary.withValues(alpha: 0.4),
                            blurRadius: 8,
                          ),
                        ]
                      : null,
                ),
                child: ClipOval(
                  child: AtelierImage(
                    assetPath: assetPath,
                    fit: BoxFit.cover,
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                name,
                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                  fontSize: 12,
                  fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
                  color: isSelected
                      ? FansivibeColors.primary
                      : FansivibeColors.onSurface,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Editorial Look Card adhering to the 65% image / 35% content card rule.
class EditorialLookCard extends StatelessWidget {
  const EditorialLookCard({
    required this.id,
    required this.title,
    required this.subtitle,
    required this.savesCount,
    required this.imageAsset,
    required this.onTap,
    this.isSaved = false,
    this.onFavoriteToggle,
    super.key,
  });

  final String id;
  final String title;
  final String subtitle;
  final String savesCount;
  final String imageAsset;
  final VoidCallback onTap;
  final bool isSaved;
  final VoidCallback? onFavoriteToggle;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: '$title look, $savesCount',
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          decoration: BoxDecoration(
            color: FansivibeColors.surfaceContainerLow,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: Colors.white.withValues(alpha: 0.06),
              width: 1,
            ),
          ),
          clipBehavior: Clip.antiAlias,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // 65% visual area
              AspectRatio(
                aspectRatio: 0.85,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    AtelierImage(
                      assetPath: imageAsset,
                      fit: BoxFit.cover,
                    ),
                    // Bottom gradient for pill readability
                    Positioned(
                      left: 0,
                      right: 0,
                      bottom: 0,
                      height: 60,
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [
                              Colors.transparent,
                              Colors.black.withValues(alpha: 0.65),
                            ],
                          ),
                        ),
                      ),
                    ),
                    // Save / Favorite heart button (top right)
                    Positioned(
                      top: 10,
                      right: 10,
                      child: Semantics(
                        button: true,
                        label: isSaved ? 'Remove from saved' : 'Save look',
                        child: InkWell(
                          onTap: onFavoriteToggle,
                          borderRadius: BorderRadius.circular(20),
                          child: Container(
                            width: 32,
                            height: 32,
                            decoration: BoxDecoration(
                              color: Colors.black.withValues(alpha: 0.45),
                              shape: BoxShape.circle,
                              border: Border.all(
                                color: Colors.white.withValues(alpha: 0.15),
                                width: 0.8,
                              ),
                            ),
                            child: Icon(
                              isSaved
                                  ? Icons.favorite_rounded
                                  : Icons.favorite_border_rounded,
                              color: isSaved
                                  ? FansivibeColors.primary
                                  : Colors.white,
                              size: 16,
                            ),
                          ),
                        ),
                      ),
                    ),
                    // Saves counter pill (bottom left)
                    Positioned(
                      left: 10,
                      bottom: 10,
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.6),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: Colors.white.withValues(alpha: 0.15),
                            width: 0.8,
                          ),
                        ),
                        child: Text(
                          savesCount,
                          style: FansivibeTypography.labelSmallWithFamily.copyWith(
                            fontSize: 9.5,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.6,
                            color: Colors.white,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              // 35% content area
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: FansivibeTypography.titleLargeWithFamily.copyWith(
                        fontSize: 14.5,
                        fontWeight: FontWeight.w600,
                        color: FansivibeColors.onSurface,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 3),
                    Text(
                      subtitle,
                      style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                        fontSize: 11.5,
                        color: FansivibeColors.secondary,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
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

/// Editorial Commerce Item Card (Zara Wool Coat, Adidas Samba in Trending.jpg).
class EditorialCommerceItemCard extends StatelessWidget {
  const EditorialCommerceItemCard({
    required this.brand,
    required this.productName,
    required this.price,
    required this.imageAsset,
    required this.onTap,
    this.isSaved = false,
    this.onFavoriteToggle,
    super.key,
  });

  final String brand;
  final String productName;
  final String price;
  final String imageAsset;
  final VoidCallback onTap;
  final bool isSaved;
  final VoidCallback? onFavoriteToggle;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: '$brand $productName, $price',
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          decoration: BoxDecoration(
            color: FansivibeColors.surfaceContainerLow,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: Colors.white.withValues(alpha: 0.06),
              width: 1,
            ),
          ),
          clipBehavior: Clip.antiAlias,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Product image
              AspectRatio(
                aspectRatio: 0.95,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    AtelierImage(
                      assetPath: imageAsset,
                      fit: BoxFit.cover,
                    ),
                    // Favorite button
                    Positioned(
                      top: 10,
                      right: 10,
                      child: Semantics(
                        button: true,
                        label: isSaved ? 'Remove from wishlist' : 'Save item',
                        child: InkWell(
                          onTap: onFavoriteToggle,
                          borderRadius: BorderRadius.circular(20),
                          child: Container(
                            width: 32,
                            height: 32,
                            decoration: BoxDecoration(
                              color: Colors.black.withValues(alpha: 0.45),
                              shape: BoxShape.circle,
                              border: Border.all(
                                color: Colors.white.withValues(alpha: 0.15),
                                width: 0.8,
                              ),
                            ),
                            child: Icon(
                              isSaved
                                  ? Icons.favorite_rounded
                                  : Icons.favorite_border_rounded,
                              color: isSaved
                                  ? FansivibeColors.primary
                                  : Colors.white,
                              size: 16,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              // Commerce details
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      brand.toUpperCase(),
                      style: FansivibeTypography.labelSmallWithFamily.copyWith(
                        fontSize: 10,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0.8,
                        color: FansivibeColors.primaryContainer,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 3),
                    Text(
                      productName,
                      style: FansivibeTypography.titleLargeWithFamily.copyWith(
                        fontSize: 13.5,
                        fontWeight: FontWeight.w500,
                        color: FansivibeColors.onSurface,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      price,
                      style: FansivibeTypography.titleLargeWithFamily.copyWith(
                        fontSize: 13.5,
                        fontWeight: FontWeight.w700,
                        color: FansivibeColors.primary,
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

/// Asymmetric Editorial Moodboard for Style Inspiration in Trending.jpg.
class EditorialMoodboardGrid extends StatelessWidget {
  const EditorialMoodboardGrid({
    required this.onTextureTap,
    required this.onSilhouetteTap,
    required this.onAccentsTap,
    super.key,
  });

  final VoidCallback onTextureTap;
  final VoidCallback onSilhouetteTap;
  final VoidCallback onAccentsTap;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 330,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Left tall card: Texture & Drape
          Expanded(
            flex: 1,
            child: Semantics(
              button: true,
              label: 'Texture & Drape Inspiration',
              child: InkWell(
                onTap: onTextureTap,
                borderRadius: BorderRadius.circular(16),
                child: Container(
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(16),
                    color: FansivibeColors.surfaceContainerLow,
                    border: Border.all(
                      color: Colors.white.withValues(alpha: 0.06),
                      width: 1,
                    ),
                  ),
                  clipBehavior: Clip.antiAlias,
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      const AtelierImage(
                        assetPath: 'assets/images/discover_moodboard_texture.jpg',
                        fit: BoxFit.cover,
                      ),
                      Positioned(
                        left: 0,
                        right: 0,
                        bottom: 0,
                        height: 80,
                        child: DecoratedBox(
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              begin: Alignment.topCenter,
                              end: Alignment.bottomCenter,
                              colors: [
                                Colors.transparent,
                                Colors.black.withValues(alpha: 0.8),
                              ],
                            ),
                          ),
                          child: Padding(
                            padding: const EdgeInsets.all(12),
                            child: Align(
                              alignment: Alignment.bottomLeft,
                              child: Text(
                                'Texture & Drape',
                                style: TextStyle(
                                  fontFamily: 'Noto Serif',
                                  fontStyle: FontStyle.italic,
                                  fontSize: 13.5,
                                  fontWeight: FontWeight.w500,
                                  color: Colors.white,
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(width: 12),
          // Right column: two stacked cards (Silhouettes, Accents)
          Expanded(
            flex: 1,
            child: Column(
              children: [
                // Top: Silhouettes
                Expanded(
                  child: Semantics(
                    button: true,
                    label: 'Silhouettes Inspiration',
                    child: InkWell(
                      onTap: onSilhouetteTap,
                      borderRadius: BorderRadius.circular(16),
                      child: Container(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(16),
                          color: FansivibeColors.surfaceContainerLow,
                          border: Border.all(
                            color: Colors.white.withValues(alpha: 0.06),
                            width: 1,
                          ),
                        ),
                        clipBehavior: Clip.antiAlias,
                        child: Stack(
                          fit: StackFit.expand,
                          children: [
                            const AtelierImage(
                              assetPath: 'assets/images/discover_moodboard_silhouette.jpg',
                              fit: BoxFit.cover,
                            ),
                            Positioned(
                              left: 0,
                              right: 0,
                              bottom: 0,
                              height: 50,
                              child: DecoratedBox(
                                decoration: BoxDecoration(
                                  gradient: LinearGradient(
                                    begin: Alignment.topCenter,
                                    end: Alignment.bottomCenter,
                                    colors: [
                                      Colors.transparent,
                                      Colors.black.withValues(alpha: 0.75),
                                    ],
                                  ),
                                ),
                                child: Padding(
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 10,
                                    vertical: 8,
                                  ),
                                  child: Align(
                                    alignment: Alignment.bottomLeft,
                                    child: Text(
                                      'Silhouettes',
                                      style: FansivibeTypography.labelMediumWithFamily.copyWith(
                                        fontSize: 11,
                                        fontWeight: FontWeight.w600,
                                        color: Colors.white,
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                // Bottom: Accents
                Expanded(
                  child: Semantics(
                    button: true,
                    label: 'Accents Inspiration',
                    child: InkWell(
                      onTap: onAccentsTap,
                      borderRadius: BorderRadius.circular(16),
                      child: Container(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(16),
                          color: FansivibeColors.surfaceContainerLow,
                          border: Border.all(
                            color: Colors.white.withValues(alpha: 0.06),
                            width: 1,
                          ),
                        ),
                        clipBehavior: Clip.antiAlias,
                        child: Stack(
                          fit: StackFit.expand,
                          children: [
                            const AtelierImage(
                              assetPath: 'assets/images/discover_moodboard_accents.jpg',
                              fit: BoxFit.cover,
                            ),
                            Positioned(
                              left: 0,
                              right: 0,
                              bottom: 0,
                              height: 50,
                              child: DecoratedBox(
                                decoration: BoxDecoration(
                                  gradient: LinearGradient(
                                    begin: Alignment.topCenter,
                                    end: Alignment.bottomCenter,
                                    colors: [
                                      Colors.transparent,
                                      Colors.black.withValues(alpha: 0.75),
                                    ],
                                  ),
                                ),
                                child: Padding(
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 10,
                                    vertical: 8,
                                  ),
                                  child: Align(
                                    alignment: Alignment.bottomLeft,
                                    child: Text(
                                      'Accents',
                                      style: FansivibeTypography.labelMediumWithFamily.copyWith(
                                        fontSize: 11,
                                        fontWeight: FontWeight.w600,
                                        color: Colors.white,
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ],
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
    );
  }
}

/// Overlapping Editorial Composition for For You screen in ForYou.jpg.
class ForYouOverlappingHero extends StatelessWidget {
  const ForYouOverlappingHero({super.key});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 310,
      child: Center(
        child: SizedBox(
          width: 320,
          child: Stack(
            clipBehavior: Clip.none,
            children: [
              // Top right decorative atelier badge
              Positioned(
                top: 0,
                right: 4,
                child: Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(
                    color: FansivibeColors.surfaceContainerHigh,
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: FansivibeColors.primary.withValues(alpha: 0.5),
                      width: 1,
                    ),
                  ),
                  child: const Icon(
                    Icons.auto_awesome_rounded,
                    color: FansivibeColors.primary,
                    size: 16,
                  ),
                ),
              ),
              // Left card: ARCHIVE VOL. 01 (tilted)
              Positioned(
                left: 10,
                top: 25,
                child: Transform.rotate(
                  angle: -0.07,
                  child: Container(
                    width: 160,
                    height: 225,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(16),
                      color: FansivibeColors.surfaceContainerLow,
                      border: Border.all(
                        color: Colors.white.withValues(alpha: 0.08),
                        width: 1,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.6),
                          blurRadius: 16,
                          offset: const Offset(0, 8),
                        ),
                      ],
                    ),
                    clipBehavior: Clip.antiAlias,
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        const AtelierImage(
                          assetPath: 'assets/images/discover_foryou_archive.jpg',
                          fit: BoxFit.cover,
                        ),
                        Positioned(
                          left: 0,
                          right: 0,
                          bottom: 0,
                          height: 50,
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                begin: Alignment.topCenter,
                                end: Alignment.bottomCenter,
                                colors: [
                                  Colors.transparent,
                                  Colors.black.withValues(alpha: 0.8),
                                ],
                              ),
                            ),
                            child: Padding(
                              padding: const EdgeInsets.all(10),
                              child: Align(
                                alignment: Alignment.bottomLeft,
                                child: Text(
                                  'ARCHIVE VOL. 01',
                                  style: FansivibeTypography.labelSmallWithFamily.copyWith(
                                    fontSize: 9.5,
                                    fontWeight: FontWeight.w700,
                                    letterSpacing: 1.2,
                                    color: Colors.white,
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              // Right card: SILHOUETTE Nº 4 (taller, overlapping)
              Positioned(
                left: 130,
                top: 10,
                child: Container(
                  width: 175,
                  height: 255,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(16),
                    color: FansivibeColors.surfaceContainerLow,
                    border: Border.all(
                      color: FansivibeColors.primary.withValues(alpha: 0.35),
                      width: 1.2,
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.7),
                        blurRadius: 20,
                        offset: const Offset(4, 10),
                      ),
                    ],
                  ),
                  clipBehavior: Clip.antiAlias,
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      const AtelierImage(
                        assetPath: 'assets/images/discover_foryou_silhouette.jpg',
                        fit: BoxFit.cover,
                      ),
                      Positioned(
                        left: 0,
                        right: 0,
                        bottom: 0,
                        height: 70,
                        child: DecoratedBox(
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              begin: Alignment.topCenter,
                              end: Alignment.bottomCenter,
                              colors: [
                                Colors.transparent,
                                Colors.black.withValues(alpha: 0.85),
                              ],
                            ),
                          ),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 10,
                            ),
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.end,
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Fansivibe — For You',
                                  style: FansivibeTypography.labelSmallWithFamily.copyWith(
                                    fontSize: 9,
                                    color: Colors.white70,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                  children: [
                                    Flexible(
                                      child: Text(
                                        'SILHOUETTE Nº 4',
                                        style: FansivibeTypography.labelSmallWithFamily.copyWith(
                                          fontSize: 9.5,
                                          fontWeight: FontWeight.w700,
                                          letterSpacing: 1.0,
                                          color: Colors.white,
                                        ),
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                    Container(
                                      width: 6,
                                      height: 6,
                                      decoration: const BoxDecoration(
                                        color: FansivibeColors.primary,
                                        shape: BoxShape.circle,
                                      ),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Calibration Step Card in For You tab (01, 02, 03, 04).
class CalibrationStepCard extends StatelessWidget {
  const CalibrationStepCard({
    required this.stepNumber,
    required this.stepTitle,
    required this.stepDescription,
    required this.icon,
    super.key,
  });

  final String stepNumber;
  final String stepTitle;
  final String stepDescription;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.05),
          width: 1,
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Circular icon badge
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color: FansivibeColors.surfaceContainerHigh,
              shape: BoxShape.circle,
              border: Border.all(
                color: FansivibeColors.primary.withValues(alpha: 0.2),
                width: 1,
              ),
            ),
            child: Icon(
              icon,
              color: FansivibeColors.primary,
              size: 18,
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      stepNumber,
                      style: TextStyle(
                        fontFamily: 'Inter',
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: FansivibeColors.primaryContainer,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        stepTitle,
                        style: FansivibeTypography.titleLargeWithFamily.copyWith(
                          fontSize: 14.5,
                          fontWeight: FontWeight.w600,
                          color: FansivibeColors.onSurface,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 5),
                Text(
                  stepDescription,
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    fontSize: 12.5,
                    color: FansivibeColors.secondary,
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Preview Archive Box at the bottom of For You tab in ForYou.jpg.
class PreviewArchiveBox extends StatelessWidget {
  const PreviewArchiveBox({
    required this.savedLooksCount,
    super.key,
  });

  final int savedLooksCount;

  @override
  Widget build(BuildContext context) {
    final progress = (savedLooksCount / 3.0).clamp(0.0, 1.0);

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: FansivibeColors.primary.withValues(alpha: 0.25),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: FansivibeColors.primary.withValues(alpha: 0.5),
                    width: 1,
                  ),
                ),
                child: Text(
                  'PREVIEW ARCHIVE',
                  style: FansivibeTypography.labelSmallWithFamily.copyWith(
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.2,
                    color: FansivibeColors.primary,
                  ),
                ),
              ),
              Icon(
                Icons.lock_outline_rounded,
                color: FansivibeColors.primary.withValues(alpha: 0.8),
                size: 18,
              ),
            ],
          ),
          const SizedBox(height: 14),
          Text(
            'Personalized Daily Directives',
            style: TextStyle(
              fontFamily: 'Noto Serif',
              fontSize: 18,
              fontWeight: FontWeight.w600,
              color: FansivibeColors.onSurface,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            'Zero synthetic match scores. Your bespoke styling feed activates automatically upon your first 3 saved ensembles.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              fontSize: 12.5,
              color: FansivibeColors.secondary,
              height: 1.4,
            ),
          ),
          const SizedBox(height: 16),
          // Progress row
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Sartorial Calibration',
                style: TextStyle(
                  fontFamily: 'Inter',
                  fontSize: 11.5,
                  color: FansivibeColors.secondary,
                ),
              ),
              Text(
                '$savedLooksCount / 3 Looks Saved',
                style: TextStyle(
                  fontFamily: 'Inter',
                  fontSize: 11.5,
                  fontWeight: FontWeight.w700,
                  color: FansivibeColors.primary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: progress,
              backgroundColor: FansivibeColors.surfaceContainerHigh,
              valueColor: const AlwaysStoppedAnimation<Color>(FansivibeColors.primary),
              minHeight: 3.5,
            ),
          ),
          const SizedBox(height: 16),
          // Direction tags
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: const [
              _ArchiveTag(label: 'Structured Suiting'),
              _ArchiveTag(label: 'Warm Minimalist'),
              _ArchiveTag(label: 'Tokyo Avant-Garde'),
            ],
          ),
        ],
      ),
    );
  }
}

class _ArchiveTag extends StatelessWidget {
  const _ArchiveTag({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainer,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.06),
          width: 1,
        ),
      ),
      child: Text(
        label,
        style: FansivibeTypography.labelSmallWithFamily.copyWith(
          fontSize: 11,
          color: FansivibeColors.secondary,
        ),
      ),
    );
  }
}
