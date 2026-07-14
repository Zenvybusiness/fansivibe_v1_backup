import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/home/data/home_mock_data.dart';
import 'package:fansivibe/features/home/presentation/widgets/home_widgets.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

/// The Home screen - Daily personalized style dashboard.
class HomeScreen extends StatelessWidget {
  /// Creates a [HomeScreen].
  const HomeScreen({super.key});

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
                        // Greeting Header
                        GreetingHeader(data: GreetingData.mock),
                        const SizedBox(height: 28),

                        // Today's Look Card
                        TodaysLookCard(
                          data: TodaysLookData.mock,
                          onTryThisLook: () => _handleTryThisLook(context),
                          onChangeStyle: () => _handleChangeStyle(context),
                        ),
                        const SizedBox(height: 24),

                        // Style Score Card
                        StyleScoreCard(data: StyleScoreData.mock),
                        const SizedBox(height: 24),

                        // Quick Actions Section
                        HomeSectionTitle(
                          title: 'Quick Actions',
                          subtitle: 'AI-powered style tools',
                        ),
                        const SizedBox(height: 16),
                        _buildQuickActions(context),
                        const SizedBox(height: 24),

                        // Style Streak Card
                        StyleStreakCard(data: StyleStreakData.mock),
                        const SizedBox(height: 24),

                        // AI Wardrobe Insight Card
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
    return Column(
      children: QuickActionData.mockActions.map((action) {
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
    // TODO: Navigate to wardrobe gaps
  }
}
