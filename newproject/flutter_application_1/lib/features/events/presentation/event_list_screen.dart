import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/events/data/event_models.dart';
import 'package:fansivibe/features/events/data/events_repository.dart';
import 'package:fansivibe/features/events/presentation/widgets/events_widgets.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/components/fansi_error_view.dart';
import 'package:fansivibe/shared/components/fansi_loading_view.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

/// Backend-first event list (M8-D).
///
/// The backend `/v1/events` collection is the single source of truth:
/// no mock fallback, no fake local creation, no local numeric IDs. A
/// null page means the backend is unavailable — the screen shows a
/// truthful error with a retry instead of fabricated rows.
class EventListScreen extends StatefulWidget {
  /// Creates an [EventListScreen] with an optional repository for testing.
  /// Without a repository, uses the live backend implementation.
  const EventListScreen({this.repository, super.key});

  /// Backend repository override (tests only).
  final EventsRepository? repository;

  @override
  State<EventListScreen> createState() => _EventListScreenState();
}

class _EventListScreenState extends State<EventListScreen> {
  late Future<EventListPage?> _future;

  EventsRepository get _repository =>
      widget.repository ?? EventsRepositoryImpl();

  @override
  void initState() {
    super.initState();
    _future = Future.sync(() => _repository.listEvents());
  }

  void _reload() {
    setState(() {
      _future = Future.sync(() => _repository.listEvents());
    });
  }

  Future<void> _addEvent() async {
    final created = await context.pushNamed<bool>(RouteNames.eventAdd);
    if (created == true && mounted) {
      _reload();
    }
  }

  Future<void> _openEvent(EventItem event) async {
    final changed = await context.pushNamed<bool>(
      RouteNames.eventDetails,
      extra: event,
    );
    if (changed == true && mounted) {
      _reload();
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('My Events'),
        leading: IconButton(
          icon: Icon(
            Icons.arrow_back_rounded,
            color: FansivibeColors.textPrimary,
          ),
          onPressed: () => Navigator.of(context).pop(),
        ),
        actions: [
          IconButton(
            icon: Icon(Icons.add_rounded, color: FansivibeColors.accentGold),
            onPressed: _addEvent,
            tooltip: 'Add Event',
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
                        Text(
                          'Upcoming Events',
                          style: theme.textTheme.displayLarge?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: FansivibeColors.textPrimary,
                            fontSize: 28,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Plan outfits for your events',
                          style: theme.textTheme.bodyLarge?.copyWith(
                            color: FansivibeColors.textSecondary,
                          ),
                        ),
                        const SizedBox(height: 28),
                        Padding(
                          padding: const EdgeInsets.only(bottom: 20),
                          child: FansiButton.primary(
                            label: 'Add event',
                            icon: Icons.add_rounded,
                            onPressed: _addEvent,
                          ),
                        ),
                        FutureBuilder<EventListPage?>(
                          future: _future,
                          builder: (context, snapshot) {
                            if (snapshot.connectionState ==
                                ConnectionState.waiting) {
                              return const Padding(
                                padding: EdgeInsets.symmetric(vertical: 60),
                                child: FansiLoadingView(
                                  message: 'Loading your events…',
                                ),
                              );
                            }
                            final page = snapshot.data;
                            if (!snapshot.hasData || page == null) {
                              return FansiErrorView(
                                message:
                                    'Couldn\'t load your events. Check your connection and try again.',
                                onRetry: _reload,
                              );
                            }
                            if (page.isEmpty) {
                              return _buildEmptyState(context);
                            }
                            return Column(
                              children: [
                                ...page.items.map(
                                  (event) => Padding(
                                    padding: const EdgeInsets.only(bottom: 12),
                                    child: EventCard(
                                      event: event,
                                      onTap: () => _openEvent(event),
                                    ),
                                  ),
                                ),
                              ],
                            );
                          },
                        ),
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

  Widget _buildEmptyState(BuildContext context) {
    final theme = Theme.of(context);

    return SizedBox(
      width: double.infinity,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 60),
        child: Column(
          children: [
            Icon(
              Icons.event_busy_outlined,
              size: 64,
              color: FansivibeColors.textSecondary.withValues(alpha: 0.4),
            ),
            const SizedBox(height: 16),
            Text(
              'No events yet',
              style: theme.textTheme.headlineMedium?.copyWith(
                color: FansivibeColors.textPrimary,
                fontSize: 20,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Tap + to add your first event',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: FansivibeColors.textSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
