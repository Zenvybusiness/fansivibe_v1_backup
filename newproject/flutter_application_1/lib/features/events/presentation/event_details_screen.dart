import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/events/data/event_mock_data.dart';
import 'package:fansivibe/features/events/data/event_models.dart';
import 'package:fansivibe/features/events/data/events_repository.dart';
import 'package:fansivibe/features/outfit_builder/presentation/widgets/outfit_builder_widgets.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

/// Backend-first event details (M8-D).
///
/// Operates on the backend [EventItem] (UUID identity throughout —
/// never a stale mock object). Supports owner delete (confirm → exact
/// UUID → 204), full-replace edit (via the `eventEdit` route, which
/// pops the updated backend item), and backend outfit generation
/// rendered inline as-is: never persisted, worn, or signaled from
/// here. A 204 outfit response renders a truthful "no outfit
/// available" state instead of a fabricated recommendation.
class EventDetailsScreen extends StatefulWidget {
  /// Creates an [EventDetailsScreen] with an optional repository for
  /// testing. Without a repository, uses the live backend
  /// implementation.
  const EventDetailsScreen({required this.event, this.repository, super.key});

  /// Backend event under display (UUID identity).
  final EventItem event;

  /// Backend repository override (tests only).
  final EventsRepository? repository;

  @override
  State<EventDetailsScreen> createState() => _EventDetailsScreenState();
}

class _EventDetailsScreenState extends State<EventDetailsScreen> {
  late EventItem _event;
  bool _changed = false;
  bool _deleting = false;
  bool _generating = false;
  EventOutfitResult? _outfit;

  EventsRepository get _repository =>
      widget.repository ?? EventsRepositoryImpl();

  @override
  void initState() {
    super.initState();
    _event = widget.event;
  }

  EventType get _eventType =>
      EventType.byCodeOrNull(_event.eventType) ?? EventType.mockTypes.last;

  Future<bool> _confirmDelete() async {
    final confirmed = await showDialog<bool?>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Delete Event'),
        content: Text('Are you sure you want to remove "${_event.title}"?'),
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
    return confirmed == true;
  }

  Future<void> _deleteEvent() async {
    if (_deleting) return;
    if (!await _confirmDelete()) return;
    setState(() => _deleting = true);
    try {
      final outcome = await _repository.deleteEvent(id: _event.id);
      if (!mounted) return;
      if (outcome == EventDeleteOutcome.deleted ||
          outcome == EventDeleteOutcome.alreadyGone) {
        // Deleted or already gone server-side: the list reload drops the
        // row either way (saved-looks already-gone precedent).
        Navigator.of(context).pop<bool>(true);
      } else {
        _showMessage('Couldn\'t delete your event. Please try again.');
      }
    } finally {
      if (mounted) {
        setState(() => _deleting = false);
      }
    }
  }

  Future<void> _editEvent() async {
    final updated = await context.pushNamed<EventItem?>(
      RouteNames.eventEdit,
      extra: _event,
    );
    if (updated != null && mounted) {
      setState(() {
        _event = updated;
        _changed = true;
        // A new event version may deserve a fresh recommendation.
        _outfit = null;
      });
    }
  }

  Future<void> _generateOutfit() async {
    if (_generating) return;
    setState(() {
      _generating = true;
    });
    try {
      final result = await _repository.generateEventOutfit(id: _event.id);
      if (!mounted) return;
      if (result == null) {
        _showMessage('Couldn\'t generate an outfit. Please try again.');
        return;
      }
      setState(() {
        _outfit = result;
      });
    } finally {
      if (mounted) {
        setState(() => _generating = false);
      }
    }
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: FansivibeColors.accentGold,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.smdBorder),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Event Details'),
        leading: IconButton(
          icon: Icon(
            Icons.arrow_back_rounded,
            color: FansivibeColors.textPrimary,
          ),
          onPressed: () => Navigator.of(context).pop<bool>(_changed),
        ),
        actions: [
          IconButton(
            icon: Icon(
              Icons.delete_outline_rounded,
              color: FansivibeColors.textPrimary,
            ),
            onPressed: _deleting ? null : _deleteEvent,
            tooltip: 'Delete event',
          ),
        ],
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

                        // Event name header
                        _buildHeader(context),

                        const SizedBox(height: 28),

                        // Event info card
                        _buildInfoCard(context),

                        const SizedBox(height: 20),

                        // Action: Generate Outfit
                        _buildGenerateOutfitButton(context),

                        const SizedBox(height: 12),

                        // Action: Edit Event
                        _buildEditEventButton(context),

                        const SizedBox(height: 20),

                        // Outfit result (when requested)
                        if (_outfit != null) ...[
                          _buildOutfitSection(context),
                          const SizedBox(height: 12),
                        ],

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

  Widget _buildHeader(BuildContext context) {
    final theme = Theme.of(context);

    return Row(
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: FansivibeColors.accentGold.withValues(alpha: 0.12),
            borderRadius: FansivibeRadius.baseBorder,
          ),
          child: Icon(
            _eventType.icon,
            color: FansivibeColors.accentGold,
            size: 28,
          ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                _event.title,
                style: theme.textTheme.displayLarge?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: FansivibeColors.textPrimary,
                  fontSize: 24,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                _eventType.name,
                style: theme.textTheme.bodyLarge?.copyWith(
                  color: FansivibeColors.accentGold.withValues(alpha: 0.8),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildInfoCard(BuildContext context) {
    final rows = <Widget>[
      _infoRow(
        context,
        icon: Icons.calendar_today_outlined,
        label: 'Date',
        value: _event.displayDate,
      ),
      const SizedBox(height: 16),
      _infoRow(
        context,
        icon: Icons.access_time_rounded,
        label: 'Time',
        value: _event.displayTime ?? '—',
      ),
      const SizedBox(height: 16),
      _infoRow(
        context,
        icon: _eventType.icon,
        label: 'Type',
        value: _eventType.name,
      ),
    ];
    if (_event.location != null) {
      rows.addAll([
        const SizedBox(height: 16),
        _infoRow(
          context,
          icon: Icons.place_outlined,
          label: 'Location',
          value: _event.location!,
        ),
      ]);
    }
    if (_event.notes != null) {
      rows.addAll([
        const SizedBox(height: 16),
        _infoRow(
          context,
          icon: Icons.notes_outlined,
          label: 'Notes',
          value: _event.notes!,
        ),
      ]);
    }
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.baseBorder,
      ),
      child: Column(children: rows),
    );
  }

  Widget _infoRow(
    BuildContext context, {
    required IconData icon,
    required String label,
    required String value,
  }) {
    final theme = Theme.of(context);

    return Row(
      children: [
        Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: FansivibeColors.accentGold.withValues(alpha: 0.1),
            borderRadius: FansivibeRadius.smdBorder,
          ),
          child: Icon(icon, size: 18, color: FansivibeColors.accentGold),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: FansivibeColors.textSecondary,
                  fontSize: 12,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                value,
                style: theme.textTheme.bodyLarge?.copyWith(
                  fontWeight: FontWeight.w500,
                  color: FansivibeColors.textPrimary,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildGenerateOutfitButton(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: FansiButton.primary(
        label: _generating ? 'Generating…' : 'Generate Outfit',
        icon: Icons.auto_awesome_rounded,
        onPressed: _generating ? null : _generateOutfit,
      ),
    );
  }

  Widget _buildEditEventButton(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: FansiButton.secondary(
        label: 'Edit Event',
        icon: Icons.edit_outlined,
        onPressed: _editEvent,
      ),
    );
  }

  Widget _buildOutfitSection(BuildContext context) {
    final theme = Theme.of(context);
    final result = _outfit!;

    if (!result.available || result.outfit == null) {
      return FansivibeCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'No outfit available',
              style: theme.textTheme.bodyLarge?.copyWith(
                fontWeight: FontWeight.w600,
                color: FansivibeColors.textPrimary,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              'Add more pieces to your wardrobe and try again.',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: FansivibeColors.textSecondary,
              ),
            ),
          ],
        ),
      );
    }

    final outfit = result.outfit!;
    return FansivibeCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            outfit.title,
            style: theme.textTheme.bodyLarge?.copyWith(
              fontWeight: FontWeight.w600,
              color: FansivibeColors.textPrimary,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            'Picked for your ${outfit.selectedOccasion} occasion',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: FansivibeColors.textSecondary,
            ),
          ),
          const SizedBox(height: 16),
          Center(
            child: ScoreCircle(
              score: outfit.matchScore.clamp(0.0, 1.0),
              label: 'Match Score',
            ),
          ),
          const SizedBox(height: 16),
          ...outfit.components.map(
            (component) => Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                children: [
                  Icon(
                    Icons.checkroom_rounded,
                    size: 16,
                    color: FansivibeColors.accentGold,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          component.name,
                          style: theme.textTheme.bodyMedium?.copyWith(
                            fontWeight: FontWeight.w600,
                            color: FansivibeColors.textPrimary,
                          ),
                        ),
                        Text(
                          '${component.category} \u2022 ${component.color}',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: FansivibeColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 8),
          ...outfit.reasons.map(
            (reason) => Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '\u2022 ',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: FansivibeColors.accentGold,
                    ),
                  ),
                  Expanded(
                    child: Text(
                      reason,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: FansivibeColors.textSecondary,
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
}
