import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/assistant/domain/assistant_service.dart';
import 'package:fansivibe/features/assistant/presentation/assistant_routes.dart';
import 'package:fansivibe/features/assistant/presentation/widgets/assistant_widgets.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// The Fansivibe Assistant — our own AI concierge.
///
/// Ask anything, get suggestions as rich cards, and let it take you to the
/// right screen. Grounded in the user model; falls back to the offline rules
/// assistant when the backend is unreachable.
class AssistantScreen extends StatefulWidget {
  const AssistantScreen({super.key, this.service});

  /// Injectable for tests; when null the screen owns its own service.
  final AssistantService? service;

  @override
  State<AssistantScreen> createState() => _AssistantScreenState();
}

class _AssistantScreenState extends State<AssistantScreen> {
  final TextEditingController _input = TextEditingController();
  final ScrollController _scroll = ScrollController();
  late final AssistantService _service;
  late final bool _ownsService;

  @override
  void initState() {
    super.initState();
    _ownsService = widget.service == null;
    _service =
        widget.service ??
        (AssistantService()..attachLearning(LearningService.instance));
    _service.addListener(_onServiceChanged);
  }

  void _onServiceChanged() {
    if (!mounted) return;
    setState(() {});
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  void dispose() {
    _service.removeListener(_onServiceChanged);
    if (_ownsService) {
      _service.dispose();
    }
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _send() {
    final text = _input.text;
    if (text.trim().isEmpty) return;
    _input.clear();
    _service.send(text);
  }

  void _onCardAction(SuggestionCard card) {
    _service.onCardOpened(card);
    final route = AssistantRoutes.routeFor(card.action);
    if (context.mounted) context.goNamed(route);
  }

  void _onClarification(ClarificationOption option) {
    _service.selectClarification(option);
  }

  void _onNavigationRequest(NavigationRequest request) {
    _service.onNavigated(request);
    final route = AssistantRoutes.routeFor(request.route);
    if (context.mounted) context.goNamed(route);
  }

  /// Outfit Save: delegates to the existing service orchestration, which
  /// POSTs the snapshot and returns backend-confirmed success/failure.
  /// No local learning signals: the backend owns look_saved/outfit_selected.
  Future<bool> _onOutfitSave(OutfitIntelligence intelligence) =>
      _service.saveOutfit(intelligence);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: FansivibeColors.surface,
      appBar: AppBar(
        backgroundColor: FansivibeColors.surface,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded),
          color: FansivibeColors.onSurface,
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Assistant',
              style: FansivibeTypography.bodyLargeWithFamily.copyWith(
                color: FansivibeColors.onSurface,
                fontWeight: FontWeight.w700,
                fontSize: 18,
              ),
            ),
            Text(
              'Ask. Get styled. I learn as we talk.',
              style: FansivibeTypography.labelSmallWithFamily.copyWith(
                color: FansivibeColors.secondary,
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.auto_awesome_rounded),
            color: FansivibeColors.primary,
            onPressed: () {
              if (_service.messages.isEmpty) return;
              _service.send('suggest an outfit');
            },
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: _service.messages.isEmpty
                  ? _buildEmptyState()
                  : ListView.builder(
                      controller: _scroll,
                      padding: const EdgeInsets.fromLTRB(
                        FansivibeSpacing.md,
                        FansivibeSpacing.sm,
                        FansivibeSpacing.md,
                        FansivibeSpacing.md,
                      ),
                      itemCount: _service.messages.length,
                      itemBuilder: (context, index) {
                        final message = _service.messages[index];
                        return MessageBubble(
                          message: message,
                          onCardAction: _onCardAction,
                          onClarification: _onClarification,
                          onNavigation: _onNavigationRequest,
                          onOutfitSave: _onOutfitSave,
                        );
                      },
                    ),
            ),
            _buildInputBar(),
          ],
        ),
      ),
    );
  }

  Widget _buildEmptyState() {
    final suggestions = [
      'What should I wear to a date?',
      'Best hairstyle for me?',
      'Grooming tips',
      'Show my wardrobe',
      'Open my wardrobe',
    ];
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(FansivibeSpacing.lg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: FansivibeColors.primary.withValues(alpha: 0.12),
              ),
              child: const Icon(
                Icons.auto_awesome_rounded,
                size: 32,
                color: FansivibeColors.primary,
              ),
            ),
            const SizedBox(height: FansivibeSpacing.md),
            Text(
              'Your AI stylist',
              style: FansivibeTypography.titleLargeWithFamily.copyWith(
                color: FansivibeColors.onSurface,
              ),
            ),
            const SizedBox(height: FansivibeSpacing.sm),
            Text(
              'Ask for an outfit, a hairstyle, or grooming tips. '
              'I learn from your wardrobe and scans.',
              textAlign: TextAlign.center,
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.secondary,
              ),
            ),
            const SizedBox(height: FansivibeSpacing.lg),
            for (final s in suggestions)
              Padding(
                padding: const EdgeInsets.only(bottom: FansivibeSpacing.sm),
                child: OutlinedButton(
                  onPressed: () => _service.send(s),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: FansivibeColors.primary,
                    side: BorderSide(
                      color: FansivibeColors.primary.withValues(alpha: 0.4),
                    ),
                    shape: RoundedRectangleBorder(
                      borderRadius: FansivibeRadius.fullBorder,
                    ),
                  ),
                  child: Text(s),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildInputBar() {
    return Container(
      padding: const EdgeInsets.fromLTRB(
        FansivibeSpacing.md,
        FansivibeSpacing.sm,
        FansivibeSpacing.md,
        FansivibeSpacing.sm + 4,
      ),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: const BorderRadius.vertical(
          top: Radius.circular(FansivibeRadius.lg),
        ),
      ),
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _input,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => _send(),
                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                  color: FansivibeColors.onSurface,
                ),
                decoration: InputDecoration(
                  hintText: 'Ask your stylist…',
                  hintStyle: FansivibeTypography.bodyMediumWithFamily.copyWith(
                    color: FansivibeColors.secondary.withValues(alpha: 0.6),
                  ),
                  filled: true,
                  fillColor: FansivibeColors.surfaceContainerHigh,
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: FansivibeSpacing.md,
                    vertical: 12,
                  ),
                  border: OutlineInputBorder(
                    borderRadius: FansivibeRadius.fullBorder,
                    borderSide: BorderSide.none,
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: FansivibeRadius.fullBorder,
                    borderSide: BorderSide(
                      color: FansivibeColors.primary.withValues(alpha: 0.6),
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(width: FansivibeSpacing.sm),
            IconButton.filled(
              onPressed: _service.isSending ? null : _send,
              icon: const Icon(Icons.send_rounded, size: 20),
              style: IconButton.styleFrom(
                backgroundColor: FansivibeColors.primary,
                foregroundColor: FansivibeColors.onPrimary,
                disabledBackgroundColor: FansivibeColors.surfaceContainerHigh,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
