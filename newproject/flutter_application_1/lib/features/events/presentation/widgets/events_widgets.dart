import 'package:flutter/material.dart';
import 'package:fansivibe/features/events/data/event_mock_data.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

class EventCard extends StatelessWidget {
  const EventCard({required this.event, required this.onTap, super.key});

  final UserEvent event;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

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
                event.eventType.icon,
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
                    event.name,
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
                          '${event.date} \u2022 ${event.time}',
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
                    event.eventType.name,
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
            Column(
              children: [
                _buildStatusBadge(context),
                const SizedBox(height: 4),
                Icon(
                  Icons.chevron_right_rounded,
                  color: FansivibeColors.textSecondary,
                  size: 20,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStatusBadge(BuildContext context) {
    final theme = Theme.of(context);
    final hasOutfit = event.hasOutfitRecommendation;
    final bgColor = hasOutfit
        ? FansivibeColors.successContainer.withValues(alpha: 0.2)
        : FansivibeColors.textSecondary.withValues(alpha: 0.1);
    final textColor = hasOutfit
        ? FansivibeColors.onSuccessContainer
        : FansivibeColors.textSecondary;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: FansivibeRadius.smBorder,
      ),
      child: Text(
        hasOutfit ? 'Ready' : 'Pending',
        style: theme.textTheme.bodySmall?.copyWith(
          color: textColor,
          fontSize: 10,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
