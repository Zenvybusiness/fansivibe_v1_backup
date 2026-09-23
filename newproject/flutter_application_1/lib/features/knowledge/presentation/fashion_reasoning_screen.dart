import 'package:flutter/material.dart';

import 'package:fansivibe/features/knowledge/data/knowledge_repository.dart';
import 'package:fansivibe/features/knowledge/presentation/view_models/fashion_reasoning_view_model.dart';
import 'package:fansivibe/features/knowledge/presentation/widgets/fashion_reasoning_view.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// Screen for interactive fashion reasoning grounded in the FFO knowledge corpus.
class FashionReasoningScreen extends StatefulWidget {
  const FashionReasoningScreen({
    this.initialQuery,
    this.viewModel,
    this.repository,
    super.key,
  });

  /// Optional query to execute automatically upon opening.
  final String? initialQuery;

  /// Injectable ViewModel for testing.
  final FashionReasoningViewModel? viewModel;

  /// Injectable Repository for testing.
  final KnowledgeRepository? repository;

  @override
  State<FashionReasoningScreen> createState() => _FashionReasoningScreenState();
}

class _FashionReasoningScreenState extends State<FashionReasoningScreen> {
  final TextEditingController _inputController = TextEditingController();
  late final FashionReasoningViewModel _viewModel;
  late final bool _ownsViewModel;

  @override
  void initState() {
    super.initState();
    _ownsViewModel = widget.viewModel == null;
    _viewModel =
        widget.viewModel ??
        FashionReasoningViewModel(repository: widget.repository);

    if (widget.initialQuery != null && widget.initialQuery!.trim().isNotEmpty) {
      _inputController.text = widget.initialQuery!.trim();
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _viewModel.queryReasoning(widget.initialQuery!.trim());
      });
    }
  }

  @override
  void dispose() {
    _inputController.dispose();
    if (_ownsViewModel) {
      _viewModel.dispose();
    }
    super.dispose();
  }

  void _submit() {
    final text = _inputController.text.trim();
    if (text.isEmpty) return;
    _viewModel.queryReasoning(text);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: FansivibeColors.surface,
      appBar: AppBar(
        backgroundColor: FansivibeColors.surface,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded),
          color: FansivibeColors.onSurface,
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Fashion Reasoning',
              style: FansivibeTypography.bodyLargeWithFamily.copyWith(
                color: FansivibeColors.onSurface,
                fontWeight: FontWeight.w700,
                fontSize: 18,
              ),
            ),
            Text(
              'Grounded in verified fashion ontology',
              style: FansivibeTypography.labelSmallWithFamily.copyWith(
                color: FansivibeColors.secondary,
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.restart_alt_rounded),
            color: FansivibeColors.secondary,
            tooltip: 'Reset',
            onPressed: () {
              _inputController.clear();
              _viewModel.reset();
            },
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: ListenableBuilder(
                listenable: _viewModel,
                builder: (context, _) {
                  return FashionReasoningView(
                    state: _viewModel.state,
                    onSelectSampleQuery: (q) {
                      _inputController.text = q;
                      _viewModel.queryReasoning(q);
                    },
                    onRetry: () => _viewModel.retry(),
                  );
                },
              ),
            ),
            _buildInputBar(),
          ],
        ),
      ),
    );
  }

  Widget _buildInputBar() {
    return Container(
      padding: const EdgeInsets.fromLTRB(
        FansivibeSpacing.md,
        FansivibeSpacing.sm,
        FansivibeSpacing.md,
        FansivibeSpacing.sm + 4,
      ),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: const BorderRadius.vertical(
          top: Radius.circular(FansivibeRadius.lg),
        ),
      ),
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _inputController,
                textInputAction: TextInputAction.search,
                onSubmitted: (_) => _submit(),
                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                  color: FansivibeColors.onSurface,
                ),
                decoration: InputDecoration(
                  hintText: 'Ask about garments, styles, or textiles…',
                  hintStyle: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.secondary.withValues(alpha: 0.6),
                  ),
                  filled: true,
                  fillColor: FansivibeColors.surfaceContainerHigh,
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: FansivibeSpacing.md,
                    vertical: 12,
                  ),
                  border: OutlineInputBorder(
                    borderRadius: FansivibeRadius.fullBorder,
                    borderSide: BorderSide.none,
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: FansivibeRadius.fullBorder,
                    borderSide: BorderSide(
                      color: FansivibeColors.primary.withValues(alpha: 0.6),
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(width: FansivibeSpacing.sm),
            ListenableBuilder(
              listenable: _viewModel,
              builder: (context, _) {
                final isLoading = _viewModel.state.isLoading;
                return IconButton.filled(
                  onPressed: isLoading ? null : _submit,
                  icon: const Icon(Icons.arrow_upward_rounded, size: 20),
                  style: IconButton.styleFrom(
                    backgroundColor: FansivibeColors.primary,
                    foregroundColor: FansivibeColors.onPrimary,
                    disabledBackgroundColor:
                        FansivibeColors.surfaceContainerHigh,
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}
