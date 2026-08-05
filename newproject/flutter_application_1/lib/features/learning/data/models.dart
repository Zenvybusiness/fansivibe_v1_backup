import 'dart:convert';

/// A wardrobe item in the user's evolving model.
class WardrobeEntry {
  const WardrobeEntry({
    required this.id,
    required this.name,
    required this.category,
    required this.color,
    this.material,
    this.isFavorite = false,
  });

  final String id;
  final String name;
  final String category;
  final String color;
  final String? material;
  final bool isFavorite;

  WardrobeEntry copyWith({bool? isFavorite}) => WardrobeEntry(
    id: id,
    name: name,
    category: category,
    color: color,
    material: material,
    isFavorite: isFavorite ?? this.isFavorite,
  );

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'category': category,
    'color': color,
    'material': material,
    'isFavorite': isFavorite,
  };

  factory WardrobeEntry.fromJson(Map<String, dynamic> json) => WardrobeEntry(
    id: json['id'] as String,
    name: json['name'] as String,
    category: json['category'] as String,
    color: json['color'] as String,
    material: json['material'] as String?,
    isFavorite: json['isFavorite'] as bool? ?? false,
  );
}

/// Face/analysis attributes learned from onboarding and scans.
class FaceProfile {
  const FaceProfile({
    this.faceShape,
    this.skinTone,
    this.bodyType,
    this.styleType,
  });

  final String? faceShape;
  final String? skinTone;
  final String? bodyType;
  final String? styleType;

  Map<String, dynamic> toJson() => {
    'faceShape': faceShape,
    'skinTone': skinTone,
    'bodyType': bodyType,
    'styleType': styleType,
  };

  factory FaceProfile.fromJson(Map<String, dynamic> json) => FaceProfile(
    faceShape: json['faceShape'] as String?,
    skinTone: json['skinTone'] as String?,
    bodyType: json['bodyType'] as String?,
    styleType: json['styleType'] as String?,
  );
}

/// A typed interaction signal. Signals accumulate over time and drive the
/// gradual learning: every add/save/scan/feedback the user makes is recorded.
class LearningSignal {
  const LearningSignal({
    required this.type,
    required this.label,
    this.timestamp,
  });

  final String type;
  final String label;
  final int? timestamp;

  Map<String, dynamic> toJson() => {
    'type': type,
    'label': label,
    'timestamp': timestamp ?? DateTime.now().millisecondsSinceEpoch,
  };

  factory LearningSignal.fromJson(Map<String, dynamic> json) => LearningSignal(
    type: json['type'] as String,
    label: json['label'] as String,
    timestamp: json['timestamp'] as int?,
  );
}

/// The evolving on-device user model. This is the source of truth for
/// personalization and is sent (as a snapshot) to the AI backend.
class UserModel {
  UserModel({
    required this.wardrobe,
    this.face,
    this.styleType,
    this.savedLooks = const [],
    this.preferredOccasions = const [],
    this.signals = const [],
  });

  final List<WardrobeEntry> wardrobe;
  final FaceProfile? face;
  final String? styleType;
  final List<String> savedLooks;
  final List<String> preferredOccasions;
  final List<LearningSignal> signals;

  UserModel copyWith({
    List<WardrobeEntry>? wardrobe,
    FaceProfile? face,
    String? styleType,
    List<String>? savedLooks,
    List<String>? preferredOccasions,
    List<LearningSignal>? signals,
  }) => UserModel(
    wardrobe: wardrobe ?? this.wardrobe,
    face: face ?? this.face,
    styleType: styleType ?? this.styleType,
    savedLooks: savedLooks ?? this.savedLooks,
    preferredOccasions: preferredOccasions ?? this.preferredOccasions,
    signals: signals ?? this.signals,
  );

  Map<String, dynamic> toJson() => {
    'wardrobe': wardrobe.map((e) => e.toJson()).toList(),
    'face': face?.toJson(),
    'styleType': styleType,
    'savedLooks': savedLooks,
    'preferredOccasions': preferredOccasions,
    'signals': signals.map((e) => e.toJson()).toList(),
  };

  static UserModel fromJson(Map<String, dynamic> json) => UserModel(
    wardrobe: (json['wardrobe'] as List<dynamic>? ?? [])
        .map((e) => WardrobeEntry.fromJson(e as Map<String, dynamic>))
        .toList(),
    face: json['face'] == null
        ? null
        : FaceProfile.fromJson(json['face'] as Map<String, dynamic>),
    styleType: json['styleType'] as String?,
    savedLooks: (json['savedLooks'] as List<dynamic>? ?? [])
        .map((e) => e as String)
        .toList(),
    preferredOccasions: (json['preferredOccasions'] as List<dynamic>? ?? [])
        .map((e) => e as String)
        .toList(),
    signals: (json['signals'] as List<dynamic>? ?? [])
        .map((e) => LearningSignal.fromJson(e as Map<String, dynamic>))
        .toList(),
  );

  String encode() => jsonEncode(toJson());

  static UserModel decode(String source) =>
      fromJson(jsonDecode(source) as Map<String, dynamic>);
}
