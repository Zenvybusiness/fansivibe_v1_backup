import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/widgets/wardrobe_widgets.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/utils/user_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

WardrobeEntry _toEntry(WardrobeItemData item) => WardrobeEntry(
  id: item.id,
  name: item.name,
  category: item.category,
  color: item.color,
  material: item.material,
  isFavorite: item.isFavorite,
);

WardrobeItemData _toItem(WardrobeEntry entry) => WardrobeItemData(
  id: entry.id,
  name: entry.name,
  category: entry.category,
  color: entry.color,
  material: entry.material,
  isFavorite: entry.isFavorite,
);

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
  });

  final WardrobeRepository? insightRepository;
  final WardrobeRepository? repository;

  @override
  State<WardrobeScreen> createState() => _WardrobeScreenState();
}

class _WardrobeScreenState extends State<WardrobeScreen> {
  String _selectedCategory = 'all';
  late final WardrobeRepository _repository;
  List<WardrobeItemData> _items = [];
  bool _isLoading = true;
  String? _errorMessage;
  late final Future<WardrobeInsightData?> _insightFuture;
  late final Future<WearSummary?> _wearSummaryFuture;

  @override
  void initState() {
    super.initState();
    _repository =
        widget.repository ?? widget.insightRepository ?? WardrobeRepositoryImpl();
    // Independent from the item list: the list renders immediately while
    // the insight resolves on its own. Single fetch — no refetch storms.
    _insightFuture = _repository.getInsight();
    // Independent from the insight: same seam, separate future, separate
    // slot — W-7 loading/error/204 behavior is unchanged by this fetch.
    _wearSummaryFuture =
        Future.sync(() => _repository.getWearSummary());
    _loadItems();
  }

  Future<void> _loadItems() async {
    if (!mounted) return;
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final items = await _repository.listItems(pageSize: 100);
      if (!mounted) return;
      setState(() {
        _items = items;
        _isLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = 'Failed to load wardrobe. Please check your connection.';
        _isLoading = false;
      });
    }
  }

  void _selectCategory(String categoryId) {
    setState(() {
      _selectedCategory = categoryId;
    });
  }

  List<WardrobeItemData> get _filteredItems {
    if (_selectedCategory == 'all') {
      return _items;
    }
    return _items.where((item) => item.category == _selectedCategory).toList();
  }

  int get _favoritesCount => _items.where((item) => item.isFavorite).length;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final filteredItems = _filteredItems;
    final totalItems = _items.length;

    final screenWidth = MediaQuery.sizeOf(context).width;
    final isWide = screenWidth > 600;

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
                            styleType: WardrobeMockData.styleType,
                            favoritesCount: _favoritesCount,
                            categoryCount: WardrobeMockData.categories.length - 1,
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
                              itemCount: WardrobeMockData.categories.length,
                              separatorBuilder: (_, __) =>
                                  const SizedBox(width: FansivibeSpacing.sm),
                              itemBuilder: (context, index) {
                                final cat = WardrobeMockData.categories[index];
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
                                      : WardrobeMockData.categories
                                            .firstWhere(
                                              (c) => c.id == _selectedCategory,
                                            )
                                            .name,
                                  style: FansivibeTypography.labelMediumWithFamily
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
                'No items in this category yet',
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
    final result = await context.pushNamed<WardrobeItemData>(
      RouteNames.wardrobeAddCategory,
    );
    if (result != null && context.mounted) {
      LearningService.instance.addItem(_toEntry(result));
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

  void _handleItemTap(BuildContext context, WardrobeItemData item) async {
    await context.pushNamed<String>(RouteNames.wardrobeItemDetails, extra: item.id);
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
