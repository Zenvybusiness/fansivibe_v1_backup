import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/discover/data/discover_mock_data.dart';
import 'package:fansivibe/features/discover/discover.dart';
import 'package:fansivibe/features/discover/presentation/widgets/discover_widgets.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart'
    show WardrobeItemData, WardrobeMockData;
import 'package:fansivibe/features/wardrobe/data/local_wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/components/fansi_chip.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

/// The Discover screen — personalized style discovery (M14).
///
/// Backend-first over #43 `GET /v1/looks` (UC-31): the ranked catalog
/// feed is the single source of truth. There is no local mock merge and
/// no local score math — rows render verbatim in server order (API-27,
/// never re-sorted locally) and every displayed id is a backend catalog
/// code.
///
/// Occasion/style/fit selections travel verbatim as the frozen query
/// params (`all` is omitted); the current catalog honors no filters, so
/// a non-`all` selection truthfully surfaces the backend 422 instead of
/// fake-filtering. The search box is a client-side pseudo-filter over
/// loaded backend titles/descriptions only (wardrobe `all`-chip
/// precedent) — it never invents attributes and never changes ids.
class DiscoverScreen extends StatefulWidget {
  /// Creates a [DiscoverScreen].
  const DiscoverScreen({super.key, this.repository, this.wardrobeRepository});

  /// Injectable for tests; when null the screen owns its own repository.
  final DiscoverRepository? repository;

  /// Wardrobe source for the Clothes tab; injectable for tests.
  final WardrobeRepository? wardrobeRepository;

  @override
  State<DiscoverScreen> createState() => _DiscoverScreenState();
}

/// Active Discover feed. Explore is the ranked catalog (#43);
/// For You is the owner-personalized reorder (M12 P1); Clothes is the
/// owner's persisted wardrobe (M12 P3). No Trending tab exists — there
/// is no trend source to back one.
enum _DiscoverTab { explore, forYou, clothes }

class _DiscoverScreenState extends State<DiscoverScreen> {
  String _searchQuery = '';
  final TextEditingController _searchController = TextEditingController();
  _DiscoverTab _tab = _DiscoverTab.explore;

  // Filter states (`all` = omitted from the backend query).
  String _selectedOccasion = 'all';
  String _selectedStyle = 'all';
  String _selectedFit = 'all';

  // Filter options (presentation labels; ids travel verbatim).
  List<FilterOption> _occasionOptions = OccasionFilters.options;
  List<FilterOption> _styleOptions = StyleFilters.options;
  List<FilterOption> _fitOptions = FitFilters.options;

  late final DiscoverRepository _repository;

  bool _loading = true;
  DiscoverFailure? _failure;
  List<LookSummary> _items = [];
  String? _nextCursor;
  bool _hasMore = false;
  bool _loadingMore = false;

  // For You bucket (M12 P1): separate feed state per tab — rows are
  // never mixed, never persisted, and die with this screen (no global
  // cache, so user transitions cannot leak rows across sessions).
  bool _forYouLoading = false;
  bool _forYouLoaded = false;
  DiscoverFailure? _forYouFailure;
  List<LookSummary> _forYouItems = [];
  String? _forYouCursor;
  bool _forYouHasMore = false;
  bool _forYouLoadingMore = false;
  bool _forYouPersonalized = false;

  // Clothes bucket (M12 P3): the owner's persisted wardrobe via the
  // existing WardrobeRepository (server-side category filter, one page
  // of 100 — the wardrobe-screen precedent). Screen-local only.
  late final WardrobeRepository _wardrobeRepository;
  bool _clothesLoading = false;
  bool _clothesLoaded = false;
  bool _clothesFailed = false;
  List<WardrobeItemData> _clothesItems = [];
  String _clothesCategory = 'all';

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? DiscoverRepositoryImpl();
    // Phase 2.1 guests read the Clothes tab from the on-device wardrobe
    // (same cards, same add flow, zero API calls). Explore/ForYou stay
    // server-side: the bodies below keep their honest prompts.
    _wardrobeRepository = isGuestUser
        ? LocalWardrobeRepository()
        : (widget.wardrobeRepository ?? WardrobeRepositoryImpl());
    // Phase 2 guests never fetch: GET /v1/looks, /v1/looks/for-you, and
    // /v1/wardrobe/items all 401 without a session. The bodies below
    // render the sign-in prompt instead.
    if (!isGuestUser) _refresh();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  String? _activeOrNull(String id) => id == 'all' ? null : id;

  Future<void> _refresh() async {
    if (isGuestUser) return;
    setState(() {
      _loading = true;
      _failure = null;
    });
    final result = await _repository.getLookFeed(
      occasion: _activeOrNull(_selectedOccasion),
      style: _activeOrNull(_selectedStyle),
      fit: _activeOrNull(_selectedFit),
    );
    if (!mounted) return;
    setState(() {
      _loading = false;
      if (result.isPage) {
        _items = result.page!.items;
        _nextCursor = result.page!.nextCursor;
        _hasMore = result.page!.hasMore;
      } else {
        _failure = result.failure;
        _items = [];
        _nextCursor = null;
        _hasMore = false;
      }
    });
  }

  Future<void> _loadMore() async {
    if (isGuestUser) return;
    if (_loadingMore || !_hasMore || _nextCursor == null) return;
    setState(() => _loadingMore = true);
    final result = await _repository.getLookFeed(
      occasion: _activeOrNull(_selectedOccasion),
      style: _activeOrNull(_selectedStyle),
      fit: _activeOrNull(_selectedFit),
      cursor: _nextCursor,
    );
    if (!mounted) return;
    setState(() => _loadingMore = false);
    if (result.isPage) {
      setState(() {
        _items = [..._items, ...result.page!.items];
        _nextCursor = result.page!.nextCursor;
        _hasMore = result.page!.hasMore;
      });
    } else {
      // Failure keeps the loaded rows with a truthful message (retry
      // keeps the same cursor).
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(_failureCopy(result.failure)),
          backgroundColor: FansivibeColors.accentGold,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(
            borderRadius: FansivibeRadius.smdBorder,
          ),
        ),
      );
    }
  }

  void _selectTab(_DiscoverTab tab) {
    if (_tab == tab) return;
    setState(() => _tab = tab);
    if (tab == _DiscoverTab.forYou && !_forYouLoaded) _refreshForYou();
    if (tab == _DiscoverTab.clothes && !_clothesLoaded) _refreshClothes();
  }

  Future<void> _refreshClothes() async {
    setState(() {
      _clothesLoading = true;
      _clothesFailed = false;
    });
    try {
      // Guests hydrate the on-device model first so persisted local
      // items appear; load() is idempotent after the first call.
      if (isGuestUser) await LearningService.instance.load();
      final items = await _wardrobeRepository.listItems(
        category: _clothesCategory == 'all' ? null : _clothesCategory,
        pageSize: 100,
      );
      if (!mounted) return;
      setState(() {
        _clothesLoading = false;
        _clothesLoaded = true;
        _clothesItems = items;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _clothesLoading = false;
        _clothesLoaded = true;
        _clothesFailed = true;
        _clothesItems = [];
      });
    }
  }

  void _selectClothesCategory(String id) {
    if (_clothesCategory == id) return;
    setState(() => _clothesCategory = id);
    _refreshClothes();
  }

  /// Loaded wardrobe rows, narrowed by the client-side search box only
  /// (same precedent as the look feeds).
  List<WardrobeItemData> _clothesVisible() {
    if (_searchQuery.isEmpty) return _clothesItems;
    final query = _searchQuery.toLowerCase();
    return _clothesItems
        .where((item) => item.name.toLowerCase().contains(query))
        .toList();
  }

  void _handleClothesTap(BuildContext context, WardrobeItemData item) {
    // Existing wardrobe detail architecture — backend UUID travels verbatim.
    // Phase 2.1 guests resolve through the local repository instead.
    context.pushNamed(RouteNames.wardrobeItemDetails, extra: item.id);
  }

  Future<void> _handleClothesAdd(BuildContext context) async {
    // Existing Add Wardrobe Item flow (M11 P2 intact); reload on return
    // so a fresh save appears — backend stays canonical.
    final result = await context.pushNamed<WardrobeItemData>(
      RouteNames.wardrobeAddCategory,
    );
    if (result != null && mounted) _refreshClothes();
  }

  Future<void> _refreshForYou() async {
    if (isGuestUser) return;
    setState(() {
      _forYouLoading = true;
      _forYouFailure = null;
    });
    final result = await _repository.getForYouFeed();
    if (!mounted) return;
    setState(() {
      _forYouLoading = false;
      _forYouLoaded = true;
      if (result.isPage) {
        _forYouItems = result.page!.items;
        _forYouCursor = result.page!.nextCursor;
        _forYouHasMore = result.page!.hasMore;
        _forYouPersonalized = result.page!.personalized;
      } else {
        _forYouFailure = result.failure;
        _forYouItems = [];
        _forYouCursor = null;
        _forYouHasMore = false;
        _forYouPersonalized = false;
      }
    });
  }

  Future<void> _loadMoreForYou() async {
    if (isGuestUser) return;
    if (_forYouLoadingMore || !_forYouHasMore || _forYouCursor == null) {
      return;
    }
    setState(() => _forYouLoadingMore = true);
    final result = await _repository.getForYouFeed(cursor: _forYouCursor);
    if (!mounted) return;
    setState(() => _forYouLoadingMore = false);
    if (result.isPage) {
      setState(() {
        // Backend windows never overlap, but ids already on screen are
        // never appended twice.
        final seen = _forYouItems.map((e) => e.id).toSet();
        _forYouItems = [
          ..._forYouItems,
          ...result.page!.items.where((e) => seen.add(e.id)),
        ];
        _forYouCursor = result.page!.nextCursor;
        _forYouHasMore = result.page!.hasMore;
        _forYouPersonalized = result.page!.personalized;
      });
    } else {
      // Failure keeps the loaded rows with a truthful message (retry
      // keeps the same cursor). Never the /v1/looks feed, never mocks.
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(_failureCopy(result.failure)),
          backgroundColor: FansivibeColors.accentGold,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(
            borderRadius: FansivibeRadius.smdBorder,
          ),
        ),
      );
    }
  }

  static String _failureCopy(DiscoverFailure? failure) {
    switch (failure) {
      case DiscoverFailure.unauthorized:
        return 'Your session expired. Please sign in again.';
      case DiscoverFailure.invalidInput:
        return 'These filters aren\u2019t supported by the current look catalog yet.';
      case DiscoverFailure.rateLimited:
        return 'Too many requests. Please try again shortly.';
      case DiscoverFailure.networkError:
        return 'Check your connection and try again.';
      case DiscoverFailure.unknown:
      case null:
        return 'Something went wrong. Please try again.';
    }
  }

  void _onOccasionChanged(FilterOption option) {
    setState(() {
      _selectedOccasion = option.id;
      _occasionOptions = _occasionOptions
          .map((o) => o.copyWith(isSelected: o.id == option.id))
          .toList();
    });
    _refresh();
  }

  void _onStyleChanged(FilterOption option) {
    setState(() {
      _selectedStyle = option.id;
      _styleOptions = _styleOptions
          .map((o) => o.copyWith(isSelected: o.id == option.id))
          .toList();
    });
    _refresh();
  }

  void _onFitChanged(FilterOption option) {
    setState(() {
      _selectedFit = option.id;
      _fitOptions = _fitOptions
          .map((o) => o.copyWith(isSelected: o.id == option.id))
          .toList();
    });
    _refresh();
  }

  void _onSearchChanged(String query) {
    setState(() {
      _searchQuery = query;
    });
  }

  void _clearSearch() {
    _searchController.clear();
    setState(() {
      _searchQuery = '';
    });
  }

  void _resetAll() {
    _searchController.clear();
    setState(() {
      _searchQuery = '';
      _selectedOccasion = 'all';
      _selectedStyle = 'all';
      _selectedFit = 'all';
      _occasionOptions = OccasionFilters.options;
      _styleOptions = StyleFilters.options;
      _fitOptions = FitFilters.options;
    });
    _refresh();
  }

  /// Loaded backend rows, narrowed by the client-side search box only.
  List<LookSummary> _getVisibleLooks([List<LookSummary>? source]) {
    final rows = source ?? _items;
    if (_searchQuery.isEmpty) return rows;
    final query = _searchQuery.toLowerCase();
    return rows
        .where(
          (look) =>
              look.title.toLowerCase().contains(query) ||
              look.description.toLowerCase().contains(query),
        )
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 20.0;
            final contentMaxWidth = maxWidth > 600 ? 600.0 : double.infinity;

            return SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              child: Center(
                child: ConstrainedBox(
                  constraints: BoxConstraints(maxWidth: contentMaxWidth),
                  child: Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: horizontalPadding,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const SizedBox(height: 8),

                        // Header
                        _buildHeader(context),

                        const SizedBox(height: 20),

                        // Explore / For You switch
                        _buildTabRow(context),

                        const SizedBox(height: 20),

                        // Search + Filter
                        _buildSearchRow(context),

                        const SizedBox(height: 20),

                        // Results count / For You banner / Clothes count
                        if (_tab == _DiscoverTab.forYou)
                          _buildForYouBanner(context)
                        else if (_tab == _DiscoverTab.clothes)
                          _buildClothesHeader(context)
                        else
                          _buildResultsHeader(
                            context,
                            _loading || _failure != null
                                ? null
                                : _getVisibleLooks().length,
                          ),

                        const SizedBox(height: 16),

                        // Looks content
                        if (_tab == _DiscoverTab.forYou)
                          _buildForYouBody(context)
                        else if (_tab == _DiscoverTab.clothes)
                          _buildClothesBody(context)
                        else
                          _buildBody(context),

                        const SizedBox(height: 32),
                      ],
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    final theme = Theme.of(context);

    return Row(
      children: [
        Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: FansivibeColors.accentGold.withValues(alpha: 0.12),
            borderRadius: FansivibeRadius.smdBorder,
          ),
          child: const Icon(
            Icons.explore_rounded,
            color: FansivibeColors.accentGold,
            size: 24,
          ),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Discover',
                style: theme.textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: FansivibeColors.textPrimary,
                  fontSize: 26,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                'Find looks tailored to your style',
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildTabRow(BuildContext context) {
    // Horizontally scrollable: three tabs must never overflow narrow
    // screens (responsive-layout precedent from the filter chips row).
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          FansiChip(
            label: 'Explore',
            icon: Icons.explore_outlined,
            selected: _tab == _DiscoverTab.explore,
            onTap: () => _selectTab(_DiscoverTab.explore),
          ),
          const SizedBox(width: 8),
          FansiChip(
            label: 'For You',
            icon: Icons.person_outline_rounded,
            selected: _tab == _DiscoverTab.forYou,
            onTap: () => _selectTab(_DiscoverTab.forYou),
          ),
          const SizedBox(width: 8),
          FansiChip(
            label: 'Clothes',
            icon: Icons.checkroom_outlined,
            selected: _tab == _DiscoverTab.clothes,
            onTap: () => _selectTab(_DiscoverTab.clothes),
          ),
        ],
      ),
    );
  }

  /// Clothes tab header: live count plus the real backend category
  /// vocabulary as chips (`all` = unfiltered server query).
  Widget _buildClothesHeader(BuildContext context) {
    final theme = Theme.of(context);
    final count = _clothesLoading || _clothesFailed
        ? null
        : _clothesVisible().length;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              for (final category in WardrobeMockData.categories)
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: FansiChip(
                    label: category.name,
                    selected: _clothesCategory == category.id,
                    onTap: () => _selectClothesCategory(category.id),
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        Text(
          count == null
              ? 'Loading clothes...'
              : '$count ${count == 1 ? 'item' : 'items'} in your wardrobe',
          style: theme.textTheme.bodySmall?.copyWith(
            color: FansivibeColors.textSecondary,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }

  Widget _buildClothesBody(BuildContext context) {
    if (_clothesLoading) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(48),
          child: CircularProgressIndicator(),
        ),
      );
    }
    if (_clothesFailed) {
      return _buildErrorState(
        context,
        DiscoverFailure.networkError,
        onRetry: _refreshClothes,
        title: 'Clothes unavailable',
      );
    }
    final visible = _clothesVisible();
    if (visible.isEmpty) {
      return _buildClothesEmpty(context);
    }
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        crossAxisSpacing: 16,
        mainAxisSpacing: 16,
        childAspectRatio: 0.50,
      ),
      itemCount: visible.length,
      itemBuilder: (context, index) {
        final item = visible[index];
        return ClothesItemCard(
          item: item,
          onTap: () => _handleClothesTap(context, item),
        );
      },
    );
  }

  /// Honest empty wardrobe: never mock products, never the looks
  /// catalog — the CTA reuses the existing Add Wardrobe Item flow.
  Widget _buildClothesEmpty(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(48),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.checkroom_outlined,
              size: 64,
              color: FansivibeColors.accentGold.withValues(alpha: 0.4),
            ),
            const SizedBox(height: 16),
            Text(
              'Your wardrobe is empty',
              style: theme.textTheme.headlineMedium?.copyWith(
                fontWeight: FontWeight.w600,
                color: FansivibeColors.textPrimary,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Add clothes to see them here.',
              style: theme.textTheme.bodyLarge?.copyWith(
                color: FansivibeColors.textSecondary,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 20),
            FansiButton.primary(
              label: 'Add clothes',
              icon: Icons.add_rounded,
              onPressed: () => _handleClothesAdd(context),
            ),
          ],
        ),
      ),
    );
  }

  /// Honest For You banner driven by the backend `personalized` flag —
  /// never Trending/Popular/Recommended-for-you wording.
  Widget _buildForYouBanner(BuildContext context) {
    final theme = Theme.of(context);
    final copy = _forYouPersonalized
        ? 'For You — based on looks you\u2019ve saved.'
        : 'Browse classic looks to get started — save looks you love and this space becomes yours.';
    return Text(
      copy,
      style: theme.textTheme.bodySmall?.copyWith(
        color: FansivibeColors.textSecondary,
        fontWeight: FontWeight.w500,
      ),
    );
  }

  Widget _buildForYouBody(BuildContext context) {
    // Phase 2 guests: honest sign-in prompt, never a 401-backed error.
    if (isGuestUser) return _buildGuestBody(context);
    if (_forYouLoading) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(48),
          child: CircularProgressIndicator(),
        ),
      );
    }
    if (_forYouFailure != null) {
      return _buildErrorState(
        context,
        _forYouFailure!,
        onRetry: _refreshForYou,
      );
    }
    final visible = _getVisibleLooks(_forYouItems);
    if (visible.isEmpty) {
      return _buildEmptyState(context);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildLooksGrid(context, visible),
        if (_forYouHasMore) ...[
          const SizedBox(height: 20),
          Center(
            child: _forYouLoadingMore
                ? const CircularProgressIndicator()
                : FansiButton.secondary(
                    label: 'Load more',
                    icon: Icons.expand_more_rounded,
                    onPressed: _loadMoreForYou,
                  ),
          ),
        ],
      ],
    );
  }

  Widget _buildSearchRow(BuildContext context) {
    final theme = Theme.of(context);
    final activeCount = _activeFilterCount();

    return Row(
      children: [
        Expanded(
          child: TextField(
            controller: _searchController,
            onChanged: _onSearchChanged,
            style: theme.textTheme.bodyLarge?.copyWith(
              color: FansivibeColors.textPrimary,
            ),
            decoration: InputDecoration(
              hintText: 'Search looks, styles, occasions...',
              hintStyle: theme.textTheme.bodyLarge?.copyWith(
                color: FansivibeColors.textSecondary.withValues(alpha: 0.6),
              ),
              prefixIcon: Icon(
                Icons.search_rounded,
                color: FansivibeColors.textSecondary,
                size: 22,
              ),
              suffixIcon: _searchQuery.isNotEmpty
                  ? IconButton(
                      icon: Icon(
                        Icons.clear_rounded,
                        color: FansivibeColors.textSecondary,
                        size: 22,
                      ),
                      onPressed: _clearSearch,
                    )
                  : null,
              filled: true,
              fillColor: FansivibeColors.surface,
              contentPadding: const EdgeInsets.symmetric(
                horizontal: 16,
                vertical: 14,
              ),
              border: OutlineInputBorder(
                borderRadius: FansivibeRadius.smdBorder,
                borderSide: BorderSide(
                  color: FansivibeColors.accentGold.withValues(alpha: 0.1),
                  width: 1,
                ),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: FansivibeRadius.smdBorder,
                borderSide: BorderSide(
                  color: FansivibeColors.accentGold.withValues(alpha: 0.1),
                  width: 1,
                ),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: FansivibeRadius.smdBorder,
                borderSide: const BorderSide(
                  color: FansivibeColors.accentGold,
                  width: 2,
                ),
              ),
            ),
          ),
        ),
        const SizedBox(width: 10),
        Semantics(
          button: true,
          label: 'Open filters',
          child: InkWell(
            onTap: () => _showFilterSheet(context),
            borderRadius: FansivibeRadius.smdBorder,
            child: Container(
              height: 50,
              width: 50,
              decoration: BoxDecoration(
                color: activeCount > 0
                    ? FansivibeColors.accentGold.withValues(alpha: 0.15)
                    : FansivibeColors.surface,
                borderRadius: FansivibeRadius.smdBorder,
                border: Border.all(
                  color: activeCount > 0
                      ? FansivibeColors.accentGold.withValues(alpha: 0.4)
                      : FansivibeColors.accentGold.withValues(alpha: 0.1),
                  width: 1,
                ),
              ),
              child: Stack(
                alignment: Alignment.center,
                children: [
                  Icon(
                    Icons.tune_rounded,
                    size: 22,
                    color: activeCount > 0
                        ? FansivibeColors.accentGold
                        : FansivibeColors.textSecondary,
                  ),
                  if (activeCount > 0)
                    Positioned(
                      top: 8,
                      right: 8,
                      child: Container(
                        width: 18,
                        height: 18,
                        decoration: const BoxDecoration(
                          color: FansivibeColors.accentGold,
                          shape: BoxShape.circle,
                        ),
                        child: Center(
                          child: Text(
                            '$activeCount',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: FansivibeColors.onPrimary,
                              fontSize: 10,
                              fontWeight: FontWeight.bold,
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
      ],
    );
  }

  int _activeFilterCount() {
    int count = 0;
    if (_selectedOccasion != 'all') count++;
    if (_selectedStyle != 'all') count++;
    if (_selectedFit != 'all') count++;
    return count;
  }

  void _showFilterSheet(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => _FilterSheet(
        occasionOptions: _occasionOptions,
        styleOptions: _styleOptions,
        fitOptions: _fitOptions,
        onOccasionChanged: (option) {
          _onOccasionChanged(option);
          setState(() {});
        },
        onStyleChanged: (option) {
          _onStyleChanged(option);
          setState(() {});
        },
        onFitChanged: (option) {
          _onFitChanged(option);
          setState(() {});
        },
        onClearAll: () {
          setState(() {
            _selectedOccasion = 'all';
            _selectedStyle = 'all';
            _selectedFit = 'all';
            _occasionOptions = OccasionFilters.options;
            _styleOptions = StyleFilters.options;
            _fitOptions = FitFilters.options;
          });
          Navigator.of(ctx).pop();
          _refresh();
        },
      ),
    );
  }

  Widget _buildResultsHeader(BuildContext context, [int? count]) {
    final theme = Theme.of(context);

    final label = count == null
        ? 'Loading looks...'
        : '$count ${count == 1 ? 'look' : 'looks'} found';

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: theme.textTheme.bodySmall?.copyWith(
            color: FansivibeColors.textSecondary,
            fontWeight: FontWeight.w500,
          ),
        ),
        if (_selectedOccasion != 'all' ||
            _selectedStyle != 'all' ||
            _selectedFit != 'all')
          FansiButton.tertiary(label: 'Clear filters', onPressed: _resetAll),
      ],
    );
  }

  Widget _buildBody(BuildContext context) {
    // Phase 2 guests: honest sign-in prompt, never a 401-backed error.
    if (isGuestUser) return _buildGuestBody(context);
    if (_loading) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(48),
          child: CircularProgressIndicator(),
        ),
      );
    }
    if (_failure != null) {
      return _buildErrorState(context, _failure!);
    }
    final visible = _getVisibleLooks();
    if (visible.isEmpty) {
      return _buildEmptyState(context);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildLooksGrid(context, visible),
        if (_hasMore) ...[
          const SizedBox(height: 20),
          Center(
            child: _loadingMore
                ? const CircularProgressIndicator()
                : FansiButton.secondary(
                    label: 'Load more',
                    icon: Icons.expand_more_rounded,
                    onPressed: _loadMore,
                  ),
          ),
        ],
      ],
    );
  }

  Widget _buildErrorState(
    BuildContext context,
    DiscoverFailure failure, {
    VoidCallback? onRetry,
    String title = 'Looks unavailable',
  }) {
    final theme = Theme.of(context);

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(48),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              failure == DiscoverFailure.networkError
                  ? Icons.cloud_off_rounded
                  : Icons.info_outline_rounded,
              size: 64,
              color: FansivibeColors.accentGold.withValues(alpha: 0.4),
            ),
            const SizedBox(height: 16),
            Text(
              failure == DiscoverFailure.invalidInput
                  ? 'Filters not supported yet'
                  : title,
              style: theme.textTheme.headlineMedium?.copyWith(
                fontWeight: FontWeight.w600,
                color: FansivibeColors.textPrimary,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              _failureCopy(failure),
              style: theme.textTheme.bodyLarge?.copyWith(
                color: FansivibeColors.textSecondary,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 20),
            if (failure == DiscoverFailure.invalidInput)
              FansiButton.primary(
                label: 'Reset filters',
                icon: Icons.refresh_rounded,
                onPressed: _resetAll,
              )
            else
              FansiButton.primary(
                label: 'Try Again',
                icon: Icons.refresh_rounded,
                onPressed: onRetry ?? _refresh,
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildLooksGrid(BuildContext context, List<LookSummary> looks) {
    final maxWidth = MediaQuery.of(context).size.width;

    // Determine cross axis count based on screen width
    int crossAxisCount;
    if (maxWidth > 900) {
      crossAxisCount = 3;
    } else if (maxWidth > 600) {
      crossAxisCount = 2;
    } else {
      crossAxisCount = 2;
    }

    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: crossAxisCount,
        crossAxisSpacing: 16,
        mainAxisSpacing: 16,
        childAspectRatio: 0.50,
      ),
      itemCount: looks.length,
      itemBuilder: (context, index) {
        final look = looks[index];
        return LookCard(
          data: look,
          onTap: () => _handleLookTap(context, look),
          showMatchBadge: true,
        );
      },
    );
  }

  /// Phase 2 guest state: the look catalog and wardrobe are
  /// account-backed, so guests get an honest sign-in prompt — never
  /// mock looks, never a 401-backed error card.
  Widget _buildGuestBody(BuildContext context) {
    return const GuestSignInCard(
      title: 'Discover looks',
      message:
          'The look catalog lives in your account. Sign in to explore personalized looks — browsing stays free.',
    );
  }

  Widget _buildEmptyState(BuildContext context) {
    final theme = Theme.of(context);

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(48),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.search_off_rounded,
              size: 64,
              color: FansivibeColors.accentGold.withValues(alpha: 0.4),
            ),
            const SizedBox(height: 16),
            Text(
              'No looks found',
              style: theme.textTheme.headlineMedium?.copyWith(
                fontWeight: FontWeight.w600,
                color: FansivibeColors.textPrimary,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              _searchQuery.isNotEmpty
                  ? 'Try adjusting your search or filters'
                  : 'No looks match your current filters',
              style: theme.textTheme.bodyLarge?.copyWith(
                color: FansivibeColors.textSecondary,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 20),
            FansiButton.primary(
              label: 'Reset filters',
              icon: Icons.refresh_rounded,
              onPressed: _resetAll,
            ),
          ],
        ),
      ),
    );
  }

  void _handleLookTap(BuildContext context, LookSummary look) {
    // Phase 2 guests: the detail fetch is account-only — prompt at the
    // button instead of pushing into a 401-backed screen.
    if (isGuestUser) {
      promptGuestSignIn(
        context,
        action: 'Sign in to open look details. Browsing stays free.',
      );
      return;
    }
    // The backend catalog code travels verbatim — never a local id.
    context.pushNamed(RouteNames.lookDetails, extra: look.id);
  }
}

class _FilterSheet extends StatelessWidget {
  const _FilterSheet({
    required this.occasionOptions,
    required this.styleOptions,
    required this.fitOptions,
    required this.onOccasionChanged,
    required this.onStyleChanged,
    required this.onFitChanged,
    required this.onClearAll,
  });

  final List<FilterOption> occasionOptions;
  final List<FilterOption> styleOptions;
  final List<FilterOption> fitOptions;
  final void Function(FilterOption) onOccasionChanged;
  final void Function(FilterOption) onStyleChanged;
  final void Function(FilterOption) onFitChanged;
  final VoidCallback onClearAll;

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.of(context).viewInsets.bottom;

    return Container(
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainer,
        borderRadius: const BorderRadius.vertical(
          top: Radius.circular(FansivibeRadius.md),
        ),
      ),
      child: Padding(
        padding: EdgeInsets.only(bottom: bottomInset),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildHandle(context),
            _buildHeader(context),
            const Divider(
              height: 1,
              color: FansivibeColors.surfaceContainerHighest,
            ),
            Flexible(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(24, 8, 24, 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _buildSection(
                      context,
                      icon: Icons.event_rounded,
                      title: 'Occasion',
                      options: occasionOptions,
                      onChanged: onOccasionChanged,
                    ),
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 12),
                      child: Divider(
                        height: 1,
                        color: FansivibeColors.surfaceContainerHighest,
                      ),
                    ),
                    _buildSection(
                      context,
                      icon: Icons.palette_outlined,
                      title: 'Style',
                      options: styleOptions,
                      onChanged: onStyleChanged,
                    ),
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 12),
                      child: Divider(
                        height: 1,
                        color: FansivibeColors.surfaceContainerHighest,
                      ),
                    ),
                    _buildSection(
                      context,
                      icon: Icons.straighten_rounded,
                      title: 'Fit',
                      options: fitOptions,
                      onChanged: onFitChanged,
                    ),
                  ],
                ),
              ),
            ),
            _buildFooter(context),
          ],
        ),
      ),
    );
  }

  Widget _buildHandle(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.only(top: 10, bottom: 4),
        child: Container(
          width: 36,
          height: 4,
          decoration: BoxDecoration(
            color: FansivibeColors.textSecondary.withValues(alpha: 0.3),
            borderRadius: FansivibeRadius.xsBorder,
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 12, 12, 12),
      child: Row(
        children: [
          Icon(Icons.tune_rounded, size: 20, color: FansivibeColors.accentGold),
          const SizedBox(width: 10),
          Text(
            'Filter',
            style: theme.textTheme.titleLarge?.copyWith(
              fontWeight: FontWeight.bold,
              color: FansivibeColors.textPrimary,
            ),
          ),
          const Spacer(),
          IconButton(
            icon: Icon(
              Icons.close_rounded,
              color: FansivibeColors.textSecondary,
            ),
            onPressed: () => Navigator.of(context).pop(),
          ),
        ],
      ),
    );
  }

  Widget _buildSection(
    BuildContext context, {
    required IconData icon,
    required String title,
    required List<FilterOption> options,
    required void Function(FilterOption) onChanged,
  }) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(icon, size: 16, color: FansivibeColors.accentGold),
            const SizedBox(width: 8),
            Text(
              title,
              style: theme.textTheme.titleSmall?.copyWith(
                fontWeight: FontWeight.w600,
                color: FansivibeColors.textPrimary,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: options.map((option) {
            return FansiChip(
              label: option.label,
              icon: option.icon,
              selected: option.isSelected,
              onTap: () => onChanged(option),
            );
          }).toList(),
        ),
      ],
    );
  }

  Widget _buildFooter(BuildContext context) {
    final hasActiveFilters =
        occasionOptions.any((o) => o.isSelected && o.id != 'all') ||
        styleOptions.any((o) => o.isSelected && o.id != 'all') ||
        fitOptions.any((o) => o.isSelected && o.id != 'all');

    return Container(
      padding: EdgeInsets.only(
        left: 24,
        right: 24,
        top: 12,
        bottom: MediaQuery.of(context).padding.bottom + 12,
      ),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainer,
        border: Border(
          top: BorderSide(color: FansivibeColors.surfaceContainerHighest),
        ),
      ),
      child: Row(
        children: [
          if (hasActiveFilters)
            Expanded(
              child: FansiButton.secondary(
                label: 'Clear all',
                icon: Icons.refresh_rounded,
                onPressed: onClearAll,
                expanded: false,
              ),
            ),
          const Spacer(),
          FansiButton.primary(
            label: 'Show results',
            icon: Icons.check_rounded,
            onPressed: () => Navigator.of(context).pop(),
            expanded: false,
          ),
        ],
      ),
    );
  }
}
