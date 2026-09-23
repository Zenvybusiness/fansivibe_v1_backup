import 'package:flutter/material.dart';

import 'package:fansivibe/features/knowledge/data/knowledge_api_models.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// Digital Atelier card displaying grounded fashion reasoning conclusions.
///
/// Follows Fansivibe design system rules:
/// - 65% visual / 35% content balance where applicable
/// - Tokens from [FansivibeColors], [FansivibeRadius], [FansivibeSpacing], [FansivibeTypography]
/// - Internal evidence IDs (`term-denim`, etc.) are NEVER exposed as primary prose
/// - Admitted conclusions, uncertainties, and missing evidence are rendered explicitly
class FashionReasoningCard extends StatelessWidget {
  const FashionReasoningCard({
    required this.response,
    this.query,
    super.key,
  });

  final FashionReasoningResponse response;
  final String? query;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // ── Primary Answer Card ──
        FansivibeCard(
          variant: CardVariant.container,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildHeader(context),
              const SizedBox(height: FansivibeSpacing.md),
              Text(
                response.answer,
                style: FansivibeTypography.bodyLargeWithFamily.copyWith(
                  color: FansivibeColors.onSurface,
                  height: 1.5,
                  fontSize: 16,
                ),
              ),
            ],
          ),
        ),

        // ── Admitted Conclusions ──
        if (response.conclusions.isNotEmpty) ...[
          const SizedBox(height: FansivibeSpacing.md),
          _buildConclusionsSection(context),
        ],

        // ── Uncertainties ──
        if (response.uncertainties.isNotEmpty) ...[
          const SizedBox(height: FansivibeSpacing.md),
          _buildUncertaintiesSection(context),
        ],

        // ── Missing Evidence ──
        if (response.missingEvidence.isNotEmpty) ...[
          const SizedBox(height: FansivibeSpacing.md),
          _buildMissingEvidenceSection(context),
        ],

        // ── Contradictions (if any) ──
        if (response.contradictions.isNotEmpty) ...[
          const SizedBox(height: FansivibeSpacing.md),
          _buildContradictionsSection(context),
        ],

        // ── Grounding & Version Footer ──
        const SizedBox(height: FansivibeSpacing.md),
        _buildVersionsFooter(context),
      ],
    );
  }

  Widget _buildHeader(BuildContext context) {
    final confidenceColor = _confidenceColor(response.confidence);

    return Row(
      children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: FansivibeColors.primary.withValues(alpha: 0.15),
            borderRadius: FansivibeRadius.smdBorder,
          ),
          child: const Icon(
            Icons.auto_awesome_rounded,
            size: 20,
            color: FansivibeColors.primary,
          ),
        ),
        const SizedBox(width: FansivibeSpacing.sm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Fashion Analysis',
                style: FansivibeTypography.titleLargeWithFamily.copyWith(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.onSurface,
                ),
              ),
              Text(
                'Ontology-grounded reasoning',
                style: FansivibeTypography.labelSmallWithFamily.copyWith(
                  color: FansivibeColors.secondary,
                ),
              ),
            ],
          ),
        ),
        _TagBadge(
          label: response.confidence.toUpperCase(),
          color: confidenceColor,
        ),
      ],
    );
  }

  Widget _buildConclusionsSection(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: FansivibeSpacing.xs,
            vertical: FansivibeSpacing.xs,
          ),
          child: Row(
            children: [
              Text(
                'Admitted Conclusions',
                style: FansivibeTypography.titleLargeWithFamily.copyWith(
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.onSurface,
                ),
              ),
              const SizedBox(width: FansivibeSpacing.sm),
              _TagBadge(
                label: '${response.conclusions.length}',
                color: FansivibeColors.primary,
              ),
            ],
          ),
        ),
        const SizedBox(height: FansivibeSpacing.xs),
        for (int i = 0; i < response.conclusions.length; i++)
          Padding(
            padding: const EdgeInsets.only(bottom: FansivibeSpacing.sm),
            child: _buildConclusionItem(context, response.conclusions[i], i + 1),
          ),
      ],
    );
  }

  Widget _buildConclusionItem(
    BuildContext context,
    ReasoningConclusion conclusion,
    int index,
  ) {
    final isSupported = conclusion.standing.toLowerCase() == 'supported';
    final standingColor = isSupported
        ? FansivibeColors.success
        : FansivibeColors.warning;

    return ClipRRect(
      borderRadius: FansivibeRadius.mdBorder,
      child: Material(
        color: FansivibeColors.surfaceContainerLow,
        child: Padding(
          padding: const EdgeInsets.all(FansivibeSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Text(
                      conclusion.statement,
                      style: FansivibeTypography.bodyLargeWithFamily.copyWith(
                        color: FansivibeColors.onSurface,
                        fontWeight: FontWeight.w500,
                        fontSize: 15,
                        height: 1.4,
                      ),
                    ),
                  ),
                  const SizedBox(width: FansivibeSpacing.sm),
                  _TagBadge(
                    label: conclusion.standing.toUpperCase(),
                    color: standingColor,
                  ),
                ],
              ),
              if (conclusion.reasoningNote.isNotEmpty) ...[
                const SizedBox(height: FansivibeSpacing.xs + 2),
                Text(
                  conclusion.reasoningNote,
                  style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.secondary,
                    fontStyle: FontStyle.italic,
                    height: 1.4,
                  ),
                ),
              ],
              const SizedBox(height: FansivibeSpacing.sm),
              // Grounding citation metadata (clean indicator; no raw ID prose)
              Row(
                children: [
                  Icon(
                    Icons.verified_outlined,
                    size: 14,
                    color: FansivibeColors.primary.withValues(alpha: 0.8),
                  ),
                  const SizedBox(width: 4),
                  Text(
                    'Grounded in verified fashion sources (${conclusion.evidenceIds.length} citations)',
                    style: FansivibeTypography.labelSmallWithFamily.copyWith(
                      color: FansivibeColors.primary.withValues(alpha: 0.9),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildUncertaintiesSection(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(FansivibeSpacing.md),
      decoration: BoxDecoration(
        color: FansivibeColors.warning.withValues(alpha: 0.08),
        borderRadius: FansivibeRadius.mdBorder,
        border: Border.all(
          color: FansivibeColors.warning.withValues(alpha: 0.25),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.warning_amber_rounded,
                size: 18,
                color: FansivibeColors.warning,
              ),
              const SizedBox(width: FansivibeSpacing.sm),
              Text(
                'Uncertainties & Considerations',
                style: FansivibeTypography.titleLargeWithFamily.copyWith(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.warning,
                ),
              ),
            ],
          ),
          const SizedBox(height: FansivibeSpacing.xs + 2),
          for (final unc in response.uncertainties)
            Padding(
              padding: const EdgeInsets.only(top: FansivibeSpacing.xs),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '• ',
                    style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                      color: FansivibeColors.warning,
                    ),
                  ),
                  Expanded(
                    child: Text(
                      unc,
                      style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                        color: FansivibeColors.onSurface,
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

  Widget _buildMissingEvidenceSection(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(FansivibeSpacing.md),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerHigh,
        borderRadius: FansivibeRadius.mdBorder,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.help_outline_rounded,
                size: 18,
                color: FansivibeColors.secondary,
              ),
              const SizedBox(width: FansivibeSpacing.sm),
              Text(
                'What is Missing from Current Sources',
                style: FansivibeTypography.titleLargeWithFamily.copyWith(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.onSurface,
                ),
              ),
            ],
          ),
          const SizedBox(height: FansivibeSpacing.xs + 2),
          for (final missing in response.missingEvidence)
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
                      missing,
                      style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                        color: FansivibeColors.secondary,
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

  Widget _buildContradictionsSection(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(FansivibeSpacing.md),
      decoration: BoxDecoration(
        color: FansivibeColors.error.withValues(alpha: 0.08),
        borderRadius: FansivibeRadius.mdBorder,
        border: Border.all(
          color: FansivibeColors.error.withValues(alpha: 0.25),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.sync_problem_rounded,
                size: 18,
                color: FansivibeColors.error,
              ),
              const SizedBox(width: FansivibeSpacing.sm),
              Text(
                'Conflicting Knowledge Points',
                style: FansivibeTypography.titleLargeWithFamily.copyWith(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.error,
                ),
              ),
            ],
          ),
          const SizedBox(height: FansivibeSpacing.xs + 2),
          for (final contradiction in response.contradictions)
            Padding(
              padding: const EdgeInsets.only(top: FansivibeSpacing.xs),
              child: Text(
                '• $contradiction',
                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                  color: FansivibeColors.onSurface,
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildVersionsFooter(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: FansivibeSpacing.xs),
      child: Text(
        'Verified Fashion Ontology v${response.versions.ffoVersion} • Reasoning Contract v${response.versions.reasoningContractVersion}',
        textAlign: TextAlign.center,
        style: FansivibeTypography.labelSmallWithFamily.copyWith(
          color: FansivibeColors.secondary.withValues(alpha: 0.6),
          letterSpacing: 0.5,
        ),
      ),
    );
  }

  static Color _confidenceColor(String confidence) {
    return switch (confidence.toLowerCase()) {
      'high' => FansivibeColors.success,
      'medium' => FansivibeColors.primary,
      'low' => FansivibeColors.warning,
      _ => FansivibeColors.secondary,
    };
  }
}

class _TagBadge extends StatelessWidget {
  const _TagBadge({
    required this.label,
    required this.color,
  });

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: FansivibeRadius.smBorder,
      ),
      child: Text(
        label,
        style: FansivibeTypography.labelSmallWithFamily.copyWith(
          color: color,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.5,
        ),
      ),
    );
  }
}
