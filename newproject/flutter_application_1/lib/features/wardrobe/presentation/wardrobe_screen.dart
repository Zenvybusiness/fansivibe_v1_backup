import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/knowledge/data/knowledge_api_models.dart';
import 'package:fansivibe/features/knowledge/data/knowledge_repository.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_item_photo.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/local_wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_extraction_screen.dart';
import 'package:fansivibe/features/wardrobe/presentation/widgets/first_time_wardrobe_view.dart';
import 'package:fansivibe/features/wardrobe/presentation/widgets/wardrobe_widgets.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/utils/user_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

/// Converts UI data to the on-device mirror entry, preserving the stored
/// photo when the item carries no new bytes (see the wardrobe photo
/// helper — edits must not wipe the image).
WardrobeEntry _toEntry(WardrobeItemData item) => wardrobeEntryFromItem(item);

enum _WardrobeSort { none, nameAsc, nameDesc, newest }

class WardrobeScreen extends StatefulWidget {
  /// Creates the wardrobe screen.
  ///
  /// [repository] is the source for the live backend wardrobe item list,
  /// the live backend insight card, and the live backend wear-summary card.
  /// It defaults to the API-primary repository; tests inject a fake to
  /// control the list and insights without networking.
  /// [insightRepository] is retained for backward compatibility with tests
  /// that supply an insight repository.
  const WardrobeScreen({
    super.key,
    this.insightRepository,
    this.repository,
    this.knowledgeRepository,
  });

  final WardrobeRepository? insightRepository;
  final WardrobeRepository? repository;
  final KnowledgeRepository? knowledgeRepository;

  @override
  State<WardrobeScreen> createState() => _WardrobeScreenState();
}

class _WardrobeScreenState extends State<WardrobeScreen> {
  String _selectedCategory = 'all';
  String? _selectedColor;
  bool _favoritesOnly = false;
  _WardrobeSort _sort = _WardrobeSort.none;
  final TextEditingController _searchController = TextEditingController();
  late WardrobeRepository _repository;
  List<WardrobeItemData> _items = [];
  List<KnowledgeVocabularyItem> _vocabularyCategories = [];
  bool _isLoading = true;
  String? _errorMessage;
  int _loadGeneration = 0;
  late Future<WardrobeInsightData?> _insightFuture;
  late Future<WearSummary?> _wearSummaryFuture;
  bool get _showFirstTimeExperience {
    if (_isLoading) return false;
    return UserSession.isNewUserInInitialExploration && _items.isEmpty;
  }

  @override
  void initState() {
    super.initState();
    LearningService.instance.addListener(_onLocalChanged);
    UserSession.savedWardrobeItemNotifier.addListener(_onLocalChanged);
    _initDataSource();
    // Data sources are session-derived: a sign-in/out on a mounted
    // shell branch must swap local <-> server sources instead of
    // keeping the initState snapshot (same pattern as DailyOutfit).
    AuthSession.authVersion.addListener(_onAuthChanged);
  }

  /// Selects the data source for the current session state and loads.
  ///
  /// Signed-out screens run the full wardrobe on-device: the local
  /// repository serves the same list/detail/add/edit/delete flows with
  /// zero API calls (insight/wear-summary have no on-device equivalent
  /// and stay hidden). Injected fakes are ignored without a session, so
  /// guest tests can assert the backend is never touched.
  void _initDataSource() {
    final hasInjectedRepo =
        widget.repository != null || widget.insightRepository != null;
    if (isGuestUser || (!AuthSession.isAuthenticated && !hasInjectedRepo)) {
      _repository = LocalWardrobeRepository();
      _vocabularyCategories = [];
      _insightFuture = Future.value(null);
      _wearSummaryFuture = Future.value(null);
      // Hydrate persisted on-device items, then render; live mutations
      // (add/edit/delete returns) refresh through the listener.
      LearningService.instance.load().then((_) {
        if (mounted) _loadItems();
      });
      _loadItems();
      return;
    }
    _repository =
        widget.repository ??
        widget.insightRepository ??
        WardrobeRepositoryImpl();
    // Independent from the item list: the list renders immediately while
    // the insight resolves on its own. Single fetch — no refetch storms.
    _insightFuture = _repository.getInsight();
    // Independent from the insight: same seam, separate future, separate
    // slot — W-7 loading/error/204 behavior is unchanged by this fetch.
    _wearSummaryFuture = Future.sync(() => _repository.getWearSummary());
    final knowledgeRepository = widget.knowledgeRepository;
    if (knowledgeRepository != null) {
      _loadVocabulary(knowledgeRepository);
    } else if (!hasInjectedRepo) {
      _loadVocabulary(KnowledgeRepositoryImpl());
    }
    _loadItems();
  }

  Future<void> _loadVocabulary(KnowledgeRepository repository) async {
    final vocabulary = await repository.listCategories(pageSize: 100);
    if (!mounted || vocabulary == null) return;
    setState(() => _vocabularyCategories = vocabulary.items);
  }

  void _onAuthChanged() {
    if (!mounted) return;
    _initDataSource();
    setState(() {});
  }

  @override
  void dispose() {
    AuthSession.authVersion.removeListener(_onAuthChanged);
    LearningService.instance.removeListener(_onLocalChanged);
    UserSession.savedWardrobeItemNotifier.removeListener(_onLocalChanged);
    _searchController.dispose();
    super.dispose();
  }

  void _onLocalChanged() {
    if (mounted) _loadItems();
  }

  Future<void> _loadItems() async {
    if (!mounted) return;
    final generation = ++_loadGeneration;
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      const pageSize = 100;
      const maxPages = 100;
      final allItems = <WardrobeItemData>[];
      final seenIds = <String>{};

      for (var page = 1; page <= maxPages; page++) {
        final pageItems = await _repository.listItems(
          page: page,
          pageSize: pageSize,
        );
        if (!mounted || generation != _loadGeneration) return;

        var addedThisPage = 0;
        for (final item in pageItems) {
          if (seenIds.add(item.id)) {
            allItems.add(attachLocalPhoto(item));
            addedThisPage++;
          }
        }

        if (pageItems.isEmpty ||
            pageItems.length < pageSize ||
            (page > 1 && addedThisPage == 0)) {
          break;
        }
      }

      if (!mounted || generation != _loadGeneration) return;
      setState(() {
        // Backend rows carry metadata only: rehydrate each item's photo
        // from the on-device mirror by id (imageless rows pass through).
        _items = allItems;
        _isLoading = false;
      });
    } catch (e) {
      if (!mounted || generation != _loadGeneration) return;
      setState(() {
        _errorMessage =
            'Failed to load wardrobe. Please check your connection.';
        _isLoading = false;
      });
    }
  }

  void _selectCategory(String categoryId) {
    setState(() {
      _selectedCategory = categoryId;
    });
  }

  String _displayLabel(String code) => code
      .split('_')
      .map(
        (word) =>
            word.isEmpty ? word : word[0].toUpperCase() + word.substring(1),
      )
      .join(' ');

  List<WardrobeCategory> get _categoryOptions {
    final categories = <WardrobeCategory>[
      const WardrobeCategory(
        id: 'all',
        name: 'All Items',
        iconName: 'checkroom_outlined',
      ),
    ];
    if (_vocabularyCategories.isEmpty) {
      final codes = _items.map((item) => item.category).toSet().toList();
      for (final code in codes) {
        categories.add(
          WardrobeCategory(
            id: code,
            name: _displayLabel(code),
            iconName: 'checkroom_outlined',
          ),
        );
      }
      return categories;
    }
    for (final item in _vocabularyCategories) {
      categories.add(
        WardrobeCategory(
          id: item.code,
          name: item.label,
          iconName: 'checkroom_outlined',
        ),
      );
    }
    return categories;
  }

  List<String> get _availableColors {
    final colors =
        _items
            .map((item) => item.color)
            .where((color) => color.trim().isNotEmpty)
            .toSet()
            .toList()
          ..sort();
    return colors;
  }

  List<WardrobeItemData> get _filteredItems {
    final query = _searchController.text.trim().toLowerCase();
    final items = _items.where((item) {
      if (_selectedCategory != 'all' && item.category != _selectedCategory) {
        return false;
      }
      if (_selectedColor != null && item.color != _selectedColor) {
        return false;
      }
      if (_favoritesOnly && !item.isFavorite) {
        return false;
      }
      if (query.isEmpty) {
        return true;
      }
      final searchable = [
        item.name,
        item.category,
        item.color,
        item.material ?? '',
      ].join(' ').toLowerCase();
      return searchable.contains(query);
    }).toList();

    switch (_sort) {
      case _WardrobeSort.nameAsc:
        items.sort(
          (a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase()),
        );
      case _WardrobeSort.nameDesc:
        items.sort(
          (a, b) => b.name.toLowerCase().compareTo(a.name.toLowerCase()),
        );
      case _WardrobeSort.newest:
        int timestamp(WardrobeItemData item) =>
            (item.createdAt ??
                    item.updatedAt ??
                    DateTime.fromMillisecondsSinceEpoch(0))
                .millisecondsSinceEpoch;
        items.sort((a, b) => timestamp(b).compareTo(timestamp(a)));
      case _WardrobeSort.none:
        break;
    }
    return items;
  }

  String _sortLabel(_WardrobeSort sort) {
    switch (sort) {
      case _WardrobeSort.none:
        return 'Default order';
      case _WardrobeSort.nameAsc:
        return 'Name A-Z';
      case _WardrobeSort.nameDesc:
        return 'Name Z-A';
      case _WardrobeSort.newest:
        return 'Newest first';
    }
  }

  Future<void> _openFilterSheet() {
    return showModalBottomSheet<void>(
      context: context,
      builder: (sheetContext) {
        return SafeArea(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 420),
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(FansivibeSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          'Filter wardrobe',
                          style: FansivibeTypography.titleLargeWithFamily,
                        ),
                      ),
                      TextButton.icon(
                        onPressed: () {
                          setState(() {
                            _selectedCategory = 'all';
                            _selectedColor = null;
                            _favoritesOnly = false;
                            _searchController.clear();
                          });
                          Navigator.of(sheetContext).pop();
                        },
                        icon: const Icon(Icons.close_rounded, size: 16),
                        label: const Text('Clear all'),
                      ),
                    ],
                  ),
                  const SizedBox(height: FansivibeSpacing.sm),
                  Text(
                    'Category',
                    style: FansivibeTypography.labelMediumWithFamily,
                  ),
                  Wrap(
                    spacing: FansivibeSpacing.xs,
                    children: [
                      for (final category in _categoryOptions)
                        FilterChip(
                          label: Text(category.name),
                          selected: _selectedCategory == category.id,
                          onSelected: (_) {
                            _selectCategory(category.id);
                            Navigator.of(sheetContext).pop();
                          },
                        ),
                    ],
                  ),
                  const SizedBox(height: FansivibeSpacing.sm),
                  Text(
                    'Color',
                    style: FansivibeTypography.labelMediumWithFamily,
                  ),
                  Wrap(
                    spacing: FansivibeSpacing.xs,
                    children: [
                      for (final color in _availableColors)
                        FilterChip(
                          label: Text(color),
                          selected: _selectedColor == color,
                          onSelected: (_) {
                            setState(() => _selectedColor = color);
                            Navigator.of(sheetContext).pop();
                          },
                        ),
                    ],
                  ),
                  const SizedBox(height: FansivibeSpacing.sm),
                  FilterChip(
                    label: const Text('Favorites only'),
                    selected: _favoritesOnly,
                    onSelected: (selected) {
                      setState(() => _favoritesOnly = selected);
                      Navigator.of(sheetContext).pop();
                    },
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Future<void> _openSortSheet() {
    return showModalBottomSheet<void>(
      context: context,
      builder: (sheetContext) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Padding(
                padding: const EdgeInsets.all(FansivibeSpacing.md),
                child: Text(
                  'Sort wardrobe',
                  style: FansivibeTypography.titleLargeWithFamily,
                ),
              ),
              for (final option in _WardrobeSort.values)
                ListTile(
                  title: Text(_sortLabel(option)),
                  trailing: option == _sort
                      ? Icon(
                          Icons.check_rounded,
                          color: FansivibeColors.primary,
                        )
                      : null,
                  onTap: () {
                    setState(() => _sort = option);
                    Navigator.of(sheetContext).pop();
                  },
                ),
            ],
          ),
        );
      },
    );
  }

  int get _favoritesCount => _items.where((item) => item.isFavorite).length;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    // Phase 2.1 guests use the same body over the local repository:
    // real counts, real grid, honest empty state — no sign-in wall.
    // Insight/wear slots stay hidden (null futures, no on-device
    // equivalent); the Add button opens the local add flow.
    final filteredItems = _filteredItems;
    final totalItems = _items.length;

    final screenWidth = MediaQuery.sizeOf(context).width;
    final isWide = screenWidth > 600;

    // First-time empty wardrobe experience for new users in initial exploration
    if (_showFirstTimeExperience) {
      return Scaffold(
        backgroundColor: theme.scaffoldBackgroundColor,
        body: SafeArea(
          child: FirstTimeWardrobeView(
            onAddFirstItem: () => _handleAddItem(context),
            onImportFromPhotos: () => _handleImportFromPhotos(context),
          ),
        ),
      );
    }

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      bottomNavigationBar: SafeArea(
        top: false,
        child: Container(
          padding: EdgeInsets.fromLTRB(
            isWide ? 48.0 : 20.0,
            FansivibeSpacing.sm,
            isWide ? 48.0 : 20.0,
            FansivibeSpacing.md,
          ),
          color: theme.scaffoldBackgroundColor,
          child: Center(
            heightFactor: 1,
            child: ConstrainedBox(
              constraints: BoxConstraints(
                maxWidth: isWide ? 520.0 : double.infinity,
              ),
              child: FansiButton.primary(
                label: 'Add Item to Wardrobe',
                icon: Icons.add_rounded,
                onPressed: () => _handleAddItem(context),
              ),
            ),
          ),
        ),
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 20.0;
            final contentMaxWidth = maxWidth > 600 ? 520.0 : double.infinity;
            final crossAxisCount = maxWidth > 600 ? 3 : 2;

            return RefreshIndicator(
              onRefresh: _loadItems,
              color: FansivibeColors.accentGold,
              child: SingleChildScrollView(
                physics: const AlwaysScrollableScrollPhysics(
                  parent: BouncingScrollPhysics(),
                ),
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
                          const SizedBox(height: FansivibeSpacing.xs),
                          WardrobeDashboardHeader(
                            totalItems: totalItems,
                            // Real on-device style identity. A fixed house
                            // style here would pose as the user's own, so an
                            // unknown identity says so instead of inventing one.
                            styleType:
                                LearningService.instance.styleType ??
                                'Style not set',
                            favoritesCount: _favoritesCount,
                            categoryCount: _categoryOptions.length - 1,
                            searchController: _searchController,
                            onSearchChanged: (_) => setState(() {}),
                            onFilterTap: _openFilterSheet,
                            onSortTap: _openSortSheet,
                          ),
                          const SizedBox(height: FansivibeSpacing.sm + 4),
                          _InsightSlot(future: _insightFuture),
                          const SizedBox(height: FansivibeSpacing.sm + 4),
                          _WearSummarySlot(future: _wearSummaryFuture),
                          const SizedBox(height: FansivibeSpacing.sm + 4),
                          SizedBox(
                            height: 40,
                            child: ListView.separated(
                              scrollDirection: Axis.horizontal,
                              physics: const BouncingScrollPhysics(),
                              itemCount: _categoryOptions.length,
                              separatorBuilder: (_, __) =>
                                  const SizedBox(width: FansivibeSpacing.sm),
                              itemBuilder: (context, index) {
                                final cat = _categoryOptions[index];
                                final count = cat.id == 'all'
                                    ? totalItems
                                    : _items
                                          .where(
                                            (item) => item.category == cat.id,
                                          )
                                          .length;
                                return CategoryTile(
                                  name: cat.name,
                                  iconName: cat.iconName,
                                  count: count,
                                  selected: _selectedCategory == cat.id,
                                  onTap: () => _selectCategory(cat.id),
                                );
                              },
                            ),
                          ),
                          const SizedBox(height: FansivibeSpacing.md),
                          Row(
                            children: [
                              Expanded(
                                child: Text(
                                  _selectedCategory == 'all'
                                      ? 'All Items'
                                      : _categoryOptions
                                            .firstWhere(
                                              (c) => c.id == _selectedCategory,
                                              orElse: () =>
                                                  _categoryOptions.first,
                                            )
                                            .name,
                                  style: FansivibeTypography
                                      .labelMediumWithFamily
                                      .copyWith(
                                        fontWeight: FontWeight.w600,
                                        color: FansivibeColors.onSurface,
                                      ),
                                ),
                              ),
                              Text(
                                '${filteredItems.length} ${filteredItems.length == 1 ? 'item' : 'items'}',
                                style: FansivibeTypography.labelSmallWithFamily
                                    .copyWith(color: FansivibeColors.secondary),
                              ),
                            ],
                          ),
                          const SizedBox(height: FansivibeSpacing.md),
                          _buildItemGrid(
                            context,
                            items: filteredItems,
                            crossAxisCount: crossAxisCount,
                          ),
                          const SizedBox(height: FansivibeSpacing.lg),
                        ],
                      ),
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

  Widget _buildItemGrid(
    BuildContext context, {
    required List<WardrobeItemData> items,
    required int crossAxisCount,
  }) {
    if (_isLoading) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: FansivibeSpacing.xxl),
        child: Center(child: CircularProgressIndicator()),
      );
    }

    if (_errorMessage != null) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: FansivibeSpacing.xxl),
        child: Center(
          child: Column(
            children: [
              const Icon(
                Icons.error_outline_rounded,
                size: 48,
                color: FansivibeColors.secondary,
              ),
              const SizedBox(height: FansivibeSpacing.md),
              Text(
                _errorMessage!,
                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                  color: FansivibeColors.secondary,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: FansivibeSpacing.md),
              TextButton.icon(
                onPressed: _loadItems,
                icon: const Icon(Icons.refresh_rounded),
                label: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
    }

    final width = MediaQuery.of(context).size.width;
    final hp = width > 600 ? 48.0 : 20.0;
    final available = (width > 600 ? 520.0 : width) - hp * 2;
    final spacing = 12.0;
    final childW =
        (available - spacing * (crossAxisCount - 1)) / crossAxisCount;
    final aspect = childW / (childW * 1.55);

    if (items.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: FansivibeSpacing.xxl),
        child: Center(
          child: Column(
            children: [
              Icon(
                Icons.inventory_2_outlined,
                size: 64,
                color: FansivibeColors.secondary.withValues(alpha: 0.3),
              ),
              const SizedBox(height: FansivibeSpacing.md),
              Text(
                // ponytail: truthful copy per filter scope — the
                // bottom-bar [Add Item to Wardrobe] is the CTA.
                _selectedCategory == 'all'
                    ? 'No wardrobe items yet.'
                    : 'No items in this category yet',
                style: FansivibeTypography.bodyLargeWithFamily.copyWith(
                  color: FansivibeColors.secondary,
                ),
              ),
              const SizedBox(height: FansivibeSpacing.sm),
              Text(
                'Add your first piece to get started',
                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                  color: FansivibeColors.secondary.withValues(alpha: 0.6),
                ),
              ),
            ],
          ),
        ),
      );
    }

    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: crossAxisCount,
        crossAxisSpacing: spacing,
        mainAxisSpacing: spacing,
        childAspectRatio: aspect,
      ),
      itemCount: items.length,
      itemBuilder: (context, index) {
        final item = items[index];
        return ClothingItemCard(
          item: item,
          onTap: () => _handleItemTap(context, item),
        );
      },
    );
  }

  void _handleAddItem(BuildContext context) async {
    final dynamic result = await context.pushNamed(
      RouteNames.wardrobeAddCategory,
    );
    if (result != null && context.mounted) {
      if (result is List<WardrobeItemData>) {
        for (final item in result) {
          if (!isGuestUser &&
              !LearningService.instance.wardrobe.any((e) => e.id == item.id)) {
            LearningService.instance.addItem(_toEntry(item));
          }
        }
        UserSession.hasSavedWardrobeItem = true;
        _loadItems();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              result.length == 1
                  ? '${result.first.name} added to wardrobe'
                  : '${result.length} items added to wardrobe',
            ),
            backgroundColor: FansivibeColors.accentGold,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(
              borderRadius: FansivibeRadius.smdBorder,
            ),
          ),
        );
      } else if (result is WardrobeItemData) {
        if (!isGuestUser &&
            !LearningService.instance.wardrobe.any((e) => e.id == result.id)) {
          LearningService.instance.addItem(_toEntry(result));
        }
        UserSession.hasSavedWardrobeItem = true;
        _loadItems();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('${result.name} added to wardrobe'),
            backgroundColor: FansivibeColors.accentGold,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(
              borderRadius: FansivibeRadius.smdBorder,
            ),
          ),
        );
      }
    }
  }

  void _handleImportFromPhotos(BuildContext context) async {
    final dynamic result = await Navigator.of(context).push(
      MaterialPageRoute<dynamic>(
        builder: (_) => WardrobeExtractionScreen(repository: _repository),
      ),
    );
    if (result != null && context.mounted) {
      if (result is List<WardrobeItemData>) {
        for (final item in result) {
          if (!isGuestUser &&
              !LearningService.instance.wardrobe.any((e) => e.id == item.id)) {
            LearningService.instance.addItem(_toEntry(item));
          }
        }
        UserSession.hasSavedWardrobeItem = true;
        _loadItems();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              result.length == 1
                  ? '${result.first.name} added to wardrobe'
                  : '${result.length} items added to wardrobe',
            ),
            backgroundColor: FansivibeColors.accentGold,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(
              borderRadius: FansivibeRadius.smdBorder,
            ),
          ),
        );
      } else if (result is WardrobeItemData) {
        if (!isGuestUser &&
            !LearningService.instance.wardrobe.any((e) => e.id == result.id)) {
          LearningService.instance.addItem(_toEntry(result));
        }
        UserSession.hasSavedWardrobeItem = true;
        _loadItems();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('${result.name} added to wardrobe'),
            backgroundColor: FansivibeColors.accentGold,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(
              borderRadius: FansivibeRadius.smdBorder,
            ),
          ),
        );
      }
    }
  }

  void _handleItemTap(BuildContext context, WardrobeItemData item) async {
    // Phase 2.1 guests open the same details over the local repository
    // (wired in initState) — no prompt, no backend fetch.
    await context.pushNamed<String>(
      RouteNames.wardrobeItemDetails,
      extra: item.id,
    );
    if (mounted) {
      _loadItems();
    }
  }
}

/// Live backend insight slot for the wardrobe screen.
///
/// - Loading: renders nothing so the wardrobe item list is never blocked.
/// - 200: renders the backend title/insight verbatim via
///   [WardrobeInsightCard]. The backend currently omits `action`/`route`,
///   so no CTA is wired — no dead navigation is ever rendered.
/// - 204 / unreachable / error: renders nothing (no fabricated advice,
///   no error banner breaking the list).
class _InsightSlot extends StatelessWidget {
  const _InsightSlot({required this.future});

  final Future<WardrobeInsightData?> future;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<WardrobeInsightData?>(
      future: future,
      builder: (context, snapshot) {
        final insight = snapshot.data;
        if (insight == null) return const SizedBox.shrink();
        return WardrobeInsightCard(data: insight);
      },
    );
  }
}

/// Live backend wear-summary slot for the wardrobe screen.
///
/// Mirrors [_InsightSlot]: loading renders nothing so the wardrobe item
/// list is never blocked; a usable summary renders grounded counts-only
/// copy via [mapWearSummaryToUi] through the existing
/// [WardrobeInsightCard] (its `actionLabel` is always null here, so no
/// CTA — and no dead navigation — is ever rendered); null,
/// empty-history, unreachable, or error renders nothing. W-7 behavior is
/// untouched — separate future, separate slot, no shared state, and the
/// summary never mixes wear facts into the insight text.
class _WearSummarySlot extends StatelessWidget {
  const _WearSummarySlot({required this.future});

  final Future<WearSummary?> future;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<WearSummary?>(
      future: future,
      builder: (context, snapshot) {
        final card = snapshot.data == null
            ? null
            : mapWearSummaryToUi(snapshot.data!);
        if (card == null) return const SizedBox.shrink();
        return WardrobeInsightCard(data: card);
      },
    );
  }
}
