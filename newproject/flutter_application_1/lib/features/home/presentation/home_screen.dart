import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/home/data/home_mock_data.dart';
import 'package:fansivibe/features/home/presentation/first_time_home_screen.dart';
import 'package:fansivibe/features/home/presentation/first_time_light_path_home_screen.dart';
import 'package:fansivibe/features/home/presentation/widgets/home_widgets.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/utils/user_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

class HomeScreen extends StatelessWidget {
  final Map<String, dynamic>? onboardingData;

  const HomeScreen({super.key, this.onboardingData});

  Map<String, dynamic>? _onboardingDataFromLocalStorage() {
    if (onboardingData != null) return null;
    final hasCompleted = LocalStorage.onboardingComplete;
    final storedDisplayName = LocalStorage.displayName;
    final storedVibe = LocalStorage.vibe;
    if (hasCompleted && storedDisplayName != null) {
      return <String, dynamic>{
        'onboarding_complete': true,
        'display_name': storedDisplayName,
        'vibe': storedVibe,
        'analysis_cached': LocalStorage.analysisCached,
        'saved_locally': LocalStorage.savedLocally,
      };
    }
    return null;
  }

  bool get _isFirstVisit => onboardingData != null ||
      _onboardingDataFromLocalStorage() != null;
  bool get _hasAnalysis =>
      onboardingData?.containsKey('onboarding_complete') == true ||
      (_onboardingDataFromLocalStorage()?.containsKey('onboarding_complete') == true);
  String? get _displayName =>
      onboardingData?['display_name'] as String? ??
      _onboardingDataFromLocalStorage()?['display_name'] as String?;
  String? get _vibeName =>
      onboardingData?['vibe'] as String? ??
      _onboardingDataFromLocalStorage()?['vibe'] as String?;

  @override
  Widget build(BuildContext context) {
    final learningService = LearningService.instance;
    final userState = _userState(learningService);

    if (_isFirstVisit && _hasAnalysis && UserSession.hasSavedWardrobeItem) {
      return FirstTimeLightPathHomeScreen(vibeName: _vibeName);
    }
    if (_isFirstVisit && _hasAnalysis) {
      return FirstTimeHomeScreen(displayName: _displayName);
    }
    if (_isFirstVisit) {
      return FirstTimeLightPathHomeScreen(vibeName: _vibeName);
    }

    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 20.0;
            final contentMaxWidth = maxWidth > 600 ? 520.0 : double.infinity;

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
                        _buildGreetingHeader(theme, _displayName),
                        const SizedBox(height: 28),
                        _buildTodaysLookCard(context, learningService),
                        const SizedBox(height: 24),
                        StyleScoreCard(data: StyleScoreData.mock),
                        const SizedBox(height: 24),
                        HomeSectionTitle(
                          title: 'Quick Actions',
                          subtitle: 'AI-powered style tools',
                        ),
                        const SizedBox(height: 16),
                        _buildQuickActions(context, learningService),
                        const SizedBox(height: 24),
                        StyleStreakCard(data: StyleStreakData.mock),
                        const SizedBox(height: 24),
                        _buildAIInsight(context, learningService),
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

  UserState _userState(LearningService learningService) {
    final face = learningService.face;
    final preferredOccasions = learningService.preferredOccasions;
    final savedLooks = learningService.savedLooks;
    return UserState(
      hasAnalysis: face != null,
      hasPreferences: preferredOccasions.isNotEmpty,
      hasSavedLooks: savedLooks.isNotEmpty,
      face: face,
      styleType: learningService.styleType,
      savedLooksCount: savedLooks.length,
      preferredOccasions: preferredOccasions,
    );
  }

  Widget _buildGreetingHeader(ThemeData theme, String? displayName) {
    final name = displayName ?? 'Alex';
    return GreetingHeader(
      data: GreetingData(
        greeting: 'Good morning',
        name: name,
        dateLabel: _formatDate(),
      ),
    );
  }

  String _formatDate() {
    final now = DateTime.now();
    final weekdays = [
      'Monday',
      'Tuesday',
      'Wednesday',
      'Thursday',
      'Friday',
      'Saturday',
      'Sunday',
    ];
    final months = [
      'January',
      'February',
      'March',
      'April',
      'May',
      'June',
      'July',
      'August',
      'September',
      'October',
      'November',
      'December',
    ];
    return '${weekdays[now.weekday - 1]}, ${months[now.month - 1]} ${now.day}';
  }

  Widget _buildTodaysLookCard(BuildContext context, LearningService learningService) {
    final hasWardrobe = learningService.wardrobe.isNotEmpty;

    if (!hasWardrobe) {
      // Show honest state when no wardrobe data
      return TodaysLookCard(
        data: TodaysLookData.mock,
        onTryThisLook: () => context.pushNamed(RouteNames.dailyOutfit),
        onChangeStyle: () => context.pushNamed(RouteNames.buildOutfit),
      );
    }

    // Build personalized today's look based on actual wardrobe
    final outerwear = learningService.wardrobe
        .where((item) => item.category == 'outerwear')
        .map((e) => e.name)
        .toList();
    final tops = learningService.wardrobe
        .where((item) => item.category == 'tops')
        .map((e) => e.name)
        .toList();

    final title = outerwear.isNotEmpty ? 'Your Look' : 'Building Your Look';
    final occasion = _determineOccasion(learningService);
    final description = _buildDescription(outerwear, tops);

    return TodaysLookCard(
      data: TodaysLookData.mock.copyWith(
        title: title,
        occasion: occasion,
        description: description,
        items: _buildOutfitItems(outerwear, tops),
      ),
      onTryThisLook: () => context.pushNamed(RouteNames.dailyOutfit),
      onChangeStyle: () => context.pushNamed(RouteNames.buildOutfit),
    );
  }

  String _determineOccasion(LearningService learningService) {
    final occasions = learningService.preferredOccasions;
    if (occasions.isNotEmpty) {
      return occasions.join(' • ');
    }
    return 'Everyday';
  }

  String _buildDescription(List<String> outerwear, List<String> tops) {
    if (outerwear.isNotEmpty && tops.isNotEmpty) {
      return 'Great start with ${outerwear.first} and ${tops.first}. '
          'Consider adding bottoms and accessories for complete looks.';
    }
    if (outerwear.isNotEmpty) {
      return 'You have ${outerwear.first}. '
          'Add tops and other categories to build complete outfits.';
    }
    return 'Start building your wardrobe by adding key pieces.';
  }

  List<OutfitItemData> _buildOutfitItems(List<String> outerwear, List<String> tops) {
    final items = <OutfitItemData>[];

    if (outerwear.isNotEmpty) {
      items.add(OutfitItemData(
        id: '1',
        name: outerwear.first,
        category: 'outerwear',
        color: 'Charcoal',
      ));
    }
    if (tops.isNotEmpty) {
      items.add(OutfitItemData(
        id: '2',
        name: tops.first,
        category: 'tops',
        color: 'Off-White',
      ));
    }

    // Add default items if wardrobe is sparse
    if (items.isEmpty) {
      items.addAll(_defaultOutfitItems());
    }

    return items;
  }

  List<OutfitItemData> _defaultOutfitItems() {
    return const [
      OutfitItemData(
        id: '1',
        name: 'Charcoal Unstructured Blazer',
        category: 'outerwear',
        color: 'Charcoal',
      ),
      OutfitItemData(
        id: '2',
        name: 'Merino Wool Crewneck',
        category: 'tops',
        color: 'Off-White',
      ),
      OutfitItemData(
        id: '3',
        name: 'Tapered Wool Trousers',
        category: 'bottoms',
        color: 'Charcoal',
      ),
      OutfitItemData(
        id: '4',
        name: 'Leather Chelsea Boots',
        category: 'footwear',
        color: 'Black',
      ),
      OutfitItemData(
        id: '5',
        name: 'Minimalist Leather Belt',
        category: 'accessories',
        color: 'Black',
      ),
    ];
  }

  Widget _buildQuickActions(BuildContext context, LearningService learningService) {
    final hasData = learningService.wardrobe.isNotEmpty ||
        learningService.savedLooks.isNotEmpty;

    if (!hasData) {
      return const SizedBox.shrink();
    }

    final actions = QuickActionData.mockActions;
    return Column(
      children: actions.map((action) {
        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: QuickActionCard(
            data: action,
            onTap: () => _handleQuickAction(context, action),
          ),
        );
      }).toList(),
    );
  }

  Widget _buildAIInsight(BuildContext context, LearningService learningService) {
    final hasWardrobe = learningService.wardrobe.isNotEmpty;

    if (!hasWardrobe) {
      return const SizedBox.shrink();
    }

    final outerwearCount =
        learningService.wardrobe.where((item) => item.category == 'outerwear')
            .length;
    final topsCount =
        learningService.wardrobe.where((item) => item.category == 'tops').length;

    final insightTitle = 'Wardrobe Insight';
    final insightBody =
        'You have $outerwearCount outerwear pieces and $topsCount tops. '
        'Adding more variety would unlock additional outfit combinations.';
    final actionLabel = 'View Recommendations';

    return AIInsightCard(
      data: AIWardrobeInsightData.mock.copyWith(
        title: insightTitle,
        insight: insightBody,
        actionLabel: actionLabel,
      ),
      onActionPressed: () => _handleViewRecommendations(context),
    );
  }

  void _handleQuickAction(BuildContext context, QuickActionData action) {
    switch (action.id) {
      case 'scan_outfit':
        context.pushNamed(RouteNames.scanOutfit);
        break;
      case 'build_outfit':
        context.pushNamed(RouteNames.buildOutfit);
        break;
      case 'change_style':
        context.pushNamed(RouteNames.buildOutfit);
        break;
      default:
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Opening ${action.title}...'),
            backgroundColor: Color(action.accentColor),
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(
              borderRadius: FansivibeRadius.smdBorder,
            ),
          ),
        );
    }
  }

  void _handleViewRecommendations(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('Opening Wardrobe Recommendations...'),
        backgroundColor: FansivibeColors.accentGold,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.smdBorder),
      ),
    );
  }
}

class UserState {
  final bool hasAnalysis;
  final bool hasPreferences;
  final bool hasSavedLooks;
  final dynamic face;
  final String? styleType;
  final int savedLooksCount;
  final List<String> preferredOccasions;

  UserState({
    required this.hasAnalysis,
    required this.hasPreferences,
    required this.hasSavedLooks,
    required this.face,
    required this.styleType,
    required this.savedLooksCount,
    required this.preferredOccasions,
  });
}