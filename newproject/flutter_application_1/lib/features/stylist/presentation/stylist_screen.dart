import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/components/section_title.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class StylistActionData {
  const StylistActionData({
    required this.id,
    required this.title,
    required this.subtitle,
    required this.icon,
    this.accentColor = FansivibeColors.accentGold,
  });

  final String id;
  final String title;
  final String subtitle;
  final IconData icon;
  final Color accentColor;

  static const List<StylistActionData> mockActions = [
    StylistActionData(
      id: 'scan_outfit',
      title: 'Scan My Outfit',
      subtitle: 'Get AI analysis of your current look',
      icon: Icons.camera_alt_outlined,
    ),
    StylistActionData(
      id: 'build_outfit',
      title: 'Build Outfit',
      subtitle: 'Create a look from your wardrobe',
      icon: Icons.checkroom_outlined,
      accentColor: Color(0xFF8B7D6B),
    ),
    StylistActionData(
      id: 'hairstyle',
      title: 'Hairstyle',
      subtitle: 'Find your perfect hairstyle',
      icon: Icons.face_rounded,
      accentColor: Color(0xFF7B8E6B),
    ),
    StylistActionData(
      id: 'grooming',
      title: 'Beard / Glasses',
      subtitle: 'Grooming and accessory suggestions',
      icon: Icons.spa_outlined,
      accentColor: Color(0xFF6B8E8E),
    ),
    StylistActionData(
      id: 'event',
      title: 'Event Planning',
      subtitle: 'Plan outfits for upcoming events',
      icon: Icons.event_outlined,
      accentColor: Color(0xFF8E6B8E),
    ),
  ];
}

class StylistScreen extends StatelessWidget {
  const StylistScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
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
                        SectionTitle(
                          title: 'Stylist',
                          subtitle: 'AI-powered style tools',
                        ),
                        const SizedBox(height: 28),
                        ...StylistActionData.mockActions.map(
                          (action) => Padding(
                            padding: const EdgeInsets.only(bottom: 12),
                            child: _buildActionCard(context, action),
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

  Widget _buildActionCard(BuildContext context, StylistActionData action) {
    final theme = Theme.of(context);

    return FansivibeCard(
      padding: const EdgeInsets.all(20),
      onTap: () => _handleAction(context, action),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: action.accentColor.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Icon(action.icon, color: action.accentColor, size: 24),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  action.title,
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: FansivibeColors.textPrimary,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  action.subtitle,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: FansivibeColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
          Icon(
            Icons.chevron_right_rounded,
            color: FansivibeColors.textSecondary,
            size: 24,
          ),
        ],
      ),
    );
  }

  void _handleAction(BuildContext context, StylistActionData action) {
    switch (action.id) {
      case 'scan_outfit':
        context.pushNamed(RouteNames.scanOutfit);
      case 'build_outfit':
        context.pushNamed(RouteNames.buildOutfit);
      case 'hairstyle':
        context.pushNamed(RouteNames.hairstyle);
      case 'grooming':
        context.pushNamed(RouteNames.grooming);
      case 'event':
        context.pushNamed(RouteNames.events);
    }
  }
}
