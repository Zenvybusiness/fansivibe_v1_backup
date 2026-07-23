import 'package:flutter/material.dart';
import 'package:fansivibe/features/discover/data/discover_mock_data.dart';
import 'package:fansivibe/features/discover/presentation/widgets/look_details_widgets.dart';
import 'package:fansivibe/shared/components/fansi_badge.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

/// The Look Details screen (DISCOVER-002).
class LookDetailsScreen extends StatelessWidget {
  const LookDetailsScreen({required this.look, super.key});

  final DiscoverLookData look;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        backgroundColor: FansivibeColors.background,
        elevation: 0,
        leading: IconButton(
          icon: Icon(
            Icons.arrow_back_rounded,
            color: FansivibeColors.textPrimary,
          ),
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: Text(
          look.title,
          style: theme.textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
          ),
        ),
        actions: [
          IconButton(
            icon: Icon(
              Icons.share_rounded,
              color: FansivibeColors.textSecondary,
            ),
            onPressed: () => _handleShare(context),
          ),
          IconButton(
            icon: Icon(
              Icons.favorite_border_rounded,
              color: FansivibeColors.textSecondary,
            ),
            onPressed: () => _handleSave(context),
          ),
        ],
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 20.0;
            final contentMaxWidth = maxWidth > 600 ? 600.0 : double.infinity;

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
                        const SizedBox(height: 12),

                        _buildHeroSection(context),
                        const SizedBox(height: 24),

                        _buildMatchScoreSection(context),
                        if (look.recommendationReasons != null &&
                            look.recommendationReasons!.isNotEmpty) ...[
                          const SizedBox(height: 24),
                          _buildReasonsSection(context),
                        ],
                        const SizedBox(height: 24),
                        _buildTagsSection(context),
                        const SizedBox(height: 24),

                        if (look.ensembleComponents != null &&
                            look.ensembleComponents!.isNotEmpty) ...[
                          _buildEnsembleSection(context),
                          const SizedBox(height: 24),
                        ],

                        if (look.wardrobeAlternatives != null &&
                            look.wardrobeAlternatives!.isNotEmpty) ...[
                          _buildAlternativesSection(context),
                          const SizedBox(height: 24),
                        ],

                        _buildActionsSection(context),
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

  Widget _buildHeroSection(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: double.infinity,
          height: 200,
          decoration: BoxDecoration(
            color: FansivibeColors.surface,
            borderRadius: BorderRadius.circular(16),
          ),
          child: Stack(
            fit: StackFit.expand,
            children: [
              Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.checkroom_rounded,
                      size: 48,
                      color: FansivibeColors.accentGold.withValues(alpha: 0.3),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Look Image',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: FansivibeColors.textSecondary.withValues(
                          alpha: 0.7,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              Positioned(
                top: 12,
                right: 12,
                child: FansiBadge(
                  score: look.matchScore,
                  size: BadgeSize.medium,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        Text(
          look.title,
          style: theme.textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.bold,
            color: FansivibeColors.textPrimary,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          look.description,
          style: theme.textTheme.bodyLarge?.copyWith(
            color: FansivibeColors.textSecondary,
          ),
        ),
      ],
    );
  }

  Widget _buildMatchScoreSection(BuildContext context) {
    final details = look.matchScoreDetails;
    if (details == null) {
      return const SizedBox.shrink();
    }

    return LookDetailCard(
      title: 'Match Score',
      subtitle: 'How well this look fits your style',
      child: Column(
        children: [
          ScoreCategoryRow(label: 'Fit', score: details.fit),
          const SizedBox(height: 12),
          ScoreCategoryRow(label: 'Color Harmony', score: details.colorHarmony),
          const SizedBox(height: 12),
          ScoreCategoryRow(label: 'Occasion', score: details.occasion),
          const SizedBox(height: 12),
          ScoreCategoryRow(label: 'Creativity', score: details.creativity),
        ],
      ),
    );
  }

  Widget _buildReasonsSection(BuildContext context) {
    final reasons = look.recommendationReasons!;

    return LookDetailCard(
      title: 'Why We Recommend This',
      subtitle: 'Personalized matching reasons',
      child: Column(
        children: reasons
            .map(
              (reason) => Padding(
                padding: EdgeInsets.only(
                  bottom: reason == reasons.last ? 0 : 14,
                ),
                child: ReasonRow(reason: reason),
              ),
            )
            .toList(),
      ),
    );
  }

  Widget _buildTagsSection(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'STYLE & FIT',
          style: theme.textTheme.bodySmall?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textSecondary,
            letterSpacing: 0.5,
          ),
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            ...look.styleTags.map((tag) => LookTag(label: tag)),
            ...look.fitTags.map((tag) => LookTag(label: tag, isFit: true)),
          ],
        ),
        const SizedBox(height: 12),
        Text(
          look.occasion,
          style: theme.textTheme.bodyMedium?.copyWith(
            color: FansivibeColors.accentGold,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }

  Widget _buildEnsembleSection(BuildContext context) {
    final components = look.ensembleComponents!;

    return LookDetailCard(
      title: 'Complete The Look',
      subtitle: 'Pieces in this ensemble',
      child: Column(
        children: components
            .map(
              (component) => Padding(
                padding: EdgeInsets.only(
                  bottom: component == components.last ? 0 : 12,
                ),
                child: ComponentRow(component: component),
              ),
            )
            .toList(),
      ),
    );
  }

  Widget _buildAlternativesSection(BuildContext context) {
    final alternatives = look.wardrobeAlternatives!;

    return LookDetailCard(
      title: 'Wardrobe Alternatives',
      subtitle: 'Swap pieces from your wardrobe',
      child: Column(
        children: alternatives
            .map(
              (alt) => Padding(
                padding: EdgeInsets.only(
                  bottom: alt == alternatives.last ? 0 : 16,
                ),
                child: AlternativeSection(alternative: alt),
              ),
            )
            .toList(),
      ),
    );
  }

  Widget _buildActionsSection(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: FansiButton.primary(
            label: 'Save Look',
            icon: Icons.favorite_rounded,
            onPressed: () => _handleSave(context),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: FansiButton.secondary(
            label: 'Share',
            icon: Icons.share_rounded,
            onPressed: () => _handleShare(context),
          ),
        ),
      ],
    );
  }

  void _handleSave(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('${look.title} saved to your looks'),
        backgroundColor: FansivibeColors.accentGold,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  void _handleShare(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Sharing ${look.title}...'),
        backgroundColor: FansivibeColors.accentGold,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }
}
