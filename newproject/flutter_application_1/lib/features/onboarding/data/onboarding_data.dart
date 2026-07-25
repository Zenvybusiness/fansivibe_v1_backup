enum StyleVibe {
  minimalist('Minimalist', 'Clean lines, neutral palette, intentional simplicity'),
  bold('Bold', 'Strong colors, statement pieces, confident presence'),
  classic('Classic', 'Timeless tailoring, refined silhouettes, investment pieces'),
  trendy('Trendy', 'Current fashion, dynamic silhouettes, cultural edge'),
  natural('Natural', 'Relaxed textures, earth tones, effortless comfort'),
  edgy('Edgy', 'Dark palette, unconventional cuts, artistic expression');

  final String label;
  final String description;
  const StyleVibe(this.label, this.description);
}

class AnalysisResult {
  final int score;
  final String silhouetteLabel;
  final List<String> observations;
  final List<PaletteSwatch> palette;
  final String formalityLabel;

  const AnalysisResult({
    required this.score,
    required this.silhouetteLabel,
    required this.observations,
    required this.palette,
    required this.formalityLabel,
  });
}

class PaletteSwatch {
  final int color;
  final String label;
  const PaletteSwatch({required this.color, required this.label});
}

class AiCapability {
  final String name;
  final String description;
  final bool active;
  final String? unlockHint;

  const AiCapability({
    required this.name,
    required this.description,
    required this.active,
    this.unlockHint,
  });
}

class OnboardingResult {
  final StyleVibe? vibe;
  final AnalysisResult? analysis;
  final String? displayName;

  const OnboardingResult({this.vibe, this.analysis, this.displayName});

  bool get hasAnalysis => analysis != null;
}

const List<AiCapability> allCapabilities = [
  AiCapability(
    name: 'Face Analysis',
    description: 'AI understands your face shape and proportions',
    active: true,
  ),
  AiCapability(
    name: 'Hairstyle Profile',
    description: 'Personalized hairstyle recommendations',
    active: false,
    unlockHint: 'Try a hairstyle scan',
  ),
  AiCapability(
    name: 'Color Analysis',
    description: 'Your personal color palette and harmony',
    active: true,
  ),
  AiCapability(
    name: 'Wardrobe Intelligence',
    description: 'AI understands your wardrobe',
    active: false,
    unlockHint: 'Add wardrobe items',
  ),
  AiCapability(
    name: 'Grooming Profile',
    description: 'Beard and glasses recommendations',
    active: false,
    unlockHint: 'Try a grooming scan',
  ),
  AiCapability(
    name: 'Event Styling',
    description: 'Outfits for your occasions',
    active: false,
    unlockHint: 'Add an event',
  ),
  AiCapability(
    name: 'Shopping Assistant',
    description: 'Find pieces that match your style',
    active: false,
    unlockHint: 'Coming soon',
  ),
];
