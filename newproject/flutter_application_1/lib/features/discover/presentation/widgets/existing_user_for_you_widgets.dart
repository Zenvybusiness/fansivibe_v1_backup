import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/discover/presentation/widgets/discover_editorial_widgets.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Data model representing a shoppable fashion product in the For You feed.
class ForYouProductItem {
  const ForYouProductItem({
    required this.id,
    required this.brand,
    required this.title,
    required this.price,
    required this.imageAsset,
    this.retailer = 'Retailer',
    this.matchScore = 90,
    this.category = 'All Picks',
    this.reasons = const [],
    this.isSaved = false,
  });

  final String id;
  final String brand;
  final String title;
  final String price;
  final String imageAsset;
  final String retailer;
  final int matchScore;
  final String category;
  final List<String> reasons;
  final bool isSaved;

  ForYouProductItem copyWith({
    String? id,
    String? brand,
    String? title,
    String? price,
    String? imageAsset,
    String? retailer,
    int? matchScore,
    String? category,
    List<String>? reasons,
    bool? isSaved,
  }) {
    return ForYouProductItem(
      id: id ?? this.id,
      brand: brand ?? this.brand,
      title: title ?? this.title,
      price: price ?? this.price,
      imageAsset: imageAsset ?? this.imageAsset,
      retailer: retailer ?? this.retailer,
      matchScore: matchScore ?? this.matchScore,
      category: category ?? this.category,
      reasons: reasons ?? this.reasons,
      isSaved: isSaved ?? this.isSaved,
    );
  }
}

/// The complete established-user personalized For You feed matching
/// `Foryou page for old user.jpg`.
class EstablishedUserForYouFeed extends StatefulWidget {
  const EstablishedUserForYouFeed({
    super.key,
    this.searchQuery = '',
    this.onShopTap,
    this.onBuildLookTap,
  });

  final String searchQuery;
  final void Function(ForYouProductItem product)? onShopTap;
  final VoidCallback? onBuildLookTap;

  @override
  State<EstablishedUserForYouFeed> createState() =>
      _EstablishedUserForYouFeedState();
}

class _EstablishedUserForYouFeedState extends State<EstablishedUserForYouFeed> {
  String _selectedCategory = 'All Picks';
  late Set<String> _savedProductIds;

  @override
  void initState() {
    super.initState();
    _savedProductIds = Set<String>.from(LocalStorage.savedLookIds);
  }

  void _toggleSave(String id, String title) {
    setState(() {
      if (_savedProductIds.contains(id)) {
        _savedProductIds.remove(id);
      } else {
        _savedProductIds.add(id);
        LearningService.instance.addSavedLook(title);
      }
      LocalStorage.savedLookIds = _savedProductIds.toList();
    });
  }

  void _handleShop(BuildContext context, ForYouProductItem product) {
    if (widget.onShopTap != null) {
      widget.onShopTap!(product);
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Opening ${product.retailer}...'),
        backgroundColor: FansivibeColors.accentGold,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: FansivibeRadius.smdBorder,
        ),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  void _handleBuildLook(BuildContext context) {
    if (widget.onBuildLookTap != null) {
      widget.onBuildLookTap!();
      return;
    }
    context.pushNamed(RouteNames.buildOutfit);
  }

  @override
  Widget build(BuildContext context) {
    final learningService = LearningService.instance;
    final userStyleType = learningService.styleType ?? 'Minimal Tailoring';
    final userScore = learningService.styleScore;
    final affinityScore = (userScore + 12).clamp(84, 96);
    final userWardrobe = learningService.wardrobe;

    // Pick user item or fallback
    final wardrobePieceName = userWardrobe.isNotEmpty
        ? userWardrobe.firstWhere(
            (item) => item.category == 'bottoms',
            orElse: () => userWardrobe.first,
          ).name
        : 'Black Wide-Leg Trousers';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // ----------------------------------------------------
        // SECTION 1: PERSONALIZED HERO PRODUCT CARD
        // ----------------------------------------------------
        PersonalizedHeroProductCard(
          product: ForYouProductItem(
            id: 'hero_cos_overshirt',
            brand: 'COS',
            title: 'Structured Double-Faced Wool Overshirt',
            price: '₹12,500',
            retailer: 'COS Official',
            matchScore: 94,
            imageAsset: 'assets/images/discover_hero_quiet_luxury.jpg',
            reasons: [
              'Matches your neutral palette and minimal preference',
              'Relaxed tailored fit complements your silhouette profile',
              userWardrobe.isNotEmpty
                  ? 'Complements ${userWardrobe.length} pieces in your existing wardrobe'
                  : 'Works with foundational dark trousers and knitwear',
              'High style affinity based on your recent activity',
            ],
            isSaved: _savedProductIds.contains('hero_cos_overshirt'),
          ),
          onFavoriteToggle: () => _toggleSave(
            'hero_cos_overshirt',
            'Structured Double-Faced Wool Overshirt',
          ),
          onShopTap: (p) => _handleShop(context, p),
        ),

        const SizedBox(height: 24),

        // ----------------------------------------------------
        // SECTION 2: CURATED FOR YOU AFFINITY SUMMARY
        // ----------------------------------------------------
        CuratedForYouSummaryCard(affinityScore: affinityScore),

        const SizedBox(height: 32),

        // ----------------------------------------------------
        // SECTION 3: WARDROBE MATCH
        // ----------------------------------------------------
        WardrobeMatchCard(
          userItemName: wardrobePieceName,
          hasRealWardrobe: userWardrobe.isNotEmpty,
          onBuildLookTap: () => _handleBuildLook(context),
        ),

        const SizedBox(height: 32),

        // ----------------------------------------------------
        // SECTION 4: PRODUCT CATEGORY FILTER CHIPS
        // ----------------------------------------------------
        ProductFilterChipsRow(
          selectedCategory: _selectedCategory,
          onCategorySelected: (cat) {
            setState(() => _selectedCategory = cat);
          },
        ),

        const SizedBox(height: 24),

        // ----------------------------------------------------
        // SECTION 5: BECAUSE YOU LIKE... (2-COLUMN GRID)
        // ----------------------------------------------------
        BecauseYouLikeSection(
          styleName: userStyleType,
          selectedCategory: _selectedCategory,
          savedIds: _savedProductIds,
          onFavoriteToggle: _toggleSave,
          onShopTap: (p) => _handleShop(context, p),
          searchQuery: widget.searchQuery,
        ),

        const SizedBox(height: 36),

        // ----------------------------------------------------
        // SECTION 6: ENSEMBLE CURATION / COMPLETE LOOK
        // ----------------------------------------------------
        EnsembleCurationCard(
          onShopLookTap: () {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: const Text(
                  'Adding curated ensemble (3 pieces) to cart...',
                ),
                backgroundColor: FansivibeColors.accentGold,
                behavior: SnackBarBehavior.floating,
                shape: RoundedRectangleBorder(
                  borderRadius: FansivibeRadius.smdBorder,
                ),
                duration: const Duration(seconds: 2),
              ),
            );
          },
        ),

        const SizedBox(height: 36),

        // ----------------------------------------------------
        // SECTION 7: TRENDING IN YOUR STYLE
        // ----------------------------------------------------
        TrendingInYourStyleSection(
          savedIds: _savedProductIds,
          onFavoriteToggle: _toggleSave,
          onShopTap: (p) => _handleShop(context, p),
        ),

        const SizedBox(height: 36),

        // ----------------------------------------------------
        // SECTION 8: CURATED COLLECTIONS
        // ----------------------------------------------------
        const CuratedCollectionsSection(),

        const SizedBox(height: 36),

        // ----------------------------------------------------
        // SECTION 9: THE FINISHING TOUCHES (ACCESSORIES)
        // ----------------------------------------------------
        FinishingTouchesSection(
          onShopTap: (p) => _handleShop(context, p),
        ),

        const SizedBox(height: 36),

        // ----------------------------------------------------
        // PROTOCOL FOOTER
        // ----------------------------------------------------
        Center(
          child: Text(
            'ALEXANDRIA COMMERCE PROTOCOL • FANSIVIBE ATELIER',
            style: FansivibeTypography.labelSmallWithFamily.copyWith(
              fontSize: 10,
              fontWeight: FontWeight.w600,
              letterSpacing: 2.0,
              color: FansivibeColors.secondary.withValues(alpha: 0.5),
            ),
          ),
        ),
      ],
    );
  }
}

// =========================================================================
// SECTION 1: PERSONALIZED HERO PRODUCT CARD
// =========================================================================

class PersonalizedHeroProductCard extends StatefulWidget {
  const PersonalizedHeroProductCard({
    required this.product,
    required this.onFavoriteToggle,
    required this.onShopTap,
    super.key,
  });

  final ForYouProductItem product;
  final VoidCallback onFavoriteToggle;
  final void Function(ForYouProductItem) onShopTap;

  @override
  State<PersonalizedHeroProductCard> createState() =>
      _PersonalizedHeroProductCardState();
}

class _PersonalizedHeroProductCardState
    extends State<PersonalizedHeroProductCard> {
  bool _expanded = true;

  @override
  Widget build(BuildContext context) {
    final product = widget.product;

    return Container(
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.06),
          width: 1,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // 65% Visual Hero Image Area
          AspectRatio(
            aspectRatio: 0.82,
            child: Stack(
              fit: StackFit.expand,
              children: [
                AtelierImage(
                  assetPath: product.imageAsset,
                  fit: BoxFit.cover,
                ),
                // Top gradient vignette
                Positioned(
                  top: 0,
                  left: 0,
                  right: 0,
                  height: 80,
                  child: Container(
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
                // 94% STYLE MATCH badge top-left
                Positioned(
                  top: 14,
                  left: 14,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 5,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.black.withValues(alpha: 0.75),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(
                        color: FansivibeColors.primary.withValues(alpha: 0.6),
                        width: 1,
                      ),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(
                          Icons.auto_awesome,
                          color: FansivibeColors.primary,
                          size: 13,
                        ),
                        const SizedBox(width: 5),
                        Text(
                          '${product.matchScore}% STYLE MATCH',
                          style: TextStyle(
                            fontFamily: 'Inter',
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 0.8,
                            color: FansivibeColors.primary,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                // Heart Save Button top-right
                Positioned(
                  top: 14,
                  right: 14,
                  child: Semantics(
                    button: true,
                    label: product.isSaved
                        ? 'Remove from wishlist'
                        : 'Save product',
                    child: InkWell(
                      onTap: widget.onFavoriteToggle,
                      borderRadius: BorderRadius.circular(20),
                      child: Container(
                        width: 36,
                        height: 36,
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.6),
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: Colors.white.withValues(alpha: 0.2),
                            width: 1,
                          ),
                        ),
                        child: Icon(
                          product.isSaved
                              ? Icons.favorite_rounded
                              : Icons.favorite_border_rounded,
                          color: product.isSaved
                              ? FansivibeColors.primary
                              : Colors.white,
                          size: 18,
                        ),
                      ),
                    ),
                  ),
                ),
                // Bottom style tags on image
                Positioned(
                  bottom: 12,
                  left: 14,
                  right: 14,
                  child: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.65),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          'MINIMAL TAILORING',
                          style: TextStyle(
                            fontFamily: 'Inter',
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.5,
                            color: Colors.white.withValues(alpha: 0.9),
                          ),
                        ),
                      ),
                      const SizedBox(width: 6),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.65),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          'RELAXED SILHOUETTE',
                          style: TextStyle(
                            fontFamily: 'Inter',
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.5,
                            color: Colors.white.withValues(alpha: 0.9),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          // 35% Information Hierarchy & Commerce Content
          Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Brand & Price Row
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  crossAxisAlignment: CrossAxisAlignment.baseline,
                  textBaseline: TextBaseline.alphabetic,
                  children: [
                    Text(
                      product.brand.toUpperCase(),
                      style: TextStyle(
                        fontFamily: 'Inter',
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 1.5,
                        color: FansivibeColors.primary,
                      ),
                    ),
                    Text(
                      product.price,
                      style: const TextStyle(
                        fontFamily: 'Inter',
                        fontSize: 20,
                        fontWeight: FontWeight.w700,
                        color: FansivibeColors.onSurface,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 4),

                // Product Name
                Text(
                  product.title,
                  style: const TextStyle(
                    fontFamily: 'Noto Serif',
                    fontSize: 20,
                    fontWeight: FontWeight.w500,
                    height: 1.25,
                    color: FansivibeColors.onSurface,
                  ),
                ),
                const SizedBox(height: 4),

                // Retailer Information
                Text(
                  'Available at ${product.retailer}',
                  style: TextStyle(
                    fontFamily: 'Inter',
                    fontSize: 12.5,
                    color: FansivibeColors.secondary,
                  ),
                ),

                const SizedBox(height: 16),

                // Expandable: WHY THIS IS FOR YOU
                Container(
                  decoration: BoxDecoration(
                    color: FansivibeColors.surfaceContainer,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: Colors.white.withValues(alpha: 0.04),
                    ),
                  ),
                  child: Column(
                    children: [
                      InkWell(
                        onTap: () => setState(() => _expanded = !_expanded),
                        borderRadius: BorderRadius.circular(12),
                        child: Padding(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 14,
                            vertical: 12,
                          ),
                          child: Row(
                            children: [
                              const Icon(
                                Icons.auto_awesome,
                                size: 14,
                                color: FansivibeColors.primary,
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  'WHY THIS IS FOR YOU',
                                  style: TextStyle(
                                    fontFamily: 'Inter',
                                    fontSize: 11.5,
                                    fontWeight: FontWeight.w700,
                                    letterSpacing: 1.2,
                                    color: FansivibeColors.onSurface,
                                  ),
                                ),
                              ),
                              Icon(
                                _expanded
                                    ? Icons.keyboard_arrow_up_rounded
                                    : Icons.keyboard_arrow_down_rounded,
                                color: FansivibeColors.secondary,
                                size: 20,
                              ),
                            ],
                          ),
                        ),
                      ),
                      if (_expanded)
                        Padding(
                          padding: const EdgeInsets.only(
                            left: 14,
                            right: 14,
                            bottom: 14,
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: product.reasons.map((reason) {
                              return Padding(
                                padding: const EdgeInsets.symmetric(vertical: 4),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    const Text(
                                      '✓ ',
                                      style: TextStyle(
                                        color: FansivibeColors.primary,
                                        fontWeight: FontWeight.bold,
                                        fontSize: 13,
                                      ),
                                    ),
                                    Expanded(
                                      child: Text(
                                        reason,
                                        style: TextStyle(
                                          fontFamily: 'Inter',
                                          fontSize: 12.5,
                                          height: 1.35,
                                          color: FansivibeColors.onSurface
                                              .withValues(alpha: 0.9),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              );
                            }).toList(),
                          ),
                        ),
                    ],
                  ),
                ),

                const SizedBox(height: 18),

                // SHOP AT [RETAILER] → CTA Button
                Semantics(
                  button: true,
                  label: 'Shop at ${product.retailer}',
                  child: InkWell(
                    onTap: () => widget.onShopTap(product),
                    borderRadius: BorderRadius.circular(26),
                    child: Container(
                      height: 50,
                      decoration: BoxDecoration(
                        color: FansivibeColors.primary,
                        borderRadius: BorderRadius.circular(26),
                        boxShadow: [
                          BoxShadow(
                            color: FansivibeColors.primary.withValues(alpha: 0.3),
                            blurRadius: 12,
                            offset: const Offset(0, 4),
                          ),
                        ],
                      ),
                      child: Center(
                        child: Text(
                          'SHOP AT ${product.brand.toUpperCase()} →',
                          style: const TextStyle(
                            fontFamily: 'Inter',
                            fontSize: 13,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 1.2,
                            color: Color(0xFF131313),
                          ),
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

// =========================================================================
// SECTION 2: CURATED FOR YOU AFFINITY SUMMARY CARD
// =========================================================================

class CuratedForYouSummaryCard extends StatelessWidget {
  const CuratedForYouSummaryCard({
    required this.affinityScore,
    super.key,
  });

  final int affinityScore;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.06),
          width: 1,
        ),
      ),
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'CURATED FOR YOU',
                style: TextStyle(
                  fontFamily: 'Inter',
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.5,
                  color: FansivibeColors.primary,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 4,
                ),
                decoration: BoxDecoration(
                  color: FansivibeColors.primary.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: FansivibeColors.primary.withValues(alpha: 0.4),
                    width: 0.8,
                  ),
                ),
                child: Text(
                  '$affinityScore% OVERALL AFFINITY',
                  style: TextStyle(
                    fontFamily: 'Inter',
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.5,
                    color: FansivibeColors.primary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            'Based on your style profile, saved looks, wardrobe and recent activity.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              fontSize: 13,
              color: FansivibeColors.secondary,
              height: 1.45,
            ),
          ),
          const SizedBox(height: 12),
          InkWell(
            onTap: () {
              showModalBottomSheet<void>(
                context: context,
                backgroundColor: FansivibeColors.surface,
                shape: const RoundedRectangleBorder(
                  borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
                ),
                builder: (ctx) => Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Affinity Precision',
                        style: TextStyle(
                          fontFamily: 'Noto Serif',
                          fontSize: 22,
                          fontWeight: FontWeight.w500,
                          color: FansivibeColors.onSurface,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Fansivibe combines silhouette analysis, color palette balance, wardrobe synergy, and your interaction history to calculate your personal style affinity.',
                        style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                          fontSize: 13.5,
                          color: FansivibeColors.secondary,
                          height: 1.4,
                        ),
                      ),
                      const SizedBox(height: 20),
                    ],
                  ),
                ),
              );
            },
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'WHY THIS MATTERS →',
                  style: TextStyle(
                    fontFamily: 'Inter',
                    fontSize: 11.5,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.0,
                    color: FansivibeColors.primary,
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

// =========================================================================
// SECTION 3: WARDROBE MATCH
// =========================================================================

class WardrobeMatchCard extends StatelessWidget {
  const WardrobeMatchCard({
    required this.userItemName,
    required this.hasRealWardrobe,
    required this.onBuildLookTap,
    super.key,
  });

  final String userItemName;
  final bool hasRealWardrobe;
  final VoidCallback onBuildLookTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.06),
          width: 1,
        ),
      ),
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Section Monograph
          Text(
            'WARDROBE MATCH',
            style: TextStyle(
              fontFamily: 'Inter',
              fontSize: 11,
              fontWeight: FontWeight.w700,
              letterSpacing: 1.5,
              color: FansivibeColors.primary,
            ),
          ),
          const SizedBox(height: 4),
          const Text(
            'Works with what you own',
            style: TextStyle(
              fontFamily: 'Noto Serif',
              fontSize: 22,
              fontWeight: FontWeight.w500,
              color: FansivibeColors.onSurface,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            'New pieces selected to complement your existing wardrobe.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              fontSize: 13,
              color: FansivibeColors.secondary,
            ),
          ),
          const SizedBox(height: 18),

          // Wardrobe Item Row 1: Owned piece
          _buildItemRow(
            badge: hasRealWardrobe ? 'YOUR ITEM' : 'WARDROBE FOUNDATION',
            badgeColor: FansivibeColors.primary,
            title: userItemName,
            subtitle: hasRealWardrobe ? 'In your wardrobe' : 'Essential staple',
            imageAsset: 'assets/images/discover_cat_clothing.jpg',
          ),

          const Center(
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Text(
                '+',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  color: FansivibeColors.primary,
                ),
              ),
            ),
          ),

          // Recommended Pairing Row 2
          _buildItemRow(
            badge: 'RECOMMENDED',
            badgeColor: FansivibeColors.secondary,
            title: 'Cream Minimal Knit Polo',
            subtitle: 'COS • ₹6,800',
            imageAsset: 'assets/images/discover_moodboard_texture.jpg',
          ),

          const Center(
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Text(
                '+',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  color: FansivibeColors.primary,
                ),
              ),
            ),
          ),

          // Recommended Pairing Row 3
          _buildItemRow(
            badge: 'RECOMMENDED',
            badgeColor: FansivibeColors.secondary,
            title: 'Minimal Leather Sneakers',
            subtitle: 'Common Projects • ₹28,500',
            imageAsset: 'assets/images/discover_cat_sneakers.jpg',
          ),

          const SizedBox(height: 20),

          // BUILD THIS LOOK (3 PIECES) → CTA
          Semantics(
            button: true,
            label: 'Build This Look (3 Pieces)',
            child: InkWell(
              onTap: onBuildLookTap,
              borderRadius: BorderRadius.circular(26),
              child: Container(
                height: 48,
                decoration: BoxDecoration(
                  color: FansivibeColors.primary,
                  borderRadius: BorderRadius.circular(26),
                ),
                child: const Center(
                  child: Text(
                    'BUILD THIS LOOK (3 PIECES) →',
                    style: TextStyle(
                      fontFamily: 'Inter',
                      fontSize: 12.5,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.2,
                      color: Color(0xFF131313),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildItemRow({
    required String badge,
    required Color badgeColor,
    required String title,
    required String subtitle,
    required String imageAsset,
  }) {
    return Container(
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainer,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.04),
        ),
      ),
      padding: const EdgeInsets.all(10),
      child: Row(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: SizedBox(
              width: 54,
              height: 54,
              child: AtelierImage(
                assetPath: imageAsset,
                fit: BoxFit.cover,
              ),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  badge,
                  style: TextStyle(
                    fontFamily: 'Inter',
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.0,
                    color: badgeColor,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  title,
                  style: const TextStyle(
                    fontFamily: 'Inter',
                    fontSize: 13.5,
                    fontWeight: FontWeight.w600,
                    color: FansivibeColors.onSurface,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: TextStyle(
                    fontFamily: 'Inter',
                    fontSize: 12,
                    color: FansivibeColors.secondary,
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

// =========================================================================
// SECTION 4: PRODUCT CATEGORY FILTER CHIPS
// =========================================================================

class ProductFilterChipsRow extends StatelessWidget {
  const ProductFilterChipsRow({
    required this.selectedCategory,
    required this.onCategorySelected,
    super.key,
  });

  final String selectedCategory;
  final ValueChanged<String> onCategorySelected;

  static const List<String> categories = [
    'All Picks',
    'Jackets & Coats',
    'Knitwear',
    'Trousers',
    'Sneakers',
    'Accessories',
  ];

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 38,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        physics: const BouncingScrollPhysics(),
        itemCount: categories.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (context, index) {
          final cat = categories[index];
          final isSelected = cat == selectedCategory;

          return Semantics(
            button: true,
            selected: isSelected,
            label: cat,
            child: InkWell(
              onTap: () => onCategorySelected(cat),
              borderRadius: BorderRadius.circular(19),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                padding: const EdgeInsets.symmetric(horizontal: 16),
                decoration: BoxDecoration(
                  color: isSelected
                      ? FansivibeColors.primary
                      : FansivibeColors.surfaceContainerLow,
                  borderRadius: BorderRadius.circular(19),
                  border: Border.all(
                    color: isSelected
                        ? FansivibeColors.primary
                        : Colors.white.withValues(alpha: 0.08),
                    width: 1,
                  ),
                ),
                child: Center(
                  child: Text(
                    cat,
                    style: TextStyle(
                      fontFamily: 'Inter',
                      fontSize: 12.5,
                      fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                      color: isSelected
                          ? const Color(0xFF131313)
                          : FansivibeColors.onSurface.withValues(alpha: 0.85),
                    ),
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

// =========================================================================
// SECTION 5: BECAUSE YOU LIKE... (2-COLUMN GRID)
// =========================================================================

class BecauseYouLikeSection extends StatelessWidget {
  const BecauseYouLikeSection({
    required this.styleName,
    required this.selectedCategory,
    required this.savedIds,
    required this.onFavoriteToggle,
    required this.onShopTap,
    this.searchQuery = '',
    super.key,
  });

  final String styleName;
  final String selectedCategory;
  final Set<String> savedIds;
  final void Function(String id, String title) onFavoriteToggle;
  final void Function(ForYouProductItem) onShopTap;
  final String searchQuery;

  static const List<ForYouProductItem> allCatalogProducts = [
    ForYouProductItem(
      id: 'prod_lemaire_trousers',
      brand: 'LEMAIRE',
      title: 'Pleated Wool Flannel Pant',
      price: '₹32,400',
      retailer: 'SSENSE',
      matchScore: 92,
      category: 'Trousers',
      imageAsset: 'assets/images/discover_look_urban_minimal.jpg',
    ),
    ForYouProductItem(
      id: 'prod_arket_shirt',
      brand: 'ARKET',
      title: 'Relaxed Poplin Shirt',
      price: '₹6,200',
      retailer: 'ARKET Direct',
      matchScore: 88,
      category: 'Knitwear',
      imageAsset: 'assets/images/discover_moodboard_texture.jpg',
    ),
    ForYouProductItem(
      id: 'prod_nicholson_derby',
      brand: 'STUDIO NICHOLSON',
      title: 'Chunky Derby Shoe',
      price: '₹41,000',
      retailer: 'Farfetch',
      matchScore: 90,
      category: 'Sneakers',
      imageAsset: 'assets/images/discover_cat_sneakers.jpg',
    ),
    ForYouProductItem(
      id: 'prod_tomwood_ring',
      brand: 'TOM WOOD',
      title: 'Cushion Gold Ring',
      price: '₹24,500',
      retailer: 'MatchesFashion',
      matchScore: 86,
      category: 'Accessories',
      imageAsset: 'assets/images/discover_cat_accessories.jpg',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    var filtered = selectedCategory == 'All Picks'
        ? allCatalogProducts
        : allCatalogProducts
            .where((p) => p.category == selectedCategory)
            .toList();

    if (searchQuery.trim().isNotEmpty) {
      final q = searchQuery.toLowerCase().trim();
      final searched = filtered
          .where(
            (p) =>
                p.title.toLowerCase().contains(q) ||
                p.brand.toLowerCase().contains(q) ||
                p.category.toLowerCase().contains(q),
          )
          .toList();
      if (searched.isNotEmpty) filtered = searched;
    }

    final displayProducts =
        filtered.isNotEmpty ? filtered : allCatalogProducts;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'BECAUSE YOU LIKE',
          style: TextStyle(
            fontFamily: 'Inter',
            fontSize: 11,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.5,
            color: FansivibeColors.primary,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          styleName,
          style: const TextStyle(
            fontFamily: 'Noto Serif',
            fontSize: 22,
            fontWeight: FontWeight.w500,
            color: FansivibeColors.onSurface,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          'Products inspired by your saved styles and preferences.',
          style: FansivibeTypography.bodyMediumWithFamily.copyWith(
            fontSize: 13,
            color: FansivibeColors.secondary,
          ),
        ),
        const SizedBox(height: 16),

        // 2-Column Mathematical Grid
        LayoutBuilder(
          builder: (context, constraints) {
            const gap = 14.0;
            final columnWidth = (constraints.maxWidth - gap) / 2;

            return Wrap(
              spacing: gap,
              runSpacing: gap,
              children: displayProducts.map((p) {
                final isSaved = savedIds.contains(p.id);

                return SizedBox(
                  width: columnWidth,
                  child: ForYouGridProductCard(
                    product: p,
                    isSaved: isSaved,
                    onFavoriteToggle: () => onFavoriteToggle(p.id, p.title),
                    onShopTap: () => onShopTap(p),
                  ),
                );
              }).toList(),
            );
          },
        ),
      ],
    );
  }
}

/// One card in the 2-column mathematical grid.
class ForYouGridProductCard extends StatelessWidget {
  const ForYouGridProductCard({
    required this.product,
    required this.isSaved,
    required this.onFavoriteToggle,
    required this.onShopTap,
    super.key,
  });

  final ForYouProductItem product;
  final bool isSaved;
  final VoidCallback onFavoriteToggle;
  final VoidCallback onShopTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.05),
          width: 1,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Visual Area with Match Badge and Favorite Button
          AspectRatio(
            aspectRatio: 0.95,
            child: Stack(
              fit: StackFit.expand,
              children: [
                AtelierImage(
                  assetPath: product.imageAsset,
                  fit: BoxFit.cover,
                ),
                // Match badge top-left
                Positioned(
                  top: 8,
                  left: 8,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 6,
                      vertical: 3,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.black.withValues(alpha: 0.7),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(
                        color: FansivibeColors.primary.withValues(alpha: 0.5),
                        width: 0.8,
                      ),
                    ),
                    child: Text(
                      '${product.matchScore}% MATCH',
                      style: TextStyle(
                        fontFamily: 'Inter',
                        fontSize: 9.5,
                        fontWeight: FontWeight.w700,
                        color: FansivibeColors.primary,
                      ),
                    ),
                  ),
                ),
                // Favorite Button top-right
                Positioned(
                  top: 8,
                  right: 8,
                  child: Semantics(
                    button: true,
                    label: isSaved ? 'Remove from wishlist' : 'Save item',
                    child: InkWell(
                      onTap: onFavoriteToggle,
                      borderRadius: BorderRadius.circular(16),
                      child: Container(
                        width: 30,
                        height: 30,
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.5),
                          shape: BoxShape.circle,
                        ),
                        child: Icon(
                          isSaved
                              ? Icons.favorite_rounded
                              : Icons.favorite_border_rounded,
                          color: isSaved
                              ? FansivibeColors.primary
                              : Colors.white,
                          size: 15,
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),

          // Content Area
          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  product.brand.toUpperCase(),
                  style: TextStyle(
                    fontFamily: 'Inter',
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.0,
                    color: FansivibeColors.primary,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 3),
                Text(
                  product.title,
                  style: const TextStyle(
                    fontFamily: 'Inter',
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                    color: FansivibeColors.onSurface,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 4),
                Text(
                  product.price,
                  style: const TextStyle(
                    fontFamily: 'Inter',
                    fontSize: 13.5,
                    fontWeight: FontWeight.w700,
                    color: FansivibeColors.onSurface,
                  ),
                ),
                const SizedBox(height: 10),
                Semantics(
                  button: true,
                  label: 'Shop ${product.title}',
                  child: InkWell(
                    onTap: onShopTap,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          'SHOP →',
                          style: TextStyle(
                            fontFamily: 'Inter',
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 1.0,
                            color: FansivibeColors.primary,
                          ),
                        ),
                      ],
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

// =========================================================================
// SECTION 6: ENSEMBLE CURATION / COMPLETE LOOK
// =========================================================================

class EnsembleCurationCard extends StatelessWidget {
  const EnsembleCurationCard({
    required this.onShopLookTap,
    super.key,
  });

  final VoidCallback onShopLookTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.06),
          width: 1,
        ),
      ),
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'ENSEMBLE CURATION',
                style: TextStyle(
                  fontFamily: 'Inter',
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.5,
                  color: FansivibeColors.primary,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 8,
                  vertical: 3,
                ),
                decoration: BoxDecoration(
                  color: FansivibeColors.primary.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  '3 PIECES',
                  style: TextStyle(
                    fontFamily: 'Inter',
                    fontSize: 9.5,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.8,
                    color: FansivibeColors.primary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          const Text(
            'Curated Autumn Evening',
            style: TextStyle(
              fontFamily: 'Noto Serif',
              fontSize: 22,
              fontWeight: FontWeight.w500,
              color: FansivibeColors.onSurface,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            'A complete look selected around your style profile.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              fontSize: 13,
              color: FansivibeColors.secondary,
            ),
          ),
          const SizedBox(height: 18),

          // 3-Product Row
          Row(
            children: [
              Expanded(
                child: _buildLookPiece(
                  title: 'Wool Overcoat',
                  price: '₹28,000',
                  asset: 'assets/images/discover_item_wool_coat.jpg',
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _buildLookPiece(
                  title: 'Cashmere Knit',
                  price: '₹14,500',
                  asset: 'assets/images/discover_moodboard_texture.jpg',
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _buildLookPiece(
                  title: 'Chelsea Boot',
                  price: '₹18,200',
                  asset: 'assets/images/discover_cat_sneakers.jpg',
                ),
              ),
            ],
          ),

          const SizedBox(height: 16),

          // Total Look Price Row
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'TOTAL LOOK',
                style: TextStyle(
                  fontFamily: 'Inter',
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.2,
                  color: FansivibeColors.secondary,
                ),
              ),
              const Text(
                '₹60,700',
                style: TextStyle(
                  fontFamily: 'Inter',
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: FansivibeColors.onSurface,
                ),
              ),
            ],
          ),

          const SizedBox(height: 16),

          // SHOP THE LOOK (3 PIECES) → CTA
          Semantics(
            button: true,
            label: 'Shop the Look (3 Pieces)',
            child: InkWell(
              onTap: onShopLookTap,
              borderRadius: BorderRadius.circular(26),
              child: Container(
                height: 48,
                decoration: BoxDecoration(
                  color: FansivibeColors.primary,
                  borderRadius: BorderRadius.circular(26),
                ),
                child: const Center(
                  child: Text(
                    'SHOP THE LOOK (3 PIECES) →',
                    style: TextStyle(
                      fontFamily: 'Inter',
                      fontSize: 12.5,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.2,
                      color: Color(0xFF131313),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLookPiece({
    required String title,
    required String price,
    required String asset,
  }) {
    return Container(
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainer,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.04),
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AspectRatio(
            aspectRatio: 1.0,
            child: AtelierImage(
              assetPath: asset,
              fit: BoxFit.cover,
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontFamily: 'Inter',
                    fontSize: 11.5,
                    fontWeight: FontWeight.w500,
                    color: FansivibeColors.onSurface,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2),
                Text(
                  price,
                  style: TextStyle(
                    fontFamily: 'Inter',
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: FansivibeColors.primary,
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

// =========================================================================
// SECTION 7: TRENDING IN YOUR STYLE
// =========================================================================

class TrendingInYourStyleSection extends StatelessWidget {
  const TrendingInYourStyleSection({
    required this.savedIds,
    required this.onFavoriteToggle,
    required this.onShopTap,
    super.key,
  });

  final Set<String> savedIds;
  final void Function(String id, String title) onFavoriteToggle;
  final void Function(ForYouProductItem) onShopTap;

  @override
  Widget build(BuildContext context) {
    const p1 = ForYouProductItem(
      id: 'trend_our_legacy_shirt',
      brand: 'OUR LEGACY',
      title: 'Box Shirt in Silk',
      price: '₹18,500',
      retailer: 'End Clothing',
      matchScore: 91,
      imageAsset: 'assets/images/discover_look_modern_classics.jpg',
    );

    const p2 = ForYouProductItem(
      id: 'trend_apc_mac_coat',
      brand: 'A.P.C.',
      title: 'Mac Coat in Gabardine',
      price: '₹38,000',
      retailer: 'Mr Porter',
      matchScore: 89,
      imageAsset: 'assets/images/editorial_look_streetwear.jpg',
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Trending In Your Style',
                    style: TextStyle(
                      fontFamily: 'Noto Serif',
                      fontSize: 22,
                      fontWeight: FontWeight.w500,
                      color: FansivibeColors.onSurface,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    'Quiet tailoring & smart casual.',
                    style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                      fontSize: 13,
                      color: FansivibeColors.secondary,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Text(
              'PERSONALIZED',
              style: TextStyle(
                fontFamily: 'Inter',
                fontSize: 10,
                fontWeight: FontWeight.w700,
                letterSpacing: 1.2,
                color: FansivibeColors.primary,
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),

        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: ForYouGridProductCard(
                product: p1,
                isSaved: savedIds.contains(p1.id),
                onFavoriteToggle: () => onFavoriteToggle(p1.id, p1.title),
                onShopTap: () => onShopTap(p1),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: ForYouGridProductCard(
                product: p2,
                isSaved: savedIds.contains(p2.id),
                onFavoriteToggle: () => onFavoriteToggle(p2.id, p2.title),
                onShopTap: () => onShopTap(p2),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

// =========================================================================
// SECTION 8: CURATED COLLECTIONS
// =========================================================================

class CuratedCollectionsSection extends StatelessWidget {
  const CuratedCollectionsSection({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'CURATED COLLECTIONS',
          style: TextStyle(
            fontFamily: 'Inter',
            fontSize: 11,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.5,
            color: FansivibeColors.primary,
          ),
        ),
        const SizedBox(height: 4),
        const Text(
          'Seasonal Directives',
          style: TextStyle(
            fontFamily: 'Noto Serif',
            fontSize: 22,
            fontWeight: FontWeight.w500,
            color: FansivibeColors.onSurface,
          ),
        ),
        const SizedBox(height: 16),

        _buildCollectionCard(
          context,
          title: 'Quiet Luxury',
          subtitle: 'The art of understated elegance and impeccable fabrics.',
          count: '28 PIECES',
          imageAsset: 'assets/images/discover_foryou_archive.jpg',
        ),

        const SizedBox(height: 14),

        _buildCollectionCard(
          context,
          title: 'Modern Minimal',
          subtitle: 'Clean lines, neutral tones, and architectural forms.',
          count: '34 PIECES',
          imageAsset: 'assets/images/discover_foryou_silhouette.jpg',
        ),
      ],
    );
  }

  Widget _buildCollectionCard(
    BuildContext context, {
    required String title,
    required String subtitle,
    required String count,
    required String imageAsset,
  }) {
    return Semantics(
      button: true,
      label: 'Explore $title Collection',
      child: InkWell(
        onTap: () {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Opening $title collection...'),
              backgroundColor: FansivibeColors.accentGold,
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(
                borderRadius: FansivibeRadius.smdBorder,
              ),
              duration: const Duration(seconds: 2),
            ),
          );
        },
        borderRadius: BorderRadius.circular(16),
        child: Container(
          height: 170,
          decoration: BoxDecoration(
            color: FansivibeColors.surfaceContainerLow,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: Colors.white.withValues(alpha: 0.06),
              width: 1,
            ),
          ),
          clipBehavior: Clip.antiAlias,
          child: Stack(
            fit: StackFit.expand,
            children: [
              AtelierImage(
                assetPath: imageAsset,
                fit: BoxFit.cover,
              ),
              Container(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.centerLeft,
                    end: Alignment.centerRight,
                    colors: [
                      Colors.black.withValues(alpha: 0.85),
                      Colors.black.withValues(alpha: 0.45),
                    ],
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 3,
                      ),
                      decoration: BoxDecoration(
                        color: FansivibeColors.primary.withValues(alpha: 0.2),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        count,
                        style: TextStyle(
                          fontFamily: 'Inter',
                          fontSize: 9.5,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 1.0,
                          color: FansivibeColors.primary,
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      title,
                      style: const TextStyle(
                        fontFamily: 'Noto Serif',
                        fontSize: 22,
                        fontWeight: FontWeight.w600,
                        color: FansivibeColors.onSurface,
                      ),
                    ),
                    const SizedBox(height: 4),
                    SizedBox(
                      width: 220,
                      child: Text(
                        subtitle,
                        style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                          fontSize: 12,
                          color: Colors.white.withValues(alpha: 0.8),
                          height: 1.35,
                        ),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    const SizedBox(height: 10),
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          'SHOP NOW →',
                          style: TextStyle(
                            fontFamily: 'Inter',
                            fontSize: 11.5,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 1.0,
                            color: FansivibeColors.primary,
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
    );
  }
}

// =========================================================================
// SECTION 9: THE FINISHING TOUCHES (ACCESSORIES)
// =========================================================================

class FinishingTouchesSection extends StatelessWidget {
  const FinishingTouchesSection({
    required this.onShopTap,
    super.key,
  });

  final void Function(ForYouProductItem) onShopTap;

  @override
  Widget build(BuildContext context) {
    const items = [
      ForYouProductItem(
        id: 'acc_ring',
        brand: 'TOM WOOD',
        title: 'Signet Ring',
        price: '₹8,200',
        retailer: 'MatchesFashion',
        imageAsset: 'assets/images/discover_cat_accessories.jpg',
      ),
      ForYouProductItem(
        id: 'acc_shades',
        brand: 'CUBITTS',
        title: 'Sunglasses',
        price: '₹14,000',
        retailer: 'SSENSE',
        imageAsset: 'assets/images/discover_moodboard_accents.jpg',
      ),
      ForYouProductItem(
        id: 'acc_tote',
        brand: 'ACNE STUDIOS',
        title: 'Leather Tote',
        price: '₹22,500',
        retailer: 'Mytheresa',
        imageAsset: 'assets/images/discover_cat_clothing.jpg',
      ),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'THE FINISHING TOUCHES',
          style: TextStyle(
            fontFamily: 'Inter',
            fontSize: 11,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.5,
            color: FansivibeColors.primary,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          'Accessories matching your personal style.',
          style: FansivibeTypography.bodyMediumWithFamily.copyWith(
            fontSize: 13,
            color: FansivibeColors.secondary,
          ),
        ),
        const SizedBox(height: 16),

        Row(
          children: items.map((item) {
            return Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4),
                child: Semantics(
                  button: true,
                  label: '${item.brand} ${item.title}, ${item.price}',
                  child: InkWell(
                    onTap: () => onShopTap(item),
                    borderRadius: BorderRadius.circular(12),
                    child: Container(
                      decoration: BoxDecoration(
                        color: FansivibeColors.surfaceContainerLow,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: Colors.white.withValues(alpha: 0.05),
                        ),
                      ),
                      clipBehavior: Clip.antiAlias,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          AspectRatio(
                            aspectRatio: 1.0,
                            child: AtelierImage(
                              assetPath: item.imageAsset,
                              fit: BoxFit.cover,
                            ),
                          ),
                          Padding(
                            padding: const EdgeInsets.all(8),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  item.title,
                                  style: const TextStyle(
                                    fontFamily: 'Inter',
                                    fontSize: 11,
                                    fontWeight: FontWeight.w600,
                                    color: FansivibeColors.onSurface,
                                  ),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  item.price,
                                  style: TextStyle(
                                    fontFamily: 'Inter',
                                    fontSize: 11.5,
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
                ),
              ),
            );
          }).toList(),
        ),
      ],
    );
  }
}
