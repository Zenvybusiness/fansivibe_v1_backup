import 'package:flutter/foundation.dart';

import 'package:fansivibe/features/learning/data/local_store.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/learning_repository.dart';

/// Default starter wardrobe (mirrors `WardrobeMockData.items`) so a brand-new
/// user immediately has a usable wardrobe and the app keeps its current UX.
const List<WardrobeEntry> defaultWardrobe = [
  WardrobeEntry(
    id: '1',
    name: 'Merino Crew Neck',
    category: 'tops',
    color: 'Charcoal',
    material: 'Wool',
    isFavorite: true,
  ),
  WardrobeEntry(
    id: '2',
    name: 'Linen Button-Down',
    category: 'tops',
    color: 'White',
    material: 'Linen',
  ),
  WardrobeEntry(
    id: '3',
    name: 'Cashmere Sweater',
    category: 'tops',
    color: 'Navy',
    material: 'Cashmere',
    isFavorite: true,
  ),
  WardrobeEntry(
    id: '4',
    name: 'Silk Blouse',
    category: 'tops',
    color: 'Blush',
    material: 'Silk',
  ),
  WardrobeEntry(
    id: '5',
    name: 'Oxford Shirt',
    category: 'tops',
    color: 'Light Blue',
    material: 'Cotton',
  ),
  WardrobeEntry(
    id: '6',
    name: 'Graphic Tee',
    category: 'tops',
    color: 'Black',
    material: 'Cotton',
  ),
  WardrobeEntry(
    id: '7',
    name: 'Polo Shirt',
    category: 'tops',
    color: 'Burgundy',
    material: 'Pique Cotton',
  ),
  WardrobeEntry(
    id: '8',
    name: 'Turtleneck',
    category: 'tops',
    color: 'Cream',
    material: 'Merino Wool',
  ),
  WardrobeEntry(
    id: '9',
    name: 'Tapered Trousers',
    category: 'bottoms',
    color: 'Charcoal',
    material: 'Wool',
    isFavorite: true,
  ),
  WardrobeEntry(
    id: '10',
    name: 'Slim Chinos',
    category: 'bottoms',
    color: 'Khaki',
    material: 'Cotton',
  ),
  WardrobeEntry(
    id: '11',
    name: 'Dark Denim Jeans',
    category: 'bottoms',
    color: 'Indigo',
    material: 'Denim',
    isFavorite: true,
  ),
  WardrobeEntry(
    id: '12',
    name: 'Linen Shorts',
    category: 'bottoms',
    color: 'Beige',
    material: 'Linen',
  ),
  WardrobeEntry(
    id: '13',
    name: 'Pleated Trousers',
    category: 'bottoms',
    color: 'Black',
    material: 'Polyester',
  ),
  WardrobeEntry(
    id: '14',
    name: 'Unstructured Blazer',
    category: 'outerwear',
    color: 'Charcoal',
    material: 'Wool Blend',
    isFavorite: true,
  ),
  WardrobeEntry(
    id: '15',
    name: 'Leather Jacket',
    category: 'outerwear',
    color: 'Black',
    material: 'Leather',
    isFavorite: true,
  ),
  WardrobeEntry(
    id: '16',
    name: 'Denim Jacket',
    category: 'outerwear',
    color: 'Light Wash',
    material: 'Denim',
  ),
  WardrobeEntry(
    id: '17',
    name: 'Trench Coat',
    category: 'outerwear',
    color: 'Stone',
    material: 'Cotton',
  ),
  WardrobeEntry(
    id: '18',
    name: 'Leather Chelsea Boots',
    category: 'footwear',
    color: 'Black',
    material: 'Leather',
    isFavorite: true,
  ),
  WardrobeEntry(
    id: '19',
    name: 'White Sneakers',
    category: 'footwear',
    color: 'White',
    material: 'Canvas',
  ),
  WardrobeEntry(
    id: '20',
    name: 'Loafers',
    category: 'footwear',
    color: 'Brown',
    material: 'Suede',
  ),
  WardrobeEntry(
    id: '21',
    name: 'Dress Oxfords',
    category: 'footwear',
    color: 'Tan',
    material: 'Leather',
  ),
  WardrobeEntry(
    id: '22',
    name: 'Leather Belt',
    category: 'accessories',
    color: 'Black',
    material: 'Leather',
    isFavorite: true,
  ),
  WardrobeEntry(
    id: '23',
    name: 'Silk Tie',
    category: 'accessories',
    color: 'Navy',
    material: 'Silk',
  ),
  WardrobeEntry(
    id: '24',
    name: 'Watch',
    category: 'accessories',
    color: 'Silver',
    material: 'Stainless Steel',
    isFavorite: true,
  ),
];

/// The concrete, singleton implementation of [LearningRepository].
///
/// Holds the user model in memory, seeds it with [defaultWardrobe] on first
/// launch, and persists it as JSON via [LocalStore]. Every mutation records a
/// [LearningSignal] so the app visibly "learns" as the user interacts.
class LearningService extends ChangeNotifier implements LearningRepository {
  LearningService._({LocalStore? store}) : _store = store ?? LocalStore();

  static final LearningService instance = LearningService._();

  final LocalStore _store;
  UserModel _model = UserModel(wardrobe: defaultWardrobe);
  bool _loaded = false;

  @override
  List<WardrobeEntry> get wardrobe => List.unmodifiable(_model.wardrobe);

  @override
  FaceProfile? get face => _model.face;

  @override
  String? get styleType => _model.styleType;

  @override
  List<String> get savedLooks => List.unmodifiable(_model.savedLooks);

  @override
  List<String> get preferredOccasions =>
      List.unmodifiable(_model.preferredOccasions);

  @override
  List<LearningSignal> get signals => List.unmodifiable(_model.signals);

  bool get isLoaded => _loaded;

  /// Progressive score: base 60, +1 per wardrobe item (max +20), +2 per saved
  /// look (max +20). So the score rises as the model fills in.
  @override
  int get styleScore {
    final itemPoints = _model.wardrobe.length.clamp(0, 20);
    final lookPoints = (_model.savedLooks.length * 2).clamp(0, 20);
    return 60 + itemPoints + lookPoints;
  }

  @override
  Future<void> load() async {
    if (_loaded) return;
    final persisted = await _store.load();
    if (persisted != null && persisted.wardrobe.isNotEmpty) {
      _model = persisted;
    }
    _loaded = true;
    notifyListeners();
  }

  Future<void> _persist() async {
    await _store.save(_model);
  }

  void _mutate(
    void Function() change, {
    String? signalType,
    String? signalLabel,
  }) {
    change();
    if (signalType != null) {
      _model = _model.copyWith(
        signals: [
          ..._model.signals,
          LearningSignal(type: signalType, label: signalLabel ?? ''),
        ],
      );
    }
    notifyListeners();
    _persist();
  }

  @override
  void addItem(WardrobeEntry item) {
    _mutate(
      () => _model = _model.copyWith(wardrobe: [..._model.wardrobe, item]),
      signalType: 'item_added',
      signalLabel: '${item.name} (${item.category})',
    );
  }

  @override
  void setFace(FaceProfile face) {
    _mutate(
      () => _model = _model.copyWith(face: face),
      signalType: 'analysis_updated',
      signalLabel: 'Face analysis saved',
    );
  }

  @override
  void setStyleType(String styleType) {
    _mutate(
      () => _model = _model.copyWith(styleType: styleType),
      signalType: 'style_updated',
      signalLabel: styleType,
    );
  }

  @override
  void addSavedLook(String title) {
    if (_model.savedLooks.contains(title)) return;
    _mutate(
      () => _model = _model.copyWith(savedLooks: [..._model.savedLooks, title]),
      signalType: 'look_saved',
      signalLabel: title,
    );
  }

  @override
  void addPreferredOccasion(String occasion) {
    if (_model.preferredOccasions.contains(occasion)) return;
    _mutate(
      () => _model = _model.copyWith(
        preferredOccasions: [..._model.preferredOccasions, occasion],
      ),
      signalType: 'occasion_preferred',
      signalLabel: occasion,
    );
  }

  @override
  void recordSignal(String type, String label) {
    _mutate(
      () => _model = _model.copyWith(
        signals: [
          ..._model.signals,
          LearningSignal(type: type, label: label),
        ],
      ),
    );
  }

  /// Resets the singleton to its default seeded state (tests only).
  @visibleForTesting
  void resetForTest() {
    _model = UserModel(wardrobe: defaultWardrobe);
    _loaded = false;
  }
}
