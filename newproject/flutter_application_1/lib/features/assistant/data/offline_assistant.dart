import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/grooming/data/grooming_mock_data.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/learning/data/models.dart';

/// A single outfit suggestion mirroring `backend/app/data/catalog.py`.
class _LookCard {
  const _LookCard({
    required this.title,
    required this.items,
    required this.score,
  });

  final String title;
  final List<String> items;
  final int score;
}

/// Deterministic offline assistant (our own rules engine, mirrored on-device).
///
/// When the backend is unreachable this answers from the app's own data so the
/// assistant stays fully functional with zero network and near-zero CPU/RAM —
/// critical for low-end devices and offline use. Structure mirrors
/// `backend/app/ai/engine.py`.
class OfflineAssistant {
  static const List<String> _occasions = [
    'casual',
    'office',
    'date',
    'party',
    'travel',
  ];

  AssistantReply replyFor(String text, AssistantUserContext context) {
    final low = text.toLowerCase().trim();
    final words = low
        .split(RegExp(r"[^a-z']+"))
        .where((w) => w.isNotEmpty)
        .toSet();

    if (words.contains('hi') ||
        words.contains('hello') ||
        words.contains('hey')) {
      return const AssistantReply(
        intent: 'greeting',
        text:
            "Hey! I'm your Fansivibe stylist. Ask me what to wear, which "
            'hairstyle suits you, or for grooming tips. I learn from your '
            'wardrobe as we talk.',
      );
    }

    if (words.contains('thanks') ||
        words.contains('thank') ||
        words.contains('thx')) {
      return const AssistantReply(
        intent: 'thanks',
        text:
            "Anytime! Want me to build an outfit or find you a new hairstyle next?",
      );
    }

    if (low.contains('open') ||
        low.contains('go to') ||
        low.contains('take me')) {
      final nav = _navigateFor(low);
      if (nav != null) {
        return AssistantReply(
          intent: 'navigate',
          text: 'Taking you to ${nav.label}.',
          navigation: nav,
        );
      }
    }

    final occasion = _occasionFor(low);
    if (occasion != null && words.length <= 2) {
      return _outfit(occasion);
    }

    if (_hasAny(words, [
      'grooming',
      'beard',
      'moustache',
      'mustache',
      'glasses',
      'eyewear',
      'stubble',
      'goatee',
      'shave',
    ])) {
      return _grooming(context);
    }

    if (_hasAny(words, [
      'hairstyle',
      'hair',
      'haircut',
      'quiff',
      'pompadour',
      'fade',
      'barber',
    ])) {
      return _hairstyle(context);
    }

    if (_hasAny(words, ['wardrobe', 'closet', 'inventory', 'own'])) {
      return _wardrobe(context);
    }

    if (_hasAny(words, [
      'outfit',
      'wear',
      'look',
      'dress',
      'style',
      'clothes',
      'shirt',
      'jacket',
    ])) {
      final occasion = _occasionFor(low);
      if (occasion == null) {
        return const AssistantReply(
          intent: 'outfit',
          text:
              "What's the occasion? That helps me pick the perfect look for you.",
          clarifications: [
            ClarificationOption(label: 'Casual', value: 'casual'),
            ClarificationOption(label: 'Office', value: 'office'),
            ClarificationOption(label: 'Date', value: 'date'),
            ClarificationOption(label: 'Party', value: 'party'),
            ClarificationOption(label: 'Travel', value: 'travel'),
          ],
        );
      }
      return _outfit(occasion);
    }

    if (words.length < 2) {
      return _help();
    }

    return _help();
  }

  AssistantReply _outfit(String occasion) {
    final look = switch (occasion) {
      'office' => _LookCard(
        title: 'Refined Office Ensemble',
        items: const [
          'Navy Textured Blazer - Outerwear',
          'Cream Cotton Oxford - Tops',
          'Charcoal Tailored Trousers - Bottoms',
          'Brown Leather Derbies - Footwear',
          'Gold Minimalist Watch - Accessories',
        ],
        score: 91,
      ),
      'date' => _LookCard(
        title: 'Date Night Refined',
        items: const [
          'Leather Chelsea Boots - Footwear',
          'Burgundy Polo - Tops',
          'Dark Denim Jeans - Bottoms',
        ],
        score: 89,
      ),
      'party' => _LookCard(
        title: 'Party Statement',
        items: const [
          'Leather Jacket - Outerwear',
          'Black Graphic Tee - Tops',
          'Black Pleated Trousers - Bottoms',
        ],
        score: 86,
      ),
      'travel' => _LookCard(
        title: 'Travel Comfort',
        items: const [
          'Linen Button-Down - Tops',
          'Slim Chinos - Bottoms',
          'Loafers - Footwear',
        ],
        score: 87,
      ),
      _ => _LookCard(
        title: 'Effortless Casual',
        items: const [
          'Light Wash Denim Jacket - Outerwear',
          'White Cotton Tee - Tops',
          'Dark Denim Jeans - Bottoms',
          'White Sneakers - Footwear',
        ],
        score: 88,
      ),
    };
    return AssistantReply(
      intent: 'outfit',
      text:
          "For $occasion, I'd go with the ${look.title}. "
          'Tap the card to build it.',
      cards: [
        SuggestionCard(
          kind: 'outfit',
          title: look.title,
          subtitle: look.items.join(', '),
          score: look.score,
          items: look.items,
          action: 'open_outfit',
        ),
      ],
    );
  }

  AssistantReply _hairstyle(AssistantUserContext context) {
    final top = HairstyleAnalysisResult.mock.topRecommendation;
    return AssistantReply(
      intent: 'hairstyle',
      text:
          'Your top pick is the ${top.name} (${(top.matchScore * 100).round()}% match). '
          '${top.stylingTips}',
      cards: [
        SuggestionCard(
          kind: 'hairstyle',
          title: top.name,
          subtitle: top.description,
          score: (top.matchScore * 100).round(),
          items: [top.stylingTips, top.maintenance, top.bestFor],
          action: 'open_hairstyle',
        ),
      ],
    );
  }

  AssistantReply _grooming(AssistantUserContext context) {
    final top = GroomingAnalysisResult.mock.topRecommendation;
    return AssistantReply(
      intent: 'grooming',
      text:
          'The ${top.name} suits you best (${(top.matchScore * 100).round()}% match). '
          '${top.stylingTips}',
      cards: [
        SuggestionCard(
          kind: 'grooming',
          title: top.name,
          subtitle: top.description,
          score: (top.matchScore * 100).round(),
          items: [
            for (final s in [top.beardLength, top.eyewearRecommendation, top.maintenance])
              if (s != null && s.isNotEmpty) s
          ],
          action: 'open_grooming',
        ),
      ],
    );
  }

  AssistantReply _wardrobe(AssistantUserContext context) {
    final items = context.wardrobe;
    if (items.isEmpty) {
      return const AssistantReply(
        intent: 'wardrobe',
        text:
            'Your wardrobe is currently empty. Add your clothes to get personalized outfit recommendations!',
        cards: [
          SuggestionCard(
            kind: 'wardrobe',
            title: 'Wardrobe Empty',
            subtitle:
                'Start by adding tops, bottoms, and shoes to your wardrobe.',
            items: [
              '0 items',
              '0 favourites',
              '0 categories',
            ],
            action: 'open_wardrobe',
          ),
        ],
      );
    }
    final favorites = items.where((i) => i.isFavorite).length;
    final categories = items.map((i) => i.category).toSet().length;
    return AssistantReply(
      intent: 'wardrobe',
      text:
          'Here\u2019s what I know about your wardrobe: ${items.length} items '
          'across $categories categories, $favorites favourites.',
      cards: [
        SuggestionCard(
          kind: 'wardrobe',
          title: 'Wardrobe Health',
          subtitle:
              'You have ${items.length} items across $categories categories. '
              'A lightweight jacket would unlock more combinations.',
          items: [
            '${items.length} items',
            '$favorites favourites',
            '$categories categories',
          ],
          action: 'open_wardrobe',
        ),
      ],
    );
  }

  AssistantReply _help() => const AssistantReply(
    intent: 'unknown',
    text:
        'I can help with outfits, hairstyles, grooming, and your wardrobe. '
        "Try asking: 'What should I wear to a date?' or 'Which beard suits me?'",
    clarifications: [
      ClarificationOption(label: 'What should I wear?', value: 'outfit'),
      ClarificationOption(label: 'Best hairstyle for me?', value: 'hairstyle'),
      ClarificationOption(label: 'Grooming tips', value: 'grooming'),
      ClarificationOption(label: 'Show my wardrobe', value: 'wardrobe'),
    ],
  );

  NavigationRequest? _navigateFor(String low) {
    const targets = {
      'wardrobe': ('wardrobe', 'My Wardrobe'),
      'stylist': ('stylist', 'Stylist'),
      'discover': ('discover', 'Discover'),
      'home': ('home', 'Home'),
      'profile': ('profile', 'Profile'),
      'today': ('daily-outfit', "Today's Look"),
      'hairstyle': ('hairstyle', 'Hairstyle Studio'),
      'grooming': ('grooming', 'Grooming Studio'),
      'outfit': ('build-outfit', 'Build Outfit'),
    };
    for (final entry in targets.entries) {
      if (low.contains(entry.key)) {
        return NavigationRequest(route: entry.value.$1, label: entry.value.$2);
      }
    }
    return null;
  }

  String? _occasionFor(String low) {
    for (final o in _occasions) {
      if (low.contains(o)) return o;
    }
    if (low.contains('work') ||
        low.contains('office') ||
        low.contains('meeting')) {
      return 'office';
    }
    return null;
  }

  bool _hasAny(Set<String> words, List<String> keywords) =>
      keywords.any(words.contains);
}
