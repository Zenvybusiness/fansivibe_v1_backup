import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/shared/components/fansivibe_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

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
                        _buildHeader(context),
                        const SizedBox(height: 24),
                        _buildAssistantHero(context),
                        const SizedBox(height: 24),
                        _buildActionGrid(context),
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
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: FansivibeColors.accentGold.withValues(alpha: 0.12),
            borderRadius: FansivibeRadius.mdBorder,
          ),
          child: Icon(
            Icons.auto_awesome_rounded,
            color: FansivibeColors.accentGold,
            size: 24,
          ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Stylist',
                style: theme.textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: FansivibeColors.textPrimary,
                  fontSize: 28,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                'AI-powered style tools',
                style: theme.textTheme.bodyLarge?.copyWith(
                  color: FansivibeColors.textSecondary,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildAssistantHero(BuildContext context) {
    final theme = Theme.of(context);

    return Semantics(
      button: true,
      child: InkWell(
        // Phase 2 guests: the assistant chat is account-gated (the
        // Phase 1 guard bounces guests to /entry) — prompt at the
        // button instead of bouncing.
        onTap: () {
          if (isGuestUser) {
            promptGuestSignIn(
              context,
              action: 'Sign in to chat with the assistant. Browsing stays free.',
            );
            return;
          }
          context.pushNamed(RouteNames.assistant);
        },
        borderRadius: FansivibeRadius.lgBorder,
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                FansivibeColors.primary.withValues(alpha: 0.28),
                FansivibeColors.primaryContainer.withValues(alpha: 0.10),
              ],
            ),
            borderRadius: FansivibeRadius.lgBorder,
          ),
          child: Row(
            children: [
              Container(
                width: 52,
                height: 52,
                decoration: BoxDecoration(
                  color: FansivibeColors.primary,
                  borderRadius: FansivibeRadius.smBorder,
                ),
                child: const Icon(
                  Icons.chat_bubble_rounded,
                  color: FansivibeColors.onPrimary,
                  size: 26,
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Ask the Assistant',
                      style: theme.textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.w700,
                        color: FansivibeColors.onSurface,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'Chat with your AI stylist — it suggests, clarifies and takes you anywhere.',
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: FansivibeColors.secondary,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              const Icon(
                Icons.arrow_forward_ios_rounded,
                size: 16,
                color: FansivibeColors.primary,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildActionGrid(BuildContext context) {
    final actions = StylistActionData.mockActions;

    return Column(
      children: [
        Row(
          children: [
            Expanded(child: _buildGridTile(context, actions[0])),
            const SizedBox(width: 12),
            Expanded(child: _buildGridTile(context, actions[1])),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(child: _buildGridTile(context, actions[2])),
            const SizedBox(width: 12),
            Expanded(child: _buildGridTile(context, actions[3])),
          ],
        ),
        const SizedBox(height: 12),
        _buildHeroTile(context, actions[4]),
      ],
    );
  }

  Widget _buildGridTile(BuildContext context, StylistActionData action) {
    final theme = Theme.of(context);

    return Semantics(
      button: true,
      child: InkWell(
        onTap: () => _handleAction(context, action),
        borderRadius: FansivibeRadius.mdBorder,
        child: FansivibeCard(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              Container(
                width: 52,
                height: 52,
                decoration: BoxDecoration(
                  color: action.accentColor.withValues(alpha: 0.12),
                  borderRadius: FansivibeRadius.smBorder,
                ),
                child: Center(
                  child: Icon(action.icon, color: action.accentColor, size: 26),
                ),
              ),
              const SizedBox(height: 12),
              Text(
                action.title,
                style: theme.textTheme.bodyLarge?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: FansivibeColors.textPrimary,
                ),
                textAlign: TextAlign.center,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 4),
              Text(
                action.subtitle,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: FansivibeColors.textSecondary,
                  fontSize: 11,
                ),
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeroTile(BuildContext context, StylistActionData action) {
    final theme = Theme.of(context);

    return Semantics(
      button: true,
      child: InkWell(
        onTap: () => _handleAction(context, action),
        borderRadius: FansivibeRadius.mdBorder,
        child: FansivibeCard(
          padding: const EdgeInsets.all(18),
          child: Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: action.accentColor.withValues(alpha: 0.12),
                  borderRadius: FansivibeRadius.smBorder,
                ),
                child: Center(
                  child: Icon(action.icon, color: action.accentColor, size: 24),
                ),
              ),
              const SizedBox(width: 14),
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
              const SizedBox(width: 8),
              Icon(
                Icons.arrow_forward_ios_rounded,
                size: 14,
                color: FansivibeColors.textSecondary.withValues(alpha: 0.4),
              ),
            ],
          ),
        ),
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
