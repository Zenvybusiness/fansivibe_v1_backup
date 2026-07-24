import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/discover/data/discover_mock_data.dart';
import 'package:fansivibe/features/discover/presentation/widgets/discover_widgets.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/components/fansi_chip.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

/// The Discover screen - Personalized style discovery.
class DiscoverScreen extends StatefulWidget {
  /// Creates a [DiscoverScreen].
  const DiscoverScreen({super.key});

  @override
  State<DiscoverScreen> createState() => _DiscoverScreenState();
}

class _DiscoverScreenState extends State<DiscoverScreen> {
  DiscoverTab _selectedTab = DiscoverTab.forYou;
  String _searchQuery = '';
  final TextEditingController _searchController = TextEditingController();

  // Filter states
  String _selectedOccasion = 'all';
  String _selectedStyle = 'all';
  String _selectedFit = 'all';

  // Filter options
  List<FilterOption> _occasionOptions = OccasionFilters.options;
  List<FilterOption> _styleOptions = StyleFilters.options;
  List<FilterOption> _fitOptions = FitFilters.options;

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _onTabChanged(DiscoverTab tab) {
    setState(() {
      _selectedTab = tab;
    });
  }

  void _onOccasionChanged(FilterOption option) {
    setState(() {
      _selectedOccasion = option.id;
      _occasionOptions = _occasionOptions
          .map((o) => o.copyWith(isSelected: o.id == option.id))
          .toList();
    });
  }

  void _onStyleChanged(FilterOption option) {
    setState(() {
      _selectedStyle = option.id;
      _styleOptions = _styleOptions
          .map((o) => o.copyWith(isSelected: o.id == option.id))
          .toList();
    });
  }

  void _onFitChanged(FilterOption option) {
    setState(() {
      _selectedFit = option.id;
      _fitOptions = _fitOptions
          .map((o) => o.copyWith(isSelected: o.id == option.id))
          .toList();
    });
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

  List<DiscoverLookData> _getFilteredLooks() {
    final looks = _selectedTab == DiscoverTab.forYou
        ? DiscoverLookData.forYouMock
        : DiscoverLookData.trendingMock;

    if (_searchQuery.isEmpty &&
        _selectedOccasion == 'all' &&
        _selectedStyle == 'all' &&
        _selectedFit == 'all') {
      return looks;
    }

    return looks.where((look) {
      final matchesSearch =
          _searchQuery.isEmpty ||
          look.title.toLowerCase().contains(_searchQuery.toLowerCase()) ||
          look.description.toLowerCase().contains(_searchQuery.toLowerCase()) ||
          look.styleTags.any(
            (tag) => tag.toLowerCase().contains(_searchQuery.toLowerCase()),
          ) ||
          look.fitTags.any(
            (tag) => tag.toLowerCase().contains(_searchQuery.toLowerCase()),
          );

      final matchesOccasion =
          _selectedOccasion == 'all' ||
          look.occasion.toLowerCase().contains(_selectedOccasion);

      final matchesStyle =
          _selectedStyle == 'all' ||
          look.styleTags.any((tag) => tag.toLowerCase() == _selectedStyle);

      final matchesFit =
          _selectedFit == 'all' ||
          look.fitTags.any((tag) => tag.toLowerCase() == _selectedFit);

      return matchesSearch && matchesOccasion && matchesStyle && matchesFit;
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final filteredLooks = _getFilteredLooks();

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

                        // Search + Filter
                        _buildSearchRow(context),

                        const SizedBox(height: 20),

                        // Tabs (For You / Trending)
                        _buildTabs(context),

                        const SizedBox(height: 20),

                        // Results count
                        _buildResultsHeader(context, filteredLooks.length),

                        const SizedBox(height: 16),

                        // Looks Grid
                        _buildLooksGrid(context, filteredLooks),

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
            borderRadius: BorderRadius.circular(12),
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
                borderRadius: BorderRadius.circular(14),
                borderSide: BorderSide(
                  color: FansivibeColors.accentGold.withValues(alpha: 0.1),
                  width: 1,
                ),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(14),
                borderSide: BorderSide(
                  color: FansivibeColors.accentGold.withValues(alpha: 0.1),
                  width: 1,
                ),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(14),
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
            borderRadius: BorderRadius.circular(14),
            child: Container(
              height: 50,
              width: 50,
              decoration: BoxDecoration(
                color: activeCount > 0
                    ? FansivibeColors.accentGold.withValues(alpha: 0.15)
                    : FansivibeColors.surface,
                borderRadius: BorderRadius.circular(14),
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

  Widget _buildTabs(BuildContext context) {
    return Row(
      children: DiscoverTabData.all.map((tabData) {
        final isSelected = _selectedTab == tabData.tab;
        return Padding(
          padding: EdgeInsets.only(
            right: tabData == DiscoverTabData.all.last ? 0 : 12,
          ),
          child: DiscoverTabButton(
            data: tabData,
            isSelected: isSelected,
            onTap: () => _onTabChanged(tabData.tab),
          ),
        );
      }).toList(),
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
        },
      ),
    );
  }

  Widget _buildResultsHeader(BuildContext context, int count) {
    final theme = Theme.of(context);

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          '$count ${count == 1 ? 'look' : 'looks'} found',
          style: theme.textTheme.bodySmall?.copyWith(
            color: FansivibeColors.textSecondary,
            fontWeight: FontWeight.w500,
          ),
        ),
        if (_selectedOccasion != 'all' ||
            _selectedStyle != 'all' ||
            _selectedFit != 'all')
          FansiButton.tertiary(
            label: 'Clear filters',
            onPressed: () {
              setState(() {
                _selectedOccasion = 'all';
                _selectedStyle = 'all';
                _selectedFit = 'all';
                _occasionOptions = OccasionFilters.options;
                _styleOptions = StyleFilters.options;
                _fitOptions = FitFilters.options;
              });
            },
          ),
      ],
    );
  }

  Widget _buildLooksGrid(BuildContext context, List<DiscoverLookData> looks) {
    final maxWidth = MediaQuery.of(context).size.width;

    if (looks.isEmpty) {
      return _buildEmptyState(context);
    }

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
          showTrendingBadge: look.isTrending,
        );
      },
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
              onPressed: () {
                setState(() {
                  _searchQuery = '';
                  _searchController.clear();
                  _selectedOccasion = 'all';
                  _selectedStyle = 'all';
                  _selectedFit = 'all';
                  _occasionOptions = OccasionFilters.options;
                  _styleOptions = StyleFilters.options;
                  _fitOptions = FitFilters.options;
                });
              },
            ),
          ],
        ),
      ),
    );
  }

  void _handleLookTap(BuildContext context, DiscoverLookData look) {
    context.pushNamed(RouteNames.lookDetails, extra: look);
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
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
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
            borderRadius: BorderRadius.circular(2),
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
