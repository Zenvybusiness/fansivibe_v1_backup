import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

/// App-wide floating button that opens the AI assistant from any tab.
class FloatingAssistantButton extends StatelessWidget {
  const FloatingAssistantButton({super.key});

  @override
  Widget build(BuildContext context) {
    return FloatingActionButton(
      onPressed: () => context.pushNamed(RouteNames.assistant),
      backgroundColor: FansivibeColors.primary,
      foregroundColor: FansivibeColors.onPrimary,
      shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.fullBorder),
      child: const Icon(Icons.chat_bubble_rounded),
    );
  }
}
