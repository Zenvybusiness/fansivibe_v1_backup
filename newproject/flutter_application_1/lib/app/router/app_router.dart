import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/app/router/router_shell.dart';
import 'package:fansivibe/features/discover/data/discover_mock_data.dart';
import 'package:fansivibe/features/discover/presentation/discover_screen.dart';
import 'package:fansivibe/features/discover/presentation/look_details_screen.dart';
import 'package:fansivibe/features/events/data/event_mock_data.dart';
import 'package:fansivibe/features/events/presentation/add_event_screen.dart';
import 'package:fansivibe/features/events/presentation/event_details_screen.dart';
import 'package:fansivibe/features/events/presentation/event_list_screen.dart';
import 'package:fansivibe/features/grooming/data/grooming_mock_data.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_details_screen.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_input_screen.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_processing_screen.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_result_screen.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/presentation/face_processing_screen.dart';
import 'package:fansivibe/features/hairstyle/presentation/face_scan_screen.dart';
import 'package:fansivibe/features/hairstyle/presentation/hairstyle_details_screen.dart';
import 'package:fansivibe/features/hairstyle/presentation/hairstyle_result_screen.dart';
import 'package:fansivibe/features/home/presentation/daily_outfit_screen.dart';
import 'package:fansivibe/features/home/presentation/home_screen.dart';
import 'package:fansivibe/features/outfit_builder/presentation/build_outfit_screen.dart';
import 'package:fansivibe/features/outfit_builder/presentation/outfit_generation_screen.dart';
import 'package:fansivibe/features/outfit_builder/presentation/outfit_recommendation_screen.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_analysis_screen.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_processing_screen.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_scan_screen.dart';
import 'package:fansivibe/features/profile/presentation/preferences_screen.dart';
import 'package:fansivibe/features/profile/presentation/profile_screen.dart';
import 'package:fansivibe/features/profile/presentation/saved_looks_screen.dart';
import 'package:fansivibe/features/profile/presentation/settings_screen.dart';
import 'package:fansivibe/features/profile/presentation/subscription_screen.dart';
import 'package:fansivibe/features/profile/presentation/support_screen.dart';
import 'package:fansivibe/features/stylist/presentation/stylist_screen.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/presentation/add_wardrobe_category_screen.dart';
import 'package:fansivibe/features/wardrobe/presentation/add_wardrobe_item_screen.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_item_details_screen.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_screen.dart';

final List<RouteBase> appRoutes = [
  StatefulShellRoute.indexedStack(
    builder: (context, state, navigationShell) {
      return RouterShell(navigationShell: navigationShell);
    },
    branches: [
      StatefulShellBranch(
        routes: [
          GoRoute(
            path: '/home',
            name: RouteNames.home,
            builder: (context, state) => const HomeScreen(),
            routes: [
              GoRoute(
                path: 'daily-outfit',
                name: RouteNames.dailyOutfit,
                builder: (context, state) => const DailyOutfitScreen(),
              ),
            ],
          ),
        ],
      ),
      StatefulShellBranch(
        routes: [
          GoRoute(
            path: '/discover',
            name: RouteNames.discover,
            builder: (context, state) => const DiscoverScreen(),
            routes: [
              GoRoute(
                path: 'look-details',
                name: RouteNames.lookDetails,
                builder: (context, state) {
                  final look = state.extra as DiscoverLookData?;
                  return look != null
                      ? LookDetailsScreen(look: look)
                      : const SizedBox();
                },
              ),
            ],
          ),
        ],
      ),
      StatefulShellBranch(
        routes: [
          GoRoute(
            path: '/stylist',
            name: RouteNames.stylist,
            builder: (context, state) => const StylistScreen(),
            routes: [
              GoRoute(
                path: 'scan-outfit',
                name: RouteNames.scanOutfit,
                builder: (context, state) => const OutfitScanScreen(),
                routes: [
                  GoRoute(
                    path: 'processing',
                    name: RouteNames.scanProcessing,
                    builder: (context, state) {
                      final localPath = state.extra as String?;
                      return OutfitProcessingScreen(
                        capturedImagePath: localPath,
                      );
                    },
                    routes: [
                      GoRoute(
                        path: 'analysis',
                        name: RouteNames.scanAnalysis,
                        builder: (context, state) {
                          final localPath = state.extra as String?;
                          return OutfitAnalysisScreen(
                            capturedImagePath: localPath,
                          );
                        },
                      ),
                    ],
                  ),
                ],
              ),
              GoRoute(
                path: 'build-outfit',
                name: RouteNames.buildOutfit,
                builder: (context, state) => const BuildOutfitScreen(),
                routes: [
                  GoRoute(
                    path: 'generation',
                    name: RouteNames.outfitGeneration,
                    builder: (context, state) {
                      final data = state.extra as Map<String, String>?;
                      if (data == null) return const SizedBox();
                      return OutfitGenerationScreen(
                        occasion: data['occasion']!,
                        mood: data['mood']!,
                        fit: data['fit']!,
                        colorPalette: data['colorPalette']!,
                      );
                    },
                    routes: [
                      GoRoute(
                        path: 'recommendation',
                        name: RouteNames.outfitRecommendation,
                        builder: (context, state) =>
                            const OutfitRecommendationScreen(),
                      ),
                    ],
                  ),
                ],
              ),
              GoRoute(
                path: 'hairstyle',
                name: RouteNames.hairstyle,
                builder: (context, state) => const FaceScanScreen(),
                routes: [
                  GoRoute(
                    path: 'processing',
                    name: RouteNames.hairstyleProcessing,
                    builder: (context, state) => const FaceProcessingScreen(),
                    routes: [
                      GoRoute(
                        path: 'result',
                        name: RouteNames.hairstyleResult,
                        builder: (context, state) =>
                            const HairstyleResultScreen(),
                        routes: [
                          GoRoute(
                            path: 'details',
                            name: RouteNames.hairstyleDetails,
                            builder: (context, state) {
                              final rec =
                                  state.extra as HairstyleRecommendation?;
                              return rec != null
                                  ? HairstyleDetailsScreen(recommendation: rec)
                                  : const SizedBox();
                            },
                          ),
                        ],
                      ),
                    ],
                  ),
                ],
              ),
              GoRoute(
                path: 'grooming',
                name: RouteNames.grooming,
                builder: (context, state) => const GroomingInputScreen(),
                routes: [
                  GoRoute(
                    path: 'processing',
                    name: RouteNames.groomingProcessing,
                    builder: (context, state) {
                      final data = state.extra as Map<String, String>?;
                      if (data == null) return const SizedBox();
                      return GroomingProcessingScreen(
                        faceShape: data['faceShape']!,
                        beardStyle: data['beardStyle']!,
                        beardDensity: data['beardDensity']!,
                        beardColor: data['beardColor']!,
                      );
                    },
                    routes: [
                      GoRoute(
                        path: 'result',
                        name: RouteNames.groomingResult,
                        builder: (context, state) {
                          final data = state.extra as Map<String, String>?;
                          if (data == null) return const SizedBox();
                          return GroomingResultScreen(
                            faceShape: data['faceShape']!,
                            beardStyle: data['beardStyle']!,
                            beardDensity: data['beardDensity']!,
                            beardColor: data['beardColor']!,
                          );
                        },
                        routes: [
                          GoRoute(
                            path: 'details',
                            name: RouteNames.groomingDetails,
                            builder: (context, state) {
                              final rec =
                                  state.extra as GroomingRecommendation?;
                              return rec != null
                                  ? GroomingDetailsScreen(recommendation: rec)
                                  : const SizedBox();
                            },
                          ),
                        ],
                      ),
                    ],
                  ),
                ],
              ),
              GoRoute(
                path: 'events',
                name: RouteNames.events,
                builder: (context, state) => const EventListScreen(),
                routes: [
                  GoRoute(
                    path: 'add',
                    name: RouteNames.eventAdd,
                    builder: (context, state) => const AddEventScreen(),
                  ),
                  GoRoute(
                    path: 'details',
                    name: RouteNames.eventDetails,
                    builder: (context, state) {
                      final event = state.extra as UserEvent?;
                      return event != null
                          ? EventDetailsScreen(event: event)
                          : const SizedBox();
                    },
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
      StatefulShellBranch(
        routes: [
          GoRoute(
            path: '/wardrobe',
            name: RouteNames.wardrobe,
            builder: (context, state) => const WardrobeScreen(),
            routes: [
              GoRoute(
                path: 'add-category',
                name: RouteNames.wardrobeAddCategory,
                builder: (context, state) => const AddWardrobeCategoryScreen(),
              ),
              GoRoute(
                path: 'add-item',
                name: RouteNames.wardrobeAddItem,
                builder: (context, state) {
                  final category = state.extra as AddItemCategoryConfig?;
                  return category != null
                      ? AddWardrobeItemScreen(category: category)
                      : const SizedBox();
                },
              ),
              GoRoute(
                path: 'item-details',
                name: RouteNames.wardrobeItemDetails,
                builder: (context, state) {
                  final item = state.extra as WardrobeItemData?;
                  return item != null
                      ? WardrobeItemDetailsScreen(item: item)
                      : const SizedBox();
                },
              ),
            ],
          ),
        ],
      ),
      StatefulShellBranch(
        routes: [
          GoRoute(
            path: '/profile',
            name: RouteNames.profile,
            builder: (context, state) => const ProfileScreen(),
            routes: [
              GoRoute(
                path: 'preferences',
                name: RouteNames.profilePreferences,
                builder: (context, state) => const PreferencesScreen(),
              ),
              GoRoute(
                path: 'saved-looks',
                name: RouteNames.profileSavedLooks,
                builder: (context, state) => const SavedLooksScreen(),
              ),
              GoRoute(
                path: 'subscription',
                name: RouteNames.profileSubscription,
                builder: (context, state) => const SubscriptionScreen(),
              ),
              GoRoute(
                path: 'support',
                name: RouteNames.profileSupport,
                builder: (context, state) => const SupportScreen(),
              ),
              GoRoute(
                path: 'settings',
                name: RouteNames.profileSettings,
                builder: (context, state) => const SettingsScreen(),
              ),
            ],
          ),
        ],
      ),
    ],
  ),
];

final GoRouter appRouter = GoRouter(
  initialLocation: '/home',
  routes: appRoutes,
);
