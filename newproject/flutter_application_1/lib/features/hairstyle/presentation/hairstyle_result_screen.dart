import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/domain/hairstyle_service.dart';
import 'package:fansivibe/features/hairstyle/presentation/widgets/hairstyle_widgets.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/components/fansi_error_view.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/analytics/analytics_service.dart';

class HairstyleResultScreen extends StatefulWidget {
  const HairstyleResultScreen({super.key, this.result, this.service});

  /// The analysis result to render; null renders an explicit error state
  /// (never mock content — a missing result is not a result).
  final HairstyleAnalysisResult? result;

  /// Injectable for tests; when null a temporary service is created on save.
  final HairstyleService? service;

  @override
  State<HairstyleResultScreen> createState() => _HairstyleResultScreenState();
}

class _HairstyleResultScreenState extends State<HairstyleResultScreen> {
  static final AnalyticsService _analytics = AnalyticsService.instance;

  /// Once-guards so the experiment events emit exactly once per real result
  /// (duplicate protection is structural, not tied to rebuilds).
  bool _viewedEmitted = false;
  bool _explanationEmitted = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hasMock = widget.result == null;
    // Missing result is an explicit error, never mock content: without a
    // backend result there is nothing truthful to render.
    if (hasMock) {
      return Scaffold(
        backgroundColor: theme.scaffoldBackgroundColor,
        appBar: AppBar(
          title: const Text('Hairstyle Results'),
          leading: IconButton(
            icon: Icon(
              Icons.arrow_back_rounded,
              color: FansivibeColors.textPrimary,
            ),
            onPressed: () {
              if (context.canPop()) {
                context.pop();
              } else {
                context.goNamed(RouteNames.stylist);
              }
            },
          ),
        ),
        body: SafeArea(
          child: FansiErrorView(
            message:
                'No hairstyle analysis available. Please run a scan first.',
            onRetry: () {
              if (context.canPop()) {
                context.pop();
              } else {
                context.goNamed(RouteNames.stylist);
              }
            },
          ),
        ),
      );
    }
    final resolved = widget.result!;

    // Emit recommendations_viewed only for real backend recommendations,
    // not mock/fallback data, and only once per real result.
    if (!hasMock && !_viewedEmitted) {
      _viewedEmitted = true;
      _analytics.emitRecommendationsViewed(
        recommendationId: resolved.topRecommendation.id,
        confidenceScore: resolved.topRecommendation.matchScore,
        hasExplanation: true,
        topStyleName: resolved.topRecommendation.name,
        isMock: false,
      );
    }

    // Emit explanation_viewed exactly once per real result using the
    // engine's grounded reasons (never a locally derived approximation).
    // time_in_view is null because precise scroll-position tracking would
    // require fragile hacks that could produce duplicate events on rebuilds.
    if (!hasMock && !_explanationEmitted) {
      _explanationEmitted = true;
      _analytics.emitExplanationViewed(
        explanationText: _groundedExplanation(resolved),
        timeInView: null,
      );
    }

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Hairstyle Results'),
        leading: IconButton(
          icon: Icon(
            Icons.arrow_back_rounded,
            color: FansivibeColors.textPrimary,
          ),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 20.0;
            final contentMaxWidth = maxWidth > 600 ? 560.0 : double.infinity;

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

                        _buildHeader(context, resolved),
                        const SizedBox(height: 24),

                        _buildStyleProfile(context, resolved),
                        const SizedBox(height: 24),

                        _buildTopRecommendation(context, resolved),
                        const SizedBox(height: 24),

                        _buildAlternativesSection(context, resolved),
                        const SizedBox(height: 24),

                        _buildActions(context, resolved),
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

  Widget _buildHeader(BuildContext context, HairstyleAnalysisResult result) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Your Style Profile',
          style: theme.textTheme.displayLarge?.copyWith(
            fontWeight: FontWeight.bold,
            color: FansivibeColors.textPrimary,
            fontSize: 28,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          'AI-powered hairstyle analysis',
          style: theme.textTheme.bodyLarge?.copyWith(
            color: FansivibeColors.textSecondary,
          ),
        ),
      ],
    );
  }

  /// The engine's grounded reason sentences for the top recommendation. This
  /// is the authoritative explanation per the analytics contract — never a
  /// locally computed approximation of the match score.
  String _groundedExplanation(HairstyleAnalysisResult result) {
    final reasons = result.topRecommendation.reasons;
    if (reasons.isEmpty) return 'No grounded explanation available.';
    return reasons.join('. ');
  }

  Widget _buildStyleProfile(
    BuildContext context,
    HairstyleAnalysisResult result,
  ) {
    final theme = Theme.of(context);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.baseBorder,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Style Profile',
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w600,
              color: FansivibeColors.textPrimary,
            ),
          ),
          const SizedBox(height: 16),
          _buildProfileRow(
            context,
            Icons.person_outline_rounded,
            'Face Shape',
            result.faceShape,
          ),
          const SizedBox(height: 10),
          _buildProfileRow(
            context,
            Icons.palette_outlined,
            'Skin Tone',
            result.skinTone,
          ),
          const SizedBox(height: 10),
          _buildProfileRow(
            context,
            Icons.auto_awesome_rounded,
            'Style DNA',
            result.styleDna,
          ),
        ],
      ),
    );
  }

  Widget _buildProfileRow(
    BuildContext context,
    IconData icon,
    String label,
    String value,
  ) {
    final theme = Theme.of(context);

    return Row(
      children: [
        Icon(icon, size: 16, color: FansivibeColors.accentGold),
        const SizedBox(width: 10),
        Flexible(
          child: Text(
            '$label: ',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: FansivibeColors.textSecondary,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
        Expanded(
          child: Text(
            value,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: FansivibeColors.textPrimary,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildTopRecommendation(
    BuildContext context,
    HairstyleAnalysisResult result,
  ) {
    final theme = Theme.of(context);
    final top = result.topRecommendation;
    final percentage = (top.matchScore * 100).round();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Top Recommendation',
          style: theme.textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
            fontSize: 22,
          ),
        ),
        const SizedBox(height: 4),
        Row(
          children: [
            Text(
              '$percentage% match',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: FansivibeColors.success,
                fontWeight: FontWeight.w500,
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                '\u2022 Why it works',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 4),
        Text(
          'Score reflects how well this fits your current profile \u2014 advice based on the data we have, not a guarantee.',
          style: theme.textTheme.bodySmall?.copyWith(
            color: FansivibeColors.textSecondary,
          ),
        ),
        const SizedBox(height: 14),
        HairstyleCard(
          recommendation: top,
          onTap: () => _openDetails(context, top),
        ),
      ],
    );
  }

  Widget _buildAlternativesSection(
    BuildContext context,
    HairstyleAnalysisResult result,
  ) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Alternative Hairstyles',
          style: theme.textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
            fontSize: 22,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          '${result.alternatives.length} curated alternatives for you',
          style: theme.textTheme.bodyMedium?.copyWith(
            color: FansivibeColors.textSecondary,
          ),
        ),
        const SizedBox(height: 14),
        ...result.alternatives.map(
          (alt) => HairstyleCard(
            recommendation: alt,
            onTap: () => _openDetails(context, alt),
            isCompact: true,
          ),
        ),
      ],
    );
  }

  Widget _buildActions(BuildContext context, HairstyleAnalysisResult result) {
    final top = result.topRecommendation;

    return Column(
      children: [
        FansiButton.secondary(
          label: 'Try Another',
          icon: Icons.refresh_rounded,
          onPressed: () {
            _analytics.emitRecommendationSelected(
              action: 'dismiss',
              recommendationId: top.id,
              confidenceAtSelection: top.matchScore,
            );
            context.replaceNamed(RouteNames.hairstyle);
          },
        ),
        const SizedBox(height: 12),
        const Text(
          'Save Style → saved to profile for later reference',
          style: TextStyle(
            fontSize: 10,
            color: FansivibeColors.textSecondary,
          ),
        ),
        FansiButton.primary(
          label: 'Save Style',
          icon: Icons.favorite_rounded,
          onPressed: () {
            _analytics.emitRecommendationSelected(
              action: 'save',
              recommendationId: top.id,
              confidenceAtSelection: top.matchScore,
            );
            _saveStyle(context, top);
          },
        ),
      ],
    );
  }

  Future<void> _saveStyle(
    BuildContext context,
    HairstyleRecommendation recommendation,
  ) async {
    final owned = widget.service == null;
    final svc = widget.service ?? HairstyleService();
    if (owned) {
      // Keep the on-device memory in sync so a save here also records the
      // look_saved signal and grows the saved-looks list (G-19).
      svc.attachLearning(LearningService.instance);
    }
    try {
      final ok = await svc.saveLook(
        recommendation: recommendation,
        title: recommendation.name,
      );
      if (!context.mounted) return;
      final snackbarShown = true;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            ok ? 'Hairstyle saved to profile' : 'Could not save hairstyle',
          ),
          backgroundColor: ok
              ? FansivibeColors.accentGold
              : FansivibeColors.surfaceContainerHigh,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(
            borderRadius: FansivibeRadius.smdBorder,
          ),
        ),
      );
      // Authoritative save result: the key actually sent and whether the
      // on-device look_saved signal committed (G-7).
      _analytics.emitRecommendationSaved(
        saveSuccess: ok,
        idempotencyKey: svc.lastIdempotencyKey ?? 'unknown',
        lookSavedSignalCommitted: svc.lastSavedSignalCommitted,
        snackbarShown: snackbarShown,
      );
    } finally {
      if (owned) {
        svc.dispose();
      }
    }
  }

  void _openDetails(BuildContext context, HairstyleRecommendation rec) {
    context.pushNamed(RouteNames.hairstyleDetails, extra: rec);
  }
}
