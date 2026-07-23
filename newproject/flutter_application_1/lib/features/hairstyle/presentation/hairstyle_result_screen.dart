import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/presentation/widgets/hairstyle_widgets.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class HairstyleResultScreen extends StatelessWidget {
  const HairstyleResultScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final result = HairstyleAnalysisResult.mock;

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

                        _buildHeader(context, result),
                        const SizedBox(height: 24),

                        _buildStyleProfile(context, result),
                        const SizedBox(height: 24),

                        _buildTopRecommendation(context, result),
                        const SizedBox(height: 24),

                        _buildAlternativesSection(context, result),
                        const SizedBox(height: 24),

                        _buildActions(context),
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

  Widget _buildStyleProfile(
    BuildContext context,
    HairstyleAnalysisResult result,
  ) {
    final theme = Theme.of(context);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.15),
        ),
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
        Text(
          '$label: ',
          style: theme.textTheme.bodyMedium?.copyWith(
            color: FansivibeColors.textSecondary,
            fontWeight: FontWeight.w500,
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
                color: const Color(0xFF4CAF50),
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

  Widget _buildActions(BuildContext context) {
    return Column(
      children: [
        FansiButton.secondary(
          label: 'Try Another',
          icon: Icons.refresh_rounded,
          onPressed: () {
            context.replaceNamed(RouteNames.hairstyle);
          },
        ),
        const SizedBox(height: 12),
        FansiButton.primary(
          label: 'Save Style',
          icon: Icons.favorite_rounded,
          onPressed: () {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: const Text('Hairstyle saved to profile'),
                backgroundColor: FansivibeColors.accentGold,
                behavior: SnackBarBehavior.floating,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
            );
          },
        ),
      ],
    );
  }

  void _openDetails(BuildContext context, HairstyleRecommendation rec) {
    context.pushNamed(RouteNames.hairstyleDetails, extra: rec);
  }
}
