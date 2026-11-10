import 'package:flutter/material.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/theme/fansivibe_typography.dart';

/// 20 major city centroids matching backend `MAJOR_CITIES` (Stage 2 P1-3).
const List<String> kMajorCities = [
  'London',
  'Paris',
  'New York',
  'Tokyo',
  'Seattle',
  'San Francisco',
  'Los Angeles',
  'Chicago',
  'Berlin',
  'Sydney',
  'Toronto',
  'Milan',
  'Rome',
  'Oslo',
  'Stockholm',
  'Amsterdam',
  'Madrid',
  'Barcelona',
  'Singapore',
  'Seoul',
];

/// Shows the manual city selection sheet (Digital Atelier modal).
///
/// Returns:
/// - A trimmed city name (e.g. `'Seattle'`) on confirmation.
/// - `''` (empty string) if location was cleared.
/// - `null` if dismissed without changes.
Future<String?> showCitySelectionSheet(
  BuildContext context, {
  String? currentCity,
}) {
  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (sheetContext) => CitySelectionSheet(initialCity: currentCity),
  );
}

/// Modal bottom sheet allowing manual city selection without GPS permission.
class CitySelectionSheet extends StatefulWidget {
  const CitySelectionSheet({super.key, this.initialCity});

  final String? initialCity;

  @override
  State<CitySelectionSheet> createState() => _CitySelectionSheetState();
}

class _CitySelectionSheetState extends State<CitySelectionSheet> {
  late final TextEditingController _controller;
  String _filterQuery = '';

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.initialCity ?? '');
    _controller.addListener(() {
      setState(() {
        _filterQuery = _controller.text.trim().toLowerCase();
      });
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _onSelectCity(String city) {
    Navigator.of(context).pop(city.trim());
  }

  /// Enter selects an exact supported city; free text never claims weather
  /// support the backend cannot resolve (only `MAJOR_CITIES` exist).
  void _onConfirmInput() {
    final query = _controller.text.trim().toLowerCase();
    if (query.isEmpty) return;
    for (final city in kMajorCities) {
      if (city.toLowerCase() == query) {
        Navigator.of(context).pop(city);
        return;
      }
    }
  }

  void _onClearLocation() {
    Navigator.of(context).pop('');
  }

  @override
  Widget build(BuildContext context) {
    final viewInsets = MediaQuery.of(context).viewInsets;
    final maxSheetHeight = MediaQuery.of(context).size.height * 0.85;

    final filteredCities = kMajorCities.where((c) {
      if (_filterQuery.isEmpty) return true;
      return c.toLowerCase().contains(_filterQuery);
    }).toList();

    return Container(
      constraints: BoxConstraints(maxHeight: maxSheetHeight),
      margin: EdgeInsets.only(bottom: viewInsets.bottom),
      decoration: BoxDecoration(
        color: FansivibeColors.surfaceContainerLow,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        border: Border.all(
          color: FansivibeColors.outlineVariant.withValues(alpha: 0.35),
          width: 1,
        ),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Drag Handle
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: FansivibeColors.outlineVariant.withValues(
                      alpha: 0.6,
                    ),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // Title and Subtitle
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'WEATHER LOCATION',
                        style: FansivibeTypography.labelSmallWithFamily
                            .copyWith(
                              color: FansivibeColors.primary,
                              letterSpacing: 2.0,
                              fontWeight: FontWeight.w700,
                              fontSize: 10,
                            ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Select Your City',
                        style: TextStyle(
                          fontFamily: FansivibeTypography.displayFamily,
                          fontSize: 22,
                          fontWeight: FontWeight.w600,
                          color: FansivibeColors.onSurface,
                        ),
                      ),
                    ],
                  ),
                  if (widget.initialCity != null &&
                      widget.initialCity!.isNotEmpty)
                    TextButton(
                      onPressed: _onClearLocation,
                      child: Text(
                        'Clear',
                        style: TextStyle(
                          color: FansivibeColors.error,
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                'Choose a city for local weather. Coarse city resolution only — no GPS required.',
                style: FansivibeTypography.bodyMediumWithFamily.copyWith(
                  color: FansivibeColors.secondary,
                  fontSize: 13,
                  height: 1.4,
                ),
              ),
              const SizedBox(height: 16),

              // Search Field (filters the supported cities below)
              Container(
                decoration: BoxDecoration(
                  color: FansivibeColors.surfaceContainer,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: FansivibeColors.outlineVariant.withValues(
                      alpha: 0.4,
                    ),
                  ),
                ),
                child: TextField(
                  controller: _controller,
                  textInputAction: TextInputAction.done,
                  onSubmitted: (_) => _onConfirmInput(),
                  style: TextStyle(
                    color: FansivibeColors.onSurface,
                    fontSize: 14,
                  ),
                  decoration: InputDecoration(
                    hintText: 'Search supported cities',
                    hintStyle: TextStyle(
                      color: FansivibeColors.secondary.withValues(alpha: 0.6),
                      fontSize: 14,
                    ),
                    prefixIcon: Icon(
                      Icons.search_rounded,
                      size: 20,
                      color: FansivibeColors.secondary,
                    ),
                    suffixIcon: _controller.text.isNotEmpty
                        ? IconButton(
                            icon: const Icon(Icons.clear_rounded, size: 18),
                            color: FansivibeColors.secondary,
                            onPressed: () => _controller.clear(),
                          )
                        : null,
                    border: InputBorder.none,
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 12,
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 16),

              // Supported Cities Section
              Text(
                'SUPPORTED CITIES',
                style: FansivibeTypography.labelSmallWithFamily.copyWith(
                  color: FansivibeColors.secondary,
                  letterSpacing: 1.5,
                  fontSize: 10,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 10),

              // City Chips
              Expanded(
                child: SingleChildScrollView(
                  physics: const BouncingScrollPhysics(),
                  child: filteredCities.isEmpty
                      ? Text(
                          'No supported city matches "${_controller.text.trim()}".',
                          style: FansivibeTypography.bodyMediumWithFamily
                              .copyWith(
                                color: FansivibeColors.secondary,
                                fontSize: 13,
                              ),
                        )
                      : Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: filteredCities.map((city) {
                            final isSelected =
                                widget.initialCity != null &&
                                widget.initialCity!.toLowerCase() ==
                                    city.toLowerCase();
                            return Semantics(
                              button: true,
                              label: 'Select $city',
                              child: InkWell(
                                onTap: () => _onSelectCity(city),
                                borderRadius: FansivibeRadius.fullBorder,
                                child: Container(
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 14,
                                    vertical: 8,
                                  ),
                                  decoration: BoxDecoration(
                                    color: isSelected
                                        ? FansivibeColors.primary.withValues(
                                            alpha: 0.2,
                                          )
                                        : FansivibeColors.surfaceContainer,
                                    borderRadius: FansivibeRadius.fullBorder,
                                    border: Border.all(
                                      color: isSelected
                                          ? FansivibeColors.primary
                                          : FansivibeColors.outlineVariant
                                                .withValues(alpha: 0.35),
                                      width: isSelected ? 1.5 : 1,
                                    ),
                                  ),
                                  child: Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      Icon(
                                        Icons.location_city_rounded,
                                        size: 14,
                                        color: isSelected
                                            ? FansivibeColors.primary
                                            : FansivibeColors.secondary,
                                      ),
                                      const SizedBox(width: 6),
                                      Text(
                                        city,
                                        style: FansivibeTypography
                                            .labelSmallWithFamily
                                            .copyWith(
                                              color: isSelected
                                                  ? FansivibeColors.primary
                                                  : FansivibeColors.onSurface,
                                              fontWeight: isSelected
                                                  ? FontWeight.w700
                                                  : FontWeight.w500,
                                              fontSize: 12,
                                            ),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            );
                          }).toList(),
                        ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
