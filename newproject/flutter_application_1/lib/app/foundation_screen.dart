import 'package:flutter/material.dart';

/// A minimal temporary screen to verify setup and theme loading.
class FoundationScreen extends StatelessWidget {
  /// Creates a [FoundationScreen].
  const FoundationScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text('Fansivibe', style: theme.textTheme.displayLarge),
            const SizedBox(height: 16),
            Text(
              'Foundation ready',
              style: theme.textTheme.bodyLarge?.copyWith(
                color: theme.primaryColor,
                letterSpacing: 1.2,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
