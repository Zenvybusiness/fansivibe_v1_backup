/// Category data for wardrobe filtering.
class WardrobeCategory {
  const WardrobeCategory({
    required this.id,
    required this.name,
    required this.iconName,
    this.itemCount = 0,
  });

  final String id;
  final String name;
  final String iconName;
  final int itemCount;
}

/// Data for a single wardrobe clothing item.
class WardrobeItemData {
  const WardrobeItemData({
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
}

/// AI wardrobe insight data.
class WardrobeInsightData {
  const WardrobeInsightData({
    required this.title,
    required this.insight,
    required this.iconName,
    required this.accentColor,
    required this.actionLabel,
  });

  final String title;
  final String insight;
  final String iconName;
  final int accentColor;
  final String actionLabel;

  static const WardrobeInsightData mock = WardrobeInsightData(
    title: 'Wardrobe Health',
    insight:
        'Your wardrobe is balanced across seasons. Consider adding a lightweight jacket to expand spring outfit options by 8+ combinations.',
    iconName: 'lightbulb_outline_rounded',
    accentColor: 0xFFC5A059,
    actionLabel: 'View Analysis',
  );
}

/// Mock wardrobe data.
abstract final class WardrobeMockData {
  static const String styleType = 'Modern Minimalist';

  static const List<WardrobeCategory> categories = [
    WardrobeCategory(
      id: 'all',
      name: 'All Items',
      iconName: 'checkroom_rounded',
      itemCount: 24,
    ),
    WardrobeCategory(
      id: 'tops',
      name: 'Tops',
      iconName: 'person_rounded',
      itemCount: 8,
    ),
    WardrobeCategory(
      id: 'bottoms',
      name: 'Bottoms',
      iconName: 'accessibility_rounded',
      itemCount: 5,
    ),
    WardrobeCategory(
      id: 'outerwear',
      name: 'Outerwear',
      iconName: 'checkroom_rounded',
      itemCount: 4,
    ),
    WardrobeCategory(
      id: 'footwear',
      name: 'Footwear',
      iconName: 'directions_walk_rounded',
      itemCount: 4,
    ),
    WardrobeCategory(
      id: 'accessories',
      name: 'Accessories',
      iconName: 'diamond_rounded',
      itemCount: 3,
    ),
  ];

  static const List<WardrobeItemData> items = [
    WardrobeItemData(
      id: '1',
      name: 'Merino Crew Neck',
      category: 'tops',
      color: 'Charcoal',
      material: 'Wool',
      isFavorite: true,
    ),
    WardrobeItemData(
      id: '2',
      name: 'Linen Button-Down',
      category: 'tops',
      color: 'White',
      material: 'Linen',
    ),
    WardrobeItemData(
      id: '3',
      name: 'Cashmere Sweater',
      category: 'tops',
      color: 'Navy',
      material: 'Cashmere',
      isFavorite: true,
    ),
    WardrobeItemData(
      id: '4',
      name: 'Silk Blouse',
      category: 'tops',
      color: 'Blush',
      material: 'Silk',
    ),
    WardrobeItemData(
      id: '5',
      name: 'Oxford Shirt',
      category: 'tops',
      color: 'Light Blue',
      material: 'Cotton',
    ),
    WardrobeItemData(
      id: '6',
      name: 'Graphic Tee',
      category: 'tops',
      color: 'Black',
      material: 'Cotton',
    ),
    WardrobeItemData(
      id: '7',
      name: 'Polo Shirt',
      category: 'tops',
      color: 'Burgundy',
      material: 'Pique Cotton',
    ),
    WardrobeItemData(
      id: '8',
      name: 'Turtleneck',
      category: 'tops',
      color: 'Cream',
      material: 'Merino Wool',
    ),
    WardrobeItemData(
      id: '9',
      name: 'Tapered Trousers',
      category: 'bottoms',
      color: 'Charcoal',
      material: 'Wool',
      isFavorite: true,
    ),
    WardrobeItemData(
      id: '10',
      name: 'Slim Chinos',
      category: 'bottoms',
      color: 'Khaki',
      material: 'Cotton',
    ),
    WardrobeItemData(
      id: '11',
      name: 'Dark Denim Jeans',
      category: 'bottoms',
      color: 'Indigo',
      material: 'Denim',
      isFavorite: true,
    ),
    WardrobeItemData(
      id: '12',
      name: 'Linen Shorts',
      category: 'bottoms',
      color: 'Beige',
      material: 'Linen',
    ),
    WardrobeItemData(
      id: '13',
      name: 'Pleated Trousers',
      category: 'bottoms',
      color: 'Black',
      material: 'Polyester',
    ),
    WardrobeItemData(
      id: '14',
      name: 'Unstructured Blazer',
      category: 'outerwear',
      color: 'Charcoal',
      material: 'Wool Blend',
      isFavorite: true,
    ),
    WardrobeItemData(
      id: '15',
      name: 'Leather Jacket',
      category: 'outerwear',
      color: 'Black',
      material: 'Leather',
      isFavorite: true,
    ),
    WardrobeItemData(
      id: '16',
      name: 'Denim Jacket',
      category: 'outerwear',
      color: 'Light Wash',
      material: 'Denim',
    ),
    WardrobeItemData(
      id: '17',
      name: 'Trench Coat',
      category: 'outerwear',
      color: 'Stone',
      material: 'Cotton',
    ),
    WardrobeItemData(
      id: '18',
      name: 'Leather Chelsea Boots',
      category: 'footwear',
      color: 'Black',
      material: 'Leather',
      isFavorite: true,
    ),
    WardrobeItemData(
      id: '19',
      name: 'White Sneakers',
      category: 'footwear',
      color: 'White',
      material: 'Canvas',
    ),
    WardrobeItemData(
      id: '20',
      name: 'Loafers',
      category: 'footwear',
      color: 'Brown',
      material: 'Suede',
    ),
    WardrobeItemData(
      id: '21',
      name: 'Dress Oxfords',
      category: 'footwear',
      color: 'Tan',
      material: 'Leather',
    ),
    WardrobeItemData(
      id: '22',
      name: 'Leather Belt',
      category: 'accessories',
      color: 'Black',
      material: 'Leather',
      isFavorite: true,
    ),
    WardrobeItemData(
      id: '23',
      name: 'Silk Tie',
      category: 'accessories',
      color: 'Navy',
      material: 'Silk',
    ),
    WardrobeItemData(
      id: '24',
      name: 'Watch',
      category: 'accessories',
      color: 'Silver',
      material: 'Stainless Steel',
      isFavorite: true,
    ),
  ];

  static List<WardrobeItemData> itemsForCategory(String categoryId) {
    if (categoryId == 'all') return items;
    return items.where((item) => item.category == categoryId).toList();
  }

  static int countForCategory(String categoryId) {
    if (categoryId == 'all') return items.length;
    return items.where((item) => item.category == categoryId).length;
  }
}

/// Configuration for an add-item category.
class AddItemCategoryConfig {
  const AddItemCategoryConfig({
    required this.id,
    required this.name,
    required this.iconName,
    required this.types,
  });

  final String id;
  final String name;
  final String iconName;
  final List<String> types;

  /// Maps to the [WardrobeItemData.category] value used in existing items.
  String get wardrobeCategoryId {
    switch (id) {
      case 'tops':
        return 'tops';
      case 'bottoms':
        return 'bottoms';
      case 'shoes':
        return 'footwear';
      case 'layers':
        return 'outerwear';
      default:
        return id;
    }
  }
}

/// Configuration for a color option in the add-item flow.
class ColorOption {
  const ColorOption({required this.name, required this.colorValue});

  final String name;
  final int colorValue;
}

/// Configuration for a texture option in the add-item flow.
class TextureOption {
  const TextureOption({required this.name});

  final String name;
}

/// Static config data for the add-item flow.
abstract final class AddItemConfig {
  static const List<AddItemCategoryConfig> categories = [
    AddItemCategoryConfig(
      id: 'tops',
      name: 'Tops',
      iconName: 'person_rounded',
      types: [
        'T-Shirt',
        'Button-Down',
        'Dress Shirt',
        'Polo',
        'Turtleneck',
        'Tank Top',
        'Henley',
        'Sweater',
        'Hoodie',
        'Blouse',
        'Crop Top',
        'Bodysuit',
      ],
    ),
    AddItemCategoryConfig(
      id: 'bottoms',
      name: 'Bottoms',
      iconName: 'accessibility_rounded',
      types: [
        'Jeans',
        'Chinos',
        'Trousers',
        'Shorts',
        'Cargo Pants',
        'Sweatpants',
        'Leggings',
        'Skirt',
        'Joggers',
      ],
    ),
    AddItemCategoryConfig(
      id: 'shoes',
      name: 'Shoes',
      iconName: 'directions_walk_rounded',
      types: [
        'Sneakers',
        'Boots',
        'Loafers',
        'Oxfords',
        'Sandals',
        'Slides',
        'Heels',
        'Flats',
        'Espadrilles',
        'Mules',
      ],
    ),
    AddItemCategoryConfig(
      id: 'layers',
      name: 'Layers',
      iconName: 'checkroom_rounded',
      types: [
        'Blazer',
        'Jacket',
        'Coat',
        'Cardigan',
        'Vest',
        'Bomber',
        'Denim Jacket',
        'Leather Jacket',
        'Peacoat',
      ],
    ),
  ];

  static const List<ColorOption> colors = [
    ColorOption(name: 'Black', colorValue: 0xFF000000),
    ColorOption(name: 'White', colorValue: 0xFFFFFFFF),
    ColorOption(name: 'Navy', colorValue: 0xFF1A237E),
    ColorOption(name: 'Charcoal', colorValue: 0xFF333333),
    ColorOption(name: 'Grey', colorValue: 0xFF9E9E9E),
    ColorOption(name: 'Beige', colorValue: 0xFFF5F5DC),
    ColorOption(name: 'Brown', colorValue: 0xFF795548),
    ColorOption(name: 'Burgundy', colorValue: 0xFF880E4F),
    ColorOption(name: 'Olive', colorValue: 0xFF556B2F),
    ColorOption(name: 'Khaki', colorValue: 0xFFC3B091),
    ColorOption(name: 'Cream', colorValue: 0xFFFDF5E6),
    ColorOption(name: 'Light Blue', colorValue: 0xFF81D4FA),
    ColorOption(name: 'Blush', colorValue: 0xFFDEBCCD),
    ColorOption(name: 'Tan', colorValue: 0xFFD2B48C),
    ColorOption(name: 'Silver', colorValue: 0xFFBDBDBD),
    ColorOption(name: 'Gold', colorValue: 0xFFD4AF37),
    ColorOption(name: 'Indigo', colorValue: 0xFF3F51B5),
    ColorOption(name: 'Stone', colorValue: 0xFFA0A0A0),
  ];

  static const List<TextureOption> textures = [
    TextureOption(name: 'Cotton'),
    TextureOption(name: 'Linen'),
    TextureOption(name: 'Wool'),
    TextureOption(name: 'Cashmere'),
    TextureOption(name: 'Silk'),
    TextureOption(name: 'Denim'),
    TextureOption(name: 'Leather'),
    TextureOption(name: 'Suede'),
    TextureOption(name: 'Canvas'),
    TextureOption(name: 'Polyester'),
    TextureOption(name: 'Velvet'),
    TextureOption(name: 'Knit'),
    TextureOption(name: 'Jersey'),
    TextureOption(name: 'Tweed'),
    TextureOption(name: 'Corduroy'),
    TextureOption(name: 'Fleece'),
  ];
}
