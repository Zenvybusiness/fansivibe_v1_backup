import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/auth/auth.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/features/profile/data/profile_mock_data.dart'
    show ProfileMenuAction;
import 'package:fansivibe/features/profile/presentation/widgets/profile_widgets.dart';
import 'package:fansivibe/features/profile/presentation/widgets/style_summary_section.dart';
import 'package:fansivibe/shared/components/fansi_error_view.dart';
import 'package:fansivibe/shared/components/fansi_loading_view.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/user_session.dart';

const List<ProfileMenuAction> _defaultMenuActions = [
  ProfileMenuAction(
    id: 'preferences',
    label: 'Preferences',
    iconName: 'tune_rounded',
  ),
  ProfileMenuAction(
    id: 'saved_looks',
    label: 'Saved Looks',
    iconName: 'bookmark_rounded',
  ),
  ProfileMenuAction(
    id: 'subscription',
    label: 'Subscription',
    iconName: 'workspace_premium_rounded',
  ),
  ProfileMenuAction(
    id: 'support',
    label: 'Support',
    iconName: 'help_outline_rounded',
  ),
  ProfileMenuAction(
    id: 'settings',
    label: 'Settings',
    iconName: 'settings_rounded',
  ),
  ProfileMenuAction(
    id: 'sign_out',
    label: 'Sign Out',
    iconName: 'logout_rounded',
  ),
];

class ProfileScreen extends StatefulWidget {
  /// Backend summary source (M10-C). Defaults to the live repository;
  /// tests inject a fake.
  final LearningSummaryRepository? summaryRepository;

  /// Auth source (D-AUTH-1). Defaults to the live repository; tests
  /// inject a fake.
  final AuthRepository? authRepository;

  /// Optional display name override for testing / direct injection.
  final String? displayName;

  const ProfileScreen({
    super.key,
    this.summaryRepository,
    this.authRepository,
    this.displayName,
  });

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  late final LearningSummaryRepository _summaryRepository;
  late final AuthRepository _authRepository;
  late Future<LearningSummary?> _summaryFuture;
  bool _signingOut = false;

  @override
  void initState() {
    super.initState();
    // Backend-first M10 summary (STEP 19.16): fetched once. Null means
    // unavailable — the hero shows an honest placeholder and the section
    // renders its error state. No mock fallback, ever.
    _summaryRepository =
        widget.summaryRepository ?? LearningSummaryRepositoryImpl();
    _authRepository = widget.authRepository ?? AuthRepositoryImpl();
    _summaryFuture = _summaryRepository.getSummary();
  }

  void _retrySummary() {
    setState(() {
      _summaryFuture = _summaryRepository.getSummary();
    });
  }

  @override
  Widget build(BuildContext context) {
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
                        const SavedLooksRow(looks: []),
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
                            children: _defaultMenuActions.map((action) {
                              return Column(
                                children: [
                                  ProfileMenuCard(
                                    action: action,
                                    onTap: () =>
                                        _handleMenuAction(context, action.id),
                                  ),
                                  if (action.id != _defaultMenuActions.last.id)
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

  /// Truthful hero bound to real authenticated user identity.
  /// Renders real display name & initials when present, neutral empty profile
  /// state when absent, and server-authoritative score/streak from M10 summary.
  /// Never fabricates Alex, @alex_styles, fake levels, or fake ranks.
  Widget _buildHero() {
    final displayName = widget.displayName ??
        UserSession.displayName ??
        LocalStorage.displayName;
    final hasName = displayName != null && displayName.trim().isNotEmpty;
    final cleanName = hasName ? displayName.trim() : null;
    final initial = cleanName != null ? cleanName[0].toUpperCase() : null;

    return FutureBuilder<LearningSummary?>(
      future: _summaryFuture,
      builder: (context, snapshot) {
        final summary = snapshot.data;
        final score = summary?.styleScore;
        final streak = summary?.streak;

        return FansivibeCard(
          child: Column(
            children: [
              Row(
                children: [
                  CircleAvatar(
                    radius: 32,
                    backgroundColor: FansivibeColors.accentGold.withValues(
                      alpha: 0.15,
                    ),
                    child: initial != null
                        ? Text(
                            initial,
                            style: Theme.of(context)
                                .textTheme
                                .displayLarge
                                ?.copyWith(
                                  color: FansivibeColors.accentGold,
                                  fontWeight: FontWeight.bold,
                                  fontSize: 28,
                                ),
                          )
                        : const Icon(
                            Icons.person_outline_rounded,
                            color: FansivibeColors.accentGold,
                            size: 32,
                          ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          cleanName ?? 'Style Profile',
                          style: Theme.of(context)
                              .textTheme
                              .titleLarge
                              ?.copyWith(
                                fontWeight: FontWeight.bold,
                                color: FansivibeColors.textPrimary,
                              ),
                        ),
                        if (cleanName != null) ...[
                          const SizedBox(height: 2),
                          Text(
                            '@${cleanName.toLowerCase().replaceAll(' ', '_')}',
                            style: Theme.of(context)
                                .textTheme
                                .bodyMedium
                                ?.copyWith(
                                  color: FansivibeColors.textSecondary,
                                ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              Row(
                children: [
                  Expanded(
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      decoration: BoxDecoration(
                        color: FansivibeColors.surfaceContainerLow,
                        borderRadius: FansivibeRadius.smBorder,
                      ),
                      child: Column(
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              const Icon(
                                Icons.star_rounded,
                                size: 16,
                                color: FansivibeColors.accentGold,
                              ),
                              const SizedBox(width: 4),
                              Flexible(
                                child: Text(
                                  score?.toString() ?? '–',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: Theme.of(context)
                                      .textTheme
                                      .titleMedium
                                      ?.copyWith(
                                        fontWeight: FontWeight.bold,
                                        color: FansivibeColors.textPrimary,
                                        fontFamily: 'sans-serif',
                                      ),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 2),
                          Text(
                            'Style Score',
                            style: Theme.of(context)
                                .textTheme
                                .bodySmall
                                ?.copyWith(
                                  color: FansivibeColors.textSecondary,
                                  fontSize: 11,
                                ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      decoration: BoxDecoration(
                        color: FansivibeColors.surfaceContainerLow,
                        borderRadius: FansivibeRadius.smBorder,
                      ),
                      child: Column(
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              const Icon(
                                Icons.local_fire_department_rounded,
                                size: 16,
                                color: FansivibeColors.accentGold,
                              ),
                              const SizedBox(width: 4),
                              Flexible(
                                child: Text(
                                  streak != null ? '$streak d' : '–',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: Theme.of(context)
                                      .textTheme
                                      .titleMedium
                                      ?.copyWith(
                                        fontWeight: FontWeight.bold,
                                        color: FansivibeColors.textPrimary,
                                        fontFamily: 'sans-serif',
                                      ),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 2),
                          Text(
                            'Streak',
                            style: Theme.of(context)
                                .textTheme
                                .bodySmall
                                ?.copyWith(
                                  color: FansivibeColors.textSecondary,
                                  fontSize: 11,
                                ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
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
        _handleSignOut(context);
    }
  }

  /// Real sign-out (D-AUTH-1): revokes the server session, clears the
  /// local one, then returns to entry. The guard prevents double-taps
  /// from issuing parallel logouts.
  Future<void> _handleSignOut(BuildContext context) async {
    if (_signingOut) return;
    setState(() => _signingOut = true);
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
    await _authRepository.logout();
    if (!context.mounted) return;
    setState(() => _signingOut = false);
    context.goNamed(RouteNames.entry);
  }
}
