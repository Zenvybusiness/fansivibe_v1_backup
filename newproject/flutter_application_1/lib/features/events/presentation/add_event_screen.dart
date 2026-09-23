import 'package:flutter/material.dart';
import 'package:fansivibe/features/events/data/event_mock_data.dart';
import 'package:fansivibe/features/events/data/event_models.dart';
import 'package:fansivibe/features/events/data/events_repository.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/shared/theme/fansivibe_radius.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';

/// Backend-first add/edit event form (M8-D).
///
/// Create mode posts `POST /v1/events`; edit mode ([event] non-null)
/// puts a full `PUT /v1/events/{id}` replacement and pops the updated
/// backend item. Displayed type labels map to the frozen backend TYPE
/// CODES on submit. Time is optional (`HH:mm` or null); blank location
/// / notes map to null (explicit clearing on update). The backend owns
/// preference updates (R36) — this screen never touches
/// `LearningService` and never mints local IDs.
class AddEventScreen extends StatefulWidget {
  /// Creates an [AddEventScreen] with an optional repository for testing.
  /// Without a repository, uses the live backend implementation.
  /// Pass [event] to edit that backend event instead of creating one.
  const AddEventScreen({this.event, this.repository, super.key});

  /// Backend event under edit, or null to create a new event.
  final EventItem? event;

  /// Backend repository override (tests only).
  final EventsRepository? repository;

  @override
  State<AddEventScreen> createState() => _AddEventScreenState();
}

class _AddEventScreenState extends State<AddEventScreen> {
  late final TextEditingController _nameController;
  late final TextEditingController _locationController;
  late final TextEditingController _notesController;
  DateTime? _selectedDay;
  TimeOfDay? _selectedTime;
  EventType? _selectedType;
  bool _saving = false;

  bool get _isEdit => widget.event != null;

  EventsRepository get _repository =>
      widget.repository ?? EventsRepositoryImpl();

  bool get _isValid =>
      _nameController.text.trim().isNotEmpty &&
      _selectedDay != null &&
      _selectedType != null &&
      !_saving;

  @override
  void initState() {
    super.initState();
    final existing = widget.event;
    _nameController = TextEditingController(text: existing?.title ?? '');
    _locationController = TextEditingController(text: existing?.location ?? '');
    _notesController = TextEditingController(text: existing?.notes ?? '');
    if (existing != null) {
      _selectedDay = DateTime.tryParse(existing.eventDate);
      _selectedType = EventType.byCodeOrNull(existing.eventType);
      final parts = existing.eventTime?.split(':');
      if (parts != null && parts.length == 2) {
        final hour = int.tryParse(parts[0]);
        final minute = int.tryParse(parts[1]);
        if (hour != null && minute != null) {
          _selectedTime = TimeOfDay(hour: hour, minute: minute);
        }
      }
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    _locationController.dispose();
    _notesController.dispose();
    super.dispose();
  }

  String get _dateLabel {
    final day = _selectedDay;
    if (day == null) return 'Select date';
    return '${_months[day.month - 1]} ${day.day}, ${day.year}';
  }

  String get _timeLabel {
    final time = _selectedTime;
    if (time == null) return 'Select time (optional)';
    final hour12 = time.hourOfPeriod == 0 ? 12 : time.hourOfPeriod;
    final minute = time.minute.toString().padLeft(2, '0');
    final period = time.period == DayPeriod.am ? 'AM' : 'PM';
    return '$hour12:$minute $period';
  }

  String get _eventDateWire {
    final day = _selectedDay!;
    final month = day.month.toString().padLeft(2, '0');
    final date = day.day.toString().padLeft(2, '0');
    return '${day.year}-$month-$date';
  }

  String? get _eventTimeWire {
    final time = _selectedTime;
    if (time == null) return null;
    return '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}';
  }

  /// Blank optional text maps to null (absent on create, cleared on PUT).
  String? _optionalText(TextEditingController controller) {
    final text = controller.text.trim();
    return text.isEmpty ? null : controller.text;
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final picked = await showDatePicker(
      context: context,
      initialDate: _selectedDay ?? now.add(const Duration(days: 7)),
      firstDate: today,
      lastDate: now.add(const Duration(days: 365)),
      builder: (context, child) {
        return Theme(
          data: Theme.of(context).copyWith(
            colorScheme: const ColorScheme.dark(
              primary: FansivibeColors.accentGold,
              surface: FansivibeColors.surface,
            ),
          ),
          child: child!,
        );
      },
    );
    if (picked != null) {
      setState(() {
        _selectedDay = picked;
      });
    }
  }

  Future<void> _pickTime() async {
    final now = TimeOfDay.now();
    final picked = await showTimePicker(
      context: context,
      initialTime:
          _selectedTime ??
          TimeOfDay(hour: now.hour + 1 > 23 ? 18 : now.hour + 1, minute: 0),
      builder: (context, child) {
        return Theme(
          data: Theme.of(context).copyWith(
            colorScheme: const ColorScheme.dark(
              primary: FansivibeColors.accentGold,
              surface: FansivibeColors.surface,
            ),
          ),
          child: child!,
        );
      },
    );
    if (picked != null) {
      setState(() {
        _selectedTime = picked;
      });
    }
  }

  Future<void> _submit() async {
    if (!_isValid) return;
    // Phase 2 guests: creating/updating events is account-only —
    // prompt at the button instead of posting into a 401.
    if (isGuestUser) {
      promptGuestSignIn(
        context,
        action: 'Sign in to save events. Browsing stays free.',
      );
      return;
    }
    setState(() => _saving = true);
    try {
      final title = _nameController.text.trim();
      final code = _selectedType!.id;
      final date = _eventDateWire;
      final time = _eventTimeWire;
      final location = _optionalText(_locationController);
      final notes = _optionalText(_notesController);
      if (_isEdit) {
        final updated = await _repository.updateEvent(
          id: widget.event!.id,
          request: EventUpdateRequest(
            title: title,
            eventType: code,
            eventDate: date,
            eventTime: time,
            location: location,
            notes: notes,
          ),
        );
        if (!mounted) return;
        if (updated != null) {
          Navigator.of(context).pop<EventItem>(updated);
        } else {
          _showFailure('Couldn\'t save your changes. Please try again.');
        }
      } else {
        final created = await _repository.createEvent(
          EventCreateRequest(
            title: title,
            eventType: code,
            eventDate: date,
            eventTime: time,
            location: location,
            notes: notes,
          ),
        );
        if (!mounted) return;
        if (created != null) {
          // Return the backend-created item so the caller can show and
          // select it immediately (never a bare bool — the UUID is the
          // only event identity).
          Navigator.of(context).pop<EventItem>(created);
        } else {
          _showFailure('Couldn\'t create your event. Please try again.');
        }
      }
    } finally {
      if (mounted) {
        setState(() => _saving = false);
      }
    }
  }

  void _showFailure(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: FansivibeColors.accentGold,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: FansivibeRadius.smdBorder),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: Text(_isEdit ? 'Edit Event' : 'Add Event'),
        leading: IconButton(
          icon: Icon(Icons.close_rounded, color: FansivibeColors.textPrimary),
          onPressed: () => Navigator.of(context).pop(),
        ),
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
                        Text(
                          _isEdit ? 'Edit Event' : 'New Event',
                          style: theme.textTheme.displayLarge?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: FansivibeColors.textPrimary,
                            fontSize: 28,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          _isEdit
                              ? 'Update the details below'
                              : 'Fill in the details below',
                          style: theme.textTheme.bodyLarge?.copyWith(
                            color: FansivibeColors.textSecondary,
                          ),
                        ),
                        const SizedBox(height: 28),

                        // Event name
                        _buildFieldLabel(context, 'Event Name'),
                        const SizedBox(height: 8),
                        TextField(
                          controller: _nameController,
                          onChanged: (_) => setState(() {}),
                          style: theme.textTheme.bodyLarge?.copyWith(
                            color: FansivibeColors.textPrimary,
                          ),
                          decoration: _inputDecoration(
                            hint: 'e.g. Summer Wedding',
                            icon: Icons.edit_outlined,
                          ),
                        ),
                        const SizedBox(height: 24),

                        // Date
                        _buildFieldLabel(context, 'Date'),
                        const SizedBox(height: 8),
                        _buildPickerTile(
                          context,
                          icon: Icons.calendar_today_outlined,
                          value: _selectedDay != null ? _dateLabel : null,
                          hint: 'Select date',
                          onTap: _pickDate,
                        ),
                        const SizedBox(height: 24),

                        // Time
                        _buildFieldLabel(context, 'Time (optional)'),
                        const SizedBox(height: 8),
                        _buildPickerTile(
                          context,
                          icon: Icons.access_time_rounded,
                          value: _selectedTime != null ? _timeLabel : null,
                          hint: 'Select time (optional)',
                          onTap: _pickTime,
                        ),
                        const SizedBox(height: 24),

                        // Event type
                        _buildFieldLabel(context, 'Event Type'),
                        const SizedBox(height: 12),
                        _buildEventTypeGrid(context),
                        const SizedBox(height: 24),

                        // Location
                        _buildFieldLabel(context, 'Location (optional)'),
                        const SizedBox(height: 8),
                        TextField(
                          controller: _locationController,
                          style: theme.textTheme.bodyLarge?.copyWith(
                            color: FansivibeColors.textPrimary,
                          ),
                          decoration: _inputDecoration(
                            hint: 'e.g. Grand Ballroom',
                            icon: Icons.place_outlined,
                          ),
                        ),
                        const SizedBox(height: 24),

                        // Notes
                        _buildFieldLabel(context, 'Notes (optional)'),
                        const SizedBox(height: 8),
                        TextField(
                          controller: _notesController,
                          maxLines: 3,
                          style: theme.textTheme.bodyLarge?.copyWith(
                            color: FansivibeColors.textPrimary,
                          ),
                          decoration: _inputDecoration(
                            hint: 'e.g. Black tie',
                            icon: Icons.notes_outlined,
                          ),
                        ),
                        const SizedBox(height: 32),

                        // Submit button
                        SizedBox(
                          width: double.infinity,
                          child: FansiButton.primary(
                            label: _saving
                                ? 'Saving…'
                                : (_isEdit ? 'Save Changes' : 'Add Event'),
                            icon: _isEdit
                                ? Icons.check_rounded
                                : Icons.add_rounded,
                            onPressed: _isValid ? _submit : null,
                          ),
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

  Widget _buildFieldLabel(BuildContext context, String label) {
    final theme = Theme.of(context);
    return Text(
      label,
      style: theme.textTheme.titleMedium?.copyWith(
        fontWeight: FontWeight.w600,
        color: FansivibeColors.textPrimary,
      ),
    );
  }

  InputDecoration _inputDecoration({
    required String hint,
    required IconData icon,
  }) {
    return InputDecoration(
      hintText: hint,
      hintStyle: TextStyle(
        color: FansivibeColors.textSecondary.withValues(alpha: 0.5),
      ),
      prefixIcon: Icon(icon, color: FansivibeColors.textSecondary, size: 20),
      filled: true,
      fillColor: FansivibeColors.surface,
      border: OutlineInputBorder(
        borderRadius: FansivibeRadius.smdBorder,
        borderSide: BorderSide(
          color: FansivibeColors.textSecondary.withValues(alpha: 0.2),
        ),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: FansivibeRadius.smdBorder,
        borderSide: BorderSide(
          color: FansivibeColors.textSecondary.withValues(alpha: 0.2),
        ),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: FansivibeRadius.smdBorder,
        borderSide: BorderSide(
          color: FansivibeColors.accentGold.withValues(alpha: 0.6),
        ),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
    );
  }

  Widget _buildPickerTile(
    BuildContext context, {
    required IconData icon,
    required String? value,
    required String hint,
    required VoidCallback onTap,
  }) {
    final theme = Theme.of(context);

    return InkWell(
      onTap: onTap,
      borderRadius: FansivibeRadius.smdBorder,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(
          color: FansivibeColors.surface,
          borderRadius: FansivibeRadius.smdBorder,
          border: Border.all(
            color: FansivibeColors.textSecondary.withValues(alpha: 0.2),
          ),
        ),
        child: Row(
          children: [
            Icon(icon, color: FansivibeColors.textSecondary, size: 20),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                value ?? hint,
                style: theme.textTheme.bodyLarge?.copyWith(
                  color: value != null
                      ? FansivibeColors.textPrimary
                      : FansivibeColors.textSecondary.withValues(alpha: 0.5),
                ),
              ),
            ),
            Icon(
              Icons.chevron_right_rounded,
              color: FansivibeColors.textSecondary,
              size: 20,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEventTypeGrid(BuildContext context) {
    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        childAspectRatio: 2.4,
        crossAxisSpacing: 8,
        mainAxisSpacing: 8,
      ),
      itemCount: EventType.mockTypes.length,
      itemBuilder: (context, index) {
        final type = EventType.mockTypes[index];
        final isSelected = _selectedType?.id == type.id;
        final typeTheme = Theme.of(context);

        return GestureDetector(
          onTap: () => setState(() => _selectedType = type),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            decoration: BoxDecoration(
              color: isSelected
                  ? FansivibeColors.accentGold.withValues(alpha: 0.1)
                  : FansivibeColors.surface,
              borderRadius: FansivibeRadius.smdBorder,
              border: Border.all(
                color: isSelected
                    ? FansivibeColors.accentGold.withValues(alpha: 0.6)
                    : FansivibeColors.textSecondary.withValues(alpha: 0.15),
                width: isSelected ? 1.5 : 1,
              ),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  type.icon,
                  size: 16,
                  color: isSelected
                      ? FansivibeColors.accentGold
                      : FansivibeColors.textSecondary,
                ),
                const SizedBox(width: 6),
                Flexible(
                  child: Text(
                    type.name,
                    style: typeTheme.textTheme.bodySmall?.copyWith(
                      fontWeight: isSelected
                          ? FontWeight.w600
                          : FontWeight.w500,
                      color: isSelected
                          ? FansivibeColors.textPrimary
                          : FansivibeColors.textSecondary,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                if (isSelected) ...[
                  const SizedBox(width: 4),
                  Icon(
                    Icons.check_circle_rounded,
                    size: 14,
                    color: FansivibeColors.accentGold,
                  ),
                ],
              ],
            ),
          ),
        );
      },
    );
  }
}

const List<String> _months = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];
