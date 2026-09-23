import 'package:flutter/material.dart';

import 'package:fansivibe/features/knowledge/data/knowledge_repository.dart';
import 'package:fansivibe/features/knowledge/presentation/fashion_reasoning_screen.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';

/// Modal bottom sheet helper to display fashion reasoning from any screen.
abstract final class FashionReasoningSheet {
  FashionReasoningSheet._();

  /// Displays the fashion reasoning interface as a modal bottom sheet.
  static Future<void> show(
    BuildContext context, {
    String? initialQuery,
    KnowledgeRepository? repository,
  }) {
    return showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: FansivibeColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(FansivibeRadius.lg),
        ),
      ),
      builder: (context) {
        return FractionallySizedBox(
          heightFactor: 0.9,
          child: ClipRRect(
            borderRadius: const BorderRadius.vertical(
              top: Radius.circular(FansivibeRadius.lg),
            ),
            child: FashionReasoningScreen(
              initialQuery: initialQuery,
              repository: repository,
            ),
          ),
        );
      },
    );
  }
}
