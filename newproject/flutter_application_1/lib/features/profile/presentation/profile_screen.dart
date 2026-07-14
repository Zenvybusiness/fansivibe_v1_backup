import 'package:flutter/material.dart';
import 'package:fansivibe/features/profile/data/profile_mock_data.dart';
import 'package:fansivibe/features/profile/presentation/widgets/profile_widgets.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/components/section_title.dart';
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

                        // Profile Header
                        ProfileHeader(data: profile),
                        const SizedBox(height: 12),

                        // Stylist Level
                        Center(
                          child: StylistLevelBadge(data: profile.stylistLevel),
                        ),
                        const SizedBox(height: 24),

                        // Style Score & Global Rank
                        FansivibeCard(
                          child: ProfileStatRow(
                            score: profile.styleScore,
                            rank: profile.globalRank,
                          ),
                        ),
                        const SizedBox(height: 20),

                        // Style Progress
                        FansivibeCard(
                          child: StyleProgressIndicator(
                            data: profile.styleProgress,
                          ),
                        ),
                        const SizedBox(height: 24),

                        // Achievements
                        SectionTitle(
                          title: 'Achievements',
                          subtitle:
                              '${profile.achievements.where((a) => a.unlocked).length} of ${profile.achievements.length} unlocked',
                        ),
                        const SizedBox(height: 16),
                        FansivibeCard(
                          child: AchievementGrid(
                            achievements: profile.achievements,
                          ),
                        ),
                        const SizedBox(height: 24),

                        // Saved Looks Preview
                        SectionTitle(
                          title: 'Saved Looks',
                          actionLabel: 'View All',
                          onActionPressed: () =>
                              _handleMenuAction(context, 'saved_looks'),
                        ),
                        const SizedBox(height: 16),
                        SavedLooksRow(looks: profile.savedLooks),
                        const SizedBox(height: 24),

                        // Style DNA
                        SectionTitle(title: 'Style DNA'),
                        const SizedBox(height: 16),
                        FansivibeCard(
                          child: StyleDnaCard(data: profile.styleDna),
                        ),
                        const SizedBox(height: 24),

                        // Menu Actions
                        SectionTitle(title: 'Account'),
                        const SizedBox(height: 16),
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
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(_getSnackbarLabel(id)),
        backgroundColor: FansivibeColors.accentGold,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  String _getSnackbarLabel(String id) {
    switch (id) {
      case 'preferences':
        return 'Opening Preferences...';
      case 'saved_looks':
        return 'Opening Saved Looks...';
      case 'subscription':
        return 'Opening Subscription...';
      case 'support':
        return 'Opening Support...';
      case 'settings':
        return 'Opening Settings...';
      case 'sign_out':
        return 'Signing out...';
      default:
        return 'Opening...';
    }
  }
}
