import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/home/data/daily_outfit_mock_data.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/components/section_title.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class DailyOutfitScreen extends StatelessWidget {
  const DailyOutfitScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final data = DailyOutfitData.mock;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Daily Outfit'),
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
                        const SizedBox(height: 8),
                        _buildHeader(context, data),
                        const SizedBox(height: 24),
                        _buildScoreSection(context, data),
                        const SizedBox(height: 24),
                        _buildComponentsSection(context, data),
                        const SizedBox(height: 24),
                        _buildReasonsSection(context, data),
                        const SizedBox(height: 24),
                        _buildStyleDnaSection(context, data),
                        const SizedBox(height: 24),
                        _buildWardrobeContextSection(context, data),
                        const SizedBox(height: 24),
                        _buildActionsSection(context, data),
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

  Widget _buildHeader(BuildContext context, DailyOutfitData data) {
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
                      'Today\'s Look',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: FansivibeColors.textSecondary.withValues(
                          alpha: 0.7,
                        ),
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      data.weather,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: FansivibeColors.textSecondary.withValues(
                          alpha: 0.5,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        Text(
          data.title,
          style: theme.textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.bold,
            color: FansivibeColors.textPrimary,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          data.occasion,
          style: theme.textTheme.bodyLarge?.copyWith(
            color: FansivibeColors.accentGold,
          ),
        ),
        const SizedBox(height: 10),
        Text(
          data.description,
          style: theme.textTheme.bodyLarge?.copyWith(
            color: FansivibeColors.textSecondary,
            height: 1.5,
          ),
        ),
      ],
    );
  }

  Widget _buildScoreSection(BuildContext context, DailyOutfitData data) {
    final matchColor = _scoreColor(data.matchScore);
    final styleColor = _scoreColor(data.styleScore);

    return Row(
      children: [
        Expanded(
          child: _buildScoreCard(
            context: context,
            label: 'Match',
            score: data.matchScore,
            color: matchColor,
            icon: Icons.auto_awesome_rounded,
            subtitle: 'How well this fits you',
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _buildScoreCard(
            context: context,
            label: 'Style Score',
            score: data.styleScore,
            color: styleColor,
            icon: Icons.star_rounded,
            subtitle: 'Overall quality',
          ),
        ),
      ],
    );
  }

  Widget _buildScoreCard({
    required BuildContext context,
    required String label,
    required int score,
    required Color color,
    required IconData icon,
    required String subtitle,
  }) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withValues(alpha: 0.25), width: 1),
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 16, color: color),
              const SizedBox(width: 6),
              Text(
                label,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: FansivibeColors.textSecondary,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          SizedBox(
            width: 72,
            height: 72,
            child: Stack(
              fit: StackFit.expand,
              children: [
                CircularProgressIndicator(
                  value: score / 100,
                  strokeWidth: 5,
                  backgroundColor: color.withValues(alpha: 0.15),
                  valueColor: AlwaysStoppedAnimation<Color>(color),
                  strokeCap: StrokeCap.round,
                ),
                Center(
                  child: Text(
                    '$score%',
                    style: theme.textTheme.displayLarge?.copyWith(
                      fontSize: 22,
                      fontWeight: FontWeight.bold,
                      color: color,
                      fontFamily: 'sans-serif',
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 6),
          Text(
            subtitle,
            style: theme.textTheme.bodySmall?.copyWith(
              color: FansivibeColors.textSecondary,
              fontSize: 11,
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  Widget _buildComponentsSection(BuildContext context, DailyOutfitData data) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SectionTitle(
          title: 'Outfit Components',
          subtitle: '${data.components.length} curated pieces',
        ),
        const SizedBox(height: 14),
        ...data.components.map(
          (component) => Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: _buildComponentCard(context, component),
          ),
        ),
      ],
    );
  }

  Widget _buildComponentCard(
    BuildContext context,
    DailyOutfitComponent component,
  ) {
    final theme = Theme.of(context);
    final color = _parseColor(component.colorHex);

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.15),
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: color.withValues(alpha: 0.3)),
            ),
            child: Center(
              child: Icon(
                _categoryIcon(component.category),
                size: 20,
                color: color,
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  component.name,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w500,
                    color: FansivibeColors.textPrimary,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2),
                Text(
                  '${component.category} \u2022 ${component.color}',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: FansivibeColors.textSecondary,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          SizedBox(
            height: 32,
            child: OutlinedButton(
              onPressed: () => _handleReplaceComponent(context, component),
              style: OutlinedButton.styleFrom(
                foregroundColor: FansivibeColors.accentGold,
                padding: const EdgeInsets.symmetric(horizontal: 10),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
                side: BorderSide(
                  color: FansivibeColors.accentGold.withValues(alpha: 0.3),
                ),
                textStyle: theme.textTheme.bodySmall?.copyWith(fontSize: 11),
              ),
              child: Text(_replaceLabel(component.category)),
            ),
          ),
        ],
      ),
    );
  }

  String _replaceLabel(String category) {
    switch (category) {
      case 'Outerwear':
      case 'Tops':
      case 'Bottoms':
      case 'Footwear':
        return 'Change $category';
      default:
        return 'Replace';
    }
  }

  Widget _buildReasonsSection(BuildContext context, DailyOutfitData data) {
    final theme = Theme.of(context);

    return FansivibeCard(
      borderColor: FansivibeColors.accentGold.withValues(alpha: 0.2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: FansivibeColors.accentGold.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(
                  Icons.lightbulb_outline_rounded,
                  size: 18,
                  color: FansivibeColors.accentGold,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Why This Look Works',
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                        color: FansivibeColors.textPrimary,
                      ),
                    ),
                    Text(
                      'Personalized recommendation reasons',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: FansivibeColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          ...data.reasons.asMap().entries.map(
            (entry) => Padding(
              padding: EdgeInsets.only(
                bottom: entry.key < data.reasons.length - 1 ? 14 : 0,
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 24,
                    height: 24,
                    decoration: BoxDecoration(
                      color: FansivibeColors.accentGold.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Center(
                      child: Text(
                        '${entry.key + 1}',
                        style: theme.textTheme.bodySmall?.copyWith(
                          fontWeight: FontWeight.w700,
                          color: FansivibeColors.accentGold,
                          fontSize: 11,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
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
      ),
    );
  }

  Widget _buildStyleDnaSection(BuildContext context, DailyOutfitData data) {
    final theme = Theme.of(context);
    final dna = data.styleDna;

    return FansivibeCard(
      borderColor: FansivibeColors.accentGold.withValues(alpha: 0.2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: FansivibeColors.accentGold.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(
                  Icons.psychology_rounded,
                  size: 18,
                  color: FansivibeColors.accentGold,
                ),
              ),
              const SizedBox(width: 12),
              Text(
                'Your Style DNA',
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.textPrimary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: _buildDnaItem(
                  context,
                  'Style Type',
                  dna.styleType,
                  Icons.palette_outlined,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _buildDnaItem(
                  context,
                  'Body Type',
                  dna.bodyType,
                  Icons.accessibility_new_rounded,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: _buildDnaItem(
                  context,
                  'Skin Tone',
                  dna.skinTone,
                  Icons.wb_sunny_outlined,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _buildDnaItem(
                  context,
                  'Face Shape',
                  dna.faceShape,
                  Icons.face_rounded,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildDnaItem(
    BuildContext context,
    String label,
    String value,
    IconData icon,
  ) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: FansivibeColors.background,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.08),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 14, color: FansivibeColors.accentGold),
              const SizedBox(width: 6),
              Text(
                label,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: FansivibeColors.textSecondary,
                  fontSize: 10,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            value,
            style: theme.textTheme.bodyMedium?.copyWith(
              fontWeight: FontWeight.w600,
              color: FansivibeColors.textPrimary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildWardrobeContextSection(
    BuildContext context,
    DailyOutfitData data,
  ) {
    final theme = Theme.of(context);
    final wc = data.wardrobeContext;

    return FansivibeCard(
      borderColor: FansivibeColors.accentGold.withValues(alpha: 0.2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: FansivibeColors.accentGold.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(
                  Icons.checkroom_outlined,
                  size: 18,
                  color: FansivibeColors.accentGold,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Wardrobe Context',
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                        color: FansivibeColors.textPrimary,
                      ),
                    ),
                    Text(
                      'Your closet at a glance',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: FansivibeColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: _buildStatItem(
                  context,
                  '${wc.totalItems}',
                  'Total Items',
                  Icons.inventory_2_outlined,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _buildStatItem(
                  context,
                  '${wc.matchingItems}',
                  'Matching',
                  Icons.check_circle_outline_rounded,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: FansivibeColors.background,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(
                color: FansivibeColors.accentGold.withValues(alpha: 0.08),
              ),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  Icons.insights_rounded,
                  size: 16,
                  color: FansivibeColors.accentGold,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    wc.insight,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: FansivibeColors.textSecondary,
                      height: 1.4,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStatItem(
    BuildContext context,
    String value,
    String label,
    IconData icon,
  ) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: FansivibeColors.background,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.08),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 14, color: FansivibeColors.accentGold),
              const SizedBox(width: 6),
              Text(
                label,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: FansivibeColors.textSecondary,
                  fontSize: 10,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            value,
            style: theme.textTheme.headlineMedium?.copyWith(
              fontWeight: FontWeight.bold,
              color: FansivibeColors.textPrimary,
              fontFamily: 'sans-serif',
              fontSize: 20,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActionsSection(BuildContext context, DailyOutfitData data) {
    return Column(
      children: [
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            onPressed: () => _handleWearThis(context),
            icon: const Icon(Icons.check_rounded, size: 20),
            label: const Text('Wear This'),
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
        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          child: OutlinedButton.icon(
            onPressed: () => _handleSaveOutfit(context),
            icon: const Icon(Icons.bookmark_outline_rounded, size: 18),
            label: const Text('Save Outfit'),
            style: OutlinedButton.styleFrom(
              foregroundColor: FansivibeColors.accentGold,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
              side: BorderSide(
                color: FansivibeColors.accentGold.withValues(alpha: 0.3),
              ),
            ),
          ),
        ),
        const SizedBox(height: 16),
        SizedBox(
          width: double.infinity,
          child: OutlinedButton.icon(
            onPressed: () => _handleChangeStyle(context),
            icon: const Icon(Icons.refresh_rounded, size: 18),
            label: const Text('Change Style'),
            style: OutlinedButton.styleFrom(
              foregroundColor: FansivibeColors.accentGold,
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
              side: BorderSide(
                color: FansivibeColors.accentGold.withValues(alpha: 0.2),
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          child: TextButton.icon(
            onPressed: () => _handleReviewCloset(context),
            icon: const Icon(Icons.checkroom_outlined, size: 18),
            label: const Text('Review Closet'),
            style: TextButton.styleFrom(
              foregroundColor: FansivibeColors.textSecondary,
              padding: const EdgeInsets.symmetric(vertical: 12),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
        ),
      ],
    );
  }

  void _handleWearThis(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('Wearing this look!'),
        backgroundColor: FansivibeColors.accentGold,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  void _handleSaveOutfit(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('Outfit saved to your looks'),
        backgroundColor: FansivibeColors.accentGold,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  void _handleReplaceComponent(
    BuildContext context,
    DailyOutfitComponent component,
  ) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Replace ${component.name} coming soon'),
        backgroundColor: FansivibeColors.accentGold,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  void _handleChangeStyle(BuildContext context) {
    context.pushNamed(RouteNames.buildOutfit);
  }

  void _handleReviewCloset(BuildContext context) {
    context.pushNamed(RouteNames.wardrobe);
  }

  Color _scoreColor(int score) {
    if (score >= 90) return const Color(0xFF4CAF50);
    if (score >= 80) return FansivibeColors.accentGold;
    if (score >= 70) return const Color(0xFFFF9800);
    return const Color(0xFFF44336);
  }

  Color _parseColor(String? hex) {
    if (hex == null) return FansivibeColors.accentGold;
    final h = hex.replaceFirst('#', '');
    final fullHex = h.length == 6 ? 'FF$h' : h;
    return Color(int.parse(fullHex, radix: 16));
  }

  IconData _categoryIcon(String category) {
    switch (category) {
      case 'Outerwear':
        return Icons.checkroom_rounded;
      case 'Tops':
        return Icons.person_rounded;
      case 'Bottoms':
        return Icons.accessibility_rounded;
      case 'Footwear':
        return Icons.directions_walk_rounded;
      case 'Accessories':
        return Icons.diamond_rounded;
      default:
        return Icons.category_rounded;
    }
  }
}
