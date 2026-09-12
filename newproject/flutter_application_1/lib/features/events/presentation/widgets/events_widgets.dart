import 'package:flutter/material.dart';
import 'package:fansivibe/features/events/data/event_mock_data.dart';
import 'package:fansivibe/features/events/data/event_models.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

/// Backend-first event card (M8-D).
///
/// Renders one [EventItem] from the backend collection. The type icon and
/// label resolve from the frozen code table with an `other` fallback —
/// unknown codes never crash the list. The previous local
/// Ready/Pending badge is gone: the server stores no outfit status, so
/// the badge was fabricated local state.
class EventCard extends StatelessWidget {
  const EventCard({required this.event, required this.onTap, super.key});

  final EventItem event;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final eventType =
        EventType.byCodeOrNull(event.eventType) ?? EventType.mockTypes.last;
    final timeLabel = event.displayTime ?? 'No time set';

    return InkWell(
      onTap: onTap,
      borderRadius: FansivibeRadius.baseBorder,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: FansivibeColors.surfaceContainerLow,
          borderRadius: FansivibeRadius.baseBorder,
        ),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: FansivibeColors.accentGold.withValues(alpha: 0.12),
                borderRadius: FansivibeRadius.smdBorder,
              ),
              child: Icon(
                eventType.icon,
                color: FansivibeColors.accentGold,
                size: 22,
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    event.title,
                    style: theme.textTheme.bodyLarge?.copyWith(
                      fontWeight: FontWeight.w600,
                      color: FansivibeColors.textPrimary,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Icon(
                        Icons.calendar_today_outlined,
                        size: 13,
                        color: FansivibeColors.textSecondary,
                      ),
                      const SizedBox(width: 4),
                      Flexible(
                        child: Text(
                          '${event.displayDate} \u2022 $timeLabel',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: FansivibeColors.textSecondary,
                            fontSize: 12,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(
                    eventType.name,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: FansivibeColors.accentGold.withValues(alpha: 0.8),
                      fontSize: 11,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Icon(
              Icons.chevron_right_rounded,
              color: FansivibeColors.textSecondary,
              size: 20,
            ),
          ],
        ),
      ),
    );
  }
}
