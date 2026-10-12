import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import 'package:fansivibe/app/router/route_names.dart';

import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/assistant/domain/assistant_service.dart';
import 'package:fansivibe/features/assistant/presentation/assistant_routes.dart';
import 'package:fansivibe/features/assistant/presentation/widgets/assistant_widgets.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_spacing.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

/// The Fansivibe Assistant — our own AI concierge.
///
/// Ask anything, get suggestions as rich cards, and let it take you to the
/// right screen. Grounded in the user model; falls back to the offline rules
/// assistant when the backend is unreachable.
class AssistantScreen extends StatefulWidget {
  const AssistantScreen({super.key, this.service, this.pickImage});

  /// Injectable for tests; when null the screen owns its own service.
  final AssistantService? service;

  /// Injectable gallery/camera picker (defaults to [ImagePicker]); tests
  /// supply a fake. Mirrors the outfit-scan precedent.
  final Future<XFile?> Function(ImageSource source)? pickImage;

  @override
  State<AssistantScreen> createState() => _AssistantScreenState();
}

class _AssistantScreenState extends State<AssistantScreen> {
  final TextEditingController _input = TextEditingController();
  final ScrollController _scroll = ScrollController();
  late final AssistantService _service;
  late final bool _ownsService;

  /// Staged outfit photo (in-memory bytes only — never a temp path).
  /// Null means no attachment; cleared on send, kept on picker cancel.
  Uint8List? _attachedImageBytes;
  String _attachedName = 'outfit.jpg';

  /// Client-side guard mirroring the backend 20 MB image contract.
  static const int maxAttachBytes = 20 * 1024 * 1024;

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
    final attachment = _attachedImageBytes;
    if (attachment != null) {
      final text = _input.text;
      setState(() => _attachedImageBytes = null);
      _input.clear();
      _service.sendWithImage(
        text: text,
        imageBytes: attachment,
        filename: _attachedName,
      );
      return;
    }
    final text = _input.text;
    if (text.trim().isEmpty) return;
    _input.clear();
    _service.send(text);
  }

  static Future<XFile?> _defaultPickImage(ImageSource source) {
    return ImagePicker().pickImage(source: source, imageQuality: 90);
  }

  /// Stage an outfit photo beside the composer (gallery or camera via the
  /// existing [ImagePicker] architecture — no new dependency).
  ///
  /// Cancelling (sheet dismiss, picker cancel, validation failure) keeps
  /// the unsent text untouched. Disabled while a message is sending.
  Future<void> _attachImage() async {
    if (_service.isSending) return;
    final source = await _chooseImageSource();
    if (source == null || !mounted) return;
    final picked = await (widget.pickImage ?? _defaultPickImage)(source);
    if (picked == null || !mounted) return;
    final bytes = await picked.readAsBytes();
    final error = _validateAttachment(picked, bytes);
    if (error != null) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(error),
          backgroundColor: FansivibeColors.surfaceContainerHighest,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(
            borderRadius: FansivibeRadius.smdBorder,
          ),
        ),
      );
      return;
    }
    setState(() {
      _attachedImageBytes = bytes;
      _attachedName = _fileNameFor(picked);
    });
  }

  /// Multipart filename: the picker name when present, else derived from
  /// the MIME type so the upload content-type header stays truthful.
  static String _fileNameFor(XFile picked) {
    if (picked.name.isNotEmpty) return picked.name;
    return switch (picked.mimeType?.toLowerCase()) {
      'image/png' => 'outfit.png',
      'image/webp' => 'outfit.webp',
      _ => 'outfit.jpg',
    };
  }

  /// Gallery/camera chooser. Null on dismiss (cancel keeps text).
  Future<ImageSource?> _chooseImageSource() {
    return showModalBottomSheet<ImageSource>(
      context: context,
      backgroundColor: FansivibeColors.surfaceContainerLow,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              key: const Key('assistant_pick_gallery'),
              leading: const Icon(Icons.photo_library_outlined),
              title: const Text('Choose from gallery'),
              onTap: () => Navigator.of(context).pop(ImageSource.gallery),
            ),
            ListTile(
              key: const Key('assistant_pick_camera'),
              leading: const Icon(Icons.photo_camera_outlined),
              title: const Text('Take a photo'),
              onTap: () => Navigator.of(context).pop(ImageSource.camera),
            ),
          ],
        ),
      ),
    );
  }

  /// Backend-contract validation before staging: JPEG/PNG/WebP, non-empty,
  /// at most 20 MB. Returns the user-facing reason, or null when valid.
  ///
  /// The extension wins when the picker supplies a name (all real picks);
  /// otherwise the MIME type decides (`XFile.fromData` drops the name on
  /// native, so tests and pasted bytes land here).
  String? _validateAttachment(XFile picked, Uint8List bytes) {
    if (bytes.isEmpty) return 'That photo came back empty — try again.';
    if (bytes.length > maxAttachBytes) {
      return 'That photo is too large (max 20 MB).';
    }
    if (picked.name.isNotEmpty) {
      final lower = picked.name.toLowerCase();
      final namedOk =
          lower.endsWith('.jpg') ||
          lower.endsWith('.jpeg') ||
          lower.endsWith('.png') ||
          lower.endsWith('.webp');
      if (!namedOk) {
        return 'Unsupported photo format — use JPG, PNG, or WebP.';
      }
      return null;
    }
    const supportedMime = {'image/jpeg', 'image/png', 'image/webp'};
    if (!supportedMime.contains(picked.mimeType?.toLowerCase())) {
      return 'Unsupported photo format — use JPG, PNG, or WebP.';
    }
    return null;
  }

  void _onCardAction(SuggestionCard card) {
    _service.onCardOpened(card);
    final route = AssistantRoutes.routeFor(card.action);
    if (!context.mounted) return;
    if (route == null) {
      _showUnsupportedAction();
      return;
    }
    if (route == RouteNames.fashionReasoning && isGuestUser) {
      promptGuestSignIn(
        context,
        action: 'Sign in to use Fashion Reasoning.',
      );
      return;
    }
    context.goNamed(route);
  }

  void _onClarification(ClarificationOption option) {
    _service.selectClarification(option);
  }

  void _onNavigationRequest(NavigationRequest request) {
    _service.onNavigated(request);
    final route = AssistantRoutes.routeFor(request.route);
    if (!context.mounted) return;
    if (route == null) {
      _showUnsupportedAction();
      return;
    }
    if (route == RouteNames.fashionReasoning && isGuestUser) {
      promptGuestSignIn(
        context,
        action: 'Sign in to use Fashion Reasoning.',
      );
      return;
    }
    context.goNamed(route);
  }

  /// Honest fallback for assistant actions with no app destination.
  ///
  /// The tap is still recorded via `onCardOpened`/`onNavigated` above; only
  /// the navigation is withheld so an unknown action never lands the user
  /// on an unrelated screen.
  void _showUnsupportedAction() {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text("That suggestion isn't available in this version"),
        backgroundColor: FansivibeColors.surfaceContainerHighest,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.smdBorder),
      ),
    );
  }

  /// Outfit Save: delegates to the existing service orchestration, which
  /// POSTs the snapshot and returns backend-confirmed success/failure.
  /// When unauthenticated / guest, prompts sign-in through the existing
  /// intent continuation architecture and gates account-owned look persistence.
  Future<bool> _onOutfitSave(OutfitIntelligence intelligence) async {
    if (isGuestUser) {
      promptGuestSignIn(
        context,
        action: 'Sign in to save looks to your account.',
      );
      return false;
    }
    return _service.saveOutfit(intelligence);
  }

  /// Snapshot of the already-loaded learning wardrobe as displayable items.
  ///
  /// Field-for-field copy (category strings preserved verbatim) so
  /// [MessageBubble] can resolve `selectedItemIds` without new network
  /// requests. Rebuilt on every service change; the screen already listens
  /// to the service, so wardrobe edits re-render with no extra wiring.
  List<WardrobeItemData> _wardrobeItems() => _service.wardrobe
      .map(
        (entry) => WardrobeItemData(
          id: entry.id,
          name: entry.name,
          category: entry.category,
          color: entry.color,
          material: entry.material,
          isFavorite: entry.isFavorite,
        ),
      )
      .toList();

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
            icon: const Icon(Icons.psychology_alt_outlined),
            tooltip: 'Fashion Reasoning',
            color: FansivibeColors.primary,
            onPressed: () {
              if (isGuestUser) {
                promptGuestSignIn(
                  context,
                  action: 'Sign in to use Fashion Reasoning.',
                );
                return;
              }
              context.pushNamed(RouteNames.fashionReasoning);
            },
          ),
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
                          wardrobe: _wardrobeItems(),
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
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (_attachedImageBytes != null) _buildAttachmentPreview(),
            Row(
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
                      hintStyle: FansivibeTypography.bodyMediumWithFamily
                          .copyWith(
                            color: FansivibeColors.secondary.withValues(
                              alpha: 0.6,
                            ),
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
                IconButton(
                  key: const Key('assistant_attach_button'),
                  tooltip: 'Attach outfit photo',
                  onPressed: _service.isSending ? null : _attachImage,
                  icon: const Icon(Icons.image_outlined, size: 22),
                  color: FansivibeColors.primary,
                  style: IconButton.styleFrom(
                    backgroundColor: FansivibeColors.surfaceContainerHigh,
                    disabledBackgroundColor:
                        FansivibeColors.surfaceContainerHigh,
                  ),
                ),
                const SizedBox(width: FansivibeSpacing.sm),
                IconButton.filled(
                  onPressed: _service.isSending ? null : _send,
                  icon: const Icon(Icons.send_rounded, size: 20),
                  style: IconButton.styleFrom(
                    backgroundColor: FansivibeColors.primary,
                    foregroundColor: FansivibeColors.onPrimary,
                    disabledBackgroundColor:
                        FansivibeColors.surfaceContainerHigh,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  /// Staged-photo preview: thumbnail with replace/remove. Removing or
  /// replacing never touches the unsent text.
  Widget _buildAttachmentPreview() {
    final bytes = _attachedImageBytes;
    if (bytes == null) return const SizedBox.shrink();
    return Container(
      key: const Key('assistant_attachment_preview'),
      margin: const EdgeInsets.only(bottom: FansivibeSpacing.sm),
      padding: const EdgeInsets.all(FansivibeSpacing.sm),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerHigh,
        borderRadius: FansivibeRadius.smdBorder,
      ),
      child: Row(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(FansivibeRadius.xs),
            child: Image.memory(
              bytes,
              width: 56,
              height: 56,
              fit: BoxFit.cover,
              errorBuilder: (_, _, _) => Container(
                width: 56,
                height: 56,
                color: FansivibeColors.surfaceContainerHighest,
                child: const Icon(Icons.broken_image_outlined, size: 24),
              ),
            ),
          ),
          const SizedBox(width: FansivibeSpacing.sm),
          Expanded(
            child: Text(
              _attachedName,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                color: FansivibeColors.onSurface,
              ),
            ),
          ),
          IconButton(
            key: const Key('assistant_attachment_replace'),
            tooltip: 'Replace photo',
            onPressed: _service.isSending ? null : _attachImage,
            icon: const Icon(Icons.cached_rounded, size: 20),
            color: FansivibeColors.primary,
          ),
          IconButton(
            key: const Key('assistant_attachment_remove'),
            tooltip: 'Remove photo',
            onPressed: _service.isSending
                ? null
                : () => setState(() => _attachedImageBytes = null),
            icon: const Icon(Icons.close_rounded, size: 20),
            color: FansivibeColors.secondary,
          ),
        ],
      ),
    );
  }
}
