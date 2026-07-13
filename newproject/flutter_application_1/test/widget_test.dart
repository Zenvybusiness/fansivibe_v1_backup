import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/app/app.dart';

void main() {
  testWidgets('Fansivibe App renders foundation screen', (
    WidgetTester tester,
  ) async {
    // Build our app and trigger a frame.
    await tester.pumpWidget(const FansivibeApp());

    // Verify that the brand name and foundation label are rendered.
    expect(find.text('Fansivibe'), findsOneWidget);
    expect(find.text('Foundation ready'), findsOneWidget);
  });
}
