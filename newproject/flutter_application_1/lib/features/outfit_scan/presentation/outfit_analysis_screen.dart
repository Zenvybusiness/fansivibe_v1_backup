import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

class OutfitAnalysisScreen extends StatefulWidget {
  const OutfitAnalysisScreen({
    super.key,
    this.analysisResult,
    this.isLoading = false,
    this.onRetry,
  });

  final Map<String, dynamic>? analysisResult;
  final bool isLoading;
  final VoidCallback? onRetry;

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
  void didUpdateWidget(OutfitAnalysisScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.analysisResult != oldWidget.analysisResult) {
      setState(() {
        analysisResult = widget.analysisResult;
      });
    }
  }

  void _handleRetry(BuildContext context) {
    if (widget.onRetry != null) {
      widget.onRetry!();
    } else {
      Navigator.of(context).pop();
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (widget.isLoading) {
      return Scaffold(
        backgroundColor: theme.scaffoldBackgroundColor,
        appBar: _buildAppBar(context),
        body: SafeArea(child: _buildLoadingState(context)),
      );
    }

    final rawError = analysisResult?['error'];
    if (rawError != null) {
      return Scaffold(
        backgroundColor: theme.scaffoldBackgroundColor,
        appBar: _buildAppBar(context),
        body: SafeArea(child: _buildErrorState(context, rawError)),
      );
    }

    final appearance = analysisResult?['appearance'] as Map<String, dynamic>?;
    final rawConfidence = analysisResult?['confidence'];
    final double? confidence =
        (rawConfidence is num) ? rawConfidence.toDouble() : null;
    final needsMoreData = analysisResult?['needs_more_data'] as bool? ?? false;
    final recommendations =
        analysisResult?['recommendations'] as Map<String, dynamic>?;
    final topRecommendation = recommendations?['top'] as Map<String, dynamic>?;
    final appearanceError =
        (analysisResult?['appearance_error'] as Map<String, dynamic>?)?['reason']
            as String?;

    final faceShape = appearance?['faceShape'] as String?;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: _buildAppBar(context),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final isMobile = maxWidth <= 600;
            final horizontalPadding = isMobile ? (maxWidth < 360 ? 14.0 : 20.0) : 48.0;
            final contentMaxWidth = isMobile ? double.infinity : 560.0;

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
                        _buildAppearanceProfile(
                          context,
                          appearance,
                          confidence,
                          needsMoreData,
                          appearanceError: appearanceError,
                        ),

                        const SizedBox(height: 24),

                        // Recommendation card: only rendered when genuine recommendation exists.
                        // Fail closed: never render mock recommendations.
                        if (topRecommendation != null &&
                            topRecommendation.isNotEmpty) ...[
                          _buildRecommendationCard(
                            context,
                            topRecommendation,
                            needsMoreData: needsMoreData,
                            faceShape: faceShape,
                          ),
                          const SizedBox(height: 24),
                        ] else ...[
                          _buildUnavailableRecommendationCard(context),
                          const SizedBox(height: 24),
                        ],

                        // Outfit observations: report genuine observations or honest empty state.
                        _buildOutfitObservationsSection(context),

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

  AppBar _buildAppBar(BuildContext context) {
    return AppBar(
      title: const Text('Outfit Analysis'),
      leading: IconButton(
        icon: const Icon(
          Icons.arrow_back_rounded,
          color: FansivibeColors.textPrimary,
        ),
        onPressed: () => Navigator.of(context).pop(),
      ),
      actions: [
        IconButton(
          icon: const Icon(
            Icons.share_outlined,
            color: FansivibeColors.textSecondary,
          ),
          onPressed: () {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: const Text('Share feature coming soon'),
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
    );
  }

  Widget _buildLoadingState(BuildContext context) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 480),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(
                width: 48,
                height: 48,
                child: CircularProgressIndicator(
                  strokeWidth: 3,
                  valueColor: AlwaysStoppedAnimation<Color>(
                    FansivibeColors.accentGold,
                  ),
                ),
              ),
              const SizedBox(height: 20),
              Text(
                'Analyzing Photo…',
                style: FansivibeTypography.titleLarge.copyWith(
                  color: FansivibeColors.textPrimary,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              Text(
                'Extracting genuine visual observations from your photo.',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildErrorState(BuildContext context, dynamic error) {
    String errorMessage = 'We couldn\'t finish this request. Please try again.';
    if (error is String && error.trim().isNotEmpty) {
      errorMessage = error.trim();
    } else if (error is Map<String, dynamic>) {
      final details = error['details'];
      if (details is Map<String, dynamic> && details['reason'] is String) {
        errorMessage = details['reason'] as String;
      } else if (error['message'] is String && (error['message'] as String).isNotEmpty) {
        errorMessage = error['message'] as String;
      }
    }

    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 480),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 64,
                height: 64,
                decoration: BoxDecoration(
                  color: FansivibeColors.error.withValues(alpha: 0.15),
                  shape: BoxShape.circle,
                ),
                child: const Icon(
                  Icons.error_outline_rounded,
                  color: FansivibeColors.error,
                  size: 32,
                ),
              ),
              const SizedBox(height: 16),
              Text(
                'Analysis Failed',
                style: FansivibeTypography.titleLarge.copyWith(
                  color: FansivibeColors.textPrimary,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              Text(
                errorMessage,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              FansiButton.secondary(
                label: 'Try Again',
                icon: Icons.refresh_rounded,
                onPressed: () => _handleRetry(context),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildAppearanceProfile(
    BuildContext context,
    Map<String, dynamic>? appearance,
    double? confidence,
    bool needsMoreData, {
    String? appearanceError,
  }) {
    final rawFaceShape = appearance?['faceShape'] as String?;
    final rawSkinTone = appearance?['skinTone'] as String?;
    final rawBodyType = appearance?['bodyType'] as String?;
    final rawStyleType = appearance?['styleType'] as String?;

    // Rule: Face shape: display detected face shape only when supported.
    // If not visible or inconclusive, display "Unable to determine from this photo".
    // Never default to round or oval.
    final faceShapeValue =
        (rawFaceShape != null && rawFaceShape.trim().isNotEmpty)
            ? rawFaceShape.trim()
            : appearanceError == 'no_face_detected'
            ? 'Not detected in this photo'
            : 'Unable to determine from this photo';

    // Rule: Skin tone: display only if explicitly supported and valid.
    // If unsupported or inconclusive, display "Not detected".
    final skinToneValue =
        (rawSkinTone != null && rawSkinTone.trim().isNotEmpty)
            ? rawSkinTone.trim()
            : 'Not detected';

    // Rule: Body type: display only if genuinely supported.
    // If insufficient evidence, display "Not enough visual information".
    final bodyTypeValue =
        (rawBodyType != null && rawBodyType.trim().isNotEmpty)
            ? rawBodyType.trim()
            : 'Not enough visual information';

    return LayoutBuilder(
      builder: (context, cardConstraints) {
        final cardPadding = cardConstraints.maxWidth < 360 ? 16.0 : 24.0;
        final maxChipWidth = (cardConstraints.maxWidth - (cardPadding * 2)).clamp(120.0, 560.0);

        return Container(
          width: double.infinity,
          padding: EdgeInsets.all(cardPadding),
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

              // Responsive attribute chips
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  _AttributeChip(
                    label: 'Face Shape',
                    value: faceShapeValue,
                    icon: Icons.face_rounded,
                    color: FansivibeColors.accentGold,
                    maxWidth: maxChipWidth,
                  ),
                  _AttributeChip(
                    label: 'Skin Tone',
                    value: skinToneValue,
                    icon: Icons.wb_sunny_outlined,
                    color: FansivibeColors.accentGold,
                    maxWidth: maxChipWidth,
                  ),
                  _AttributeChip(
                    label: 'Body Type',
                    value: bodyTypeValue,
                    icon: Icons.accessibility_new_rounded,
                    color: FansivibeColors.accentGold,
                    maxWidth: maxChipWidth,
                  ),
                  if (rawStyleType != null && rawStyleType.trim().isNotEmpty)
                    _AttributeChip(
                      label: 'Style Vibe',
                      value: rawStyleType.trim(),
                      icon: Icons.style_outlined,
                      color: FansivibeColors.accentGold,
                      maxWidth: maxChipWidth,
                    ),
                ],
              ),

              if (appearanceError != null) ...[
                const SizedBox(height: 12),
                _buildBranchFailureNote(context, appearanceError),
              ],

              const SizedBox(height: 16),

              // Confidence and status indicators in responsive alignment
              _buildConfidenceAndStatusRow(
                context,
                confidence: confidence,
                needsMoreData: needsMoreData,
                cardWidth: cardConstraints.maxWidth - (cardPadding * 2),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildConfidenceAndStatusRow(
    BuildContext context, {
    required double? confidence,
    required bool needsMoreData,
    required double cardWidth,
  }) {
    // Confidence rule: display only if meaningful confidence measure exists.
    // Do not convert missing field into 0% or an arbitrary percentage.
    final hasConfidence =
        confidence != null && confidence >= 0.0 && confidence <= 1.0;
    final confidenceLabel = hasConfidence
        ? 'Confidence: ${(confidence * 100).toInt()}%'
        : 'Confidence unavailable';

    final confidenceWidget = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(
          hasConfidence ? Icons.trending_up_rounded : Icons.help_outline_rounded,
          size: 16,
          color: hasConfidence
              ? FansivibeColors.success
              : FansivibeColors.textSecondary,
        ),
        const SizedBox(width: 6),
        Flexible(
          child: Text(
            confidenceLabel,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: FansivibeColors.textSecondary,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
      ],
    );

    final needsMoreDataBadge = needsMoreData
        ? Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
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
          )
        : null;

    final isNarrow = cardWidth < 320;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (isNarrow) ...[
          confidenceWidget,
          if (needsMoreDataBadge != null) ...[
            const SizedBox(height: 8),
            needsMoreDataBadge,
          ],
        ] else ...[
          Row(
            children: [
              Flexible(child: confidenceWidget),
              if (needsMoreDataBadge != null) ...[
                const SizedBox(width: 12),
                needsMoreDataBadge,
              ],
            ],
          ),
        ],
        if (needsMoreData) ...[
          const SizedBox(height: 8),
          Text(
            'A clearer photo may be needed for full personalized analysis.',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: FansivibeColors.textSecondary.withValues(alpha: 0.8),
              fontSize: 11,
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildUnavailableRecommendationCard(BuildContext context) {
    return LayoutBuilder(
      builder: (context, cardConstraints) {
        final cardPadding = cardConstraints.maxWidth < 360 ? 12.0 : 20.0;

        return Container(
          width: double.infinity,
          padding: EdgeInsets.all(cardPadding),
          decoration: BoxDecoration(
            color: FansivibeColors.surfaceContainerLow,
            borderRadius: FansivibeRadius.baseBorder,
            border: Border.all(
              color: FansivibeColors.outlineVariant.withValues(alpha: 0.3),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(
                    Icons.info_outline_rounded,
                    size: 20,
                    color: FansivibeColors.textSecondary,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Personalized recommendation unavailable for this photo.',
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.w600,
                        color: FansivibeColors.textPrimary,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                'The photo did not provide sufficient visual details to produce a tailored recommendation. Ensure the subject is clearly visible with good lighting, or try retaking the photo.',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: FansivibeColors.textSecondary,
                  height: 1.4,
                ),
              ),
              const SizedBox(height: 16),
              Align(
                alignment: Alignment.centerLeft,
                child: FansiButton.secondary(
                  label: 'Retry Analysis',
                  icon: Icons.refresh_rounded,
                  onPressed: () => _handleRetry(context),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildRecommendationCard(
    BuildContext context,
    Map<String, dynamic> topRecommendation, {
    required bool needsMoreData,
    required String? faceShape,
  }) {
    final name = topRecommendation['name'] as String?;
    final description = topRecommendation['description'] as String?;
    final rawReasons = topRecommendation['reasons'] as List<dynamic>?;
    final reasons = rawReasons
            ?.map((r) => r.toString())
            .where((r) => r.trim().isNotEmpty)
            .toList() ??
        const <String>[];
    final stylingTips = topRecommendation['stylingTips'] as String?;
    final maintenance = topRecommendation['maintenance'] as String?;
    final bestFor = topRecommendation['bestFor'] as String?;

    final isPersonalized =
        (faceShape != null && faceShape.trim().isNotEmpty) && !needsMoreData;

    // Filter reasons: an uncertain or missing face shape must NEVER produce a face-shape-specific claim.
    final filteredReasons = reasons.where((reason) {
      final lower = reason.toLowerCase();
      final hasFaceShapeClaim = lower.contains('face shape') ||
          lower.contains('round face') ||
          lower.contains('oval face') ||
          lower.contains('square face') ||
          lower.contains('heart face') ||
          lower.contains('diamond face') ||
          lower.contains('rectangular face');
      if (hasFaceShapeClaim) {
        if (faceShape == null || faceShape.trim().isEmpty) {
          return false;
        }
        final cleanFace = faceShape.trim().toLowerCase();
        for (final shape in [
          'round',
          'oval',
          'square',
          'heart',
          'diamond',
          'rectangular',
        ]) {
          if (lower.contains('$shape face') && cleanFace != shape) {
            return false;
          }
        }
      }
      return true;
    }).toList();

    return LayoutBuilder(
      builder: (context, cardConstraints) {
        final cardPadding = cardConstraints.maxWidth < 360 ? 12.0 : 20.0;

        return Container(
          width: double.infinity,
          padding: EdgeInsets.all(cardPadding),
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
              Wrap(
                alignment: WrapAlignment.spaceBetween,
                crossAxisAlignment: WrapCrossAlignment.center,
                spacing: 8,
                runSpacing: 6,
                children: [
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(
                        Icons.auto_awesome_rounded,
                        size: 20,
                        color: FansivibeColors.accentGold,
                      ),
                      const SizedBox(width: 8),
                      Flexible(
                        child: Text(
                          'Recommended for you',
                          style: Theme.of(context).textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.w600,
                            color: FansivibeColors.accentGold,
                          ),
                        ),
                      ),
                    ],
                  ),
                  if (!isPersonalized)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: FansivibeColors.surfaceContainerHigh,
                        borderRadius: FansivibeRadius.smBorder,
                        border: Border.all(
                          color: FansivibeColors.outlineVariant.withValues(alpha: 0.3),
                        ),
                      ),
                      child: Text(
                        'General Styling Advice',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: FansivibeColors.secondary,
                          fontSize: 10,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 12),
          Text(
            name ?? 'Recommended Look',
            style: FansivibeTypography.titleLarge.copyWith(
              color: FansivibeColors.textPrimary,
            ),
          ),
          if (description != null && description.trim().isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              description.trim(),
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: FansivibeColors.textSecondary,
                height: 1.4,
              ),
            ),
          ],

          // Note: Fabricated match score badge (such as "99% match") and
          // hardcoded compatibility claims have been removed per policy.

          const SizedBox(height: 18),

              // Section: Why it may suit you — only rendered when supported reasons exist
              if (filteredReasons.isNotEmpty) ...[
                const SizedBox(height: 18),
                Text(
                  'Why it may suit you',
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: FansivibeColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 8),
                ...filteredReasons.map(
                  (reason) => Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Padding(
                          padding: EdgeInsets.only(top: 2),
                          child: Icon(
                            Icons.check_circle_rounded,
                            size: 14,
                            color: FansivibeColors.success,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            reason,
                            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: FansivibeColors.textPrimary,
                              height: 1.3,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],

          const SizedBox(height: 16),

          // Section: Considerations
          Text(
            'Considerations',
            style: Theme.of(context).textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.w600,
              color: FansivibeColors.textPrimary,
            ),
          ),
          const SizedBox(height: 8),
          if (!isPersonalized)
            _buildConsiderationRow(
              context,
              Icons.info_outline_rounded,
              'General styling suggestion based on aesthetic principles because photo provided partial appearance data.',
            ),
          if (maintenance != null && maintenance.trim().isNotEmpty)
            _buildConsiderationRow(
              context,
              Icons.schedule_rounded,
              'Maintenance: ${maintenance.trim()}',
            ),
          if (stylingTips != null && stylingTips.trim().isNotEmpty)
            _buildConsiderationRow(
              context,
              Icons.lightbulb_outline_rounded,
              'Styling tip: ${stylingTips.trim()}',
            ),
          if (bestFor != null && bestFor.trim().isNotEmpty)
            _buildConsiderationRow(
              context,
              Icons.stars_rounded,
              'Best for: ${bestFor.trim()}',
            ),
        ],
      ),
    );
  },
);
}

  Widget _buildConsiderationRow(
    BuildContext context,
    IconData icon,
    String text,
  ) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Icon(
              icon,
              size: 14,
              color: FansivibeColors.accentGold,
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              text,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: FansivibeColors.textSecondary,
                height: 1.3,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildOutfitObservationsSection(BuildContext context) {
    final garment = analysisResult?['garment'] as Map<String, dynamic>?;
    final garmentError =
        (analysisResult?['garment_error'] as Map<String, dynamic>?)?['reason']
            as String?;
    final detectedItems = (analysisResult?['detectedItems'] ??
        analysisResult?['detected_items'] ??
        analysisResult?['items']) as List<dynamic>?;

    final hasGarmentData = garment != null && garment.isNotEmpty;
    final hasDetectedItems = detectedItems != null && detectedItems.isNotEmpty;

    return LayoutBuilder(
      builder: (context, cardConstraints) {
        final cardPadding = cardConstraints.maxWidth < 360 ? 16.0 : 20.0;

        return Container(
          width: double.infinity,
          padding: EdgeInsets.all(cardPadding),
          decoration: BoxDecoration(
            color: FansivibeColors.surfaceContainerLow,
            borderRadius: FansivibeRadius.baseBorder,
            border: Border.all(
              color: FansivibeColors.outlineVariant.withValues(alpha: 0.2),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(
                    Icons.checkroom_rounded,
                    size: 20,
                    color: FansivibeColors.accentGold,
                  ),
                  const SizedBox(width: 8),
                  Flexible(
                    child: Text(
                      'Outfit Observations',
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.w600,
                        color: FansivibeColors.textPrimary,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              if (hasGarmentData) ...[
                _buildGarmentDetails(context, garment),
              ] else if (hasDetectedItems) ...[
                _buildDetectedItemsList(context, detectedItems),
              ] else ...[
                // Honest state when no garment branch result exists.
                if (garmentError != null)
                  _buildBranchFailureNote(context, garmentError)
                else
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(
                        Icons.info_outline_rounded,
                        size: 16,
                        color: FansivibeColors.textSecondary,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Outfit observations are unavailable in this result.',
                          style: Theme.of(context).textTheme.bodySmall
                              ?.copyWith(
                                color: FansivibeColors.textSecondary,
                                height: 1.4,
                              ),
                        ),
                      ),
                    ],
                  ),
                const SizedBox(height: 8),
                Text(
                  'Visual attributes like category, color, and fit are reported only when supported by returned analysis data.',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: FansivibeColors.textSecondary.withValues(alpha: 0.6),
                    fontSize: 11,
                  ),
                ),
              ],
            ],
          ),
        );
      },
    );
  }

  Widget _buildGarmentDetails(
    BuildContext context,
    Map<String, dynamic> garment,
  ) {
    final category = garment['category'] as String?;
    final color = garment['color'] as String?;
    final pattern = garment['pattern'] as String?;
    final material = garment['material'] as String?;
    final fit = garment['fit'] as String?;
    final style = garment['style'] as String?;

    final observations = <Widget>[];
    if (category != null && category.trim().isNotEmpty) {
      observations.add(_buildObservationItem(context, 'Category', category.trim(), Icons.category_outlined));
    }
    if (color != null && color.trim().isNotEmpty) {
      observations.add(_buildObservationItem(context, 'Color', color.trim(), Icons.palette_outlined));
    }
    if (pattern != null && pattern.trim().isNotEmpty) {
      observations.add(_buildObservationItem(context, 'Pattern', pattern.trim(), Icons.layers_outlined));
    }
    if (material != null && material.trim().isNotEmpty) {
      observations.add(_buildObservationItem(context, 'Material', material.trim(), Icons.texture_outlined));
    }
    if (fit != null && fit.trim().isNotEmpty) {
      observations.add(_buildObservationItem(context, 'Fit', fit.trim(), Icons.straighten_outlined));
    }
    if (style != null && style.trim().isNotEmpty) {
      observations.add(_buildObservationItem(context, 'Style', style.trim(), Icons.style_outlined));
    }

    if (observations.isEmpty) {
      return Text(
        'Garment attributes were inconclusive from this photo.',
        style: Theme.of(context).textTheme.bodySmall?.copyWith(
          color: FansivibeColors.textSecondary,
        ),
      );
    }

    return Column(children: observations);
  }

  Widget _buildDetectedItemsList(
    BuildContext context,
    List<dynamic> items,
  ) {
    return Column(
      children: items.map((item) {
        if (item is Map<String, dynamic>) {
          final name = item['name'] as String? ?? 'Item';
          final category = item['category'] as String? ?? '';
          final color = item['color'] as String? ?? '';
          final fit = item['fit'] as String? ?? '';

          return Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(
              children: [
                const Icon(
                  Icons.checkroom_outlined,
                  size: 16,
                  color: FansivibeColors.accentGold,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '$name${category.isNotEmpty ? ' ($category)' : ''}${color.isNotEmpty ? ' • $color' : ''}${fit.isNotEmpty ? ' • $fit' : ''}',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: FansivibeColors.textPrimary,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          );
        }
        return Padding(
          padding: const EdgeInsets.only(bottom: 4),
          child: Text(
            item.toString(),
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: FansivibeColors.textPrimary,
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _buildBranchFailureNote(BuildContext context, String reason) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Icon(
          Icons.info_outline_rounded,
          size: 16,
          color: FansivibeColors.textSecondary,
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            _branchFailureText(reason),
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: FansivibeColors.textSecondary,
              height: 1.4,
            ),
          ),
        ),
      ],
    );
  }

  String _branchFailureText(String reason) {
    switch (reason) {
      case 'no_face_detected':
        return 'No face was clearly visible in this photo, so the face branch could not be completed.';
      case 'no_garment_detected':
        return 'No clear outfit was visible in this photo, so the outfit branch could not be completed.';
      case 'ambiguous_subject':
        return 'That photo was hard to read, so this observation could not be completed.';
      case 'low_confidence':
        return "The analysis wasn't confident enough in this photo, so this observation could not be completed.";
      case 'analysis_failed':
        return 'This part of the analysis could not be completed. Please try again.';
      default:
        return 'This part of the analysis could not be completed.';
    }
  }

  Widget _buildObservationItem(
    BuildContext context,
    String label,
    String value,
    IconData icon,
  ) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        children: [
          Icon(icon, size: 14, color: FansivibeColors.accentGold),
          const SizedBox(width: 8),
          Text(
            '$label: ',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: FansivibeColors.textSecondary,
              fontWeight: FontWeight.w500,
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: FansivibeColors.textPrimary,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActions(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final isNarrow = constraints.maxWidth < 360;

        final saveButton = FansiButton.secondary(
          label: 'Save Profile',
          icon: Icons.bookmark_border,
          onPressed: () {
            if (isGuestUser) {
              promptGuestSignIn(
                context,
                action: 'Sign in to save your profile. Browsing stays free.',
              );
              return;
            }
            clearPendingEphemeralResult();
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: const Text('Appearance profile saved'),
                backgroundColor: FansivibeColors.accentGold,
                behavior: SnackBarBehavior.floating,
                shape: RoundedRectangleBorder(
                  borderRadius: FansivibeRadius.smdBorder,
                ),
              ),
            );
          },
        );

        final seeRecsButton = FansiButton.primary(
          label: 'See Recommendations',
          icon: Icons.auto_awesome_rounded,
          onPressed: () {
            if (!mounted) return;
            context.pushNamed(RouteNames.dailyOutfit);
          },
        );

        if (isNarrow) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              saveButton,
              const SizedBox(height: 12),
              seeRecsButton,
            ],
          );
        }

        return Row(
          children: [
            Expanded(child: saveButton),
            const SizedBox(width: 12),
            Expanded(child: seeRecsButton),
          ],
        );
      },
    );
  }
}

class _AttributeChip extends StatelessWidget {
  const _AttributeChip({
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
    required this.maxWidth,
  });

  final String label;
  final String value;
  final IconData icon;
  final Color color;
  final double maxWidth;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: BoxConstraints(maxWidth: maxWidth),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: FansivibeRadius.smBorder,
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Icon(icon, size: 16, color: color),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              '$label: $value',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: color,
                fontWeight: FontWeight.w500,
              ),
              softWrap: true,
            ),
          ),
        ],
      ),
    );
  }
}
