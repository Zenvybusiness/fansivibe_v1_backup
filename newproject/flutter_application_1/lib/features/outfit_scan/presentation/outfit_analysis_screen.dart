import 'package:flutter/material.dart';
import 'package:fansivibe/features/outfit_scan/data/outfit_scan_mock_data.dart';
import 'package:fansivibe/features/outfit_scan/presentation/widgets/outfit_scan_widgets.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class OutfitAnalysisScreen extends StatelessWidget {
  const OutfitAnalysisScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final data = OutfitAnalysisData.mock;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Outfit Analysis'),
        leading: IconButton(
          icon: Icon(
            Icons.arrow_back_rounded,
            color: FansivibeColors.textPrimary,
          ),
          onPressed: () => Navigator.of(context).pop(),
        ),
        actions: [
          IconButton(
            icon: Icon(
              Icons.share_outlined,
              color: FansivibeColors.textSecondary,
            ),
            onPressed: () {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: const Text('Share coming soon'),
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

                        // Title section
                        _buildHeader(context, data),
                        const SizedBox(height: 24),

                        // Outfit visual placeholder
                        _buildOutfitVisual(context),
                        const SizedBox(height: 24),

                        // Analysis sections
                        ...data.sections.map(
                          (section) => AnalysisSectionCard(section: section),
                        ),

                        const SizedBox(height: 24),

                        // Detected items
                        _buildDetectedItemsSection(context, data),
                        const SizedBox(height: 24),

                        // Actions
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

  Widget _buildHeader(BuildContext context, OutfitAnalysisData data) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          data.title,
          style: theme.textTheme.displayLarge?.copyWith(
            fontWeight: FontWeight.bold,
            color: FansivibeColors.textPrimary,
            fontSize: 28,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          'AI-powered style analysis',
          style: theme.textTheme.bodyLarge?.copyWith(
            color: FansivibeColors.textSecondary,
          ),
        ),
      ],
    );
  }

  Widget _buildOutfitVisual(BuildContext context) {
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
      child: Stack(
        fit: StackFit.expand,
        children: [
          Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.checkroom_rounded,
                  size: 64,
                  color: FansivibeColors.accentGold.withValues(alpha: 0.4),
                ),
                const SizedBox(height: 12),
                Text(
                  'Outfit Visual',
                  style: theme.textTheme.bodyLarge?.copyWith(
                    color: FansivibeColors.textSecondary,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'Captured look preview',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: FansivibeColors.textSecondary.withValues(alpha: 0.7),
                  ),
                ),
              ],
            ),
          ),
          Positioned(
            top: 12,
            left: 12,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: const Color(0xFF4CAF50).withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: const Color(0xFF4CAF50).withValues(alpha: 0.3),
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.check_circle_rounded,
                    size: 14,
                    color: const Color(0xFF4CAF50),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    'Analysis Ready',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: const Color(0xFF4CAF50),
                      fontWeight: FontWeight.w600,
                      fontSize: 11,
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

  Widget _buildDetectedItemsSection(
    BuildContext context,
    OutfitAnalysisData data,
  ) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Detected Items',
          style: theme.textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
            fontSize: 22,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          '${data.detectedItems.length} items identified',
          style: theme.textTheme.bodyMedium?.copyWith(
            color: FansivibeColors.textSecondary,
          ),
        ),
        const SizedBox(height: 16),
        ...data.detectedItems.map((item) => DetectedItemChip(item: item)),
      ],
    );
  }

  Widget _buildActions(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: OutlinedButton.icon(
            onPressed: () => Navigator.of(context).pop(),
            icon: const Icon(Icons.refresh_rounded, size: 18),
            label: const Text('Scan Again'),
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
        const SizedBox(width: 12),
        Expanded(
          child: FilledButton.icon(
            onPressed: () {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: const Text('Look saved to wardrobe'),
                  backgroundColor: FansivibeColors.accentGold,
                  behavior: SnackBarBehavior.floating,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              );
            },
            icon: const Icon(Icons.bookmark_outline_rounded, size: 18),
            label: const Text('Save Look'),
            style: FilledButton.styleFrom(
              backgroundColor: FansivibeColors.accentGold,
              foregroundColor: FansivibeColors.background,
              padding: const EdgeInsets.symmetric(vertical: 14),
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
