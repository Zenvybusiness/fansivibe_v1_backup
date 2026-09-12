import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/features/profile/data/profile_mock_data.dart';
import 'package:fansivibe/features/profile/presentation/widgets/profile_widgets.dart';
import 'package:fansivibe/features/profile/presentation/widgets/style_summary_section.dart';
import 'package:fansivibe/shared/components/fansi_error_view.dart';
import 'package:fansivibe/shared/components/fansi_loading_view.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

class ProfileScreen extends StatefulWidget {
  /// Backend summary source (M10-C). Defaults to the live repository;
  /// tests inject a fake.
  final LearningSummaryRepository? summaryRepository;

  const ProfileScreen({super.key, this.summaryRepository});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  late final LearningSummaryRepository _summaryRepository;
  late Future<LearningSummary?> _summaryFuture;

  @override
  void initState() {
    super.initState();
    // Backend-first M10 summary (STEP 19.16): fetched once. Null means
    // unavailable — the hero shows an honest placeholder and the section
    // renders its error state. No mock fallback, ever.
    _summaryRepository =
        widget.summaryRepository ?? LearningSummaryRepositoryImpl();
    _summaryFuture = _summaryRepository.getSummary();
  }

  void _retrySummary() {
    setState(() {
      _summaryFuture = _summaryRepository.getSummary();
    });
  }

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
                        _buildHero(),
                        const SizedBox(height: 24),
                        AchievementBar(achievements: profile.achievements),
                        const SizedBox(height: 24),
                        StyleDnaCard(data: profile.styleDna),
                        const SizedBox(height: 24),
                        _buildSummarySection(),
                        Row(
                          children: [
                            Expanded(
                              child: Text(
                                'Saved Looks',
                                style: Theme.of(context).textTheme.titleSmall
                                    ?.copyWith(
                                      fontWeight: FontWeight.w600,
                                      color: FansivibeColors.textPrimary,
                                    ),
                              ),
                            ),
                            GestureDetector(
                              onTap: () =>
                                  _handleMenuAction(context, 'saved_looks'),
                              child: Text(
                                'View All',
                                style: Theme.of(context).textTheme.bodySmall
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

  /// Backend-fed hero score (M10-C): the same summary future feeds the
  /// section below, so one GET serves the whole screen.
  Widget _buildHero() {
    final profile = ProfileData.mock;
    return FutureBuilder<LearningSummary?>(
      future: _summaryFuture,
      builder: (context, snapshot) {
        // Null while loading or unavailable renders the honest
        // placeholder inside the hero — never the mock score.
        return ProfileHeroCard(
          data: profile,
          styleScore: snapshot.data?.styleScore,
        );
      },
    );
  }

  /// Backend-fed summary section with truthful loading/error states.
  Widget _buildSummarySection() {
    return FutureBuilder<LearningSummary?>(
      future: _summaryFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const FansiLoadingView(message: 'Loading style summary…');
        }
        final summary = snapshot.data;
        if (snapshot.hasError || summary == null) {
          return FansiErrorView(
            message:
                'Couldn\'t load style summary. Please check your connection.',
            onRetry: _retrySummary,
          );
        }
        return StyleSummarySection(summary: summary);
      },
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
              borderRadius: FansivibeRadius.smdBorder,
            ),
          ),
        );
    }
  }
}
