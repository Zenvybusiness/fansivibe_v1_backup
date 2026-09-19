import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:fansivibe/features/learning/data/local_store.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/learning_repository.dart';

/// Starter wardrobe for test/demo environments only (mirrors `WardrobeMockData.items`).
/// In production, users start with an honest empty wardrobe until items are added or loaded.
@visibleForTesting
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
  UserModel _model = UserModel(wardrobe: const []);
  bool _loaded = false;

  /// Server sync hooks for preference persistence (STEP 11.8). Null means
  /// local-only mode: the service behaves exactly as before (instant UI +
  /// on-device persistence, no network).
  Future<bool> Function(List<String> occasions)? _pushPreferences;
  Future<List<String>?> Function()? _pullPreferences;

  /// Guards preferredOccasions against stale hydration responses: bumped on
  /// every local preference mutation; hydration only applies when the
  /// generation it captured is still current.
  int _preferenceGeneration = 0;

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
    if (persisted != null) {
      _model = persisted;
    }
    _loaded = true;
    notifyListeners();
    // STEP 11.8: best-effort server hydration on the existing startup path.
    // Fire-and-forget so local UI is never blocked; without an attached sync
    // client (or on network failure) this no-ops and local state stands.
    unawaited(hydratePreferences());
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

  void removeItem(String itemId) {
    _mutate(
      () {
        _model = _model.copyWith(
          wardrobe: _model.wardrobe.where((item) => item.id != itemId).toList(),
        );
      },
      signalType: 'item_removed',
      signalLabel: 'item $itemId removed',
    );
  }

  @override
  void updateItem(String itemId, WardrobeEntry item) {
    _mutate(
      () {
        _model = _model.copyWith(
          wardrobe: _model.wardrobe.map((existing) =>
              existing.id == itemId ? item : existing,
          ).toList(),
        );
      },
      signalType: 'item_updated',
      signalLabel: '${item.name} (${item.category}) updated',
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
    _preferenceGeneration++;
    // Write-through: push a snapshot; failure never undoes the local
    // mutation and never throws into the UI.
    _pushPreferencesNow(List.of(_model.preferredOccasions));
  }

  /// Replaces the complete local preferredOccasions list (STEP 11.8).
  ///
  /// Used for server hydration: wholesale replace, never merge, values kept
  /// verbatim (dedup preserved, no normalization). Persists locally via the
  /// existing mechanism. Records no learning signal — the values did not
  /// originate from a local user action.
  void replacePreferredOccasions(List<String> occasions) {
    _mutate(
      () => _model = _model.copyWith(
        preferredOccasions: <String>{...occasions}.toList(),
      ),
    );
    _preferenceGeneration++;
  }

  /// Attaches the server preference sync (typically once at startup).
  /// Pass nulls (or nothing) to detach back to local-only mode.
  void attachPreferenceSync({
    Future<bool> Function(List<String> occasions)? push,
    Future<List<String>?> Function()? pull,
  }) {
    _pushPreferences = push;
    _pullPreferences = pull;
  }

  /// Hydrates preferredOccasions from the server (STEP 11.8).
  ///
  /// On success the server list replaces the local list wholesale (`[]`
  /// clears) and is persisted locally. On failure — or when a newer local
  /// mutation landed while the request was in flight (generation guard) —
  /// local state is kept untouched. Never throws. Idempotent.
  Future<void> hydratePreferences() async {
    final pull = _pullPreferences;
    if (pull == null) return;
    final generation = _preferenceGeneration;
    late final List<String>? server;
    try {
      server = await pull();
    } catch (error) {
      debugPrint('Preference hydration failed: $error');
      return;
    }
    if (server == null) return;
    if (generation != _preferenceGeneration) return;
    replacePreferredOccasions(server);
  }

  void _pushPreferencesNow(List<String> snapshot) {
    final push = _pushPreferences;
    if (push == null) return;
    unawaited(() async {
      try {
        await push(snapshot);
      } catch (error) {
        debugPrint('Preference push failed: $error');
      }
    }());
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
    _pushPreferences = null;
    _pullPreferences = null;
    _preferenceGeneration = 0;
  }
}
