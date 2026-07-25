import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/home/data/home_mock_data.dart';
import 'package:fansivibe/features/home/presentation/widgets/home_widgets.dart';
import 'package:fansivibe/features/onboarding/data/onboarding_data.dart';
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
                        if (_isFirstVisit && _hasAnalysis)
                          _buildFirstVisitBanner(context),
                        if (_isFirstVisit && _hasAnalysis)
                          const SizedBox(height: 12),
                        GreetingHeader(
                          data: GreetingData(
                            greeting: _isFirstVisit ? 'Welcome' : 'Good morning',
                            name: _displayName ?? 'Alex',
                            dateLabel: _formatDate(),
                          ),
                        ),
                        const SizedBox(height: 28),
                        if (_isFirstVisit && _hasAnalysis) ...[
                          _StyleDNACard(),
                          const SizedBox(height: 24),
                          _AiProgressSection(),
                          const SizedBox(height: 24),
                        ],
                        if (!_hasAnalysis) ...[
                          _lightPathPrompt(context),
                          const SizedBox(height: 24),
                        ],
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

  Widget _buildFirstVisitBanner(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(FansivibeSpacing.md),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            FansivibeColors.primary.withValues(alpha: 0.08),
            Colors.transparent,
          ],
          begin: Alignment.centerLeft,
          end: Alignment.centerRight,
        ),
        borderRadius: FansivibeRadius.smBorder,
      ),
      child: Row(
        children: [
          Icon(
            Icons.auto_awesome_rounded,
            size: 18,
            color: FansivibeColors.primary,
          ),
          SizedBox(width: FansivibeSpacing.sm),
          Text(
            'Your Style DNA is ready. Explore your personalized dashboard.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.primary,
              fontSize: 13,
            ),
          ),
        ],
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
            Icon(
              Icons.chevron_right_rounded,
              color: FansivibeColors.secondary,
            ),
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
      'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
    ];
    final months = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December',
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

class _StyleDNACard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(FansivibeSpacing.lg),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.mdBorder,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.auto_awesome_rounded,
                size: 16,
                color: FansivibeColors.primary,
              ),
              SizedBox(width: FansivibeSpacing.sm),
              Text(
                'Your Style DNA',
                style: FansivibeTypography.headlineMediumWithFamily.copyWith(
                  fontSize: 20,
                ),
              ),
            ],
          ),
          SizedBox(height: FansivibeSpacing.md),
          Row(
            children: [
              _DnaAttribute(label: 'Refined Minimalist', icon: Icons.dashboard_rounded),
              SizedBox(width: FansivibeSpacing.md),
              _DnaAttribute(label: 'Score 82', icon: Icons.trending_up_rounded),
            ],
          ),
          SizedBox(height: FansivibeSpacing.md),
          Row(
            children: [
              _ColorDot(color: 0xFF2D2D2D),
              _ColorDot(color: 0xFF8B7D6B),
              _ColorDot(color: 0xFFC5A059),
              _ColorDot(color: 0xFFF5F0EB),
              _ColorDot(color: 0xFF4A6741),
            ],
          ),
        ],
      ),
    );
  }
}

class _DnaAttribute extends StatelessWidget {
  final String label;
  final IconData icon;
  const _DnaAttribute({required this.label, required this.icon});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: FansivibeColors.primary.withValues(alpha: 0.08),
        borderRadius: FansivibeRadius.fullBorder,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: FansivibeColors.primary),
          SizedBox(width: FansivibeSpacing.xs),
          Text(
            label,
            style: FansivibeTypography.labelMediumWithFamily.copyWith(
              color: FansivibeColors.primary,
              fontSize: 11,
            ),
          ),
        ],
      ),
    );
  }
}

class _ColorDot extends StatelessWidget {
  final int color;
  const _ColorDot({required this.color});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(right: FansivibeSpacing.sm),
      child: Container(
        width: 24,
        height: 24,
        decoration: BoxDecoration(
          color: Color(color),
          shape: BoxShape.circle,
          border: Border.all(
            color: Colors.white.withValues(alpha: 0.1),
            width: 1,
          ),
        ),
      ),
    );
  }
}

class _AiProgressSection extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(FansivibeSpacing.md),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.mdBorder,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.auto_awesome_rounded,
                size: 14,
                color: FansivibeColors.primary,
              ),
              SizedBox(width: FansivibeSpacing.sm),
              Text(
                'Appearance Intelligence',
                style: FansivibeTypography.titleLargeWithFamily.copyWith(
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          SizedBox(height: FansivibeSpacing.sm),
          Text(
            '2 of 7 capabilities active. Tap to explore more.',
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
              fontSize: 13,
            ),
          ),
          SizedBox(height: FansivibeSpacing.sm + 4),
          SizedBox(
            height: 64,
            child: ListView(
              scrollDirection: Axis.horizontal,
              physics: const BouncingScrollPhysics(),
              children: allCapabilities.map((cap) {
                return _CompactCapability(
                  name: cap.name,
                  active: cap.active,
                  hint: cap.unlockHint,
                );
              }).toList(),
            ),
          ),
        ],
      ),
    );
  }
}

class _CompactCapability extends StatelessWidget {
  final String name;
  final bool active;
  final String? hint;
  const _CompactCapability({
    required this.name,
    required this.active,
    this.hint,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 56,
      margin: EdgeInsets.only(right: FansivibeSpacing.sm),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: active
                  ? FansivibeColors.primary.withValues(alpha: 0.12)
                  : FansivibeColors.surfaceContainerHighest,
              border: active
                  ? Border.all(
                      color: FansivibeColors.primary.withValues(alpha: 0.3),
                      width: 1.5,
                    )
                  : null,
            ),
            child: Center(
              child: Icon(
                active ? Icons.check_circle_rounded : Icons.lock_rounded,
                size: 14,
                color: active
                    ? FansivibeColors.primary
                    : FansivibeColors.secondary.withValues(alpha: 0.5),
              ),
            ),
          ),
          SizedBox(height: FansivibeSpacing.xs),
          Text(
            name.split(' ').first,
            style: FansivibeTypography.labelSmallWithFamily.copyWith(
              fontSize: 8,
              color: active
                  ? FansivibeColors.primary
                  : FansivibeColors.secondary.withValues(alpha: 0.5),
            ),
            textAlign: TextAlign.center,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}
