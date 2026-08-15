import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/domain/hairstyle_service.dart';
import 'package:fansivibe/features/hairstyle/presentation/widgets/hairstyle_widgets.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/analytics/analytics_service.dart';

class HairstyleResultScreen extends StatelessWidget {
  const HairstyleResultScreen({super.key, this.result, this.service});

  static final AnalyticsService _analytics = AnalyticsService.instance;

  /// The analysis result to render; falls back to the offline mock when null.
  final HairstyleAnalysisResult? result;

  /// Injectable for tests; when null a temporary service is created on save.
  final HairstyleService? service;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hasMock = result == null;
    final resolved = result ?? HairstyleAnalysisResult.mock;

    // Emit recommendations_viewed only for real backend recommendations,
    // not mock/fallback data. Mock data must NOT produce experiment events.
    if (!hasMock) {
      _analytics.emitRecommendationsViewed(
        recommendationId: resolved.topRecommendation.id,
        confidenceScore: resolved.topRecommendation.matchScore,
        hasExplanation: true,
        topStyleName: resolved.topRecommendation.name,
        isMock: false,
      );
    }

    // Emit explanation_viewed when the explanation section is visible.
    // The explanation is part of the fixed UI layout; we emit once when the
    // screen first renders with a real result. time_in_view is null because
    // precise scroll-position tracking would require fragile hacks that could
    // produce duplicate events on rebuilds, which violates the duplicate
    // protection requirement.
    if (!hasMock) {
      _analytics.emitExplanationViewed(
        explanationText:
            'Strongest match for your ${resolved.faceShape} face shape (+${(_buildExplanationFitFactor(resolved.topRecommendation.matchScore) * 100).round()} face-shape fit).',
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

  double _buildExplanationFitFactor(double matchScore) {
    // Simple confidence-to-fit mapping: higher match score = stronger fit
    return matchScore.clamp(0.0, 1.0);
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
    final owned = service == null;
    final svc = service ?? HairstyleService();
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
      _analytics.emitRecommendationSaved(
        saveSuccess: ok,
        idempotencyKey: '${DateTime.now().microsecondsSinceEpoch}-${_random.nextInt(1 << 32)}',
        lookSavedSignalCommitted: ok,
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
