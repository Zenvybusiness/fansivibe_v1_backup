import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/profile/data/profile_mock_data.dart';
import 'package:fansivibe/features/profile/presentation/widgets/profile_widgets.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final profile = ProfileData.mock;

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
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
                        ProfileHeroCard(data: profile),
                        const SizedBox(height: 24),
                        AchievementBar(achievements: profile.achievements),
                        const SizedBox(height: 24),
                        FansivibeCard(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              StyleDnaCard(data: profile.styleDna),
                              const Padding(
                                padding: EdgeInsets.symmetric(vertical: 16),
                                child: Divider(
                                  height: 1,
                                  color:
                                      FansivibeColors.surfaceContainerHighest,
                                ),
                              ),
                              Row(
                                children: [
                                  Expanded(
                                    child: Text(
                                      'Saved Looks',
                                      style: Theme.of(context)
                                          .textTheme
                                          .titleSmall
                                          ?.copyWith(
                                            fontWeight: FontWeight.w600,
                                            color: FansivibeColors.textPrimary,
                                          ),
                                    ),
                                  ),
                                  GestureDetector(
                                    onTap: () => _handleMenuAction(
                                      context,
                                      'saved_looks',
                                    ),
                                    child: Text(
                                      'View All',
                                      style: Theme.of(context)
                                          .textTheme
                                          .bodySmall
                                          ?.copyWith(
                                            color: FansivibeColors.accentGold,
                                            fontWeight: FontWeight.w600,
                                          ),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 12),
                              SavedLooksRow(looks: profile.savedLooks),
                            ],
                          ),
                        ),
                        const SizedBox(height: 24),
                        Text(
                          'Account',
                          style: Theme.of(context).textTheme.titleSmall
                              ?.copyWith(
                                fontWeight: FontWeight.w600,
                                color: FansivibeColors.textPrimary,
                              ),
                        ),
                        const SizedBox(height: 12),
                        FansivibeCard(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 16,
                            vertical: 4,
                          ),
                          child: Column(
                            children: profile.menuActions.map((action) {
                              return Column(
                                children: [
                                  ProfileMenuCard(
                                    action: action,
                                    onTap: () =>
                                        _handleMenuAction(context, action.id),
                                  ),
                                  if (action.id != profile.menuActions.last.id)
                                    Divider(
                                      height: 1,
                                      color: FansivibeColors.accentGold
                                          .withValues(alpha: 0.1),
                                      indent: 40,
                                    ),
                                ],
                              );
                            }).toList(),
                          ),
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

  void _handleMenuAction(BuildContext context, String id) {
    switch (id) {
      case 'preferences':
        context.pushNamed(RouteNames.profilePreferences);
      case 'saved_looks':
        context.pushNamed(RouteNames.profileSavedLooks);
      case 'subscription':
        context.pushNamed(RouteNames.profileSubscription);
      case 'support':
        context.pushNamed(RouteNames.profileSupport);
      case 'settings':
        context.pushNamed(RouteNames.profileSettings);
      case 'sign_out':
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: const Text('Signing out...'),
            backgroundColor: FansivibeColors.accentGold,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
        );
    }
  }
}
