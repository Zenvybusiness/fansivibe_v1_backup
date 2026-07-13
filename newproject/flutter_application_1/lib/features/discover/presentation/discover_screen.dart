import 'package:flutter/material.dart';
import 'package:fansivibe/features/discover/data/discover_mock_data.dart';
import 'package:fansivibe/features/discover/presentation/widgets/discover_widgets.dart';
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

                        // Search Field
                        _buildSearchField(context),

                        const SizedBox(height: 20),

                        // Tabs (For You / Trending)
                        _buildTabs(context),

                        const SizedBox(height: 20),

                        // Filters
                        _buildFilters(context),

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

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Discover',
          style: theme.textTheme.displayLarge?.copyWith(
            fontWeight: FontWeight.bold,
            color: FansivibeColors.textPrimary,
            fontSize: 28,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          'Find looks tailored to your style',
          style: theme.textTheme.bodyLarge?.copyWith(
            color: FansivibeColors.textSecondary,
          ),
        ),
      ],
    );
  }

  Widget _buildSearchField(BuildContext context) {
    final theme = Theme.of(context);

    return TextField(
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

  Widget _buildFilters(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Occasion Filters
        DiscoverFilterChipsRow(
          options: _occasionOptions,
          onOptionChanged: _onOccasionChanged,
          title: 'OCCASION',
        ),

        const SizedBox(height: 16),

        // Style Filters
        DiscoverFilterChipsRow(
          options: _styleOptions,
          onOptionChanged: _onStyleChanged,
          title: 'STYLE',
        ),

        const SizedBox(height: 16),

        // Fit Filters
        DiscoverFilterChipsRow(
          options: _fitOptions,
          onOptionChanged: _onFitChanged,
          title: 'FIT',
        ),
      ],
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
          TextButton(
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
            style: TextButton.styleFrom(
              foregroundColor: FansivibeColors.accentGold,
              padding: EdgeInsets.zero,
              minimumSize: const Size(0, 32),
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child: Text(
              'Clear filters',
              style: theme.textTheme.bodySmall?.copyWith(
                fontWeight: FontWeight.w600,
                color: FansivibeColors.accentGold,
              ),
            ),
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
        childAspectRatio: 0.72,
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
            FilledButton.icon(
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
              icon: const Icon(Icons.refresh_rounded, size: 18),
              label: const Text('Reset filters'),
              style: FilledButton.styleFrom(
                backgroundColor: FansivibeColors.accentGold,
                foregroundColor: FansivibeColors.background,
                padding: const EdgeInsets.symmetric(
                  horizontal: 24,
                  vertical: 12,
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _handleLookTap(BuildContext context, DiscoverLookData look) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Opening ${look.title} details...'),
        backgroundColor: FansivibeColors.accentGold,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
    // TODO: Navigate to DISCOVER-002 LookDetailsScreen
  }
}
