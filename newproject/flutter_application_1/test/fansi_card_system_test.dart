import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/shared/components/fansi_badge.dart';
import 'package:fansivibe/shared/components/fansi_hero_card.dart';
import 'package:fansivibe/shared/components/fansi_image_well.dart';
import 'package:fansivibe/shared/components/fansi_insight_card.dart';
import 'package:fansivibe/shared/components/fansi_mini_card.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

Widget wrap(Widget child) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(
      body: Center(child: SizedBox(width: 320, height: 420, child: child)),
    ),
  );
}

Widget _well() {
  return const FansiImageWell(
    icon: Icons.checkroom_rounded,
    color: FansivibeColors.primary,
  );
}

void main() {
  group('FansiImageWell', () {
    testWidgets('renders icon and label', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: SizedBox(
              width: 200,
              height: 200,
              child: const FansiImageWell(
                icon: Icons.checkroom_rounded,
                color: FansivibeColors.primary,
                label: 'Outfit Image',
              ),
            ),
          ),
        ),
      );

      expect(find.byIcon(Icons.checkroom_rounded), findsOneWidget);
      expect(find.text('Outfit Image'), findsOneWidget);
    });
  });

  group('FansiHeroCard', () {
    testWidgets('renders image, eyebrow, title, subtitle, tags', (
      tester,
    ) async {
      await tester.pumpWidget(
        wrap(
          FansiHeroCard(
            image: _well(),
            eyebrow: "TODAY'S LOOK",
            title: 'Modern Minimalist',
            subtitle: 'Work • Casual Friday',
            tags: const ['Blazer', 'Trousers'],
            badge: const FansiBadge(score: 87),
            onTap: () {},
          ),
        ),
      );

      expect(find.text("TODAY'S LOOK"), findsOneWidget);
      expect(find.text('Modern Minimalist'), findsOneWidget);
      expect(find.text('Work • Casual Friday'), findsOneWidget);
      expect(find.text('Blazer'), findsOneWidget);
      expect(find.text('Trousers'), findsOneWidget);
      expect(find.byType(FansiBadge), findsOneWidget);
    });

    testWidgets('tap invokes callback', (tester) async {
      var tapped = false;
      await tester.pumpWidget(
        wrap(
          FansiHeroCard(
            image: _well(),
            title: 'Title',
            onTap: () => tapped = true,
          ),
        ),
      );

      await tester.tap(find.byType(FansiHeroCard));
      await tester.pump();
      expect(tapped, isTrue);
    });

    testWidgets('enforces 65/35 image/content split', (tester) async {
      await tester.pumpWidget(
        wrap(FansiHeroCard(image: _well(), title: 'Title')),
      );

      final column = tester.widget<Column>(find.byType(Column).first);
      final expanded = column.children.whereType<Expanded>().toList();
      expect(expanded, hasLength(2));
      expect(expanded[0].flex, 65);
      expect(expanded[1].flex, 35);
    });

    testWidgets('no overflow at small size with large text scale', (
      tester,
    ) async {
      tester.platformDispatcher.textScaleFactorTestValue = 1.5;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: Center(
              child: SizedBox(
                width: 240,
                height: 320,
                child: FansiHeroCard(
                  image: _well(),
                  eyebrow: "TODAY'S LOOK",
                  title: 'A very long editorial headline title',
                  subtitle:
                      'A long supporting description line that keeps going',
                  tags: const ['Long Tag One', 'Long Tag Two'],
                ),
              ),
            ),
          ),
        ),
      );

      expect(tester.takeException(), isNull);
    });
  });

  group('FansiMiniCard', () {
    testWidgets('renders image, title, meta, badge', (tester) async {
      await tester.pumpWidget(
        wrap(
          FansiMiniCard(
            image: _well(),
            title: 'Leather Chelsea Boots',
            meta: 'Black',
            badge: const Icon(
              Icons.favorite_rounded,
              size: 14,
              color: FansivibeColors.primary,
            ),
            onTap: () {},
          ),
        ),
      );

      expect(find.text('Leather Chelsea Boots'), findsOneWidget);
      expect(find.text('Black'), findsOneWidget);
      expect(find.byIcon(Icons.favorite_rounded), findsOneWidget);
    });

    testWidgets('tap invokes callback', (tester) async {
      var tapped = false;
      await tester.pumpWidget(
        wrap(
          FansiMiniCard(
            image: _well(),
            title: 'Item',
            onTap: () => tapped = true,
          ),
        ),
      );

      await tester.tap(find.byType(FansiMiniCard));
      await tester.pump();
      expect(tapped, isTrue);
    });

    testWidgets('enforces 75/25 image/content split', (tester) async {
      await tester.pumpWidget(wrap(FansiMiniCard(image: _well(), title: 'X')));

      final column = tester.widget<Column>(find.byType(Column).first);
      final expanded = column.children.whereType<Expanded>().toList();
      expect(expanded, hasLength(2));
      expect(expanded[0].flex, 75);
      expect(expanded[1].flex, 25);
    });
  });

  group('FansiInsightCard', () {
    testWidgets('renders icon, title, eyebrow, body, action', (tester) async {
      var acted = false;
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: Center(
              child: SizedBox(
                width: 320,
                child: FansiInsightCard(
                  icon: Icons.lightbulb_outline_rounded,
                  title: 'Wardrobe Gap Detected',
                  eyebrow: 'AI Insight',
                  body:
                      'You have 3 navy blazers but no lightweight spring jackets.',
                  accentColor: FansivibeColors.accentGold,
                  actionLabel: 'View Recommendations',
                  onActionPressed: () => acted = true,
                ),
              ),
            ),
          ),
        ),
      );

      expect(find.byIcon(Icons.lightbulb_outline_rounded), findsOneWidget);
      expect(find.text('Wardrobe Gap Detected'), findsOneWidget);
      expect(find.text('AI Insight'), findsOneWidget);
      expect(find.text('View Recommendations'), findsOneWidget);

      await tester.tap(find.text('View Recommendations'));
      await tester.pump();
      expect(acted, isTrue);
    });

    testWidgets('enforces 20/80 visual/content split', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: Center(
              child: SizedBox(
                width: 320,
                child: FansiInsightCard(
                  icon: Icons.lightbulb_outline_rounded,
                  title: 'Title',
                  body: 'Body',
                ),
              ),
            ),
          ),
        ),
      );

      final row = tester.widget<Row>(find.byType(Row).first);
      final expanded = row.children.whereType<Expanded>().toList();
      expect(expanded, hasLength(2));
      expect(expanded[0].flex, 20);
      expect(expanded[1].flex, 80);
    });

    testWidgets('tap on card invokes callback', (tester) async {
      var tapped = false;
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: Center(
              child: SizedBox(
                width: 320,
                child: FansiInsightCard(
                  icon: Icons.insights_rounded,
                  title: 'Title',
                  body: 'Body',
                  onTap: () => tapped = true,
                ),
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.byType(FansiInsightCard));
      await tester.pump();
      expect(tapped, isTrue);
    });
  });
}
