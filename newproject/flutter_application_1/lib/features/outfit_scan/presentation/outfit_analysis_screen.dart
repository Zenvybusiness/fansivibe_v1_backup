import 'package:flutter/material.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/outfit_scan/presentation/widgets/outfit_scan_widgets.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

class OutfitAnalysisScreen extends StatefulWidget {
  const OutfitAnalysisScreen({super.key, this.analysisResult});

  final Map<String, dynamic>? analysisResult;

  @override
  State<OutfitAnalysisScreen> createState() => _OutfitAnalysisScreenState();
}

class _OutfitAnalysisScreenState extends State<OutfitAnalysisScreen> {
  Map<String, dynamic>? analysisResult;

  @override
  void initState() {
    super.initState();
    analysisResult = widget.analysisResult;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    final appearance = analysisResult?['appearance'] as Map<String, dynamic>?;
    final confidence = (analysisResult?['confidence'] ?? 0.0) as double;
    final needsMoreData = analysisResult?['needs_more_data'] as bool? ?? false;
    final recommendations =
        analysisResult?['recommendations'] as Map<String, dynamic>?;

    final topRecommendation =
        recommendations?['top'] as Map<String, dynamic>?;

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
                    borderRadius: FansivibeRadius.smdBorder,
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

                        // Appearance profile header
                        _buildAppearanceProfile(context, appearance, confidence,
                            needsMoreData),

                        const SizedBox(height: 24),

                        // Recommendations section
                        if (topRecommendation != null) ...[
                          _buildRecommendationCard(context, topRecommendation),
                          const SizedBox(height: 24),
                        ],

                        // Analysis sections
                        _buildAnalysisSections(context),

                        const SizedBox(height: 24),

                        // Detected items
                        _buildDetectedItemsSection(context),

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

  Widget _buildAppearanceProfile(
      BuildContext context,
      Map<String, dynamic>? appearance,
      double confidence,
      bool needsMoreData) {
    final faceShape = appearance?['faceShape'] as String?;
    final skinTone = appearance?['skinTone'] as String?;
    final bodyType = appearance?['bodyType'] as String?;
    final styleType = appearance?['styleType'] as String?;

    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.baseBorder,
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.15),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Your Appearance Profile',
            style: FansivibeTypography.headlineMedium,
          ),
          const SizedBox(height: 16),

          // Primary attributes in a row
          Row(mainAxisSize: MainAxisSize.min, 
            children: [
              _AttributeChip(
                label: 'Face Shape',
                value: _formatFaceShape(faceShape),
                icon: Icons.face,
                color: FansivibeColors.accentGold,
              ),
              const SizedBox(width: 12),
              _AttributeChip(
                label: 'Skin Tone',
                value: skinTone,
                icon: Icons.wb_sunny,
                color: FansivibeColors.accentGold,
              ),
              const SizedBox(width: 12),
              _AttributeChip(
                label: 'Body Type',
                value: bodyType,
                icon: Icons.terrain,
                color: FansivibeColors.accentGold,
              ),
            ],
          ),

          if (styleType != null && styleType.isNotEmpty) ...[
            const SizedBox(height: 12),
            _AttributeChip(
              label: 'Style Vibe',
              value: styleType,
              icon: Icons.style,
              color: FansivibeColors.accentGold,
            ),
          ],

          const SizedBox(height: 16),

          // Confidence indicator
          Row(mainAxisSize: MainAxisSize.min, 
            children: [
              Icon(
                Icons.trending_up,
                size: 16,
                color: FansivibeColors.success,
              ),
              const SizedBox(width: 4),
              Text(
                'Confidence: ${(confidence * 100).toInt()}%',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
              ),
              const Spacer(),
              if (needsMoreData) ...[
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: FansivibeColors.warning.withValues(alpha: 0.15),
                    borderRadius: FansivibeRadius.smBorder,
                    border: Border.all(
                      color: FansivibeColors.warning.withValues(alpha: 0.3),
                    ),
                  ),
                  child: Text(
                    'Needs more data',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: FansivibeColors.warning,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildRecommendationCard(
      BuildContext context, Map<String, dynamic> topRecommendation) {
    final id = topRecommendation['id'] as String?;
    final name = topRecommendation['name'] as String?;
    final description = topRecommendation['description'] as String?;
    final matchScore = (topRecommendation['matchScore'] ?? 0.0) as double;
    final reasons =
        topRecommendation['reasons'] as List<dynamic>?;

    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.baseBorder,
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.15),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(mainAxisSize: MainAxisSize.min, 
            children: [
              Icon(
                Icons.auto_awesome,
                size: 24,
                color: FansivibeColors.accentGold,
              ),
              const SizedBox(width: 8),
              Text(
                'Recommended for you',
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.textPrimary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            name ?? 'Recommended Look',
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
              fontWeight: FontWeight.bold,
              color: FansivibeColors.textPrimary,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            description ?? '',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              color: FansivibeColors.textSecondary,
            ),
          ),
          const SizedBox(height: 12),
          _buildMatchScore(matchScore),
          const SizedBox(height: 16),
          if (reasons != null && reasons.isNotEmpty) ...[
            Text(
              'Why this works for you:',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: FansivibeColors.accentGold,
                fontWeight: FontWeight.w500,
              ),
            ),
            const SizedBox(height: 8),
            ...reasons.map((reason) => Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Row(mainAxisSize: MainAxisSize.min, 
                children: [
                  Icon(
                    Icons.check_circle_rounded,
                    size: 12,
                    color: FansivibeColors.success,
                  ),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      reason,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: FansivibeColors.textPrimary,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            )),
          ],
          const SizedBox(height: 16),
          if (topRecommendation['stylingTips'] != null &&
              topRecommendation['stylingTips'].isNotEmpty) ...[
            Text(
              'Styling tip: ${topRecommendation['stylingTips']}',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: FansivibeColors.textSecondary,
              ),
            ),
          ],
          const SizedBox(height: 16),
          if (topRecommendation['maintenance'] != null &&
              topRecommendation['maintenance'].isNotEmpty) ...[
            Text(
              'Maintenance: ${topRecommendation['maintenance']}',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: FansivibeColors.textSecondary,
              ),
            ),
          ],
          const SizedBox(height: 16),
          if (topRecommendation['bestFor'] != null &&
              topRecommendation['bestFor'].isNotEmpty) ...[
            Text(
              'Best for: ${topRecommendation['bestFor']}',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: FansivibeColors.textSecondary,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildMatchScore(double matchScore) {
    final scorePercent = (matchScore * 100).round();
    final color = matchScore >= 0.9
        ? FansivibeColors.success
        : matchScore >= 0.8
            ? FansivibeColors.accentGold
            : matchScore >= 0.7
                ? FansivibeColors.warning
                : FansivibeColors.error;

    return Row(mainAxisSize: MainAxisSize.min, 
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.15),
            borderRadius: FansivibeRadius.smBorder,
            border: Border.all(
              color: color.withValues(alpha: 0.3),
            ),
          ),
          child: Text(
            '$scorePercent% match',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              fontWeight: FontWeight.bold,
              color: color,
              fontFamily: 'sans-serif',
            ),
          ),
        ),
        const Spacer(),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          decoration: BoxDecoration(
            color: FansivibeColors.surface,
            borderRadius: FansivibeRadius.smBorder,
          ),
          child: Text(
            'Reasons may include face shape match, color harmony, and style compatibility',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: FansivibeColors.textSecondary.withValues(alpha: 0.7),
              fontSize: 10,
            ),
          ),
        ),
      ],
    );
  }

  Widget _formatFaceShape(String? faceShape) {
    if (faceShape == null || faceShape.isEmpty) {
      return Text(
        'Not detected',
        style: Theme.of(context).textTheme.bodySmall?.copyWith(
          color: FansivibeColors.textSecondary,
        ),
      );
    }
    return Text(
      faceShape,
      style: Theme.of(context).textTheme.bodySmall?.copyWith(
        color: FansivibeColors.textPrimary,
        fontWeight: FontWeight.w500,
      ),
    );
  }

  Widget _buildAnalysisSections(BuildContext context) {
    final faceShape = analysisResult?['appearance']?['faceShape'] as String?;
    final skinTone = analysisResult?['appearance']?['skinTone'] as String?;
    final bodyType = analysisResult?['appearance']?['bodyType'] as String?;
    final styleType =
        analysisResult?['appearance']?['styleType'] as String?;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Detected Attributes',
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
          ),
        ),
        const SizedBox(height: 12),
        if (faceShape != null && faceShape.isNotEmpty) ...[
          _buildAnalysisSection(
            context,
            'Face Shape',
            faceShape,
            Icons.face,
            FansivibeColors.accentGold,
          ),
        ],
        if (skinTone != null && skinTone.isNotEmpty) ...[
          const SizedBox(height: 8),
          _buildAnalysisSection(
            context,
            'Skin Tone',
            skinTone,
            Icons.wb_sunny,
            FansivibeColors.accentGold,
          ),
        ],
        if (bodyType != null && bodyType.isNotEmpty) ...[
          const SizedBox(height: 8),
          _buildAnalysisSection(
            context,
            'Body Type',
            bodyType,
            Icons.terrain,
            FansivibeColors.accentGold,
          ),
        ],
        if (styleType != null && styleType.isNotEmpty) ...[
          const SizedBox(height: 8),
          _buildAnalysisSection(
            context,
            'Style Vibe',
            styleType,
            Icons.style,
            FansivibeColors.accentGold,
          ),
        ],
      ],
    );
  }

  Widget _buildAnalysisSection(
      BuildContext context, String label, String value, IconData icon,
      Color color) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(mainAxisSize: MainAxisSize.min, 
        children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              value,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: FansivibeColors.textPrimary,
                fontWeight: FontWeight.w500,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDetectedItemsSection(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Analysis Details',
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.w600,
            color: FansivibeColors.textPrimary,
          ),
        ),
        const SizedBox(height: 4),
        const Text(
          'Face and appearance attributes analyzed above',
          style: TextStyle(
            color: FansivibeColors.textSecondary,
            fontSize: 12,
          ),
        ),
        const SizedBox(height: 16),
      ],
    );
  }

  Widget _buildActions(BuildContext context) {
    return Row(mainAxisSize: MainAxisSize.min, 
      children: [
        Expanded(
          child: FansiButton.secondary(
            label: 'Save Profile',
            icon: Icons.bookmark_border,
            onPressed: () {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text('Appearance profile saved'),
                  backgroundColor: FansivibeColors.accentGold,
                  behavior: SnackBarBehavior.floating,
                  shape: RoundedRectangleBorder(
                    borderRadius: FansivibeRadius.smdBorder,
                  ),
                ),
              );
            },
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: FansiButton.primary(
            label: 'See Recommendations',
            icon: Icons.auto_awesome_rounded,
            onPressed: () {
              if (!mounted) return;
              Navigator.of(context).pushNamed('/home/daily-outfit');
            },
          ),
        ),
      ],
    );
  }
}

class _AttributeChip extends StatelessWidget {
  const _AttributeChip({
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
    super.key,
  });

  final String label;
  final dynamic value;
  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final displayValue = value is String && value.isNotEmpty
        ? value
        : 'Not detected';

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: FansivibeRadius.smBorder,
        border: Border.all(
          color: color.withValues(alpha: 0.3),
        ),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, 
        children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 6),
          Text(
            '$label: $displayValue',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: color,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }
}