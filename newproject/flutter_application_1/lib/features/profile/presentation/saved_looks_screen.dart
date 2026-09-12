import 'package:flutter/material.dart';
import 'package:fansivibe/features/feedback/data/feedback_client.dart';
import 'package:fansivibe/features/feedback/feedback.dart';
import 'package:fansivibe/features/profile/data/saved_looks_models.dart';
import 'package:fansivibe/features/profile/data/saved_looks_repository.dart';
import 'package:fansivibe/shared/components/fansi_badge.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/components/fansi_error_view.dart';
import 'package:fansivibe/shared/components/fansi_hero_card.dart';
import 'package:fansivibe/shared/components/fansi_image_well.dart';
import 'package:fansivibe/shared/components/fansi_loading_view.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// Saved looks collection (DEC-013, STEP 18.4; reactions M11).
///
/// The backend `GET /v1/looks/saved` collection is the single source of
/// truth. There is no local-service merge and no mock fallback: a
/// fabricated row would corrupt the delete surface. [repository] and
/// [feedbackRepository] are injectable for tests; when null the screen
/// uses the live backend implementations.
class SavedLooksScreen extends StatefulWidget {
  const SavedLooksScreen({super.key, this.repository, this.feedbackRepository});

  /// Injectable for tests; when null the screen uses the live repository.
  final SavedLooksRepository? repository;

  /// Injectable for tests; when null the screen uses the live repository.
  final FeedbackRepository? feedbackRepository;

  @override
  State<SavedLooksScreen> createState() => _SavedLooksScreenState();
}

class _SavedLooksScreenState extends State<SavedLooksScreen> {
  late final SavedLooksRepository _repository;
  late final FeedbackRepository _feedbackRepository;
  List<SavedLookItem> _looks = [];
  bool _isLoading = true;
  bool _loadFailed = false;

  /// Backend UUIDs with a delete request in flight (pending guard).
  final Set<String> _deletingIds = <String>{};

  /// Backend UUIDs with a reaction submit in flight (pending guard).
  final Set<String> _reactingIds = <String>{};

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? SavedLooksRepositoryImpl();
    _feedbackRepository = widget.feedbackRepository ?? FeedbackRepositoryImpl();
    _loadSavedLooks();
  }

  Future<void> _loadSavedLooks() async {
    final page = await _repository.listSavedLooks(page: 1, pageSize: 20);

    if (!mounted) return;

    setState(() {
      _looks = page?.items ?? <SavedLookItem>[];
      _loadFailed = page == null;
      _isLoading = false;
    });
  }

  Future<void> _retryLoad() async {
    setState(() {
      _isLoading = true;
      _loadFailed = false;
    });
    await _loadSavedLooks();
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.smdBorder),
      ),
    );
  }

  /// Submits one reaction for a saved look (M11 `#35 POST /v1/feedback`).
  ///
  /// The row's backend UUID travels as `targetSavedLookId` with a fresh
  /// key per tap; repeated taps while pending are ignored. Only an
  /// accepted backend ack shows success — failures keep the row for a
  /// truthful retry. No local signal is recorded either way.
  Future<void> _reactToLook(SavedLookItem look, String rating) async {
    if (_reactingIds.contains(look.id)) return;
    setState(() {
      _reactingIds.add(look.id);
    });

    late final FeedbackResult result;
    try {
      result = await _feedbackRepository.submitFeedback(
        rating: rating,
        targetSavedLookId: look.id,
        idempotencyKey: newFeedbackIdempotencyKey(),
      );
    } catch (_) {
      result = const FeedbackResult.failure(FeedbackStatus.unknown);
    }

    if (!mounted) return;
    setState(() {
      _reactingIds.remove(look.id);
    });

    switch (result.status) {
      case FeedbackStatus.sent:
        _showMessage('Thanks — feedback recorded');
      case FeedbackStatus.conflict:
        _showMessage('Feedback already recorded');
      case FeedbackStatus.unauthorized:
        _showMessage('Please sign in again to send feedback.');
      case FeedbackStatus.rateLimited:
        _showMessage('Too many attempts. Please wait and try again.');
      case FeedbackStatus.networkError:
        _showMessage('Couldn\'t send feedback. Please check your connection.');
      case FeedbackStatus.invalid:
      case FeedbackStatus.unknown:
        _showMessage('Couldn\'t send feedback. Please try again.');
    }
  }

  /// Deletes one saved look after an explicit confirmation.
  ///
  /// The row is removed only after the backend confirms (or reports the
  /// row already gone, in which case no successful server-delete is
  /// claimed). Failures retain the row for a truthful retry.
  Future<void> _deleteLook(SavedLookItem look) async {
    if (_deletingIds.contains(look.id)) return;

    final shouldConfirm = await showDialog<bool?>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Delete Saved Look'),
        content: Text('Are you sure you want to remove "${look.title}"?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );

    if (shouldConfirm != true || !mounted) return;

    setState(() {
      _deletingIds.add(look.id);
    });

    late final SavedLookDeleteOutcome? outcome;
    try {
      outcome = await _repository.deleteSavedLook(id: look.id);
    } catch (_) {
      outcome = null;
    }

    if (!mounted) return;
    setState(() {
      _deletingIds.remove(look.id);
    });

    if (outcome == SavedLookDeleteOutcome.deleted) {
      _showMessage('Look removed from saved looks');
      // Reload so the server remains authoritative for the list.
      await _loadSavedLooks();
    } else if (outcome == SavedLookDeleteOutcome.alreadyGone) {
      _showMessage('Look was already removed');
      await _loadSavedLooks();
    } else {
      _showMessage('Failed to delete look. Please check your connection.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Saved Looks'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxWidth = constraints.maxWidth;
            final horizontalPadding = maxWidth > 600 ? 48.0 : 20.0;
            final contentMaxWidth = maxWidth > 600 ? 520.0 : double.infinity;

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
                        Text(
                          '${_looks.length} Saved Looks',
                          style: theme.textTheme.headlineMedium?.copyWith(
                            fontWeight: FontWeight.w600,
                            color: FansivibeColors.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Your curated style collection',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: FansivibeColors.textSecondary,
                          ),
                        ),
                        const SizedBox(height: 24),
                        _buildBody(context),
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

  Widget _buildBody(BuildContext context) {
    if (_isLoading) {
      return const FansiLoadingView(message: 'Loading saved looks…');
    }
    if (_loadFailed && _looks.isEmpty) {
      return FansiErrorView(
        message: 'Couldn\'t load saved looks. Please check your connection.',
        onRetry: _retryLoad,
      );
    }
    if (_looks.isEmpty) {
      return _buildEmptyState(context);
    }
    return Column(
      children: [
        ..._looks.map(
          (look) => Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: _SavedLookCard(
              look: look,
              isDeleting: _deletingIds.contains(look.id),
              isReacting: _reactingIds.contains(look.id),
              onDelete: () => _deleteLook(look),
              onLike: () => _reactToLook(look, FeedbackRating.like),
              onDislike: () => _reactToLook(look, FeedbackRating.dislike),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildEmptyState(BuildContext context) {
    final theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: FansivibeSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.favorite_border_rounded,
              size: 48,
              color: FansivibeColors.textSecondary.withValues(alpha: 0.6),
            ),
            const SizedBox(height: FansivibeSpacing.md),
            Text(
              'No saved looks yet',
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w600,
                color: FansivibeColors.textPrimary,
              ),
            ),
            const SizedBox(height: FansivibeSpacing.sm),
            Text(
              'Looks you save will appear here.',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: FansivibeColors.textSecondary,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}

class _SavedLookCard extends StatelessWidget {
  const _SavedLookCard({
    required this.look,
    required this.onDelete,
    required this.onLike,
    required this.onDislike,
    this.isDeleting = false,
    this.isReacting = false,
  });

  final SavedLookItem look;
  final VoidCallback onDelete;
  final VoidCallback onLike;
  final VoidCallback onDislike;
  final bool isDeleting;
  final bool isReacting;

  /// Source label derived ONLY from the backend `sourceContext`.
  /// Null/unknown values render generically — the source is never inferred
  /// from titles, snapshots, or signals (DEC-010).
  String get _eyebrow {
    return switch (look.sourceContext) {
      'grooming' => 'GROOMING LOOK',
      'hairstyle' => 'HAIRSTYLE LOOK',
      'outfit' => 'OUTFIT LOOK',
      _ => 'SAVED LOOK',
    };
  }

  IconData get _icon {
    return switch (look.sourceContext) {
      'grooming' => Icons.spa_rounded,
      'hairstyle' => Icons.face_rounded,
      'outfit' => Icons.checkroom_rounded,
      _ => Icons.bookmark_border_rounded,
    };
  }

  Color get _color {
    return switch (look.sourceContext) {
      'grooming' => FansivibeColors.accentGold,
      'hairstyle' => FansivibeColors.success,
      'outfit' => FansivibeColors.accentGold,
      _ => FansivibeColors.textSecondary,
    };
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        FansiHeroCard(
          eyebrow: _eyebrow,
          image: FansiImageWell(icon: _icon, color: _color),
          badge: FansiBadge(score: _computeScore(look)),
          title: look.title.isEmpty ? 'Untitled' : look.title,
          subtitle: look.sourceRunId != null
              ? 'From run ${look.sourceRunId}'
              : null,
          footer: Padding(
            padding: const EdgeInsets.fromLTRB(
              FansivibeSpacing.lg,
              0,
              FansivibeSpacing.lg,
              FansivibeSpacing.lg,
            ),
            child: Text(
              _buildFooterText(look),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.textSecondary,
                height: 1.4,
              ),
            ),
          ),
        ),
        Align(
          alignment: Alignment.centerRight,
          child: FansiButton.tertiary(
            label: isDeleting ? 'Removing…' : 'Remove',
            onPressed: isDeleting ? null : onDelete,
          ),
        ),
        const SizedBox(height: 4),
        Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            if (isReacting)
              const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            else ...[
              IconButton(
                tooltip: 'Like',
                icon: const Icon(Icons.thumb_up_outlined, size: 20),
                color: FansivibeColors.textSecondary,
                onPressed: onLike,
              ),
              IconButton(
                tooltip: 'Dislike',
                icon: const Icon(Icons.thumb_down_outlined, size: 20),
                color: FansivibeColors.textSecondary,
                onPressed: onDislike,
              ),
            ],
          ],
        ),
      ],
    );
  }

  int _computeScore(SavedLookItem look) {
    final matchScore = look.snapshot['matchScore'] as num?;
    if (matchScore != null) {
      return (matchScore * 100).round();
    }
    return 0;
  }

  String _buildFooterText(SavedLookItem look) {
    // Outfit rows render the persisted snapshot count only — item names
    // are never resolved in this phase, and stale wardrobe references
    // never hide the row (DEC-013).
    if (look.sourceContext == 'outfit') {
      final count = look.selectedItemIds.length;
      if (count > 0) {
        return '$count ${count == 1 ? 'item' : 'items'}';
      }
      return 'Outfit saved';
    }

    final description = look.snapshot['description'] as String?;
    if (description != null && description.isNotEmpty) {
      return description;
    }
    final reasons = look.snapshot['reasons'] as List<dynamic>? ?? const [];
    if (reasons.isNotEmpty) {
      return reasons.first as String;
    }
    if (look.sourceContext == 'grooming') {
      return 'Grooming style saved';
    }
    if (look.sourceContext == 'hairstyle') {
      return 'Hairstyle saved';
    }
    return 'Saved look';
  }
}
