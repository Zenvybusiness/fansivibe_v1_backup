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
import 'package:fansivibe/shared/utils/guest_mode.dart';

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

  /// Event chosen for outfit styling. Set immediately after creation so
  /// the new row is visibly selected, and retained while this screen
  /// lives so it survives the add → list → build navigation.
  EventItem? _selectedEvent;

  EventsRepository get _repository =>
      widget.repository ?? EventsRepositoryImpl();

  @override
  void initState() {
    super.initState();
    // Phase 2 guests never fetch: GET /v1/events 401s without a
    // session. The build below renders the sign-in prompt instead.
    if (isGuestUser) {
      _future = Future.value(null);
      return;
    }
    _future = Future.sync(() => _repository.listEvents());
  }

  void _reload() {
    if (isGuestUser) return;
    setState(() {
      _future = Future.sync(() => _repository.listEvents());
    });
  }

  Future<void> _addEvent() async {
    // Phase 2 guests: creating events is account-only — prompt at the
    // button instead of pushing into a 401-backed form.
    if (isGuestUser) {
      promptGuestSignIn(
        context,
        action: 'Sign in to plan events. Browsing stays free.',
      );
      return;
    }
    final created = await context.pushNamed<EventItem>(RouteNames.eventAdd);
    if (created != null && mounted) {
      setState(() {
        _selectedEvent = created;
      });
      _reload();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('${created.title} added and selected for styling'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  void _buildOutfitForSelected() {
    final event = _selectedEvent;
    if (event == null) return;
    context.pushNamed(
      RouteNames.buildOutfit,
      extra: <String, String>{
        'eventId': event.id,
        'eventTitle': event.title,
        'occasion': event.eventType,
      },
    );
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
                        if (_selectedEvent != null)
                          _buildSelectedBanner(context),
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
                            // Phase 2 guests: honest sign-in prompt —
                            // the list request above never fired.
                            if (isGuestUser) {
                              return const GuestSignInCard(
                                title: 'Event Planning',
                                message:
                                    'Event planning lives in your account. Sign in to plan outfits for events — browsing stays free.',
                              );
                            }
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
                                // ponytail: session expiry is handled
                                // globally via AuthSession; this retry
                                // re-issues the list request.
                                message:
                                    'Couldn\'t load your events. Please try again.',
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

  Widget _buildSelectedBanner(BuildContext context) {
    final theme = Theme.of(context);
    final event = _selectedEvent!;
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: FansivibeColors.accentGold.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: FansivibeColors.accentGold.withValues(alpha: 0.35),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  Icons.check_circle_rounded,
                  size: 16,
                  color: FansivibeColors.accentGold,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Selected for styling: ${event.title}',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: FansivibeColors.textPrimary,
                      fontWeight: FontWeight.w600,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            FansiButton.secondary(
              label: 'Build outfit for this event',
              icon: Icons.checkroom_rounded,
              onPressed: _buildOutfitForSelected,
            ),
          ],
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
