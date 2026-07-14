import 'package:flutter/material.dart';
import 'package:fansivibe/features/events/data/event_mock_data.dart';
import 'package:fansivibe/features/outfit_builder/presentation/build_outfit_screen.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class EventDetailsScreen extends StatelessWidget {
  const EventDetailsScreen({required this.event, super.key});

  final UserEvent event;

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

                        // Event name header
                        _buildHeader(context),

                        const SizedBox(height: 28),

                        // Event info card
                        _buildInfoCard(context),

                        const SizedBox(height: 20),

                        // Outfit status card
                        _buildStatusCard(context),

                        const SizedBox(height: 20),

                        // Action: Generate Outfit
                        _buildGenerateOutfitButton(context),

                        const SizedBox(height: 12),

                        // Action: Edit Event (temporary)
                        _buildEditEventButton(context),

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
            borderRadius: BorderRadius.circular(16),
          ),
          child: Icon(
            event.eventType.icon,
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
                event.name,
                style: theme.textTheme.displayLarge?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: FansivibeColors.textPrimary,
                  fontSize: 24,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                event.eventType.name,
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
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.15),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.3),
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Column(
        children: [
          _infoRow(
            context,
            icon: Icons.calendar_today_outlined,
            label: 'Date',
            value: event.date,
          ),
          const SizedBox(height: 16),
          _infoRow(
            context,
            icon: Icons.access_time_rounded,
            label: 'Time',
            value: event.time,
          ),
          const SizedBox(height: 16),
          _infoRow(
            context,
            icon: event.eventType.icon,
            label: 'Type',
            value: event.eventType.name,
          ),
        ],
      ),
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
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(icon, size: 18, color: FansivibeColors.accentGold),
        ),
        const SizedBox(width: 14),
        Column(
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
      ],
    );
  }

  Widget _buildStatusCard(BuildContext context) {
    final theme = Theme.of(context);
    final hasOutfit = event.hasOutfitRecommendation;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: FansivibeColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color:
              (hasOutfit
                      ? const Color(0xFF2E7D32)
                      : FansivibeColors.textSecondary)
                  .withValues(alpha: 0.2),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.3),
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color:
                  (hasOutfit
                          ? const Color(0xFF2E7D32)
                          : FansivibeColors.textSecondary)
                      .withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(
              hasOutfit
                  ? Icons.checklist_rounded
                  : Icons.hourglass_empty_rounded,
              size: 22,
              color: hasOutfit
                  ? const Color(0xFF81C784)
                  : FansivibeColors.textSecondary,
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Outfit Recommendation',
                  style: theme.textTheme.bodyLarge?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: FansivibeColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  hasOutfit
                      ? 'An outfit has been recommended for this event'
                      : 'No outfit recommended yet',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: FansivibeColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color:
                  (hasOutfit
                          ? const Color(0xFF2E7D32)
                          : FansivibeColors.textSecondary)
                      .withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              hasOutfit ? 'Ready' : 'Pending',
              style: theme.textTheme.bodySmall?.copyWith(
                color: hasOutfit
                    ? const Color(0xFF81C784)
                    : FansivibeColors.textSecondary,
                fontWeight: FontWeight.w600,
                fontSize: 11,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildGenerateOutfitButton(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: FilledButton.icon(
        onPressed: () => _generateOutfit(context),
        icon: const Icon(Icons.auto_awesome_rounded, size: 20),
        label: const Text('Generate Outfit'),
        style: FilledButton.styleFrom(
          backgroundColor: FansivibeColors.accentGold,
          foregroundColor: FansivibeColors.background,
          padding: const EdgeInsets.symmetric(vertical: 16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          elevation: 4,
          shadowColor: FansivibeColors.accentGold.withValues(alpha: 0.3),
        ),
      ),
    );
  }

  Widget _buildEditEventButton(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: OutlinedButton.icon(
        onPressed: () => _editEvent(context),
        icon: const Icon(Icons.edit_outlined, size: 18),
        label: const Text('Edit Event'),
        style: OutlinedButton.styleFrom(
          foregroundColor: FansivibeColors.textSecondary,
          padding: const EdgeInsets.symmetric(vertical: 14),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
          side: BorderSide(
            color: FansivibeColors.textSecondary.withValues(alpha: 0.3),
          ),
        ),
      ),
    );
  }

  void _generateOutfit(BuildContext context) {
    Navigator.of(context).push<void>(
      MaterialPageRoute<void>(builder: (_) => const BuildOutfitScreen()),
    );
  }

  void _editEvent(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('Edit Event coming soon'),
        backgroundColor: FansivibeColors.accentGold,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }
}
