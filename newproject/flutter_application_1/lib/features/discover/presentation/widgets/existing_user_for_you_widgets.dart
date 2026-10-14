import 'dart:async';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/discover/data/discover_client.dart'
    show newDiscoveryEventId;
import 'package:fansivibe/features/discover/data/discover_models.dart';
import 'package:fansivibe/features/discover/data/discover_repository.dart';
import 'package:fansivibe/features/discover/presentation/widgets/discover_editorial_widgets.dart';
import 'package:fansivibe/features/discover/presentation/widgets/product_impression_detector.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart'
    show WardrobeItemData;
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
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
    this.isSyntheticFixture = false,
    this.provenance = 'catalog',
    this.currency = 'INR',
    this.rawPrice,
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
  final bool isSyntheticFixture;
  final String provenance;
  final String currency;
  final double? rawPrice;

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
    bool? isSyntheticFixture,
    String? provenance,
    String? currency,
    double? rawPrice,
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
      isSyntheticFixture: isSyntheticFixture ?? this.isSyntheticFixture,
      provenance: provenance ?? this.provenance,
      currency: currency ?? this.currency,
      rawPrice: rawPrice ?? this.rawPrice,
    );
  }

  factory ForYouProductItem.fromRecommendation(
    ProductRecommendationItem item, {
    bool isSaved = false,
  }) {
    final currencySymbol = item.currency == 'INR'
        ? '₹'
        : (item.currency == 'USD' ? '\$' : '${item.currency} ');
    final priceStr = item.price != null
        ? '$currencySymbol${item.price!.toInt() == item.price ? item.price!.toInt().toString() : item.price!.toStringAsFixed(2)}'
        : 'Price on request';

    final reasonsList = <String>[];
    if (item.explanation.summary.isNotEmpty) {
      reasonsList.add(item.explanation.summary);
    }
    for (final r in item.explanation.reasons) {
      if (!reasonsList.contains(r)) reasonsList.add(r);
    }
    if (reasonsList.isEmpty) {
      reasonsList.add('Curated to match your visual profile and aesthetic concepts.');
    }

    final matchPercentage = item.score.round().clamp(0, 100);
    final imageUrl = item.imageUrls.isNotEmpty
        ? item.imageUrls.first
        : 'assets/images/discover_hero_quiet_luxury.jpg';

    return ForYouProductItem(
      id: item.id,
      brand: (item.brand != null && item.brand!.isNotEmpty)
          ? item.brand!
          : 'Fansivibe Atelier',
      title: item.title,
      price: priceStr,
      imageAsset: imageUrl,
      retailer: (item.brand != null && item.brand!.isNotEmpty)
          ? '${item.brand} Official'
          : 'Atelier Partner',
      matchScore: matchPercentage,
      category: (item.category != null && item.category!.isNotEmpty)
          ? item.category!
          : 'All Picks',
      reasons: reasonsList,
      isSaved: isSaved,
      isSyntheticFixture: item.isSyntheticFixture,
      provenance: item.isSyntheticFixture ? 'fixture' : 'catalog',
      currency: item.currency,
      rawPrice: item.price,
    );
  }
}

/// The complete established-user personalized For You feed matching
/// `Foryou page for old user.jpg`.
class EstablishedUserForYouFeed extends StatefulWidget {
  const EstablishedUserForYouFeed({
    super.key,
    this.repository,
    this.wardrobeRepository,
    this.searchQuery = '',
    this.onShopTap,
    this.onBuildLookTap,
    this.onResetFilters,
  });

  final DiscoverRepository? repository;
  final WardrobeRepository? wardrobeRepository;
  final String searchQuery;
  final void Function(ForYouProductItem product)? onShopTap;
  final VoidCallback? onBuildLookTap;
  final VoidCallback? onResetFilters;

  @override
  State<EstablishedUserForYouFeed> createState() =>
      _EstablishedUserForYouFeedState();
}

class _EstablishedUserForYouFeedState extends State<EstablishedUserForYouFeed> {
  String _selectedCategory = 'All Picks';
  late Set<String> _savedProductIds;
  final Set<String> _impressedProductIds = <String>{};
  final List<Timer> _retryTimers = [];

  bool _loading = false;
  bool _categoryLoading = false;
  DiscoverFailure? _failure;
  List<ProductRecommendationItem> _apiRecommendations = [];
  int _currentPage = 1;
  static const int _pageSize = 20;
  bool _hasMore = false;
  bool _loadingMore = false;
  int _totalCount = 0;
  int _totalPages = 0;
  int _forYouRequestId = 0;

  bool _completeLooksLoading = false;
  DiscoverFailure? _completeLooksFailure;
  List<CompleteLook> _apiCompleteLooks = [];
  int _selectedLookIndex = 0;
  CompleteLook? get _apiCompleteLook =>
      _apiCompleteLooks.isNotEmpty && _selectedLookIndex < _apiCompleteLooks.length
          ? _apiCompleteLooks[_selectedLookIndex]
          : null;

  // Complete Look controls (Phase 5)
  double? _selectedMaxBudget;
  String? _selectedOccasion;
  String? _selectedWardrobeAnchorId;
  List<WardrobeItemData> _ownedWardrobeItems = [];

  static List<String>? backendCategoriesFor(String category) {
    final lower = category.trim().toLowerCase();
    if (lower == 'all picks' || lower == 'all') {
      return null;
    }
    if (lower == 'jackets & coats' || lower == 'outerwear') {
      return const ['outerwear'];
    }
    if (lower == 'knitwear' || lower == 'tops') {
      return const ['tops'];
    }
    if (lower == 'trousers' || lower == 'bottoms') {
      return const ['bottoms'];
    }
    if (lower == 'sneakers' || lower == 'footwear') {
      return const ['footwear'];
    }
    if (lower == 'accessories') {
      return const ['accessories'];
    }
    return [lower];
  }

  @override
  void initState() {
    super.initState();
    _savedProductIds = Set<String>.from(LocalStorage.savedLookIds);
    AuthSession.authVersion.addListener(_handleAuthVersionChanged);
    if (widget.repository != null) {
      _fetchApiData();
    }
    _loadWardrobeItems();
  }

  @override
  void didUpdateWidget(EstablishedUserForYouFeed oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.repository != widget.repository) {
      if (widget.repository != null) {
        _fetchApiData();
      }
    }
    if (oldWidget.wardrobeRepository != widget.wardrobeRepository) {
      _loadWardrobeItems();
    }
    if (oldWidget.searchQuery.trim() != widget.searchQuery.trim()) {
      if (widget.repository != null) {
        _onSearchQueryChanged();
      }
    }
  }

  @override
  void dispose() {
    for (final timer in _retryTimers) {
      timer.cancel();
    }
    _retryTimers.clear();
    AuthSession.authVersion.removeListener(_handleAuthVersionChanged);
    super.dispose();
  }

  void _handleAuthVersionChanged() {
    if (!mounted) return;
    _loadWardrobeItems();
    if (widget.repository != null) {
      _fetchApiData();
    }
  }

  void _loadWardrobeItems() {
    if (!AuthSession.isAuthenticated) {
      _ownedWardrobeItems = const [];
      return;
    }
    final repo = widget.wardrobeRepository ?? WardrobeRepositoryImpl();
    repo.listItems().then((items) {
      if (mounted) {
        setState(() {
          _ownedWardrobeItems = items;
        });
      }
    }).catchError((_) {});
  }

  Future<void> _fetchApiData() async {
    if (widget.repository == null) return;
    final requestId = ++_forYouRequestId;
    setState(() {
      _loading = true;
      _failure = null;
      _completeLooksLoading = true;
      _completeLooksFailure = null;
    });

    final isGuest = !AuthSession.isAuthenticated;
    final backendCats = backendCategoriesFor(_selectedCategory);
    final query = widget.searchQuery.trim().isNotEmpty
        ? widget.searchQuery.trim()
        : null;

    try {
      final results = await Future.wait([
        widget.repository!.getForYouRecommendations(
          page: 1,
          pageSize: _pageSize,
          categories: backendCats,
          q: query,
          isGuest: isGuest,
        ),
        widget.repository!.getCompleteLooks(
          allowWardrobe: !isGuest,
          limit: 5,
          maxBudget: _selectedMaxBudget,
          targetOccasion: _selectedOccasion,
          anchorWardrobeItemId: !isGuest ? _selectedWardrobeAnchorId : null,
        ),
      ]);

      if (!mounted) return;
      if (requestId != _forYouRequestId) {
        final looksResult = results[1] as CompleteLooksDiscoveryResult;
        setState(() {
          _loading = false;
          _completeLooksLoading = false;
          if (looksResult.isSuccess && _apiCompleteLooks.isEmpty) {
            _apiCompleteLooks = looksResult.response!.looks;
            _selectedLookIndex = 0;
            _completeLooksFailure = null;
          }
        });
        return;
      }

      final forYouResult = results[0] as ForYouDiscoveryResult;
      final looksResult = results[1] as CompleteLooksDiscoveryResult;

      setState(() {
        _loading = false;
        _categoryLoading = false;
        _completeLooksLoading = false;

        if (forYouResult.isSuccess) {
          final resp = forYouResult.response!;
          _apiRecommendations = resp.items;
          _currentPage = resp.page;
          _hasMore = resp.hasNext;
          _totalCount = resp.totalCount;
          _totalPages = resp.totalPages;
          _failure = null;
        } else {
          _apiRecommendations = [];
          _currentPage = 1;
          _hasMore = false;
          _failure = forYouResult.failure;
        }

        if (looksResult.isSuccess) {
          _apiCompleteLooks = looksResult.response!.looks;
          _selectedLookIndex = 0;
          _completeLooksFailure = null;
        } else {
          _apiCompleteLooks = [];
          _selectedLookIndex = 0;
          _completeLooksFailure = looksResult.failure;
        }
      });
    } catch (_) {
      if (!mounted) return;
      if (requestId != _forYouRequestId) {
        setState(() {
          _loading = false;
          _completeLooksLoading = false;
        });
        return;
      }
      setState(() {
        _loading = false;
        _categoryLoading = false;
        _completeLooksLoading = false;
        _failure = DiscoverFailure.unknown;
        _completeLooksFailure = DiscoverFailure.unknown;
        _apiRecommendations = [];
        _apiCompleteLooks = [];
        _selectedLookIndex = 0;
        _currentPage = 1;
        _hasMore = false;
      });
    }
  }

  void _onCategorySelected(String cat) {
    if (_selectedCategory == cat) return;
    setState(() {
      _selectedCategory = cat;
      _currentPage = 1;
      _hasMore = false;
      _loadingMore = false;
    });

    if (widget.repository != null) {
      _fetchRecommendationsForCategory(cat);
    }
  }

  Future<void> _fetchRecommendationsForCategory(String cat) async {
    if (widget.repository == null) return;
    final requestId = ++_forYouRequestId;
    setState(() {
      _categoryLoading = true;
      _failure = null;
    });

    final isGuest = !AuthSession.isAuthenticated;
    final backendCats = backendCategoriesFor(cat);
    final query = widget.searchQuery.trim().isNotEmpty
        ? widget.searchQuery.trim()
        : null;

    try {
      final forYouResult = await widget.repository!.getForYouRecommendations(
        page: 1,
        pageSize: _pageSize,
        categories: backendCats,
        q: query,
        isGuest: isGuest,
      );

      if (!mounted || requestId != _forYouRequestId) return;

      setState(() {
        _loading = false;
        _categoryLoading = false;
        if (forYouResult.isSuccess) {
          final resp = forYouResult.response!;
          _apiRecommendations = resp.items;
          _currentPage = resp.page;
          _hasMore = resp.hasNext;
          _totalCount = resp.totalCount;
          _totalPages = resp.totalPages;
          _failure = null;
        } else {
          _apiRecommendations = [];
          _currentPage = 1;
          _hasMore = false;
          _failure = forYouResult.failure;
        }
      });
    } catch (_) {
      if (!mounted || requestId != _forYouRequestId) return;
      setState(() {
        _loading = false;
        _categoryLoading = false;
        _failure = DiscoverFailure.unknown;
        _apiRecommendations = [];
        _currentPage = 1;
        _hasMore = false;
      });
    }
  }

  Future<void> _loadMoreRecommendations() async {
    if (widget.repository == null || _loadingMore || !_hasMore) return;
    setState(() {
      _loadingMore = true;
    });

    final isGuest = !AuthSession.isAuthenticated;
    final backendCats = backendCategoriesFor(_selectedCategory);
    final nextPage = _currentPage + 1;
    final query = widget.searchQuery.trim().isNotEmpty
        ? widget.searchQuery.trim()
        : null;

    try {
      final forYouResult = await widget.repository!.getForYouRecommendations(
        page: nextPage,
        pageSize: _pageSize,
        categories: backendCats,
        q: query,
        isGuest: isGuest,
      );

      if (!mounted) return;

      setState(() {
        _loadingMore = false;
        if (forYouResult.isSuccess) {
          final resp = forYouResult.response!;
          final existingIds = _apiRecommendations.map((r) => r.id).toSet();
          final incoming =
              resp.items.where((it) => !existingIds.contains(it.id)).toList();
          _apiRecommendations.addAll(incoming);
          _currentPage = resp.page;
          _hasMore = resp.hasNext;
          _totalCount = resp.totalCount;
          _totalPages = resp.totalPages;
        } else {
          // Failure preserves already loaded results without clearing _apiRecommendations
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(_failureCopy(forYouResult.failure)),
              backgroundColor: FansivibeColors.accentGold,
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(
                borderRadius: FansivibeRadius.smdBorder,
              ),
            ),
          );
        }
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loadingMore = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(_failureCopy(DiscoverFailure.unknown)),
          backgroundColor: FansivibeColors.accentGold,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(
            borderRadius: FansivibeRadius.smdBorder,
          ),
        ),
      );
    }
  }

  Future<void> _onSearchQueryChanged() async {
    if (widget.repository == null) return;
    final requestId = ++_forYouRequestId;
    setState(() {
      _loading = false;
      _categoryLoading = true;
      _failure = null;
      _currentPage = 1;
      _hasMore = false;
      _loadingMore = false;
    });

    final isGuest = !AuthSession.isAuthenticated;
    final backendCats = backendCategoriesFor(_selectedCategory);
    final query = widget.searchQuery.trim().isNotEmpty
        ? widget.searchQuery.trim()
        : null;

    try {
      final forYouResult = await widget.repository!.getForYouRecommendations(
        page: 1,
        pageSize: _pageSize,
        categories: backendCats,
        q: query,
        isGuest: isGuest,
      );

      if (!mounted || requestId != _forYouRequestId) return;

      setState(() {
        _loading = false;
        _categoryLoading = false;
        if (forYouResult.isSuccess) {
          final resp = forYouResult.response!;
          _apiRecommendations = resp.items;
          _currentPage = resp.page;
          _hasMore = resp.hasNext;
          _totalCount = resp.totalCount;
          _totalPages = resp.totalPages;
          _failure = null;
        } else {
          _apiRecommendations = [];
          _currentPage = 1;
          _hasMore = false;
          _failure = forYouResult.failure;
        }
      });
    } catch (_) {
      if (!mounted || requestId != _forYouRequestId) return;
      setState(() {
        _loading = false;
        _categoryLoading = false;
        _failure = DiscoverFailure.unknown;
        _apiRecommendations = [];
        _currentPage = 1;
        _hasMore = false;
      });
    }
  }

  Future<void> _fetchCompleteLooks() async {
    if (widget.repository == null) return;
    setState(() {
      _completeLooksLoading = true;
      _completeLooksFailure = null;
    });

    final isGuest = !AuthSession.isAuthenticated;

    try {
      final looksResult = await widget.repository!.getCompleteLooks(
        allowWardrobe: !isGuest,
        limit: 5,
        maxBudget: _selectedMaxBudget,
        targetOccasion: _selectedOccasion,
        anchorWardrobeItemId: !isGuest ? _selectedWardrobeAnchorId : null,
      );

      if (!mounted) return;

      setState(() {
        _completeLooksLoading = false;
        if (looksResult.isSuccess) {
          _apiCompleteLooks = looksResult.response!.looks;
          _selectedLookIndex = 0;
          _completeLooksFailure = null;
        } else {
          _apiCompleteLooks = [];
          _selectedLookIndex = 0;
          _completeLooksFailure = looksResult.failure;
        }
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _completeLooksLoading = false;
        _completeLooksFailure = DiscoverFailure.unknown;
        _apiCompleteLooks = [];
        _selectedLookIndex = 0;
      });
    }
  }

  static final RegExp _uuidRegex = RegExp(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$',
  );
  static final RegExp _lookIdRegex = RegExp(r'^look_[a-f0-9]{16}$');

  Future<void> _dispatchTelemetry(DiscoveryEventItem event) async {
    if (widget.repository == null) return;
    try {
      final result = await widget.repository!.recordEvents([event]);
      if (!result.isSuccess && mounted) {
        // Retry once asynchronously preserving the identical eventId
        Timer? timer;
        timer = Timer(const Duration(milliseconds: 1000), () async {
          _retryTimers.remove(timer);
          if (!mounted) return;
          try {
            await widget.repository?.recordEvents([event]);
          } catch (_) {
            // Observational telemetry failures must never disrupt UX
          }
        });
        _retryTimers.add(timer);
      }
    } catch (_) {
      // Observational telemetry failures must never disrupt UX
    }
  }

  void _recordImpression({
    required String productId,
    required String surface,
    int? position,
    required double visibilityRatio,
    required int dwellMs,
  }) {
    if (_impressedProductIds.contains(productId)) return;
    _impressedProductIds.add(productId);

    if (!_uuidRegex.hasMatch(productId)) return;

    final event = DiscoveryEventItem(
      eventId: newDiscoveryEventId(),
      eventType: 'product_impression',
      targetType: 'product',
      targetId: productId,
      surface: surface,
      position: position,
      metadata: {
        'dwellTimeMs': dwellMs,
        'viewportRatio': visibilityRatio.clamp(0.5, 1.0),
      },
      occurredAt: DateTime.now().toUtc().toIso8601String(),
    );

    _dispatchTelemetry(event);
  }

  void _recordLookSelect(CompleteLook look) {
    if (!_lookIdRegex.hasMatch(look.lookId)) return;

    final event = DiscoveryEventItem(
      eventId: newDiscoveryEventId(),
      eventType: 'look_select',
      targetType: 'complete_look',
      targetId: look.lookId,
      surface: 'complete_looks',
      metadata: {
        'selectedSlotCount': look.slots.length.clamp(2, 5),
        if (look.totalCatalogPrice >= 0)
          'totalCatalogPrice': look.totalCatalogPrice,
      },
      occurredAt: DateTime.now().toUtc().toIso8601String(),
    );

    _dispatchTelemetry(event);
  }

  void _toggleSave(
    String id,
    String title, {
    String surface = 'because_you_like',
    int? position,
  }) {
    final willSave = !_savedProductIds.contains(id);
    setState(() {
      if (willSave) {
        _savedProductIds.add(id);
        LearningService.instance.addSavedLook(title);
      } else {
        _savedProductIds.remove(id);
      }
      LocalStorage.savedLookIds = _savedProductIds.toList();
    });

    if (_uuidRegex.hasMatch(id)) {
      final activeCat = backendCategoriesFor(_selectedCategory)?.first;
      final event = DiscoveryEventItem(
        eventId: newDiscoveryEventId(),
        eventType: willSave ? 'product_save' : 'product_unsave',
        targetType: 'product',
        targetId: id,
        surface: surface,
        position: position,
        metadata: {
          if (activeCat != null) 'activeCategoryFilter': activeCat,
        },
        occurredAt: DateTime.now().toUtc().toIso8601String(),
      );
      _dispatchTelemetry(event);
    }
  }

  void _handleShop(BuildContext context, ForYouProductItem product) {
    if (product.isSyntheticFixture) {
      showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          backgroundColor: FansivibeColors.surfaceContainerHigh,
          shape: RoundedRectangleBorder(
            borderRadius: FansivibeRadius.mdBorder,
          ),
          title: Row(
            children: const [
              Icon(Icons.science_outlined, color: Color(0xFFE67E22), size: 20),
              SizedBox(width: 8),
              Text(
                'Synthetic Demo Product',
                style: TextStyle(
                  fontFamily: 'Inter',
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: FansivibeColors.onSurface,
                ),
              ),
            ],
          ),
          content: Text(
            '${product.title} is a synthetic demonstration fixture catalog item. It is not currently available for commercial purchase from a verified retailer.',
            style: const TextStyle(
              fontFamily: 'Inter',
              fontSize: 13.5,
              height: 1.4,
              color: FansivibeColors.secondary,
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text(
                'Understood',
                style: TextStyle(
                  fontFamily: 'Inter',
                  fontWeight: FontWeight.w700,
                  color: FansivibeColors.primary,
                ),
              ),
            ),
          ],
        ),
      );
      return;
    }

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

  String _failureCopy(DiscoverFailure? failure) {
    switch (failure) {
      case DiscoverFailure.unauthorized:
        return 'Session expired. Sign in again to refresh your personal recommendations.';
      case DiscoverFailure.invalidInput:
        return 'Invalid filter configuration. Please adjust your preferences.';
      case DiscoverFailure.rateLimited:
        return 'Too many requests. Please wait a moment.';
      case DiscoverFailure.networkError:
        return "Couldn't connect to Fansivibe server. Please check your network connection.";
      case DiscoverFailure.unknown:
      case null:
        return 'Unable to load personalized recommendations at this moment.';
    }
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

    // 1. Initial loading state (when repository is present and initial fetch is running)
    if (widget.repository != null && _loading && _apiRecommendations.isEmpty && _failure == null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 64, horizontal: 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(
                width: 36,
                height: 36,
                child: CircularProgressIndicator(
                  strokeWidth: 2.5,
                  valueColor: AlwaysStoppedAnimation<Color>(FansivibeColors.primary),
                ),
              ),
              const SizedBox(height: 16),
              Text(
                'Curating your personal style feed...',
                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                  fontSize: 13,
                  color: FansivibeColors.secondary,
                ),
              ),
            ],
          ),
        ),
      );
    }

    // 2. Request failure state (when repository is present and recommendation request failed)
    if (widget.repository != null && _failure != null && _apiRecommendations.isEmpty) {
      final isNetwork = _failure == DiscoverFailure.networkError;
      return Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 48, horizontal: 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                isNetwork ? Icons.cloud_off_rounded : Icons.error_outline_rounded,
                size: 48,
                color: isNetwork
                    ? Colors.redAccent.withValues(alpha: 0.7)
                    : FansivibeColors.accentGold.withValues(alpha: 0.7),
              ),
              const SizedBox(height: 16),
              Text(
                isNetwork ? 'Connection Unavailable' : 'Recommendations Unavailable',
                style: const TextStyle(
                  fontFamily: 'Noto Serif',
                  fontSize: 20,
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.onSurface,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              Text(
                _failureCopy(_failure),
                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                  fontSize: 13.5,
                  color: FansivibeColors.secondary,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 20),
              FansiButton.primary(
                label: 'Retry',
                icon: Icons.refresh_rounded,
                onPressed: _fetchApiData,
              ),
            ],
          ),
        ),
      );
    }

    // 3. Successful response with NO results (when repository is present and recommendations are empty)
    if (widget.repository != null && _apiRecommendations.isEmpty && _failure == null && !_loading) {
      final hasActiveFilters = _selectedCategory != 'All Picks' || widget.searchQuery.trim().isNotEmpty;
      return Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 48, horizontal: 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.search_off_rounded,
                size: 48,
                color: FansivibeColors.accentGold.withValues(alpha: 0.5),
              ),
              const SizedBox(height: 16),
              Text(
                hasActiveFilters ? 'No Matching Products' : 'No Recommendations Found',
                style: const TextStyle(
                  fontFamily: 'Noto Serif',
                  fontSize: 20,
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.onSurface,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              Text(
                hasActiveFilters
                    ? 'No products match your active filters or search terms.'
                    : 'We couldn’t find personalized fashion recommendations matching your profile right now.',
                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                  fontSize: 13.5,
                  color: FansivibeColors.secondary,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 20),
              if (hasActiveFilters)
                FansiButton.primary(
                  label: 'Reset Filters',
                  icon: Icons.refresh_rounded,
                  onPressed: () {
                    _onCategorySelected('All Picks');
                    widget.onResetFilters?.call();
                  },
                )
              else
                FansiButton.primary(
                  label: 'Refresh Feed',
                  icon: Icons.refresh_rounded,
                  onPressed: _fetchApiData,
                ),
            ],
          ),
        ),
      );
    }

    final ForYouProductItem heroProduct;
    final List<ForYouProductItem> gridProducts;

    if (_apiRecommendations.isNotEmpty) {
      heroProduct = ForYouProductItem.fromRecommendation(
        _apiRecommendations.first,
        isSaved: _savedProductIds.contains(_apiRecommendations.first.id),
      );
      gridProducts = _apiRecommendations.length > 1
          ? _apiRecommendations
              .sublist(1)
              .map((r) => ForYouProductItem.fromRecommendation(
                    r,
                    isSaved: _savedProductIds.contains(r.id),
                  ))
              .toList()
          : const <ForYouProductItem>[];
    } else {
      // Standalone design preview mode only when repository is null
      heroProduct = ForYouProductItem(
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
      );
      gridProducts = const <ForYouProductItem>[];
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // ----------------------------------------------------
        // SECTION 1: PERSONALIZED HERO PRODUCT CARD
        // ----------------------------------------------------
        ProductImpressionDetector(
          productId: heroProduct.id,
          surface: 'for_you_hero',
          position: 0,
          isAlreadyImpressed: _impressedProductIds.contains(heroProduct.id),
          onImpression: _recordImpression,
          child: PersonalizedHeroProductCard(
            product: heroProduct,
            onFavoriteToggle: () => _toggleSave(
              heroProduct.id,
              heroProduct.title,
              surface: 'for_you_hero',
              position: 0,
            ),
            onShopTap: (p) => _handleShop(context, p),
          ),
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
          onCategorySelected: _onCategorySelected,
        ),

        const SizedBox(height: 24),

        // ----------------------------------------------------
        // SECTION 5: BECAUSE YOU LIKE... (2-COLUMN GRID)
        // ----------------------------------------------------
        BecauseYouLikeSection(
          styleName: userStyleType,
          selectedCategory: _selectedCategory,
          savedIds: _savedProductIds,
          onFavoriteToggle: (id, title) => _toggleSave(
            id,
            title,
            surface: 'because_you_like',
          ),
          onShopTap: (p) => _handleShop(context, p),
          searchQuery: widget.searchQuery,
          apiProducts: _apiRecommendations.isNotEmpty ? gridProducts : null,
          allowMockFallback: widget.repository == null,
          isLoading: _categoryLoading,
          onResetFilters: () {
            _onCategorySelected('All Picks');
            widget.onResetFilters?.call();
          },
          onImpression: _recordImpression,
          impressedProductIds: _impressedProductIds,
        ),

        if (widget.repository != null && (_hasMore || _loadingMore)) ...[
          const SizedBox(height: 16),
          Center(
            child: _loadingMore
                ? const Padding(
                    padding: EdgeInsets.all(12),
                    child: SizedBox(
                      width: 24,
                      height: 24,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        valueColor: AlwaysStoppedAnimation<Color>(
                          FansivibeColors.primary,
                        ),
                      ),
                    ),
                  )
                : Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      FansiButton.secondary(
                        label: 'Load more',
                        icon: Icons.expand_more_rounded,
                        onPressed: _loadMoreRecommendations,
                      ),
                      if (_totalCount > 0) ...[
                        const SizedBox(height: 8),
                        Text(
                          'Showing ${_apiRecommendations.length} of $_totalCount items • Page $_currentPage of $_totalPages',
                          style: FansivibeTypography.labelMediumWithFamily.copyWith(
                            color: FansivibeColors.secondary.withValues(alpha: 0.7),
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ],
                  ),
          ),
        ],

        const SizedBox(height: 36),

        // ----------------------------------------------------
        // SECTION 6: ENSEMBLE CURATION / COMPLETE LOOKS
        // ----------------------------------------------------
        if (widget.repository != null) ...[
          CompleteLookControlsRow(
            selectedBudget: _selectedMaxBudget,
            onBudgetChanged: (b) {
              if (_selectedMaxBudget == b) return;
              setState(() => _selectedMaxBudget = b);
              _fetchCompleteLooks();
            },
            selectedOccasion: _selectedOccasion,
            onOccasionChanged: (occ) {
              if (_selectedOccasion == occ) return;
              setState(() => _selectedOccasion = occ);
              _fetchCompleteLooks();
            },
            selectedWardrobeAnchorId: _selectedWardrobeAnchorId,
            onWardrobeAnchorChanged: (anchorId) {
              if (_selectedWardrobeAnchorId == anchorId) return;
              setState(() => _selectedWardrobeAnchorId = anchorId);
              _fetchCompleteLooks();
            },
            ownedWardrobeItems: _ownedWardrobeItems,
            isGuest: !AuthSession.isAuthenticated,
          ),
          const SizedBox(height: 16),
        ],

        EnsembleCurationCard(
          completeLooks:
              _apiCompleteLooks.isNotEmpty ? _apiCompleteLooks : null,
          completeLook: _apiCompleteLook,
          selectedLookIndex: _selectedLookIndex,
          onLookSelected: (index) {
            setState(() => _selectedLookIndex = index);
            if (_apiCompleteLooks.isNotEmpty &&
                index < _apiCompleteLooks.length) {
              _recordLookSelect(_apiCompleteLooks[index]);
            }
          },
          isLoading: _completeLooksLoading,
          failure: _completeLooksFailure,
          onRetry: _fetchCompleteLooks,
          allowMockFallback: widget.repository == null,
          onShopLookTap: () {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(
                  _apiCompleteLook != null
                      ? 'Exploring individual ensemble pieces (${_apiCompleteLook!.slots.length} items)...'
                      : 'Adding curated ensemble (3 pieces) to cart...',
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
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
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
                      if (product.isSyntheticFixture) ...[
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 5,
                          ),
                          decoration: BoxDecoration(
                            color: const Color(0xFFD35400).withValues(alpha: 0.9),
                            borderRadius: BorderRadius.circular(14),
                          ),
                          child: const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                Icons.science_outlined,
                                color: Colors.white,
                                size: 12,
                              ),
                              SizedBox(width: 4),
                              Text(
                                'DEMO FIXTURE',
                                style: TextStyle(
                                  fontFamily: 'Inter',
                                  fontSize: 10,
                                  fontWeight: FontWeight.w700,
                                  letterSpacing: 0.8,
                                  color: Colors.white,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ],
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
                if (product.isSyntheticFixture) ...[
                  const SizedBox(height: 6),
                  Row(
                    children: const [
                      Icon(Icons.info_outline, size: 13, color: Color(0xFFE67E22)),
                      SizedBox(width: 5),
                      Expanded(
                        child: Text(
                          'Synthetic fixture catalog item • Not available for retail purchase',
                          style: TextStyle(
                            fontFamily: 'Inter',
                            fontSize: 11.5,
                            fontStyle: FontStyle.italic,
                            color: Color(0xFFE67E22),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],

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
                  label: product.isSyntheticFixture
                      ? 'Synthetic demo fixture - not available for retail purchase'
                      : 'Shop at ${product.retailer}',
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
                          product.isSyntheticFixture
                              ? 'DEMO FIXTURE • NOT FOR SALE'
                              : 'SHOP AT ${product.brand.toUpperCase()} →',
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
    this.apiProducts,
    this.allowMockFallback = false,
    this.isLoading = false,
    this.onResetFilters,
    this.onImpression,
    this.impressedProductIds,
    super.key,
  });

  final String styleName;
  final String selectedCategory;
  final Set<String> savedIds;
  final void Function(String id, String title) onFavoriteToggle;
  final void Function(ForYouProductItem) onShopTap;
  final String searchQuery;
  final List<ForYouProductItem>? apiProducts;
  final bool allowMockFallback;
  final bool isLoading;
  final VoidCallback? onResetFilters;
  final OnProductImpression? onImpression;
  final Set<String>? impressedProductIds;

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
    final List<ForYouProductItem> catalog;
    if (apiProducts != null) {
      catalog = apiProducts!;
    } else if (allowMockFallback) {
      catalog = allCatalogProducts;
    } else {
      catalog = const [];
    }

    final filtered = catalog.where((p) {
      // In design preview mode (allowMockFallback), filter by category locally.
      // In server-backed mode (apiProducts != null), the server already filters by category.
      if (allowMockFallback && selectedCategory != 'All Picks') {
        final matchesCategory =
            p.category.toLowerCase().contains(selectedCategory.toLowerCase()) ||
                selectedCategory.toLowerCase().contains(p.category.toLowerCase());
        if (!matchesCategory) return false;
      }
      // Search query filtering: backend /v1/discovery/for-you does not support a search query parameter,
      // so search remains client-side filtering over the returned candidate pool without pretending to be server-backed.
      if (searchQuery.trim().isNotEmpty) {
        final q = searchQuery.toLowerCase().trim();
        final matchesQuery = p.title.toLowerCase().contains(q) ||
            p.brand.toLowerCase().contains(q) ||
            p.category.toLowerCase().contains(q);
        if (!matchesQuery) return false;
      }
      return true;
    }).toList();

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

        if (isLoading)
          Container(
            padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 16),
            alignment: Alignment.center,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SizedBox(
                  width: 28,
                  height: 28,
                  child: CircularProgressIndicator(
                    strokeWidth: 2.5,
                    valueColor: AlwaysStoppedAnimation<Color>(
                      FansivibeColors.primary,
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  'Curating $selectedCategory picks...',
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    fontSize: 13,
                    color: FansivibeColors.secondary,
                  ),
                ),
              ],
            ),
          )
        else if (catalog.isEmpty)
          Container(
            padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 16),
            decoration: BoxDecoration(
              color: FansivibeColors.surfaceContainerLow,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: Colors.white.withValues(alpha: 0.04),
              ),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.inventory_2_outlined,
                  size: 32,
                  color: FansivibeColors.secondary.withValues(alpha: 0.6),
                ),
                const SizedBox(height: 10),
                Text(
                  'No additional recommendations available',
                  style: FansivibeTypography.titleLargeWithFamily.copyWith(
                    color: FansivibeColors.onSurface,
                    fontSize: 14,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'Check back soon for new additions to your personal catalog.',
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.secondary,
                    fontSize: 12.5,
                  ),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          )
        else if (filtered.isEmpty)
          Container(
            padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 16),
            decoration: BoxDecoration(
              color: FansivibeColors.surfaceContainerLow,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: Colors.white.withValues(alpha: 0.04),
              ),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.filter_list_off_rounded,
                  size: 32,
                  color: FansivibeColors.secondary.withValues(alpha: 0.6),
                ),
                const SizedBox(height: 10),
                Text(
                  searchQuery.trim().isNotEmpty
                      ? 'No products match "$searchQuery"'
                      : 'No products in "$selectedCategory"',
                  style: FansivibeTypography.titleLargeWithFamily.copyWith(
                    color: FansivibeColors.onSurface,
                    fontSize: 14,
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 4),
                Text(
                  'Try adjusting your search or resetting category filters to see more picks.',
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.secondary,
                    fontSize: 12.5,
                  ),
                  textAlign: TextAlign.center,
                ),
                if (onResetFilters != null) ...[
                  const SizedBox(height: 14),
                  FansiButton.secondary(
                    label: 'Reset Filters',
                    icon: Icons.refresh_rounded,
                    onPressed: onResetFilters,
                  ),
                ],
              ],
            ),
          )
        else
          LayoutBuilder(
            builder: (context, constraints) {
              const gap = 14.0;
              final columnWidth = (constraints.maxWidth - gap) / 2;

              return Wrap(
                spacing: gap,
                runSpacing: gap,
                children: filtered.asMap().entries.map((entry) {
                  final index = entry.key;
                  final p = entry.value;
                  final isSaved = savedIds.contains(p.id);

                  Widget card = SizedBox(
                    width: columnWidth,
                    child: ForYouGridProductCard(
                      product: p,
                      isSaved: isSaved,
                      onFavoriteToggle: () => onFavoriteToggle(p.id, p.title),
                      onShopTap: () => onShopTap(p),
                    ),
                  );

                  if (onImpression != null) {
                    card = ProductImpressionDetector(
                      productId: p.id,
                      surface: 'because_you_like',
                      position: index + 1,
                      isAlreadyImpressed:
                          impressedProductIds?.contains(p.id) ?? false,
                      onImpression: onImpression!,
                      child: card,
                    );
                  }

                  return card;
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
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
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
                      if (product.isSyntheticFixture) ...[
                        const SizedBox(width: 4),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 5,
                            vertical: 3,
                          ),
                          decoration: BoxDecoration(
                            color: const Color(0xFFD35400).withValues(alpha: 0.9),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: const Text(
                            'DEMO',
                            style: TextStyle(
                              fontFamily: 'Inter',
                              fontSize: 9,
                              fontWeight: FontWeight.w700,
                              color: Colors.white,
                            ),
                          ),
                        ),
                      ],
                    ],
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
                  label: product.isSyntheticFixture
                      ? 'Synthetic demo product'
                      : 'Shop ${product.title}',
                  child: InkWell(
                    onTap: onShopTap,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          product.isSyntheticFixture ? 'DEMO ITEM →' : 'SHOP →',
                          style: TextStyle(
                            fontFamily: 'Inter',
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 1.0,
                            color: product.isSyntheticFixture
                                ? const Color(0xFFE67E22)
                                : FansivibeColors.primary,
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
    this.completeLook,
    this.completeLooks,
    this.selectedLookIndex = 0,
    this.onLookSelected,
    this.isLoading = false,
    this.failure,
    this.onRetry,
    this.allowMockFallback = false,
    super.key,
  });

  final VoidCallback onShopLookTap;
  final CompleteLook? completeLook;
  final List<CompleteLook>? completeLooks;
  final int selectedLookIndex;
  final ValueChanged<int>? onLookSelected;
  final bool isLoading;
  final DiscoverFailure? failure;
  final VoidCallback? onRetry;
  final bool allowMockFallback;

  @override
  Widget build(BuildContext context) {
    if (isLoading) {
      return _buildLoading(context);
    }
    if (failure != null) {
      return _buildError(context);
    }
    final looks = completeLooks ?? (completeLook != null ? [completeLook!] : null);
    if (looks != null && looks.isNotEmpty) {
      final safeIndex = selectedLookIndex.clamp(0, looks.length - 1);
      return _buildApiLook(context, looks[safeIndex], looks, safeIndex);
    }
    if (completeLook != null) {
      return _buildApiLook(context, completeLook!, [completeLook!], 0);
    }
    if (allowMockFallback) {
      return _buildDefaultLook(context);
    }
    return _buildEmpty(context);
  }

  Widget _buildLoading(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.06),
          width: 1,
        ),
      ),
      padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 18),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(
              width: 28,
              height: 28,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                valueColor: AlwaysStoppedAnimation<Color>(FansivibeColors.primary),
              ),
            ),
            const SizedBox(height: 12),
            Text(
              'Assembling complete look...',
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                fontSize: 13,
                color: FansivibeColors.secondary,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildError(BuildContext context) {
    final isNetwork = failure == DiscoverFailure.networkError;
    return Container(
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: Colors.redAccent.withValues(alpha: 0.2),
          width: 1,
        ),
      ),
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Icon(
                isNetwork ? Icons.cloud_off_rounded : Icons.error_outline_rounded,
                size: 20,
                color: isNetwork ? Colors.redAccent : FansivibeColors.accentGold,
              ),
              const SizedBox(width: 8),
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
            ],
          ),
          const SizedBox(height: 12),
          Text(
            isNetwork
                ? "Couldn't connect to server to assemble complete look."
                : "Unable to assemble a complete look for this session.",
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              fontSize: 13,
              color: FansivibeColors.secondary,
            ),
          ),
          if (onRetry != null) ...[
            const SizedBox(height: 14),
            Align(
              alignment: Alignment.centerLeft,
              child: FansiButton.secondary(
                label: 'Retry Look',
                icon: Icons.refresh_rounded,
                onPressed: onRetry,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildEmpty(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.06),
          width: 1,
        ),
      ),
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
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
          const SizedBox(height: 10),
          const Text(
            'No complete look available',
            style: TextStyle(
              fontFamily: 'Noto Serif',
              fontSize: 18,
              fontWeight: FontWeight.w500,
              color: FansivibeColors.onSurface,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            'We couldn’t assemble a compatible multi-piece outfit for this selection right now.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              fontSize: 13,
              color: FansivibeColors.secondary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildApiLook(
    BuildContext context,
    CompleteLook look,
    List<CompleteLook> allLooks,
    int currentIndex,
  ) {
    final slotEntries = look.slots.entries.toList();

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
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (look.containsSyntheticFixtures) ...[
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 7,
                        vertical: 3,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xFFD35400).withValues(alpha: 0.8),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: const Text(
                        'DEMO FIXTURES',
                        style: TextStyle(
                          fontFamily: 'Inter',
                          fontSize: 9,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 0.6,
                          color: Colors.white,
                        ),
                      ),
                    ),
                    const SizedBox(width: 6),
                  ],
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
                      '${slotEntries.length} PIECES',
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
            ],
          ),
          if (allLooks.length > 1) ...[
            const SizedBox(height: 12),
            SizedBox(
              height: 32,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                physics: const BouncingScrollPhysics(),
                itemCount: allLooks.length,
                separatorBuilder: (_, __) => const SizedBox(width: 8),
                itemBuilder: (context, idx) {
                  final isSelected = idx == currentIndex;
                  final candidate = allLooks[idx];
                  return Semantics(
                    button: true,
                    selected: isSelected,
                    label: 'Look ${idx + 1}',
                    child: InkWell(
                      onTap: () {
                        if (!isSelected && onLookSelected != null) {
                          onLookSelected!(idx);
                        }
                      },
                      borderRadius: BorderRadius.circular(16),
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12),
                        decoration: BoxDecoration(
                          color: isSelected
                              ? FansivibeColors.primary
                              : FansivibeColors.surfaceContainer,
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(
                            color: isSelected
                                ? FansivibeColors.primary
                                : Colors.white.withValues(alpha: 0.08),
                          ),
                        ),
                        child: Center(
                          child: Text(
                            'Look ${idx + 1} (${candidate.slots.length} pcs)',
                            style: TextStyle(
                              fontFamily: 'Inter',
                              fontSize: 11,
                              fontWeight: isSelected
                                  ? FontWeight.w700
                                  : FontWeight.w500,
                              color: isSelected
                                  ? const Color(0xFF131313)
                                  : FansivibeColors.onSurface,
                            ),
                          ),
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
          const SizedBox(height: 4),
          Text(
            look.explanation.summary.isNotEmpty
                ? look.explanation.summary
                : 'Curated Ensemble',
            style: const TextStyle(
              fontFamily: 'Noto Serif',
              fontSize: 22,
              fontWeight: FontWeight.w500,
              color: FansivibeColors.onSurface,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            'Selected with ${look.compatibilityScore.round().clamp(0, 100)}% style and color harmony.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              fontSize: 13,
              color: FansivibeColors.secondary,
            ),
          ),
          const SizedBox(height: 18),

          // Slots Display Row
          if (slotEntries.length <= 3)
            Row(
              children: [
                for (int i = 0; i < slotEntries.length; i++) ...[
                  if (i > 0) const SizedBox(width: 10),
                  Expanded(
                    child: _buildApiSlotPiece(slotEntries[i].value),
                  ),
                ],
              ],
            )
          else
            SizedBox(
              height: 180,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                physics: const BouncingScrollPhysics(),
                itemCount: slotEntries.length,
                separatorBuilder: (_, __) => const SizedBox(width: 10),
                itemBuilder: (context, index) {
                  return SizedBox(
                    width: 120,
                    child: _buildApiSlotPiece(slotEntries[index].value),
                  );
                },
              ),
            ),

          if (look.compatibilityReasons.isNotEmpty) ...[
            const SizedBox(height: 12),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: look.compatibilityReasons.take(2).map((reason) {
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        '✓ ',
                        style: TextStyle(
                          color: FansivibeColors.primary,
                          fontWeight: FontWeight.bold,
                          fontSize: 12,
                        ),
                      ),
                      Expanded(
                        child: Text(
                          reason,
                          style: TextStyle(
                            fontFamily: 'Inter',
                            fontSize: 12,
                            color: FansivibeColors.onSurface
                                .withValues(alpha: 0.85),
                          ),
                        ),
                      ),
                    ],
                  ),
                );
              }).toList(),
            ),
          ],

          const SizedBox(height: 16),

          // Total Look Price Row
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'CATALOG TOTAL',
                    style: TextStyle(
                      fontFamily: 'Inter',
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.2,
                      color: FansivibeColors.secondary,
                    ),
                  ),
                  if (look.wardrobeItemCount > 0)
                    Text(
                      '${look.wardrobeItemCount} owned piece${look.wardrobeItemCount > 1 ? 's' : ''} in your wardrobe (₹0)',
                      style: TextStyle(
                        fontFamily: 'Inter',
                        fontSize: 11,
                        color: FansivibeColors.primary,
                      ),
                    ),
                ],
              ),
              Text(
                '₹${look.totalCatalogPrice.toInt()}',
                style: const TextStyle(
                  fontFamily: 'Inter',
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: FansivibeColors.onSurface,
                ),
              ),
            ],
          ),

          const SizedBox(height: 12),

          // Bundle Notice: bundlePurchasable is false
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.04),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: Colors.white.withValues(alpha: 0.06),
              ),
            ),
            child: Row(
              children: const [
                Icon(
                  Icons.info_outline,
                  size: 13,
                  color: FansivibeColors.secondary,
                ),
                SizedBox(width: 6),
                Expanded(
                  child: Text(
                    'Bundle purchase unavailable • Items must be acquired individually',
                    style: TextStyle(
                      fontFamily: 'Inter',
                      fontSize: 11,
                      color: FansivibeColors.secondary,
                    ),
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: 16),

          // CTA
          Semantics(
            button: true,
            label: 'Shop Ensemble Pieces (${slotEntries.length} Pieces)',
            child: InkWell(
              onTap: onShopLookTap,
              borderRadius: BorderRadius.circular(26),
              child: Container(
                height: 48,
                decoration: BoxDecoration(
                  color: FansivibeColors.primary,
                  borderRadius: BorderRadius.circular(26),
                ),
                child: Center(
                  child: Text(
                    'SHOP ENSEMBLE PIECES (${slotEntries.length} PIECES) →',
                    style: const TextStyle(
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

  Widget _buildApiSlotPiece(LookSlotItem item) {
    final priceStr = item.isWardrobe
        ? 'OWNED (₹0)'
        : (item.price != null ? '₹${item.price!.toInt()}' : 'N/A');

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
            child: Stack(
              fit: StackFit.expand,
              children: [
                AtelierImage(
                  assetPath: item.imageUrl ??
                      'assets/images/discover_item_wool_coat.jpg',
                  fit: BoxFit.cover,
                ),
                if (item.isWardrobe)
                  Positioned(
                    top: 6,
                    left: 6,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 5,
                        vertical: 2,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.black.withValues(alpha: 0.75),
                        borderRadius: BorderRadius.circular(4),
                        border: Border.all(
                          color: FansivibeColors.primary.withValues(alpha: 0.6),
                          width: 0.8,
                        ),
                      ),
                      child: const Text(
                        'OWNED',
                        style: TextStyle(
                          fontFamily: 'Inter',
                          fontSize: 8.5,
                          fontWeight: FontWeight.w700,
                          color: FansivibeColors.primary,
                        ),
                      ),
                    ),
                  )
                else if (item.isSyntheticFixture)
                  Positioned(
                    top: 6,
                    left: 6,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 5,
                        vertical: 2,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xFFD35400).withValues(alpha: 0.85),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: const Text(
                        'FIXTURE',
                        style: TextStyle(
                          fontFamily: 'Inter',
                          fontSize: 8.5,
                          fontWeight: FontWeight.w700,
                          color: Colors.white,
                        ),
                      ),
                    ),
                  ),
              ],
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
                    fontSize: 11.5,
                    fontWeight: FontWeight.w500,
                    color: FansivibeColors.onSurface,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2),
                Text(
                  priceStr,
                  style: TextStyle(
                    fontFamily: 'Inter',
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: item.isWardrobe
                        ? const Color(0xFF2ECC71)
                        : FansivibeColors.primary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDefaultLook(BuildContext context) {
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

/// Controls for filtering Complete Looks by budget, occasion, and wardrobe anchor.
class CompleteLookControlsRow extends StatelessWidget {
  const CompleteLookControlsRow({
    required this.selectedBudget,
    required this.onBudgetChanged,
    required this.selectedOccasion,
    required this.onOccasionChanged,
    required this.selectedWardrobeAnchorId,
    required this.onWardrobeAnchorChanged,
    required this.ownedWardrobeItems,
    required this.isGuest,
    super.key,
  });

  final double? selectedBudget;
  final ValueChanged<double?> onBudgetChanged;
  final String? selectedOccasion;
  final ValueChanged<String?> onOccasionChanged;
  final String? selectedWardrobeAnchorId;
  final ValueChanged<String?> onWardrobeAnchorChanged;
  final List<WardrobeItemData> ownedWardrobeItems;
  final bool isGuest;

  static const List<MapEntry<String, double?>> budgetOptions = [
    MapEntry('Any Budget', null),
    MapEntry('Under ₹10,000', 10000.0),
    MapEntry('Under ₹15,000', 15000.0),
    MapEntry('Under ₹20,000', 20000.0),
  ];

  static const List<MapEntry<String, String?>> occasionOptions = [
    MapEntry('All Occasions', null),
    MapEntry('Casual', 'casual'),
    MapEntry('Office', 'office'),
    MapEntry('Date Night', 'date'),
    MapEntry('Party', 'party'),
  ];

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
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(
                Icons.tune_rounded,
                size: 15,
                color: FansivibeColors.primary,
              ),
              const SizedBox(width: 6),
              Text(
                'LOOK PREFERENCES',
                style: TextStyle(
                  fontFamily: 'Inter',
                  fontSize: 10.5,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.2,
                  color: FansivibeColors.primary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),

          // Occasion Chips
          Text(
            'Occasion',
            style: FansivibeTypography.labelMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
              fontSize: 11,
            ),
          ),
          const SizedBox(height: 6),
          SizedBox(
            height: 30,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              physics: const BouncingScrollPhysics(),
              itemCount: occasionOptions.length,
              separatorBuilder: (_, __) => const SizedBox(width: 6),
              itemBuilder: (context, index) {
                final entry = occasionOptions[index];
                final isSelected = selectedOccasion == entry.value;
                return Semantics(
                  button: true,
                  selected: isSelected,
                  label: entry.key,
                  child: InkWell(
                    onTap: () => onOccasionChanged(entry.value),
                    borderRadius: BorderRadius.circular(15),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10),
                      decoration: BoxDecoration(
                        color: isSelected
                            ? FansivibeColors.primary
                            : FansivibeColors.surfaceContainer,
                        borderRadius: BorderRadius.circular(15),
                        border: Border.all(
                          color: isSelected
                              ? FansivibeColors.primary
                              : Colors.white.withValues(alpha: 0.06),
                        ),
                      ),
                      child: Center(
                        child: Text(
                          entry.key,
                          style: TextStyle(
                            fontFamily: 'Inter',
                            fontSize: 11,
                            fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                            color: isSelected
                                ? const Color(0xFF131313)
                                : FansivibeColors.onSurface,
                          ),
                        ),
                      ),
                    ),
                  ),
                );
              },
            ),
          ),

          const SizedBox(height: 10),

          // Budget Chips
          Text(
            'Max Budget (INR)',
            style: FansivibeTypography.labelMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
              fontSize: 11,
            ),
          ),
          const SizedBox(height: 6),
          SizedBox(
            height: 30,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              physics: const BouncingScrollPhysics(),
              itemCount: budgetOptions.length,
              separatorBuilder: (_, __) => const SizedBox(width: 6),
              itemBuilder: (context, index) {
                final entry = budgetOptions[index];
                final isSelected = selectedBudget == entry.value;
                return Semantics(
                  button: true,
                  selected: isSelected,
                  label: entry.key,
                  child: InkWell(
                    onTap: () => onBudgetChanged(entry.value),
                    borderRadius: BorderRadius.circular(15),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10),
                      decoration: BoxDecoration(
                        color: isSelected
                            ? FansivibeColors.primary
                            : FansivibeColors.surfaceContainer,
                        borderRadius: BorderRadius.circular(15),
                        border: Border.all(
                          color: isSelected
                              ? FansivibeColors.primary
                              : Colors.white.withValues(alpha: 0.06),
                        ),
                      ),
                      child: Center(
                        child: Text(
                          entry.key,
                          style: TextStyle(
                            fontFamily: 'Inter',
                            fontSize: 11,
                            fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                            color: isSelected
                                ? const Color(0xFF131313)
                                : FansivibeColors.onSurface,
                          ),
                        ),
                      ),
                    ),
                  ),
                );
              },
            ),
          ),

          // Wardrobe Anchor selection (Authenticated only, when owned items exist)
          if (!isGuest && ownedWardrobeItems.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              'Anchor with Wardrobe Item',
              style: FansivibeTypography.labelMediumWithFamily.copyWith(
                color: FansivibeColors.secondary,
                fontSize: 11,
              ),
            ),
            const SizedBox(height: 6),
            SizedBox(
              height: 30,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                physics: const BouncingScrollPhysics(),
                itemCount: ownedWardrobeItems.length + 1,
                separatorBuilder: (_, __) => const SizedBox(width: 6),
                itemBuilder: (context, index) {
                  if (index == 0) {
                    final isSelected = selectedWardrobeAnchorId == null;
                    return Semantics(
                      button: true,
                      selected: isSelected,
                      label: 'No Anchor',
                      child: InkWell(
                        onTap: () => onWardrobeAnchorChanged(null),
                        borderRadius: BorderRadius.circular(15),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 10),
                          decoration: BoxDecoration(
                            color: isSelected
                                ? FansivibeColors.primary
                                : FansivibeColors.surfaceContainer,
                            borderRadius: BorderRadius.circular(15),
                            border: Border.all(
                              color: isSelected
                                  ? FansivibeColors.primary
                                  : Colors.white.withValues(alpha: 0.06),
                            ),
                          ),
                          child: Center(
                            child: Text(
                              'None',
                              style: TextStyle(
                                fontFamily: 'Inter',
                                fontSize: 11,
                                fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                                color: isSelected
                                    ? const Color(0xFF131313)
                                    : FansivibeColors.onSurface,
                              ),
                            ),
                          ),
                        ),
                      ),
                    );
                  }

                  final item = ownedWardrobeItems[index - 1];
                  final isSelected = selectedWardrobeAnchorId == item.id;
                  return Semantics(
                    button: true,
                    selected: isSelected,
                    label: item.name,
                    child: InkWell(
                      onTap: () => onWardrobeAnchorChanged(item.id),
                      borderRadius: BorderRadius.circular(15),
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10),
                        decoration: BoxDecoration(
                          color: isSelected
                              ? FansivibeColors.primary
                              : FansivibeColors.surfaceContainer,
                          borderRadius: BorderRadius.circular(15),
                          border: Border.all(
                            color: isSelected
                                ? FansivibeColors.primary
                                : Colors.white.withValues(alpha: 0.06),
                          ),
                        ),
                        child: Center(
                          child: Text(
                            item.name,
                            style: TextStyle(
                              fontFamily: 'Inter',
                              fontSize: 11,
                              fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                              color: isSelected
                                  ? const Color(0xFF131313)
                                  : FansivibeColors.onSurface,
                            ),
                          ),
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
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
