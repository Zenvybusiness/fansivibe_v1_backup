import 'package:fansivibe/features/learning/data/models.dart';

/// Public contract other features use to read and update the evolving user
/// model. Features must not import `learning/` internals — only this contract.
abstract class LearningRepository {
  List<WardrobeEntry> get wardrobe;

  FaceProfile? get face;

  String? get styleType;

  List<String> get savedLooks;

  List<String> get preferredOccasions;

  List<LearningSignal> get signals;

  /// Progressive style score derived from accumulated signals.
  int get styleScore;

  Future<void> load();

  void addItem(WardrobeEntry item);

  void setFace(FaceProfile face);

  void setStyleType(String styleType);

  void addSavedLook(String title);

  void addPreferredOccasion(String occasion);

  /// Record an interaction signal that feeds gradual learning.
  void recordSignal(String type, String label);

  /// Update a wardrobe item by ID with new data from the server.
  ///
  /// The [item] parameter contains the server-returned item data that should
  /// replace the existing item with matching [itemId] in the in-memory model.
  /// Unrelated items are preserved. Persists the updated model and notifies
  /// all listeners.
  void updateItem(String itemId, WardrobeEntry item);
}
