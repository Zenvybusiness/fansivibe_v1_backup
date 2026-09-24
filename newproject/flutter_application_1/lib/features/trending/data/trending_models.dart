// M14 Trending DTOs — mirrors `GET /v1/trending` exactly (camelCase).
//
// Backend is the sole source of truth: scores, provenance, and product
// fields travel verbatim. Null product fields (price/url/image/stock)
// mean "not provided by the source" — never defaulted, never faked.

/// One purchasable product matched to a trend, verbatim from backend.
class TrendingProduct {
  const TrendingProduct({
    required this.provider,
    required this.externalId,
    required this.title,
    required this.brand,
    this.priceInr,
    this.imageUrl,
    this.productUrl,
    this.inStock,
  });

  final String provider;
  final String externalId;
  final String title;
  final String brand;
  final double? priceInr;
  final String? imageUrl;
  final String? productUrl;
  final bool? inStock;

  factory TrendingProduct.fromJson(Map<String, dynamic> json) =>
      TrendingProduct(
        provider: json['provider'] as String,
        externalId: json['externalId'] as String,
        title: json['title'] as String,
        brand: json['brand'] as String,
        priceInr: (json['priceInr'] as num?)?.toDouble(),
        imageUrl: json['imageUrl'] as String?,
        productUrl: json['productUrl'] as String?,
        inStock: json['inStock'] as bool?,
      );
}

/// One normalized trend with score, freshness, provenance, products.
class TrendingItem {
  const TrendingItem({
    required this.trendId,
    required this.displayName,
    required this.category,
    required this.region,
    required this.velocity,
    required this.confidence,
    this.freshnessHours,
    required this.supportingSignals,
    required this.sources,
    required this.provenance,
    required this.matchedProducts,
  });

  final String trendId;
  final String displayName;
  final String category;
  final String region;
  final double velocity;
  final double confidence;
  final double? freshnessHours;
  final int supportingSignals;
  final List<String> sources;
  final List<Map<String, dynamic>> provenance;
  final List<TrendingProduct> matchedProducts;

  factory TrendingItem.fromJson(Map<String, dynamic> json) => TrendingItem(
    trendId: json['trendId'] as String,
    displayName: json['displayName'] as String,
    category: json['category'] as String,
    region: json['region'] as String,
    velocity: (json['velocity'] as num).toDouble(),
    confidence: (json['confidence'] as num).toDouble(),
    freshnessHours: (json['freshnessHours'] as num?)?.toDouble(),
    supportingSignals: json['supportingSignals'] as int,
    sources: (json['sources'] as List).map((e) => e as String).toList(),
    provenance: (json['provenance'] as List)
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList(),
    matchedProducts: (json['matchedProducts'] as List)
        .map((e) => TrendingProduct.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList(),
  );
}

/// Trending feed envelope.
class TrendingFeed {
  const TrendingFeed({
    required this.region,
    required this.generatedAt,
    required this.isStale,
    required this.items,
  });

  final String region;
  final String generatedAt;
  final bool isStale;
  final List<TrendingItem> items;

  factory TrendingFeed.fromJson(Map<String, dynamic> json) => TrendingFeed(
    region: json['region'] as String,
    generatedAt: json['generatedAt'] as String,
    isStale: json['isStale'] as bool? ?? false,
    items: (json['items'] as List)
        .map((e) => TrendingItem.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList(),
  );
}

/// Typed failures — never throws, never falls back to mock data.
enum TrendingFailure { unauthorized, networkError, unknown }

/// Trending result: feed page or typed failure.
class TrendingFeedResult {
  const TrendingFeedResult.page(this.feed) : failure = null;
  const TrendingFeedResult.failure(this.failure) : feed = null;

  final TrendingFeed? feed;
  final TrendingFailure? failure;
}

/// Single-trend result: item, not-found, or failure.
class TrendingDetailResult {
  const TrendingDetailResult.available(this.item)
    : notFound = false,
      failure = null;
  const TrendingDetailResult.notFound() : item = null, notFound = true, failure = null;
  const TrendingDetailResult.failure(this.failure) : item = null, notFound = false;

  final TrendingItem? item;
  final bool notFound;
  final TrendingFailure? failure;
}
