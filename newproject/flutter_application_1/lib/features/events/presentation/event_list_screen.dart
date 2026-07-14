import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/events/data/event_mock_data.dart';
import 'package:fansivibe/features/events/presentation/widgets/events_widgets.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class EventListScreen extends StatefulWidget {
  const EventListScreen({super.key});

  @override
  State<EventListScreen> createState() => _EventListScreenState();
}

class _EventListScreenState extends State<EventListScreen> {
  final List<UserEvent> _events = List<UserEvent>.from(UserEvent.mockEvents);

  Future<void> _addEvent() async {
    final newEvent = await context.pushNamed<UserEvent>(RouteNames.eventAdd);
    if (newEvent != null && mounted) {
      setState(() => _events.add(newEvent));
    }
  }

  void _openEvent(UserEvent event) {
    context.pushNamed(RouteNames.eventDetails, extra: event);
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
                        if (_events.isEmpty)
                          _buildEmptyState(context)
                        else
                          ..._events.map(
                            (event) => Padding(
                              padding: const EdgeInsets.only(bottom: 12),
                              child: EventCard(
                                event: event,
                                onTap: () => _openEvent(event),
                              ),
                            ),
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
