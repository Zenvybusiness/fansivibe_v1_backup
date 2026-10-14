import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/features/discover/data/discover_client.dart';
import 'package:fansivibe/features/discover/data/discover_models.dart';
import 'package:fansivibe/features/discover/data/discover_repository.dart';
import 'package:fansivibe/features/discover/presentation/widgets/discover_editorial_widgets.dart';
import 'package:fansivibe/features/discover/presentation/widgets/existing_user_for_you_widgets.dart';

/// Modal bottom sheet for comparing verified multi-retailer commercial offers (DISCOVERY-10B-3).
///
/// Follows Digital Atelier design language.
/// Invariants:
/// - Synthetic test fixtures display an explicit development-fixture disclosure without fake merchant buttons.
/// - Active retailer offers display verified price, currency, availability, variant details, and freshness.
/// - Outbound purchase redirect uses server-mediated redirect URLs.
/// - Records minimal offer_click attribution telemetry upon user selection.
class ProductOfferComparisonSheet extends StatefulWidget {
  const ProductOfferComparisonSheet({
    required this.product,
    this.repository,
    this.guestSessionId,
    this.onPurchaseTap,
    this.initialOffers,
    super.key,
  });

  final ForYouProductItem product;
  final DiscoverRepository? repository;
  final String? guestSessionId;
  final void Function(ProductOfferItem offer, Uri redirectUri)? onPurchaseTap;
  final List<ProductOfferItem>? initialOffers;

  @override
  State<ProductOfferComparisonSheet> createState() =>
      _ProductOfferComparisonSheetState();
}

class _ProductOfferComparisonSheetState
    extends State<ProductOfferComparisonSheet> {
  bool _isLoading = false;
  String? _errorMessage;
  List<ProductOfferItem> _offers = const [];
  bool _isSyntheticFixture = false;

  @override
  void initState() {
    super.initState();
    _isSyntheticFixture = widget.product.isSyntheticFixture;
    if (widget.initialOffers != null) {
      _offers = widget.initialOffers!;
    } else if (!_isSyntheticFixture && widget.repository != null) {
      _fetchOffers();
    }
  }

  Future<void> _fetchOffers() async {
    if (widget.repository == null) return;
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    final result = await widget.repository!.getProductOffers(widget.product.id);
    if (!mounted) return;

    if (result.isSuccess && result.response != null) {
      setState(() {
        _isLoading = false;
        _isSyntheticFixture = result.response!.isSyntheticFixture;
        _offers = result.response!.offers;
      });
    } else {
      setState(() {
        _isLoading = false;
        _errorMessage = 'Unable to load verified merchant offers. Please try again.';
      });
    }
  }

  void _handlePurchase(ProductOfferItem offer) {
    final repo = widget.repository;
    final redirectUri = repo != null
        ? repo.getOfferRedirectUri(
            offerId: offer.id,
            guestSessionId: widget.guestSessionId,
            surface: 'product_offer_sheet',
          )
        : Uri.parse(offer.redirectUrl);

    // Record minimal offer_click attribution event via repository
    if (repo != null) {
      repo.recordEvents(
        [
          DiscoveryEventItem(
            eventId: newDiscoveryEventId(),
            eventType: 'offer_click',
            targetType: 'product',
            targetId: widget.product.id,
            surface: 'product_offer_sheet',
            metadata: {
              'offerId': offer.id,
              'retailer': offer.retailer.name,
              'retailerSlug': offer.retailer.slug,
            },
            occurredAt: DateTime.now().toUtc().toIso8601String(),
          ),
        ],
        guestSessionId: widget.guestSessionId,
      );
    }

    if (widget.onPurchaseTap != null) {
      widget.onPurchaseTap!(offer, redirectUri);
      return;
    }

    Navigator.of(context).pop();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Redirecting to ${offer.retailer.name}...'),
        backgroundColor: FansivibeColors.accentGold,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: FansivibeRadius.smdBorder,
        ),
        duration: const Duration(seconds: 3),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.of(context).size.height * 0.85,
      ),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.08),
          width: 1,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Drag handle
            Center(
              child: Container(
                margin: const EdgeInsets.only(top: 12, bottom: 8),
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),

            // Header Row: Brand, Product Title, Close button
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Product thumbnail
                  ClipRRect(
                    borderRadius: BorderRadius.circular(10),
                    child: SizedBox(
                      width: 54,
                      height: 66,
                      child: AtelierImage(
                        assetPath: widget.product.imageAsset,
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
                          widget.product.brand.toUpperCase(),
                          style: TextStyle(
                            fontFamily: 'Inter',
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 1.2,
                            color: FansivibeColors.primary,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 3),
                        Text(
                          widget.product.title,
                          style: const TextStyle(
                            fontFamily: 'Noto Serif',
                            fontSize: 16.5,
                            fontWeight: FontWeight.w500,
                            color: FansivibeColors.onSurface,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close_rounded),
                    color: FansivibeColors.secondary,
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ],
              ),
            ),

            const Divider(color: Color(0x1AFFFFFF), height: 16),

            // Main Body: Synthetic Disclosure OR Offers List
            Flexible(
              child: SingleChildScrollView(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                child: _buildBody(context),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_isSyntheticFixture) {
      return _buildSyntheticFixtureNotice(context);
    }

    if (_isLoading) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 40),
        child: Column(
          children: const [
            CircularProgressIndicator(
              strokeWidth: 2,
              valueColor: AlwaysStoppedAnimation<Color>(FansivibeColors.primary),
            ),
            SizedBox(height: 16),
            Text(
              'Retrieving verified merchant pricing...',
              style: TextStyle(
                fontFamily: 'Inter',
                fontSize: 13,
                color: FansivibeColors.secondary,
              ),
            ),
          ],
        ),
      );
    }

    if (_errorMessage != null) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 32),
        child: Column(
          children: [
            const Icon(Icons.cloud_off_rounded, size: 36, color: Color(0xFFE74C3C)),
            const SizedBox(height: 12),
            Text(
              _errorMessage!,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: 'Inter',
                fontSize: 13.5,
                color: FansivibeColors.onSurface,
              ),
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _fetchOffers,
              style: ElevatedButton.styleFrom(
                backgroundColor: FansivibeColors.surfaceContainerHigh,
                foregroundColor: FansivibeColors.primary,
                shape: RoundedRectangleBorder(
                  borderRadius: FansivibeRadius.smdBorder,
                ),
              ),
              child: const Text('Retry'),
            ),
          ],
        ),
      );
    }

    if (_offers.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 36),
        child: Center(
          child: Column(
            children: const [
              Icon(Icons.storefront_outlined, size: 36, color: FansivibeColors.secondary),
              SizedBox(height: 12),
              Text(
                'No verified commercial offers found for this product.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Inter',
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.onSurface,
                ),
              ),
              SizedBox(height: 6),
              Text(
                'Merchant catalogs and partner inventory are updated regularly.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Inter',
                  fontSize: 12.5,
                  color: FansivibeColors.secondary,
                ),
              ),
            ],
          ),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            const Text(
              'AVAILABLE OFFERS',
              style: TextStyle(
                fontFamily: 'Inter',
                fontSize: 11,
                fontWeight: FontWeight.w700,
                letterSpacing: 1.2,
                color: FansivibeColors.secondary,
              ),
            ),
            Text(
              '${_offers.length} ${_offers.length == 1 ? "merchant" : "merchants"} verified',
              style: const TextStyle(
                fontFamily: 'Inter',
                fontSize: 11,
                color: FansivibeColors.secondary,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        ..._offers.map((offer) => _buildOfferCard(context, offer)),
      ],
    );
  }

  Widget _buildSyntheticFixtureNotice(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFFD35400).withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: const Color(0xFFD35400).withValues(alpha: 0.35),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: const [
              Icon(Icons.science_outlined, color: Color(0xFFE67E22), size: 20),
              SizedBox(width: 8),
              Text(
                'DEVELOPMENT FIXTURE',
                style: TextStyle(
                  fontFamily: 'Inter',
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.0,
                  color: Color(0xFFE67E22),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          const Text(
            'Synthetic Demo Product',
            style: TextStyle(
              fontFamily: 'Noto Serif',
              fontSize: 17,
              fontWeight: FontWeight.w600,
              color: FansivibeColors.onSurface,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '${widget.product.title} is a development fixture catalog item created for style harmonization and aesthetic recommendation testing. It does not possess active commercial inventory or authorized merchant checkout links.',
            style: TextStyle(
              fontFamily: 'Inter',
              fontSize: 13,
              height: 1.4,
              color: FansivibeColors.onSurface.withValues(alpha: 0.8),
            ),
          ),
          const SizedBox(height: 18),
          Center(
            child: TextButton(
              onPressed: () => Navigator.of(context).pop(),
              style: TextButton.styleFrom(
                foregroundColor: FansivibeColors.primary,
              ),
              child: const Text(
                'Understood',
                style: TextStyle(
                  fontFamily: 'Inter',
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildOfferCard(BuildContext context, ProductOfferItem offer) {
    final currencySymbol = offer.currency == 'INR'
        ? '₹'
        : (offer.currency == 'USD' ? '\$' : '${offer.currency} ');
    final priceStr = '$currencySymbol${offer.price.toInt() == offer.price ? offer.price.toInt().toString() : offer.price.toStringAsFixed(2)}';
    final originalPriceStr = offer.originalPrice != null
        ? '$currencySymbol${offer.originalPrice!.toInt() == offer.originalPrice ? offer.originalPrice!.toInt().toString() : offer.originalPrice!.toStringAsFixed(2)}'
        : null;

    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.07),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Top row: Retailer Name & Verified Price
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      offer.retailer.name,
                      style: const TextStyle(
                        fontFamily: 'Inter',
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: FansivibeColors.onSurface,
                      ),
                    ),
                    if (offer.retailer.domain.isNotEmpty)
                      Text(
                        offer.retailer.domain,
                        style: const TextStyle(
                          fontFamily: 'Inter',
                          fontSize: 11.5,
                          color: FansivibeColors.secondary,
                        ),
                      ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    priceStr,
                    style: const TextStyle(
                      fontFamily: 'Inter',
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: FansivibeColors.primary,
                    ),
                  ),
                  if (originalPriceStr != null)
                    Text(
                      originalPriceStr,
                      style: TextStyle(
                        fontFamily: 'Inter',
                        fontSize: 12,
                        decoration: TextDecoration.lineThrough,
                        color: FansivibeColors.secondary.withValues(alpha: 0.8),
                      ),
                    ),
                ],
              ),
            ],
          ),

          const SizedBox(height: 10),

          // Metadata badges: Freshness, In Stock, Variant
          Wrap(
            spacing: 8,
            runSpacing: 6,
            children: [
              // Stock badge
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                decoration: BoxDecoration(
                  color: offer.inStock
                      ? const Color(0xFF2ECC71).withValues(alpha: 0.15)
                      : const Color(0xFFE74C3C).withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  offer.inStock ? 'IN STOCK' : 'OUT OF STOCK',
                  style: TextStyle(
                    fontFamily: 'Inter',
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    color: offer.inStock
                        ? const Color(0xFF2ECC71)
                        : const Color(0xFFE74C3C),
                  ),
                ),
              ),

              // Freshness badge
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                decoration: BoxDecoration(
                  color: offer.isPriceFresh
                      ? FansivibeColors.primary.withValues(alpha: 0.15)
                      : const Color(0xFFE67E22).withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  offer.isPriceFresh
                      ? '✓ Price Verified (<24h)'
                      : '⚠️ Price Verification Stale',
                  style: TextStyle(
                    fontFamily: 'Inter',
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                    color: offer.isPriceFresh
                        ? FansivibeColors.primary
                        : const Color(0xFFE67E22),
                  ),
                ),
              ),

              // Variant details if present
              if (offer.variant != null) ...[
                if (offer.variant!.size != null)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.08),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      'Size: ${offer.variant!.size}',
                      style: const TextStyle(
                        fontFamily: 'Inter',
                        fontSize: 10,
                        color: FansivibeColors.onSurface,
                      ),
                    ),
                  ),
                if (offer.variant!.color != null)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.08),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      'Color: ${offer.variant!.color}',
                      style: const TextStyle(
                        fontFamily: 'Inter',
                        fontSize: 10,
                        color: FansivibeColors.onSurface,
                      ),
                    ),
                  ),
              ],
            ],
          ),

          const SizedBox(height: 14),

          // Clearly labeled retailer purchase action button
          Semantics(
            button: true,
            label: 'Buy at ${offer.retailer.name}',
            child: InkWell(
              onTap: offer.inStock ? () => _handlePurchase(offer) : null,
              borderRadius: BorderRadius.circular(22),
              child: Container(
                height: 44,
                decoration: BoxDecoration(
                  color: offer.inStock
                      ? FansivibeColors.primary
                      : FansivibeColors.surfaceContainer,
                  borderRadius: BorderRadius.circular(22),
                ),
                child: Center(
                  child: Text(
                    offer.inStock
                        ? 'BUY AT ${offer.retailer.name.toUpperCase()} →'
                        : 'OUT OF STOCK AT ${offer.retailer.name.toUpperCase()}',
                    style: TextStyle(
                      fontFamily: 'Inter',
                      fontSize: 12.5,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.0,
                      color: offer.inStock
                          ? const Color(0xFF131313)
                          : FansivibeColors.secondary,
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
}

/// Convenience helper to display the [ProductOfferComparisonSheet] modal bottom sheet.
Future<void> showProductOfferComparisonSheet({
  required BuildContext context,
  required ForYouProductItem product,
  DiscoverRepository? repository,
  String? guestSessionId,
  void Function(ProductOfferItem offer, Uri redirectUri)? onPurchaseTap,
  List<ProductOfferItem>? initialOffers,
}) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (ctx) => ProductOfferComparisonSheet(
      product: product,
      repository: repository,
      guestSessionId: guestSessionId,
      onPurchaseTap: onPurchaseTap,
      initialOffers: initialOffers,
    ),
  );
}
