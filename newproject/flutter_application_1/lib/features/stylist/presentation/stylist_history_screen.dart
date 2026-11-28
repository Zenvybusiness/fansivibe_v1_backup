import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_models.dart';
import 'package:fansivibe/features/hairstyle/domain/hairstyle_service.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

class StylistHistoryScreen extends StatefulWidget {
  const StylistHistoryScreen({this.service, super.key});

  final HairstyleService? service;

  @override
  State<StylistHistoryScreen> createState() => _StylistHistoryScreenState();
}

class _StylistHistoryScreenState extends State<StylistHistoryScreen> {
  late final HairstyleService _service;
  late final Future<List<AnalysisRun>> _runsFuture;

  @override
  void initState() {
    super.initState();
    _service = widget.service ?? HairstyleService();
    _runsFuture = isGuestUser
        ? Future<List<AnalysisRun>>.value(const [])
        : _service.listRuns();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Analysis History'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final horizontalPadding = constraints.maxWidth > 600 ? 48.0 : 20.0;

            return FutureBuilder<List<AnalysisRun>>(
              future: _runsFuture,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const Center(
                    child: CircularProgressIndicator(
                      color: FansivibeColors.accentGold,
                    ),
                  );
                }
                if (snapshot.hasError) {
                  return Center(
                    child: Padding(
                      padding: EdgeInsets.symmetric(
                        horizontal: horizontalPadding,
                      ),
                      child: Text(
                        'Couldn’t load your analysis history. Try again later.',
                        textAlign: TextAlign.center,
                        style: FansivibeTypography.bodyMediumWithFamily
                            .copyWith(color: FansivibeColors.textSecondary),
                      ),
                    ),
                  );
                }
                final runs = snapshot.data ?? const <AnalysisRun>[];
                if (runs.isEmpty) {
                  return Center(
                    child: Padding(
                      padding: EdgeInsets.symmetric(
                        horizontal: horizontalPadding,
                      ),
                      child: Text(
                        isGuestUser
                            ? 'Sign in to view your saved analyses.'
                            : 'No analyses yet. Your completed analyses will appear here.',
                        textAlign: TextAlign.center,
                        style: FansivibeTypography.bodyMediumWithFamily
                            .copyWith(color: FansivibeColors.textSecondary),
                      ),
                    ),
                  );
                }

                return ListView.separated(
                  padding: EdgeInsets.symmetric(
                    horizontal: horizontalPadding,
                    vertical: FansivibeSpacing.md,
                  ),
                  itemCount: runs.length,
                  separatorBuilder: (_, __) =>
                      const SizedBox(height: FansivibeSpacing.sm),
                  itemBuilder: (context, index) {
                    final run = runs[index];
                    return Semantics(
                      button: true,
                      label: 'Open analysis ${_titleFor(run.runType)}',
                      child: InkWell(
                        key: Key('analysis_run_${run.runId}'),
                        onTap: () => context.pushNamed(
                          RouteNames.analysisHistoryDetail,
                          extra: run.runId,
                        ),
                        borderRadius: FansivibeRadius.baseBorder,
                        child: Container(
                          width: double.infinity,
                          padding: const EdgeInsets.all(FansivibeSpacing.md),
                          decoration: BoxDecoration(
                            color: FansivibeColors.surfaceContainerLow,
                            borderRadius: FansivibeRadius.baseBorder,
                            border: Border.all(
                              color: Colors.white.withValues(alpha: 0.08),
                            ),
                          ),
                          child: Row(
                            children: [
                              Icon(
                                _iconFor(run.runType),
                                color: FansivibeColors.accentGold,
                                size: 22,
                              ),
                              const SizedBox(width: FansivibeSpacing.md),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      _titleFor(run.runType),
                                      style: FansivibeTypography
                                          .titleLargeWithFamily
                                          .copyWith(
                                            color: FansivibeColors.onSurface,
                                          ),
                                    ),
                                    const SizedBox(height: FansivibeSpacing.xs),
                                    Text(
                                      '${_statusFor(run)} · ${_dateFor(run.createdAt)}',
                                      style: FansivibeTypography
                                          .bodyMediumWithFamily
                                          .copyWith(
                                            color: FansivibeColors.secondary,
                                          ),
                                    ),
                                  ],
                                ),
                              ),
                              const Icon(
                                Icons.chevron_right_rounded,
                                color: FansivibeColors.secondary,
                              ),
                            ],
                          ),
                        ),
                      ),
                    );
                  },
                );
              },
            );
          },
        ),
      ),
    );
  }

  String _titleFor(String runType) {
    switch (runType) {
      case 'hairstyle':
        return 'Hairstyle analysis';
      case 'grooming':
        return 'Grooming analysis';
      case 'outfit_scan':
        return 'Outfit scan';
      default:
        return runType.replaceAll('_', ' ');
    }
  }

  IconData _iconFor(String runType) {
    switch (runType) {
      case 'hairstyle':
        return Icons.content_cut_rounded;
      case 'grooming':
        return Icons.face_retouching_natural_outlined;
      default:
        return Icons.checkroom_outlined;
    }
  }

  String _statusFor(AnalysisRun run) =>
      run.status.replaceAll('_', ' ').toUpperCase();

  String _dateFor(DateTime? date) => date == null
      ? 'Date unavailable'
      : date.toLocal().toString().split('.').first;
}

class StylistHistoryDetailScreen extends StatefulWidget {
  const StylistHistoryDetailScreen({
    required this.runId,
    this.service,
    super.key,
  });

  final String runId;
  final HairstyleService? service;

  @override
  State<StylistHistoryDetailScreen> createState() =>
      _StylistHistoryDetailScreenState();
}

class _StylistHistoryDetailScreenState
    extends State<StylistHistoryDetailScreen> {
  late final HairstyleService _service;
  late final Future<AnalysisRun?> _runFuture;

  @override
  void initState() {
    super.initState();
    _service = widget.service ?? HairstyleService();
    _runFuture = isGuestUser
        ? Future<AnalysisRun?>.value(null)
        : _service.getRun(widget.runId);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Analysis Detail'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: SafeArea(
        child: FutureBuilder<AnalysisRun?>(
          future: _runFuture,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Center(
                child: CircularProgressIndicator(
                  color: FansivibeColors.accentGold,
                ),
              );
            }
            final run = snapshot.data;
            if (run == null) {
              return Center(
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: FansivibeSpacing.xl,
                  ),
                  child: Text(
                    'This analysis is unavailable right now.',
                    textAlign: TextAlign.center,
                    style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                      color: FansivibeColors.secondary,
                    ),
                  ),
                ),
              );
            }

            return SingleChildScrollView(
              padding: const EdgeInsets.all(FansivibeSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _metaCard(run),
                  const SizedBox(height: FansivibeSpacing.md),
                  if (run.isFailed && run.error != null) ...[
                    _section('Error', [
                      _valueRow('message', run.error!['message']),
                    ]),
                    const SizedBox(height: FansivibeSpacing.md),
                  ],
                  if (run.result != null)
                    _section('Result', _entries(run.result!)),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _metaCard(AnalysisRun run) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(FansivibeSpacing.md),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.baseBorder,
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            run.runType.replaceAll('_', ' ').toUpperCase(),
            style: FansivibeTypography.titleLargeWithFamily.copyWith(
              color: FansivibeColors.onSurface,
            ),
          ),
          const SizedBox(height: FansivibeSpacing.sm),
          _valueRow('status', run.status),
          _valueRow('created', run.createdAt?.toLocal().toString() ?? '—'),
          _valueRow('completed', run.completedAt?.toLocal().toString() ?? '—'),
        ],
      ),
    );
  }

  Widget _section(String title, List<Widget> rows) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: FansivibeTypography.titleLargeWithFamily.copyWith(
            color: FansivibeColors.accentGold,
          ),
        ),
        const SizedBox(height: FansivibeSpacing.sm),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(FansivibeSpacing.md),
          decoration: BoxDecoration(
            color: FansivibeColors.surfaceContainerLow,
            borderRadius: FansivibeRadius.baseBorder,
            border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: rows.isEmpty
                ? [
                    Text(
                      'No details available.',
                      style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                        color: FansivibeColors.secondary,
                      ),
                    ),
                  ]
                : rows,
          ),
        ),
      ],
    );
  }

  List<Widget> _entries(Map<String, dynamic> result) => [
    for (final entry in result.entries) _valueRow(entry.key, entry.value),
  ];

  Widget _valueRow(String label, Object? value) {
    final rendered = value == null
        ? '—'
        : value is Map || value is List
        ? jsonEncode(value)
        : value.toString();

    return Padding(
      padding: const EdgeInsets.only(bottom: FansivibeSpacing.sm),
      child: RichText(
        text: TextSpan(
          children: [
            TextSpan(
              text: '$label: ',
              style: FansivibeTypography.labelSmallWithFamily.copyWith(
                color: FansivibeColors.secondary,
              ),
            ),
            TextSpan(
              text: rendered,
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.onSurface,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
