/// Canonical vibe-to-fashion-attribute & image mapping for Home recommendations.
///
/// Uses only supported vibe identifiers from `StyleVibe` (onboarding) and
/// `PreferencesScreen` (style archetypes) and verified bundled assets under
/// `assets/images/`. Never fabricates a vibe match for null or unknown inputs.
class HomeVibeProfile {
  const HomeVibeProfile({
    required this.canonicalId,
    required this.displayLabel,
    required this.heroImageAsset,
    required this.curatedLooks,
    required this.preferredPalette,
    required this.preferredFit,
    required this.defaultOccasion,
    required this.attributesSummary,
  });

  final String canonicalId;
  final String displayLabel;
  final String heroImageAsset;
  final List<VibeEditorialPreset> curatedLooks;
  final String preferredPalette;
  final String preferredFit;
  final String defaultOccasion;
  final String attributesSummary;
}

class VibeEditorialPreset {
  const VibeEditorialPreset({
    required this.id,
    required this.title,
    required this.category,
    required this.imageAsset,
    required this.height,
  });

  final String id;
  final String title;
  final String category;
  final String imageAsset;
  final double height;
}

class HomeVibeMapping {
  HomeVibeMapping._();

  static const String defaultFallbackImageAsset =
      'assets/images/discover_hero_quiet_luxury.jpg';

  static const Map<String, HomeVibeProfile> _profiles = {
    'minimalist': HomeVibeProfile(
      canonicalId: 'minimalist',
      displayLabel: 'Minimalist',
      heroImageAsset: 'assets/images/discover_look_urban_minimal.jpg',
      preferredPalette: 'monochrome',
      preferredFit: 'slim',
      defaultOccasion: 'office',
      attributesSummary: 'Understated neutrals, clean lines, minimal patterns',
      curatedLooks: [
        VibeEditorialPreset(
          id: 'editorial-minimal-1',
          title: 'Modern Minimal',
          category: 'STUDIO ATELIER',
          imageAsset: 'assets/images/discover_look_urban_minimal.jpg',
          height: 230,
        ),
        VibeEditorialPreset(
          id: 'editorial-minimal-2',
          title: 'Clean Silhouette',
          category: 'MONOCHROME EDIT',
          imageAsset: 'assets/images/discover_moodboard_silhouette.jpg',
          height: 250,
        ),
        VibeEditorialPreset(
          id: 'editorial-minimal-3',
          title: 'Quiet Luxury',
          category: 'TONAL TAILORING',
          imageAsset: 'assets/images/discover_hero_quiet_luxury.jpg',
          height: 180,
        ),
        VibeEditorialPreset(
          id: 'editorial-minimal-4',
          title: 'Sculpted Wool',
          category: 'ESSENTIAL LAYER',
          imageAsset: 'assets/images/discover_item_wool_coat.jpg',
          height: 260,
        ),
      ],
    ),
    'classic': HomeVibeProfile(
      canonicalId: 'classic',
      displayLabel: 'Classic',
      heroImageAsset: 'assets/images/discover_look_modern_classics.jpg',
      preferredPalette: 'cool',
      preferredFit: 'slim',
      defaultOccasion: 'formal',
      attributesSummary:
          'Structured tailoring, refined silhouettes, timeless coats',
      curatedLooks: [
        VibeEditorialPreset(
          id: 'editorial-classic-1',
          title: 'Quiet Tailoring',
          category: 'SAVILE EDIT',
          imageAsset: 'assets/images/discover_look_modern_classics.jpg',
          height: 230,
        ),
        VibeEditorialPreset(
          id: 'editorial-classic-2',
          title: 'Tailored Overcoat',
          category: 'HERITAGE WOOL',
          imageAsset: 'assets/images/discover_item_wool_coat.jpg',
          height: 250,
        ),
        VibeEditorialPreset(
          id: 'editorial-classic-3',
          title: 'Refined Hardware',
          category: 'LEATHER & GOLD',
          imageAsset: 'assets/images/discover_cat_accessories.jpg',
          height: 180,
        ),
        VibeEditorialPreset(
          id: 'editorial-classic-4',
          title: 'Evening Poise',
          category: 'TIMELESS FORM',
          imageAsset: 'assets/images/discover_hero_quiet_luxury.jpg',
          height: 260,
        ),
      ],
    ),
    'bold': HomeVibeProfile(
      canonicalId: 'bold',
      displayLabel: 'Bold',
      heroImageAsset: 'assets/images/discover_moodboard_accents.jpg',
      preferredPalette: 'warm',
      preferredFit: 'relaxed',
      defaultOccasion: 'party',
      attributesSummary: 'Statement accents, rich contrast, confident layering',
      curatedLooks: [
        VibeEditorialPreset(
          id: 'editorial-bold-1',
          title: 'Statement Accents',
          category: 'COLOR CONTRAST',
          imageAsset: 'assets/images/discover_moodboard_accents.jpg',
          height: 230,
        ),
        VibeEditorialPreset(
          id: 'editorial-bold-2',
          title: 'Editorial Silhouette',
          category: 'RUNWAY FORM',
          imageAsset: 'assets/images/discover_foryou_silhouette.jpg',
          height: 250,
        ),
        VibeEditorialPreset(
          id: 'editorial-bold-3',
          title: 'Sculptural Gold',
          category: 'STATEMENT PIECE',
          imageAsset: 'assets/images/discover_cat_accessories.jpg',
          height: 180,
        ),
        VibeEditorialPreset(
          id: 'editorial-bold-4',
          title: 'Archive Contrast',
          category: 'BOLD LAYER',
          imageAsset: 'assets/images/discover_foryou_archive.jpg',
          height: 260,
        ),
      ],
    ),
    'trendy': HomeVibeProfile(
      canonicalId: 'trendy',
      displayLabel: 'Trendy',
      heroImageAsset: 'assets/images/editorial_look_streetwear.jpg',
      preferredPalette: 'monochrome',
      preferredFit: 'relaxed',
      defaultOccasion: 'casual',
      attributesSummary:
          'Relaxed fits, street-inspired proportions, current sneakers',
      curatedLooks: [
        VibeEditorialPreset(
          id: 'editorial-trendy-1',
          title: 'Street Utility',
          category: 'URBAN LAYER',
          imageAsset: 'assets/images/editorial_look_streetwear.jpg',
          height: 230,
        ),
        VibeEditorialPreset(
          id: 'editorial-trendy-2',
          title: 'Low-Profile Kicks',
          category: 'FOOTWEAR EDIT',
          imageAsset: 'assets/images/discover_cat_sneakers.jpg',
          height: 250,
        ),
        VibeEditorialPreset(
          id: 'editorial-trendy-3',
          title: 'Retro Court',
          category: 'STREET CLASSIC',
          imageAsset: 'assets/images/discover_item_samba.jpg',
          height: 180,
        ),
        VibeEditorialPreset(
          id: 'editorial-trendy-4',
          title: 'Archive Street',
          category: 'CITY PROPORTION',
          imageAsset: 'assets/images/discover_foryou_archive.jpg',
          height: 260,
        ),
      ],
    ),
    'streetwear': HomeVibeProfile(
      canonicalId: 'streetwear',
      displayLabel: 'Street Style',
      heroImageAsset: 'assets/images/editorial_look_streetwear.jpg',
      preferredPalette: 'monochrome',
      preferredFit: 'relaxed',
      defaultOccasion: 'casual',
      attributesSummary:
          'Relaxed silhouettes, street-inspired outerwear, sneakers',
      curatedLooks: [
        VibeEditorialPreset(
          id: 'editorial-street-1',
          title: 'Relaxed Streetwear',
          category: 'ARCHIVE STREET',
          imageAsset: 'assets/images/editorial_look_streetwear.jpg',
          height: 230,
        ),
        VibeEditorialPreset(
          id: 'editorial-street-2',
          title: 'Court Sneakers',
          category: 'STREET FOOTWEAR',
          imageAsset: 'assets/images/discover_item_samba.jpg',
          height: 250,
        ),
        VibeEditorialPreset(
          id: 'editorial-street-3',
          title: 'Sneaker Rotation',
          category: 'CASUAL EDGE',
          imageAsset: 'assets/images/discover_cat_sneakers.jpg',
          height: 180,
        ),
        VibeEditorialPreset(
          id: 'editorial-street-4',
          title: 'Urban Evening',
          category: 'CITY LAYER',
          imageAsset: 'assets/images/discover_look_urban_minimal.jpg',
          height: 260,
        ),
      ],
    ),
    'natural': HomeVibeProfile(
      canonicalId: 'natural',
      displayLabel: 'Natural',
      heroImageAsset: 'assets/images/discover_moodboard_texture.jpg',
      preferredPalette: 'warm',
      preferredFit: 'relaxed',
      defaultOccasion: 'casual',
      attributesSummary:
          'Relaxed organic textures, earth tones, breathable comfort',
      curatedLooks: [
        VibeEditorialPreset(
          id: 'editorial-natural-1',
          title: 'Earth & Texture',
          category: 'ORGANIC WEAVE',
          imageAsset: 'assets/images/discover_moodboard_texture.jpg',
          height: 230,
        ),
        VibeEditorialPreset(
          id: 'editorial-natural-2',
          title: 'Soft Drape',
          category: 'RELAXED FORM',
          imageAsset: 'assets/images/discover_cat_clothing.jpg',
          height: 250,
        ),
        VibeEditorialPreset(
          id: 'editorial-natural-3',
          title: 'Warm Accents',
          category: 'TONAL EARTH',
          imageAsset: 'assets/images/discover_moodboard_accents.jpg',
          height: 180,
        ),
        VibeEditorialPreset(
          id: 'editorial-natural-4',
          title: 'Easy Tailoring',
          category: 'NATURAL FIT',
          imageAsset: 'assets/images/discover_foryou_silhouette.jpg',
          height: 260,
        ),
      ],
    ),
    'bohemian': HomeVibeProfile(
      canonicalId: 'bohemian',
      displayLabel: 'Bohemian',
      heroImageAsset: 'assets/images/discover_moodboard_texture.jpg',
      preferredPalette: 'warm',
      preferredFit: 'relaxed',
      defaultOccasion: 'casual',
      attributesSummary:
          'Flowing silhouettes, tactile weaves, expressive warm tones',
      curatedLooks: [
        VibeEditorialPreset(
          id: 'editorial-boho-1',
          title: 'Textured Drape',
          category: 'ARTISAN WEAVE',
          imageAsset: 'assets/images/discover_moodboard_texture.jpg',
          height: 230,
        ),
        VibeEditorialPreset(
          id: 'editorial-boho-2',
          title: 'Expressive Palette',
          category: 'WARM ACCENTS',
          imageAsset: 'assets/images/discover_moodboard_accents.jpg',
          height: 250,
        ),
        VibeEditorialPreset(
          id: 'editorial-boho-3',
          title: 'Fluid Silhouette',
          category: 'FLOWING FORM',
          imageAsset: 'assets/images/discover_foryou_silhouette.jpg',
          height: 180,
        ),
        VibeEditorialPreset(
          id: 'editorial-boho-4',
          title: 'Crafted Detail',
          category: 'BOHEMIAN EDIT',
          imageAsset: 'assets/images/discover_cat_accessories.jpg',
          height: 260,
        ),
      ],
    ),
    'edgy': HomeVibeProfile(
      canonicalId: 'edgy',
      displayLabel: 'Edgy',
      heroImageAsset: 'assets/images/discover_foryou_archive.jpg',
      preferredPalette: 'monochrome',
      preferredFit: 'slim',
      defaultOccasion: 'party',
      attributesSummary:
          'Dark palette, architectural cuts, monochrome contrast',
      curatedLooks: [
        VibeEditorialPreset(
          id: 'editorial-edgy-1',
          title: 'Dark Monochrome',
          category: 'ARCHIVE EDGE',
          imageAsset: 'assets/images/discover_foryou_archive.jpg',
          height: 230,
        ),
        VibeEditorialPreset(
          id: 'editorial-edgy-2',
          title: 'Noir Silhouette',
          category: 'SCULPTED CUT',
          imageAsset: 'assets/images/discover_moodboard_silhouette.jpg',
          height: 250,
        ),
        VibeEditorialPreset(
          id: 'editorial-edgy-3',
          title: 'Urban Contrast',
          category: 'NIGHT EDIT',
          imageAsset: 'assets/images/discover_look_urban_minimal.jpg',
          height: 180,
        ),
        VibeEditorialPreset(
          id: 'editorial-edgy-4',
          title: 'Street Edge',
          category: 'HIGH CONTRAST',
          imageAsset: 'assets/images/editorial_look_streetwear.jpg',
          height: 260,
        ),
      ],
    ),
    'athleisure': HomeVibeProfile(
      canonicalId: 'athleisure',
      displayLabel: 'Athleisure',
      heroImageAsset: 'assets/images/discover_cat_sneakers.jpg',
      preferredPalette: 'cool',
      preferredFit: 'relaxed',
      defaultOccasion: 'workout',
      attributesSummary:
          'Athletic-inspired layers, technical comfort, clean sneakers',
      curatedLooks: [
        VibeEditorialPreset(
          id: 'editorial-athleisure-1',
          title: 'Active Minimal',
          category: 'SPORT EDIT',
          imageAsset: 'assets/images/discover_cat_sneakers.jpg',
          height: 230,
        ),
        VibeEditorialPreset(
          id: 'editorial-athleisure-2',
          title: 'Court Runner',
          category: 'DAILY MOTION',
          imageAsset: 'assets/images/discover_item_samba.jpg',
          height: 250,
        ),
        VibeEditorialPreset(
          id: 'editorial-athleisure-3',
          title: 'Relaxed Layering',
          category: 'STREET SPORT',
          imageAsset: 'assets/images/editorial_look_streetwear.jpg',
          height: 180,
        ),
        VibeEditorialPreset(
          id: 'editorial-athleisure-4',
          title: 'Clean Essentials',
          category: 'STUDIO COMFORT',
          imageAsset: 'assets/images/discover_cat_clothing.jpg',
          height: 260,
        ),
      ],
    ),
  };

  static const Map<String, String> _aliases = {
    'minimal': 'minimalist',
    'minimalist': 'minimalist',
    'modern minimalist': 'minimalist',
    'classic': 'classic',
    'timeless': 'classic',
    'formal': 'classic',
    'bold': 'bold',
    'statement': 'bold',
    'trendy': 'trendy',
    'street': 'streetwear',
    'street style': 'streetwear',
    'street_style': 'streetwear',
    'streetwear': 'streetwear',
    'natural': 'natural',
    'boho': 'bohemian',
    'bohemian': 'bohemian',
    'edgy': 'edgy',
    'athleisure': 'athleisure',
    'sporty': 'athleisure',
    'athletic': 'athleisure',
    'casual': 'trendy',
  };

  /// Resolves [rawVibe] to a supported [HomeVibeProfile], or `null` when
  /// [rawVibe] is null, blank, or unsupported.
  static HomeVibeProfile? resolve(String? rawVibe) {
    if (rawVibe == null) return null;
    final normalized = rawVibe.trim().toLowerCase().replaceAll(
      RegExp(r'\s+'),
      ' ',
    );
    if (normalized.isEmpty) return null;
    final key = _aliases[normalized];
    if (key == null) return null;
    return _profiles[key];
  }

  /// Resolves the best matching hero image for Today's Look.
  ///
  /// Priority:
  /// 1. Explicit outfit/component [lookImageUrl] when present.
  /// 2. Supported user [vibe] profile image.
  /// 3. Occasion-aligned bundled editorial image.
  /// 4. [defaultFallbackImageAsset].
  static String heroImageFor({
    String? lookImageUrl,
    String? vibe,
    String? occasion,
  }) {
    if (lookImageUrl != null && lookImageUrl.trim().isNotEmpty) {
      return lookImageUrl.trim();
    }
    final profile = resolve(vibe);
    if (profile != null) {
      return profile.heroImageAsset;
    }
    final occ = occasion?.trim().toLowerCase();
    if (occ != null && occ.isNotEmpty) {
      if (occ == 'formal' || occ == 'business' || occ == 'office') {
        return 'assets/images/discover_look_modern_classics.jpg';
      }
      if (occ == 'workout') {
        return 'assets/images/discover_cat_sneakers.jpg';
      }
      if (occ == 'party' || occ == 'date') {
        return 'assets/images/discover_moodboard_accents.jpg';
      }
      if (occ == 'casual' || occ == 'travel') {
        return 'assets/images/editorial_look_streetwear.jpg';
      }
    }
    return defaultFallbackImageAsset;
  }

  /// Generic editorial fallback presets when no user vibe is selected.
  static const List<VibeEditorialPreset> genericEditorialPresets = [
    VibeEditorialPreset(
      id: 'editorial-generic-1',
      title: 'Quiet Tailoring',
      category: 'STUDIO ATELIER',
      imageAsset: 'assets/images/discover_look_modern_classics.jpg',
      height: 230,
    ),
    VibeEditorialPreset(
      id: 'editorial-generic-2',
      title: 'Modern Minimal',
      category: 'PARIS RUNWAY',
      imageAsset: 'assets/images/discover_moodboard_silhouette.jpg',
      height: 250,
    ),
    VibeEditorialPreset(
      id: 'editorial-generic-3',
      title: 'Soft Structure',
      category: 'LEATHER & GOLD',
      imageAsset: 'assets/images/discover_cat_accessories.jpg',
      height: 180,
    ),
    VibeEditorialPreset(
      id: 'editorial-generic-4',
      title: 'Urban Evening',
      category: 'ARCHIVE STREET',
      imageAsset: 'assets/images/discover_look_urban_minimal.jpg',
      height: 260,
    ),
  ];
}
