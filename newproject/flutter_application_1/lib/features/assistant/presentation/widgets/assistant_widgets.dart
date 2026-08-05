import 'package:flutter/material.dart';

import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

class MessageBubble extends StatelessWidget {
  const MessageBubble({
    required this.message,
    this.onCardAction,
    this.onClarification,
    this.onNavigation,
    super.key,
  });

  final AssistantMessage message;
  final void Function(SuggestionCard card)? onCardAction;
  final void Function(ClarificationOption option)? onClarification;
  final void Function(NavigationRequest request)? onNavigation;

  @override
  Widget build(BuildContext context) {
    if (message.isUser) {
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          margin: const EdgeInsets.only(top: FansivibeSpacing.sm),
          padding: const EdgeInsets.symmetric(
            horizontal: FansivibeSpacing.md,
            vertical: FansivibeSpacing.sm + 2,
          ),
          constraints: BoxConstraints(
            maxWidth: MediaQuery.of(context).size.width * 0.78,
          ),
          decoration: BoxDecoration(
            color: FansivibeColors.primary,
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(FansivibeRadius.md),
              topRight: Radius.circular(FansivibeRadius.xs),
              bottomLeft: Radius.circular(FansivibeRadius.md),
              bottomRight: Radius.circular(FansivibeRadius.md),
            ),
          ),
          child: Text(
            message.text,
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.onPrimary,
            ),
          ),
        ),
      );
    }

    if (message.pending) {
      return const Align(
        alignment: Alignment.centerLeft,
        child: Padding(
          padding: EdgeInsets.symmetric(vertical: FansivibeSpacing.sm),
          child: _TypingDots(),
        ),
      );
    }

    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(top: FansivibeSpacing.sm),
        padding: const EdgeInsets.all(FansivibeSpacing.md),
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.9,
        ),
        decoration: BoxDecoration(
          color: FansivibeColors.surfaceContainerLow,
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(FansivibeRadius.xs),
            topRight: Radius.circular(FansivibeRadius.md),
            bottomLeft: Radius.circular(FansivibeRadius.md),
            bottomRight: Radius.circular(FansivibeRadius.md),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (message.text.isNotEmpty) ...[
              Text(
                message.text,
                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                  color: FansivibeColors.onSurface,
                  height: 1.4,
                ),
              ),
            ],
            if (message.cards.isNotEmpty) ...[
              const SizedBox(height: FansivibeSpacing.sm + 4),
              for (final card in message.cards) ...[
                SuggestionCardView(
                  card: card,
                  onAction: () => onCardAction?.call(card),
                ),
                const SizedBox(height: FansivibeSpacing.sm),
              ],
            ],
            if (message.clarifications.isNotEmpty) ...[
              const SizedBox(height: FansivibeSpacing.sm + 4),
              Wrap(
                spacing: FansivibeSpacing.sm,
                runSpacing: FansivibeSpacing.sm,
                children: [
                  for (final option in message.clarifications)
                    ActionChip(
                      label: Text(
                        option.label,
                        style: FansivibeTypography.labelMediumWithFamily
                            .copyWith(color: FansivibeColors.onSurface),
                      ),
                      backgroundColor: FansivibeColors.surfaceContainerHigh,
                      side: BorderSide(
                        color: FansivibeColors.primary.withValues(alpha: 0.4),
                      ),
                      shape: RoundedRectangleBorder(
                        borderRadius: FansivibeRadius.fullBorder,
                      ),
                      onPressed: () => onClarification?.call(option),
                    ),
                ],
              ),
            ],
            if (message.navigation != null) ...[
              const SizedBox(height: FansivibeSpacing.sm + 4),
              FilledButton.tonalIcon(
                onPressed: () => onNavigation?.call(message.navigation!),
                icon: const Icon(Icons.open_in_new_rounded, size: 16),
                label: Text('Open ${message.navigation!.label}'),
                style: FilledButton.styleFrom(
                  backgroundColor: FansivibeColors.primary.withValues(
                    alpha: 0.15,
                  ),
                  foregroundColor: FansivibeColors.primary,
                  padding: const EdgeInsets.symmetric(
                    horizontal: FansivibeSpacing.md,
                    vertical: FansivibeSpacing.sm,
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius: FansivibeRadius.fullBorder,
                  ),
                  textStyle: FansivibeTypography.labelMediumWithFamily.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class SuggestionCardView extends StatelessWidget {
  const SuggestionCardView({
    required this.card,
    required this.onAction,
    super.key,
  });

  final SuggestionCard card;
  final VoidCallback onAction;

  IconData get _icon => switch (card.kind) {
    'outfit' => Icons.checkroom_rounded,
    'hairstyle' => Icons.content_cut_rounded,
    'grooming' => Icons.spa_outlined,
    'wardrobe' => Icons.inventory_2_outlined,
    _ => Icons.lightbulb_outline_rounded,
  };

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(FansivibeSpacing.md),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainer,
        borderRadius: FansivibeRadius.baseBorder,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: FansivibeColors.primary.withValues(alpha: 0.12),
                  borderRadius: FansivibeRadius.smBorder,
                ),
                child: Icon(_icon, color: FansivibeColors.primary, size: 18),
              ),
              const SizedBox(width: FansivibeSpacing.sm + 4),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      card.title,
                      style: FansivibeTypography.bodyLargeWithFamily.copyWith(
                        color: FansivibeColors.onSurface,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    if (card.score != null) ...[
                      const SizedBox(height: 2),
                      Text(
                        '${card.score}% match',
                        style: FansivibeTypography.labelSmallWithFamily
                            .copyWith(color: FansivibeColors.primary),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: FansivibeSpacing.sm),
          Text(
            card.subtitle,
            style: FansivibeTypography.bodyMediumWithFamily.copyWith(
              color: FansivibeColors.secondary,
              height: 1.4,
            ),
          ),
          if (card.items.isNotEmpty) ...[
            const SizedBox(height: FansivibeSpacing.sm + 4),
            for (final item in card.items)
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Padding(
                      padding: EdgeInsets.only(top: 5),
                      child: Icon(
                        Icons.circle,
                        size: 5,
                        color: FansivibeColors.primary,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        item,
                        style: FansivibeTypography.bodyMediumWithFamily
                            .copyWith(color: FansivibeColors.secondary),
                      ),
                    ),
                  ],
                ),
              ),
          ],
          if (card.action != null) ...[
            const SizedBox(height: FansivibeSpacing.sm),
            FilledButton.tonalIcon(
              onPressed: onAction,
              icon: const Icon(Icons.open_in_new_rounded, size: 16),
              label: const Text('Open'),
              style: FilledButton.styleFrom(
                backgroundColor: FansivibeColors.primary.withValues(
                  alpha: 0.15,
                ),
                foregroundColor: FansivibeColors.primary,
                padding: const EdgeInsets.symmetric(
                  horizontal: FansivibeSpacing.md,
                  vertical: FansivibeSpacing.sm,
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: FansivibeRadius.fullBorder,
                ),
                textStyle: FansivibeTypography.labelMediumWithFamily.copyWith(
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _TypingDots extends StatelessWidget {
  const _TypingDots();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: FansivibeSpacing.md,
        vertical: FansivibeSpacing.sm + 2,
      ),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.mdBorder,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < 3; i++)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 2),
              child: _Dot(index: i),
            ),
        ],
      ),
    );
  }
}

class _Dot extends StatefulWidget {
  const _Dot({required this.index});

  final int index;

  @override
  State<_Dot> createState() => _DotState();
}

class _DotState extends State<_Dot> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        final phase = ((_controller.value + widget.index * 0.2) % 1.0);
        return Opacity(opacity: 0.35 + phase * 0.65, child: child);
      },
    );
  }
}
