import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/home/data/home_mock_data.dart';
import 'package:fansivibe/features/home/presentation/first_time_home_screen.dart';
import 'package:fansivibe/features/home/presentation/widgets/home_widgets.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

class HomeScreen extends StatelessWidget {
  final Map<String, dynamic>? onboardingData;

  const HomeScreen({super.key, this.onboardingData});

  bool get _isFirstVisit => onboardingData != null;
  bool get _hasAnalysis =>
      onboardingData?.containsKey('onboarding_complete') == true;
  String? get _displayName => onboardingData?['display_name'] as String?;

  @override
  Widget build(BuildContext context) {
    if (_isFirstVisit && _hasAnalysis) {
      return FirstTimeHomeScreen(displayName: _displayName);
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
                        if (_isFirstVisit && !_hasAnalysis)
                          _lightPathPrompt(context),
                        if (_isFirstVisit && !_hasAnalysis)
                          const SizedBox(height: 24),
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

  Widget _lightPathPrompt(BuildContext context) {
    return GestureDetector(
      onTap: () => context.pushNamed(RouteNames.cameraPermission),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(FansivibeSpacing.lg),
        decoration: BoxDecoration(
          color: FansivibeColors.surfaceContainerLow,
          borderRadius: FansivibeRadius.mdBorder,
        ),
        child: Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: FansivibeColors.primary.withValues(alpha: 0.1),
                borderRadius: FansivibeRadius.smBorder,
              ),
              child: Icon(
                Icons.camera_alt_outlined,
                color: FansivibeColors.primary,
                size: 22,
              ),
            ),
            SizedBox(width: FansivibeSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Analyze Your Style',
                    style: FansivibeTypography.titleLargeWithFamily.copyWith(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  SizedBox(height: FansivibeSpacing.xs),
                  Text(
                    'Take a photo to unlock your personal Style DNA',
                    style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                      color: FansivibeColors.secondary,
                    ),
                  ),
                ],
              ),
            ),
            Icon(Icons.chevron_right_rounded, color: FansivibeColors.secondary),
          ],
        ),
      ),
    );
  }

  Widget _buildQuickActions(BuildContext context) {
    final actions = QuickActionData.mockActions;
    if (_isFirstVisit && !_hasAnalysis) {
      final scanAction = QuickActionData(
        id: 'scan_outfit',
        title: 'Analyze My Style',
        subtitle: 'Get your first AI analysis',
        iconName: 'camera_alt_outlined',
        route: '/onboarding/camera-permission',
        accentColor: 0xFFC5A059,
      );
      return Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: QuickActionCard(
          data: scanAction,
          onTap: () => context.pushNamed(RouteNames.cameraPermission),
        ),
      );
    }
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
