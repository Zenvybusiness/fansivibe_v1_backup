import 'package:flutter/material.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/presentation/widgets/hairstyle_widgets.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class HairstyleDetailsScreen extends StatelessWidget {
  const HairstyleDetailsScreen({required this.recommendation, super.key});

  final HairstyleRecommendation recommendation;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final percentage = (recommendation.matchScore * 100).round();

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: Text(recommendation.name),
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

                        _buildHeader(context, percentage),
                        const SizedBox(height: 24),

                        _buildVisualPlaceholder(context),
                        const SizedBox(height: 24),

                        _buildDescriptionCard(context),
                        const SizedBox(height: 20),

                        _buildReasonsSection(context),
                        const SizedBox(height: 20),

                        _buildInfoCard(
                          context,
                          Icons.auto_fix_high_rounded,
                          'Styling Tips',
                          recommendation.stylingTips,
                          FansivibeColors.accentGold,
                        ),
                        const SizedBox(height: 12),

                        _buildInfoCard(
                          context,
                          Icons.content_cut_rounded,
                          'Maintenance',
                          recommendation.maintenance,
                          const Color(0xFF4CAF50),
                        ),
                        const SizedBox(height: 12),

                        _buildInfoCard(
                          context,
                          Icons.people_outline_rounded,
                          'Best For',
                          recommendation.bestFor,
                          const Color(0xFF2196F3),
                        ),
                        const SizedBox(height: 28),

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

  Widget _buildHeader(BuildContext context, int percentage) {
    final theme = Theme.of(context);

    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                recommendation.name,
                style: theme.textTheme.displayLarge?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: FansivibeColors.textPrimary,
                  fontSize: 28,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                recommendation.bestFor,
                style: theme.textTheme.bodyLarge?.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
          decoration: BoxDecoration(
            color: const Color(0xFF4CAF50).withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: const Color(0xFF4CAF50).withValues(alpha: 0.3),
            ),
          ),
          child: Column(
            children: [
              Text(
                '$percentage%',
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: const Color(0xFF4CAF50),
                ),
              ),
              Text(
                'match',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: const Color(0xFF4CAF50),
                  fontSize: 10,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildVisualPlaceholder(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      height: 200,
      width: double.infinity,
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.15),
        ),
      ),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              recommendation.icon,
              size: 64,
              color: FansivibeColors.accentGold.withValues(alpha: 0.4),
            ),
            const SizedBox(height: 12),
            Text(
              recommendation.name,
              style: theme.textTheme.bodyLarge?.copyWith(
                color: FansivibeColors.textSecondary,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              'Style visualization',
              style: theme.textTheme.bodySmall?.copyWith(
                color: FansivibeColors.textSecondary.withValues(alpha: 0.7),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDescriptionCard(BuildContext context) {
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
      child: Text(
        recommendation.description,
        style: theme.textTheme.bodyMedium?.copyWith(
          color: FansivibeColors.textPrimary,
          height: 1.6,
        ),
      ),
    );
  }

  Widget _buildReasonsSection(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Why This Works For You',
          style: theme.textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
            fontSize: 20,
          ),
        ),
        const SizedBox(height: 14),
        ...recommendation.reasons.asMap().entries.map(
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

  Widget _buildInfoCard(
    BuildContext context,
    IconData icon,
    String title,
    String content,
    Color accentColor,
  ) {
    final theme = Theme.of(context);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: accentColor.withValues(alpha: 0.2)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: accentColor.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, size: 20, color: accentColor),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: theme.textTheme.bodyLarge?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: FansivibeColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  content,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: FansivibeColors.textSecondary,
                    height: 1.5,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActions(BuildContext context) {
    return Column(
      children: [
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            onPressed: () {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text('${recommendation.name} saved to profile'),
                  backgroundColor: FansivibeColors.accentGold,
                  behavior: SnackBarBehavior.floating,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              );
            },
            icon: const Icon(Icons.bookmark_outline_rounded, size: 20),
            label: const Text('Save to Profile'),
            style: FilledButton.styleFrom(
              backgroundColor: FansivibeColors.accentGold,
              foregroundColor: FansivibeColors.background,
              padding: const EdgeInsets.symmetric(vertical: 16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
              elevation: 4,
              shadowColor: FansivibeColors.accentGold.withValues(alpha: 0.3),
            ),
          ),
        ),
      ],
    );
  }
}
