import 'package:flutter/material.dart';

import 'package:fansivibe/features/knowledge/presentation/models/fashion_reasoning_state.dart';
import 'package:fansivibe/features/knowledge/presentation/widgets/fashion_reasoning_card.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/components/fansi_chip.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// Full-state presentation view for fashion ontology reasoning.
///
/// Handles idle, loading, success, unsupported, insufficient evidence,
/// and distinct technical failure states with fail-closed integrity.
class FashionReasoningView extends StatelessWidget {
  const FashionReasoningView({
    required this.state,
    this.onSelectSampleQuery,
    this.onRetry,
    super.key,
  });

  final FashionReasoningState state;
  final ValueChanged<String>? onSelectSampleQuery;
  final VoidCallback? onRetry;

  static const List<String> sampleQueries = [
    'what is denim',
    'cotton vs linen',
    'white sneakers',
    'kimono sizing',
    'current price of white sneakers',
  ];

  @override
  Widget build(BuildContext context) {
    return switch (state.status) {
      FashionReasoningStatus.idle => _buildIdleView(context),
      FashionReasoningStatus.loading => _buildLoadingView(context),
      FashionReasoningStatus.success => _buildSuccessView(context),
      FashionReasoningStatus.unsupported => _buildUnsupportedView(context),
      FashionReasoningStatus.insufficientEvidence =>
        _buildInsufficientEvidenceView(context),
      FashionReasoningStatus.aiUnavailable => _buildErrorView(
        context,
        icon: Icons.cloud_off_rounded,
        title: 'AI Service Unavailable',
        message:
            state.errorMessage ??
            'The fashion reasoning service is temporarily unavailable. Please try again shortly.',
      ),
      FashionReasoningStatus.timeout => _buildErrorView(
        context,
        icon: Icons.timer_outlined,
        title: 'Request Timed Out',
        message:
            state.errorMessage ??
            'The reasoning request timed out while analyzing fashion sources. Please try again.',
      ),
      FashionReasoningStatus.malformedInvalidResponse => _buildErrorView(
        context,
        icon: Icons.rule_folder_outlined,
        title: 'Response Validation Failed',
        message:
            state.errorMessage ??
            'The reasoning response could not be validated against the fashion knowledge contract.',
      ),
      FashionReasoningStatus.contractViolation => _buildErrorView(
        context,
        icon: Icons.gavel_rounded,
        title: 'Contract Violation',
        message:
            state.errorMessage ??
            'The request could not be processed due to contract constraints.',
      ),
      FashionReasoningStatus.apiNetworkError => _buildErrorView(
        context,
        icon: Icons.wifi_off_rounded,
        title: 'Network Unreachable',
        message:
            state.errorMessage ??
            'Unable to reach the reasoning service. Please check your network connection.',
      ),
      FashionReasoningStatus.unexpectedError => _buildErrorView(
        context,
        icon: Icons.error_outline_rounded,
        title: 'Unexpected Error',
        message:
            state.errorMessage ??
            'An unexpected reasoning service error occurred. Please try again later.',
      ),
    };
  }

  Widget _buildIdleView(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(FansivibeSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          FansivibeCard(
            variant: CardVariant.container,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: FansivibeColors.primary.withValues(alpha: 0.15),
                        borderRadius: FansivibeRadius.smdBorder,
                      ),
                      child: const Icon(
                        Icons.psychology_rounded,
                        color: FansivibeColors.primary,
                        size: 22,
                      ),
                    ),
                    const SizedBox(width: FansivibeSpacing.sm),
                    Expanded(
                      child: Text(
                        'Verified Fashion Reasoning',
                        style: FansivibeTypography.titleLargeWithFamily.copyWith(
                          fontSize: 17,
                          fontWeight: FontWeight.w600,
                          color: FansivibeColors.onSurface,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: FansivibeSpacing.sm),
                Text(
                  'Query our fashion ontology to receive verified reasoning about '
                  'garment taxonomies, textile attributes, styling principles, and cross-piece relationships.',
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.secondary,
                    height: 1.5,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: FansivibeSpacing.lg),
          Text(
            'Explore Suggested Questions',
            style: FansivibeTypography.titleLargeWithFamily.copyWith(
              fontSize: 15,
              fontWeight: FontWeight.w600,
              color: FansivibeColors.onSurface,
            ),
          ),
          const SizedBox(height: FansivibeSpacing.sm),
          Wrap(
            spacing: FansivibeSpacing.sm,
            runSpacing: FansivibeSpacing.sm,
            children: [
              for (final q in sampleQueries)
                FansiChip(
                  label: q,
                  selected: false,
                  onTap: () => onSelectSampleQuery?.call(q),
                ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildLoadingView(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(FansivibeSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                color: FansivibeColors.primary.withValues(alpha: 0.12),
                shape: BoxShape.circle,
              ),
              child: const Center(
                child: SizedBox(
                  width: 30,
                  height: 30,
                  child: CircularProgressIndicator(
                    strokeWidth: 2.5,
                    valueColor: AlwaysStoppedAnimation<Color>(
                      FansivibeColors.primary,
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(height: FansivibeSpacing.lg),
            Text(
              'Analyzing Fashion Knowledge',
              style: FansivibeTypography.titleLargeWithFamily.copyWith(
                fontSize: 18,
                fontWeight: FontWeight.w600,
                color: FansivibeColors.onSurface,
              ),
            ),
            const SizedBox(height: FansivibeSpacing.xs + 2),
            Text(
              'Evaluating ontology evidence, styling rules & relationships…',
              textAlign: TextAlign.center,
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.secondary,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSuccessView(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(FansivibeSpacing.md),
      child: FashionReasoningCard(
        response: state.response!,
        query: state.query,
      ),
    );
  }

  Widget _buildUnsupportedView(BuildContext context) {
    final resp = state.response;
    final message = resp?.answer.isNotEmpty == true
        ? resp!.answer
        : 'This information is not available from the current fashion knowledge sources.';

    return SingleChildScrollView(
      padding: const EdgeInsets.all(FansivibeSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            padding: const EdgeInsets.all(FansivibeSpacing.lg),
            decoration: BoxDecoration(
              color: FansivibeColors.surfaceContainer,
              borderRadius: FansivibeRadius.mdBorder,
              border: Border.all(
                color: FansivibeColors.secondary.withValues(alpha: 0.2),
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: FansivibeColors.secondary.withValues(alpha: 0.15),
                        borderRadius: FansivibeRadius.smdBorder,
                      ),
                      child: const Icon(
                        Icons.explore_off_rounded,
                        color: FansivibeColors.secondary,
                        size: 22,
                      ),
                    ),
                    const SizedBox(width: FansivibeSpacing.sm),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Outside Knowledge Scope',
                            style: FansivibeTypography.titleLargeWithFamily.copyWith(
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                              color: FansivibeColors.onSurface,
                            ),
                          ),
                          Text(
                            'Unsupported query domain',
                            style: FansivibeTypography.labelSmallWithFamily.copyWith(
                              color: FansivibeColors.secondary,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: FansivibeSpacing.md),
                Text(
                  message,
                  style: FansivibeTypography.bodyLargeWithFamily.copyWith(
                    color: FansivibeColors.onSurface,
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: FansivibeSpacing.sm),
                Text(
                  'The fashion ontology focuses on verified garment definitions, styling compatibility, '
                  'and textile characteristics. Real-time pricing, commercial inventory, or speculative trends '
                  'are not represented in the verified corpus.',
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.secondary,
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
          if (resp != null && resp.missingEvidence.isNotEmpty) ...[
            const SizedBox(height: FansivibeSpacing.md),
            _buildMissingEvidenceCard(context, resp.missingEvidence),
          ],
        ],
      ),
    );
  }

  Widget _buildInsufficientEvidenceView(BuildContext context) {
    final resp = state.response;
    final message = resp?.answer.isNotEmpty == true
        ? resp!.answer
        : 'The fashion knowledge sources do not contain enough verified evidence to draw conclusions.';

    return SingleChildScrollView(
      padding: const EdgeInsets.all(FansivibeSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            padding: const EdgeInsets.all(FansivibeSpacing.lg),
            decoration: BoxDecoration(
              color: FansivibeColors.surfaceContainer,
              borderRadius: FansivibeRadius.mdBorder,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: FansivibeColors.warning.withValues(alpha: 0.15),
                        borderRadius: FansivibeRadius.smdBorder,
                      ),
                      child: const Icon(
                        Icons.fact_check_outlined,
                        color: FansivibeColors.warning,
                        size: 22,
                      ),
                    ),
                    const SizedBox(width: FansivibeSpacing.sm),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Insufficient Evidence',
                            style: FansivibeTypography.titleLargeWithFamily.copyWith(
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                              color: FansivibeColors.onSurface,
                            ),
                          ),
                          Text(
                            'No verified conclusions admitted',
                            style: FansivibeTypography.labelSmallWithFamily.copyWith(
                              color: FansivibeColors.secondary,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: FansivibeSpacing.md),
                Text(
                  message,
                  style: FansivibeTypography.bodyLargeWithFamily.copyWith(
                    color: FansivibeColors.onSurface,
                    height: 1.5,
                  ),
                ),
              ],
            ),
          ),
          if (resp != null && resp.missingEvidence.isNotEmpty) ...[
            const SizedBox(height: FansivibeSpacing.md),
            _buildMissingEvidenceCard(context, resp.missingEvidence),
          ],
        ],
      ),
    );
  }

  Widget _buildMissingEvidenceCard(
    BuildContext context,
    List<String> missingEvidence,
  ) {
    return Container(
      padding: const EdgeInsets.all(FansivibeSpacing.md),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.mdBorder,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Missing Evidence Required',
            style: FansivibeTypography.titleLargeWithFamily.copyWith(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              color: FansivibeColors.onSurface,
            ),
          ),
          const SizedBox(height: FansivibeSpacing.xs),
          for (final item in missingEvidence)
            Padding(
              padding: const EdgeInsets.only(top: FansivibeSpacing.xs),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '• ',
                    style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                      color: FansivibeColors.secondary,
                    ),
                  ),
                  Expanded(
                    child: Text(
                      item,
                      style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                        color: FansivibeColors.secondary,
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

  Widget _buildErrorView(
    BuildContext context, {
    required IconData icon,
    required String title,
    required String message,
  }) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(FansivibeSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                color: FansivibeColors.error.withValues(alpha: 0.12),
                shape: BoxShape.circle,
              ),
              child: Icon(
                icon,
                size: 28,
                color: FansivibeColors.error.withValues(alpha: 0.8),
              ),
            ),
            const SizedBox(height: FansivibeSpacing.md),
            Text(
              title,
              style: FansivibeTypography.titleLargeWithFamily.copyWith(
                fontSize: 17,
                fontWeight: FontWeight.w600,
                color: FansivibeColors.onSurface,
              ),
            ),
            const SizedBox(height: FansivibeSpacing.xs + 2),
            Text(
              message,
              textAlign: TextAlign.center,
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.secondary,
                height: 1.4,
              ),
            ),
            if (onRetry != null) ...[
              const SizedBox(height: FansivibeSpacing.lg),
              FansiButton.secondary(
                label: 'Try Again',
                icon: Icons.refresh_rounded,
                onPressed: onRetry,
                expanded: false,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
