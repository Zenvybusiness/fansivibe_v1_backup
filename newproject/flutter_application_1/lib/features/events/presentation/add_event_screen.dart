import 'package:flutter/material.dart';
import 'package:fansivibe/features/events/data/event_mock_data.dart';
import 'package:fansivibe/shared/components/fansi_button.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

class AddEventScreen extends StatefulWidget {
  const AddEventScreen({super.key});

  @override
  State<AddEventScreen> createState() => _AddEventScreenState();
}

class _AddEventScreenState extends State<AddEventScreen> {
  final _nameController = TextEditingController();
  String? _selectedDate;
  String? _selectedTime;
  EventType? _selectedType;
  int _nextId = 5;

  bool get _isValid =>
      _nameController.text.trim().isNotEmpty &&
      _selectedDate != null &&
      _selectedTime != null &&
      _selectedType != null;

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: now.add(const Duration(days: 7)),
      firstDate: now,
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
      final months = [
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
      setState(() {
        _selectedDate =
            '${months[picked.month - 1]} ${picked.day}, ${picked.year}';
      });
    }
  }

  Future<void> _pickTime() async {
    final now = TimeOfDay.now();
    final picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(
        hour: now.hour + 1 > 23 ? 18 : now.hour + 1,
        minute: 0,
      ),
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
      final hour = picked.hourOfPeriod;
      final minute = picked.minute.toString().padLeft(2, '0');
      final period = picked.period == DayPeriod.am ? 'AM' : 'PM';
      setState(() {
        _selectedTime = '${hour == 0 ? 12 : hour}:$minute $period';
      });
    }
  }

  void _addEvent() {
    if (!_isValid) return;

    final event = UserEvent(
      id: (_nextId++).toString(),
      name: _nameController.text.trim(),
      date: _selectedDate!,
      time: _selectedTime!,
      eventType: _selectedType!,
    );

    Navigator.of(context).pop<UserEvent>(event);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Add Event'),
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
                          'New Event',
                          style: theme.textTheme.displayLarge?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: FansivibeColors.textPrimary,
                            fontSize: 28,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Fill in the details below',
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
                          value: _selectedDate,
                          hint: 'Select date',
                          onTap: _pickDate,
                        ),
                        const SizedBox(height: 24),

                        // Time
                        _buildFieldLabel(context, 'Time'),
                        const SizedBox(height: 8),
                        _buildPickerTile(
                          context,
                          icon: Icons.access_time_rounded,
                          value: _selectedTime,
                          hint: 'Select time',
                          onTap: _pickTime,
                        ),
                        const SizedBox(height: 24),

                        // Event type
                        _buildFieldLabel(context, 'Event Type'),
                        const SizedBox(height: 12),
                        _buildEventTypeGrid(context),
                        const SizedBox(height: 32),

                        // Add button
                        SizedBox(
                          width: double.infinity,
                          child: FansiButton.primary(
                            label: 'Add Event',
                            icon: Icons.add_rounded,
                            onPressed: _isValid ? _addEvent : null,
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
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(
          color: FansivibeColors.textSecondary.withValues(alpha: 0.2),
        ),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(
          color: FansivibeColors.textSecondary.withValues(alpha: 0.2),
        ),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
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
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(
          color: FansivibeColors.surface,
          borderRadius: BorderRadius.circular(12),
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
              borderRadius: BorderRadius.circular(12),
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
