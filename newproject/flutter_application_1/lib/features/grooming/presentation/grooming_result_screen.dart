import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/grooming/data/grooming_models.dart';
import 'package:fansivibe/features/grooming/data/grooming_service.dart';
import 'package:fansivibe/features/grooming/presentation/widgets/grooming_widgets.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/components/fansi_error_view.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

class GroomingResultScreen extends StatelessWidget {
  const GroomingResultScreen({
    required this.faceShape,
    required this.beardStyle,
    required this.beardDensity,
    required this.beardColor,
    this.result,
    this.service,
    super.key,
  });

  final String faceShape;
  final String beardStyle;
  final String beardDensity;
  final String beardColor;
  final GroomingAnalysisResult? result;
  final GroomingService? service;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    // Missing result is an explicit error, never mock content: without a
    // backend result there is nothing truthful to render.
    final resultThis = result;
    if (resultThis == null) {
      return Scaffold(
        backgroundColor: theme.scaffoldBackgroundColor,
        appBar: AppBar(
          title: const Text('Grooming Results'),
          leading: IconButton(
            icon: Icon(
              Icons.arrow_back_rounded,
              color: FansivibeColors.textPrimary,
            ),
            onPressed: () {
              if (context.canPop()) {
                context.pop();
              } else {
                context.goNamed(RouteNames.grooming);
              }
            },
          ),
        ),
        body: SafeArea(
          child: FansiErrorView(
            message:
                'No grooming analysis available. Please run a scan first.',
            onRetry: () {
              if (context.canPop()) {
                context.pop();
              } else {
                context.goNamed(RouteNames.grooming);
              }
            },
          ),
        ),
      );
    }

    // Automatically attach learning service if not provided
    final effectiveService = service ?? GroomingService()..attachLearning(LearningService.instance);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Grooming Results'),
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

                        _buildHeader(context, resultThis),

                        const SizedBox(height: 24),

                        _buildFeatureProfile(context, resultThis),

                        const SizedBox(height: 24),

                        _buildScoreSection(context, resultThis),

                        const SizedBox(height: 24),

                        _buildBeardRecommendation(context, resultThis),

                        const SizedBox(height: 20),

                        _buildEyewearRecommendation(context, resultThis),

                        const SizedBox(height: 24),

                        _buildWhyItWorks(context, resultThis),

                        const SizedBox(height: 24),

                        _buildSpecifications(context, resultThis),

                        const SizedBox(height: 24),

                        _buildAlternativesSection(context, resultThis),

                        const SizedBox(height: 24),

                        _buildActions(context, effectiveService),

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

  Widget _buildHeader(BuildContext context, GroomingAnalysisResult result) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Your Grooming Profile',
          style: theme.textTheme.displayLarge?.copyWith(
            fontWeight: FontWeight.bold,
            color: FansivibeColors.textPrimary,
            fontSize: 28,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          'AI-powered grooming analysis',
          style: theme.textTheme.bodyLarge?.copyWith(
            color: FansivibeColors.textSecondary,
          ),
        ),
      ],
    );
  }

  Widget _buildFeatureProfile(
    BuildContext context,
    GroomingAnalysisResult result,
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
            'Feature Profile',
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w600,
              color: FansivibeColors.textPrimary,
            ),
          ),
          const SizedBox(height: 16),
          _buildProfileRow(
            context,
            Icons.circle_outlined,
            'Face Shape',
            result.faceShape,
          ),
          const SizedBox(height: 10),
          _buildProfileRow(
            context,
            Icons.face_rounded,
            'Beard Style',
            result.beardStyle,
          ),
          const SizedBox(height: 10),
          _buildProfileRow(
            context,
            Icons.blur_on_rounded,
            'Density',
            result.beardDensity,
          ),
          const SizedBox(height: 10),
          _buildProfileRow(
            context,
            Icons.palette_outlined,
            'Color',
            result.beardColor,
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

  Widget _buildScoreSection(
    BuildContext context,
    GroomingAnalysisResult result,
  ) {
    final theme = Theme.of(context);
    final top = result.topRecommendation;
    final percentage = (top.matchScore * 100).round();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.baseBorder,
      ),
      child: Row(
        children: [
          Container(
            width: 80,
            height: 80,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(
                color: FansivibeColors.success.withValues(alpha: 0.4),
                width: 3,
              ),
            ),
            child: Center(
              child: Text(
                '$percentage%',
                style: theme.textTheme.displayLarge?.copyWith(
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                  color: FansivibeColors.success,
                ),
              ),
            ),
          ),
          const SizedBox(width: 20),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Match Score',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: FansivibeColors.textSecondary,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '${top.name} is your top match',
                  style: theme.textTheme.bodyLarge?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: FansivibeColors.textPrimary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBeardRecommendation(
    BuildContext context,
    GroomingAnalysisResult result,
  ) {
    final theme = Theme.of(context);
    final top = result.topRecommendation;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Primary Beard Recommendation',
          style: theme.textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
            fontSize: 22,
          ),
        ),
        const SizedBox(height: 14),
        GroomingRecommendationCard(
          recommendation: top,
          onTap: () => _openDetails(context, top),
        ),
      ],
    );
  }

  Widget _buildEyewearRecommendation(
    BuildContext context,
    GroomingAnalysisResult result,
  ) {
    final theme = Theme.of(context);
    final top = result.topRecommendation;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.baseBorder,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.visibility_rounded,
                size: 18,
                color: FansivibeColors.accentGold,
              ),
              const SizedBox(width: 8),
              Flexible(
                child: Text(
                  'Eyewear Suggestion',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: FansivibeColors.textPrimary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            'Recommended: ${top.eyewearFrame ?? 'N/A'} Frames',
            style: theme.textTheme.bodyLarge?.copyWith(
              fontWeight: FontWeight.w600,
              color: FansivibeColors.textPrimary,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            top.eyewearRecommendation ?? 'Not specified',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: FansivibeColors.textSecondary,
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildWhyItWorks(BuildContext context, GroomingAnalysisResult result) {
    final theme = Theme.of(context);
    final top = result.topRecommendation;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Why It Works',
          style: theme.textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
            fontSize: 20,
          ),
        ),
        const SizedBox(height: 14),
        ...top.reasons.asMap().entries.map(
          (entry) => Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${entry.key + 1}.',
                  style: theme.textTheme.bodyLarge?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: FansivibeColors.accentGold,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    entry.value,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: FansivibeColors.textPrimary,
                      height: 1.5,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildSpecifications(
    BuildContext context,
    GroomingAnalysisResult result,
  ) {
    final theme = Theme.of(context);
    final top = result.topRecommendation;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Grooming Specifications',
          style: theme.textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
            fontSize: 20,
          ),
        ),
        const SizedBox(height: 14),
        _buildSpecRow(
          context,
          Icons.straighten_rounded,
          'Beard Length',
          top.beardLength ?? 'Not specified',
          FansivibeColors.accentGold,
        ),
        const SizedBox(height: 10),
        _buildSpecRow(
          context,
          Icons.timeline_rounded,
          'Cheek Line',
          top.cheekLine ?? 'Not specified',
          FansivibeColors.success,
        ),
        const SizedBox(height: 10),
        _buildSpecRow(
          context,
          Icons.visibility_rounded,
          'Eyewear Frame',
          top.eyewearFrame ?? 'Not specified',
          FansivibeColors.accentGold,
        ),
      ],
    );
  }

  Widget _buildSpecRow(
    BuildContext context,
    IconData icon,
    String label,
    String value,
    Color accentColor,
  ) {
    final theme = Theme.of(context);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.smdBorder,
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: accentColor.withValues(alpha: 0.1),
              borderRadius: FansivibeRadius.smBorder,
            ),
            child: Icon(icon, size: 18, color: accentColor),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: FansivibeColors.textSecondary,
                    fontSize: 11,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  value,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: FansivibeColors.textPrimary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAlternativesSection(
    BuildContext context,
    GroomingAnalysisResult result,
  ) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Alternatives',
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
          (alt) => GroomingRecommendationCard(
            recommendation: alt,
            onTap: () => _openDetails(context, alt),
            isCompact: true,
          ),
        ),
      ],
    );
  }

  Widget _buildActions(BuildContext context, GroomingService service) {
    return Row(
      children: [
        Expanded(
          child: FansiButton.secondary(
            label: 'Try Another',
            icon: Icons.refresh_rounded,
            onPressed: () {
              context.replaceNamed(RouteNames.grooming);
            },
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: FansiButton.primary(
            label: 'Save Look',
            icon: Icons.favorite_rounded,
            onPressed: () async {
              // Reachable only when a real result exists (null returns the
              // error state above), so the bang never fires on missing data.
              final rec = result!.topRecommendation;
              final ok = await service.saveGroomingLook(
                recommendation: rec,
                title: rec.name,
              );
              if (!context.mounted) return;
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text(
                    ok ? 'Look saved to profile' : 'Could not save look',
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
            },
          ),
        ),
      ],
    );
  }

  void _openDetails(BuildContext context, GroomingRecommendation rec) {
    context.pushNamed(RouteNames.groomingDetails, extra: rec);
  }
}