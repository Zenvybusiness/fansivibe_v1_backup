import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/home/data/home_mock_data.dart';
import 'package:fansivibe/features/home/presentation/first_time_home_screen.dart';
import 'package:fansivibe/features/home/presentation/first_time_light_path_home_screen.dart';
import 'package:fansivibe/features/home/presentation/widgets/home_widgets.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class HomeScreen extends StatelessWidget {
  final Map<String, dynamic>? onboardingData;

  const HomeScreen({super.key, this.onboardingData});

  bool get _isFirstVisit => onboardingData != null;
  bool get _hasAnalysis =>
      onboardingData?.containsKey('onboarding_complete') == true;
  String? get _displayName => onboardingData?['display_name'] as String?;
  String? get _vibeName => onboardingData?['vibe'] as String?;

  @override
  Widget build(BuildContext context) {
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
                        GreetingHeader(
                          data: GreetingData(
                            greeting: _isFirstVisit
                                ? 'Welcome'
                                : 'Good morning',
                            name: _displayName ?? 'Alex',
                            dateLabel: _formatDate(),
                          ),
                        ),
                        const SizedBox(height: 28),
                        TodaysLookCard(
                          data: TodaysLookData.mock,
                          onTryThisLook: () => _handleTryThisLook(context),
                          onChangeStyle: () => _handleChangeStyle(context),
                        ),
                        const SizedBox(height: 24),
                        StyleScoreCard(data: StyleScoreData.mock),
                        const SizedBox(height: 24),
                        HomeSectionTitle(
                          title: 'Quick Actions',
                          subtitle: 'AI-powered style tools',
                        ),
                        const SizedBox(height: 16),
                        _buildQuickActions(context),
                        const SizedBox(height: 24),
                        StyleStreakCard(data: StyleStreakData.mock),
                        const SizedBox(height: 24),
                        AIInsightCard(
                          data: AIWardrobeInsightData.mock,
                          onActionPressed: () =>
                              _handleViewRecommendations(context),
                        ),
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

  Widget _buildQuickActions(BuildContext context) {
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

  void _handleTryThisLook(BuildContext context) {
    context.pushNamed(RouteNames.dailyOutfit);
  }

  void _handleChangeStyle(BuildContext context) {
    context.pushNamed(RouteNames.buildOutfit);
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
              borderRadius: BorderRadius.circular(12),
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
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }
}
