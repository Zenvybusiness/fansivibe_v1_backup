import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'package:fansivibe/shared/components/floating_assistant_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class RouterShell extends StatelessWidget {
  const RouterShell({required this.navigationShell, super.key});

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      body: navigationShell,
      floatingActionButton: const FloatingAssistantButton(),
      bottomNavigationBar: NavigationBar(
        selectedIndex: navigationShell.currentIndex,
        onDestinationSelected: (index) {
          navigationShell.goBranch(
            index,
            initialLocation: index == navigationShell.currentIndex,
          );
        },
        indicatorColor: Colors.transparent,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        backgroundColor: theme.colorScheme.surface,
        elevation: 8,
        destinations: const [
          NavigationDestination(
            icon: _GlowingIcon(Icons.home_outlined),
            selectedIcon: _GlowingIcon(Icons.home_rounded, glow: true),
            label: 'Home',
          ),
          NavigationDestination(
            icon: _GlowingIcon(Icons.explore_outlined),
            selectedIcon: _GlowingIcon(Icons.explore_rounded, glow: true),
            label: 'Discover',
          ),
          NavigationDestination(
            icon: _GlowingIcon(Icons.auto_awesome_outlined),
            selectedIcon: _GlowingIcon(Icons.auto_awesome_rounded, glow: true),
            label: 'Stylist',
          ),
          NavigationDestination(
            icon: _GlowingIcon(Icons.checkroom_outlined),
            selectedIcon: _GlowingIcon(Icons.checkroom_rounded, glow: true),
            label: 'Wardrobe',
          ),
          NavigationDestination(
            icon: _GlowingIcon(Icons.person_outline_rounded),
            selectedIcon: _GlowingIcon(Icons.person_rounded, glow: true),
            label: 'Profile',
          ),
        ],
      ),
    );
  }
}

class _GlowingIcon extends StatelessWidget {
  const _GlowingIcon(this.icon, {this.glow = false});

  final IconData icon;
  final bool glow;

  @override
  Widget build(BuildContext context) {
    final color = glow ? FansivibeColors.primary : FansivibeColors.secondary;
    return Text(
      String.fromCharCode(icon.codePoint),
      style: TextStyle(
        fontFamily: icon.fontFamily,
        package: icon.fontPackage,
        color: color,
        fontSize: 24,
        height: 1.0,
        shadows: glow
            ? [
                Shadow(
                  color: FansivibeColors.primary.withValues(alpha: 0.75),
                  blurRadius: 8,
                ),
                Shadow(
                  color: FansivibeColors.primary.withValues(alpha: 0.4),
                  blurRadius: 16,
                ),
              ]
            : null,
      ),
    );
  }
}
