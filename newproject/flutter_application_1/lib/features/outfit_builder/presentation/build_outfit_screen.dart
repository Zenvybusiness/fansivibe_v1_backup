import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_builder_mock_data.dart';
import 'package:fansivibe/features/outfit_builder/presentation/widgets/outfit_builder_widgets.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

class BuildOutfitScreen extends StatefulWidget {
  /// Optional event handoff from the event flow (`eventId`, `eventTitle`,
  /// `occasion` = frozen event-type code). The occasion preselects only
  /// when it matches a builder option; otherwise the user picks.
  const BuildOutfitScreen({
    super.key,
    this.eventId,
    this.eventTitle,
    this.initialOccasion,
    this.preferredItemId,
  });

  final String? eventId;
  final String? eventTitle;
  final String? initialOccasion;

  /// C-04 handoff: saved wardrobe UUID carried as the C-03 preferred
  /// item. Display-neutral — the user still picks all four prefs; the id
  /// only rides into the generation request.
  final String? preferredItemId;

  @override
  State<BuildOutfitScreen> createState() => _BuildOutfitScreenState();
}

class _BuildOutfitScreenState extends State<BuildOutfitScreen> {
  final TextEditingController _naturalLanguageController =
      TextEditingController();
  bool _showNaturalLanguage = false;
  String? _selectedOccasion;
  String? _selectedMood;
  String? _selectedFit;
  String? _selectedColorPalette;

  @override
  void initState() {
    super.initState();
    // Event-derived occasion preselects only on an exact option match —
    // never an invented mapping.
    final initial = widget.initialOccasion;
    if (initial != null &&
        BuilderOption.occasionOptions.any((o) => o.id == initial)) {
      _selectedOccasion = initial;
    }
  }

  @override
  void dispose() {
    _naturalLanguageController.dispose();
    super.dispose();
  }

  bool get _allSelected =>
      _selectedOccasion != null &&
      _selectedMood != null &&
      _selectedFit != null &&
      _selectedColorPalette != null;

  bool get _canBuild =>
      _allSelected || _naturalLanguageController.text.trim().isNotEmpty;

  void _buildOutfit() {
    if (!_canBuild) return;
    // Phase 2 guests: deriving an outfit (POST /v1/outfits/generate)
    // is account-only — prompt at the button instead of pushing into
    // a 401-backed generation screen.
    if (isGuestUser) {
      promptGuestSignIn(
        context,
        action: 'Sign in to build outfits. Browsing stays free.',
      );
      return;
    }
    final occ = _selectedOccasion ?? 'casual';
    final mood = _selectedMood ?? 'confident';
    final fit = _selectedFit ?? 'regular';
    final pal = _selectedColorPalette ?? 'monochrome';
    final queryText = _naturalLanguageController.text.trim();

    context.pushNamed(
      RouteNames.outfitGeneration,
      extra: <String, String>{
        'occasion': occ,
        'mood': mood,
        'fit': fit,
        'colorPalette': pal,
        if (queryText.isNotEmpty) 'query': queryText,
        if (widget.eventId != null) 'eventId': widget.eventId!,
        if (widget.eventTitle != null) 'eventTitle': widget.eventTitle!,
        if (widget.preferredItemId != null)
          'preferredItemId': widget.preferredItemId!,
      },
    );
  }

  Widget _buildEventChip(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: FansivibeColors.accentGold.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: FansivibeColors.accentGold.withValues(alpha: 0.35),
          ),
        ),
        child: Row(
          children: [
            Icon(
              Icons.event_outlined,
              size: 18,
              color: FansivibeColors.accentGold,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                'Styling for: ${widget.eventTitle}',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: FansivibeColors.textPrimary,
                  fontWeight: FontWeight.w600,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNaturalLanguageCard(BuildContext context) {
    if (!_showNaturalLanguage && _naturalLanguageController.text.trim().isEmpty) {
      return InkWell(
        key: const Key('btn_toggle_natural_language'),
        onTap: () => setState(() => _showNaturalLanguage = true),
        borderRadius: FansivibeRadius.smdBorder,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            color: FansivibeColors.surfaceContainerLow,
            borderRadius: FansivibeRadius.smdBorder,
            border: Border.all(
              color: FansivibeColors.accentGold.withValues(alpha: 0.25),
            ),
          ),
          child: Row(
            children: [
              Icon(
                Icons.auto_awesome_rounded,
                size: 18,
                color: FansivibeColors.accentGold,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Describe what you want in natural language…',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: FansivibeColors.accentGold,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              Icon(
                Icons.keyboard_arrow_down_rounded,
                size: 20,
                color: FansivibeColors.accentGold,
              ),
            ],
          ),
        ),
      );
    }

    const quickPrompts = [
      'Casual dinner date',
      'Smart casual office',
      'Weekend hangout',
      'Cold evening dinner',
    ];
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: FansivibeRadius.mdBorder,
        border: Border.all(
          color: FansivibeColors.accentGold.withValues(alpha: 0.25),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.auto_awesome_rounded,
                size: 18,
                color: FansivibeColors.accentGold,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Natural Language Styling',
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(
                    color: FansivibeColors.textPrimary,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.close_rounded, size: 18),
                color: FansivibeColors.textSecondary,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
                onPressed: () {
                  setState(() {
                    _naturalLanguageController.clear();
                    _showNaturalLanguage = false;
                  });
                },
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Describe an occasion, vibe, or piece in plain words:',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: FansivibeColors.textSecondary,
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            key: const Key('input_outfit_natural_language'),
            controller: _naturalLanguageController,
            style: const TextStyle(color: FansivibeColors.textPrimary, fontSize: 14),
            decoration: InputDecoration(
              hintText: 'e.g., Dinner date at a cozy bistro on a chilly evening',
              hintStyle: TextStyle(
                color: FansivibeColors.textSecondary.withValues(alpha: 0.6),
                fontSize: 13,
              ),
              filled: true,
              fillColor: FansivibeColors.surfaceContainer,
              contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              border: OutlineInputBorder(
                borderRadius: FansivibeRadius.smdBorder,
                borderSide: BorderSide(color: FansivibeColors.outlineVariant),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: FansivibeRadius.smdBorder,
                borderSide: BorderSide(color: FansivibeColors.outlineVariant),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: FansivibeRadius.smdBorder,
                borderSide: BorderSide(color: FansivibeColors.accentGold),
              ),
            ),
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 6,
            children: quickPrompts.map((prompt) {
              return InkWell(
                onTap: () {
                  _naturalLanguageController.text = prompt;
                  setState(() {});
                },
                borderRadius: BorderRadius.circular(16),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                  decoration: BoxDecoration(
                    color: FansivibeColors.surfaceContainerHigh,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(
                      color: FansivibeColors.accentGold.withValues(alpha: 0.2),
                    ),
                  ),
                  child: Text(
                    prompt,
                    style: const TextStyle(
                      color: FansivibeColors.textSecondary,
                      fontSize: 11,
                    ),
                  ),
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }

  Widget _buildOccasionTransparencyNotice(BuildContext context) {
    const copy =
        'Your outfit recommendations are tailored to the occasion you select. '
        'Date and location are not automatically considered.';
    return Semantics(
      container: true,
      label: copy,
      child: Container(
        key: const Key('occasion_context_transparency_notice'),
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: FansivibeColors.surfaceContainerLow,
          borderRadius: FansivibeRadius.smdBorder,
          border: Border.all(
            color: FansivibeColors.accentGold.withValues(alpha: 0.25),
          ),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              Icons.info_outline_rounded,
              size: 18,
              color: FansivibeColors.accentGold,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                copy,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: FansivibeColors.textSecondary,
                  height: 1.35,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Build Outfit'),
        leading: IconButton(
          icon: Icon(
            Icons.arrow_back_rounded,
            color: FansivibeColors.textPrimary,
          ),
          onPressed: () => Navigator.of(context).pop(),
        ),
        actions: [
          IconButton(
            key: const Key('btn_view_saved_outfits'),
            icon: const Icon(
              Icons.bookmark_outline_rounded,
              color: FansivibeColors.accentGold,
            ),
            tooltip: 'Saved Outfits',
            onPressed: () => context.pushNamed(RouteNames.profileSavedLooks),
          ),
        ],
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

                        // Header
                        Text(
                          'Create Your Look',
                          style: theme.textTheme.displayLarge?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: FansivibeColors.textPrimary,
                            fontSize: 28,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Tell us your preferences and we\'ll build the perfect outfit',
                          style: theme.textTheme.bodyLarge?.copyWith(
                            color: FansivibeColors.textSecondary,
                          ),
                        ),

                        const SizedBox(height: 28),

                        if (widget.eventTitle != null)
                          _buildEventChip(context),

                        // Natural Language Prompt Card
                        _buildNaturalLanguageCard(context),
                        const SizedBox(height: 24),

                        // Occasion
                        OptionSection(
                          title: 'Occasion',
                          subtitle: 'What\'s the event?',
                          helper: _buildOccasionTransparencyNotice(context),
                          options: BuilderOption.occasionOptions,
                          selectedId: _selectedOccasion,
                          onSelected: (id) =>
                              setState(() => _selectedOccasion = id),
                        ),

                        const SizedBox(height: 24),

                        // Mood
                        OptionSection(
                          title: 'Mood',
                          subtitle: 'What vibe are you going for?',
                          options: BuilderOption.moodOptions,
                          selectedId: _selectedMood,
                          onSelected: (id) =>
                              setState(() => _selectedMood = id),
                        ),

                        const SizedBox(height: 24),

                        // Preferred Fit
                        OptionSection(
                          title: 'Preferred Fit',
                          subtitle: 'How do you like your clothes to fit?',
                          options: BuilderOption.fitOptions,
                          selectedId: _selectedFit,
                          onSelected: (id) => setState(() => _selectedFit = id),
                        ),

                        const SizedBox(height: 24),

                        // Color Palette
                        OptionSection(
                          title: 'Color Palette',
                          subtitle: 'What color direction?',
                          options: BuilderOption.colorPaletteOptions,
                          selectedId: _selectedColorPalette,
                          onSelected: (id) =>
                              setState(() => _selectedColorPalette = id),
                        ),

                        const SizedBox(height: 32),

                        // Build button
                        FansiButton.primary(
                          label: 'Build Outfit',
                          icon: Icons.checkroom_rounded,
                          onPressed: _canBuild ? _buildOutfit : null,
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
}
