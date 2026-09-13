import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/app/router/router_shell.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/app/router/auth_guard.dart';
import 'package:fansivibe/shared/components/fansi_error_view.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/splash_screen.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/entry_screen.dart';
import 'package:fansivibe/features/assistant/presentation/assistant_screen.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/vibe_select_screen.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/camera_permission_screen.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/photo_capture_screen.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/ai_analysis_screen.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/your_analysis_screen.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/account_creation_screen.dart';
import 'package:fansivibe/features/discover/presentation/discover_screen.dart';
import 'package:fansivibe/features/discover/presentation/look_details_screen.dart';
import 'package:fansivibe/features/events/data/event_models.dart';
import 'package:fansivibe/features/events/presentation/add_event_screen.dart';
import 'package:fansivibe/features/events/presentation/event_details_screen.dart';
import 'package:fansivibe/features/events/presentation/event_list_screen.dart';
import 'package:fansivibe/features/grooming/data/grooming_models.dart';
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
import 'package:fansivibe/features/outfit_builder/outfit_builder.dart';
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

Widget _missingDataScreen() {
  return Scaffold(
    backgroundColor: FansivibeColors.surface,
    body: const FansiErrorView(
      message:
          'Could not load the requested content. Please go back and try again.',
    ),
  );
}

Widget _missingDataScreenWithText(String label) {
  return Scaffold(
    backgroundColor: FansivibeColors.surface,
    body: FansiErrorView(message: label),
  );
}

final List<RouteBase> appRoutes = [
  GoRoute(
    path: '/splash',
    name: RouteNames.splash,
    builder: (context, state) => const SplashScreen(),
  ),
  GoRoute(
    path: '/entry',
    name: RouteNames.entry,
    builder: (context, state) => const EntryScreen(),
  ),
  GoRoute(
    path: '/onboarding/vibe',
    name: RouteNames.vibeSelect,
    builder: (context, state) => const VibeSelectScreen(),
  ),
  GoRoute(
    path: '/onboarding/camera-permission',
    name: RouteNames.cameraPermission,
    builder: (context, state) => const CameraPermissionScreen(),
  ),
  GoRoute(
    path: '/onboarding/photo-capture',
    name: RouteNames.photoCapture,
    builder: (context, state) {
      final extra = state.extra as Map<String, dynamic>?;
      return PhotoCaptureScreen(source: extra?['source'] as String?);
    },
  ),
  GoRoute(
    path: '/onboarding/analysis',
    name: RouteNames.aiAnalysis,
    builder: (context, state) => const AiAnalysisScreen(),
  ),
  GoRoute(
    path: '/onboarding/result',
    name: RouteNames.yourAnalysis,
    builder: (context, state) => const YourAnalysisScreen(),
  ),
  GoRoute(
    path: '/onboarding/account',
    name: RouteNames.accountCreation,
    builder: (context, state) {
      final extra = state.extra as Map<String, dynamic>?;
      return AccountCreationScreen(
        mode: extra?['mode'] as String? ?? 'register',
      );
    },
  ),
  GoRoute(
    path: '/assistant',
    name: RouteNames.assistant,
    builder: (context, state) => const AssistantScreen(),
  ),
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
            builder: (context, state) {
              final extra = state.extra as Map<String, dynamic>?;
              return HomeScreen(onboardingData: extra);
            },
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
                  // The backend catalog code travels verbatim (M14) — never
                  // a local id. Missing extra renders the shared fallback.
                  final lookId = state.extra as String?;
                  return lookId != null
                      ? LookDetailsScreen(lookId: lookId)
                      : _missingDataScreen();
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
                          final runId = state.extra as String?;
                          return OutfitProcessingScreen(
                            runId: runId,
                          );
                        },
                        routes: [
                          GoRoute(
                            path: 'analysis',
                            name: RouteNames.scanAnalysis,
                            builder: (context, state) {
                              final analysisResult =
                                  state.extra as Map<String, dynamic>?;
                              return OutfitAnalysisScreen(
                                analysisResult: analysisResult,
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
                      if (data == null) {
                        return _missingDataScreenWithText(
                          'Missing outfit preferences.',
                        );
                      }
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
                        builder: (context, state) {
                          final data = state.extra as Map<String, dynamic>?;
                          final recJson =
                              data?['recommendation'] as Map<String, dynamic>?;
                          final reqJson =
                              data?['request'] as Map<String, dynamic>?;
                          if (recJson == null || reqJson == null) {
                            return _missingDataScreenWithText(
                              'Missing outfit recommendation.',
                            );
                          }
                          return OutfitRecommendationScreen(
                            recommendation: OutfitRecommendation.fromJson(
                              Map<String, dynamic>.from(recJson),
                            ),
                            request: OutfitGenerateRequest.fromJson(
                              Map<String, dynamic>.from(reqJson),
                            ),
                          );
                        },
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
                builder: (context, state) {
                  // Optional real-scan image handoff from FaceScanScreen
                  // (in-memory bytes only; absent on skip/profile-only path).
                  final extra = state.extra as Map<String, dynamic>?;
                  return FaceProcessingScreen(
                    imageBytes: extra?['imageBytes'] as Uint8List?,
                    imageFilename: extra?['imageFilename'] as String?,
                    imageContentType: extra?['imageContentType'] as String?,
                  );
                },
                    routes: [
                      GoRoute(
                        path: 'result',
                        name: RouteNames.hairstyleResult,
                        builder: (context, state) {
                          final result = state.extra as HairstyleAnalysisResult?;
                          return HairstyleResultScreen(result: result);
                        },
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
                      if (data == null) {
                        return _missingDataScreenWithText(
                          'Missing grooming data.',
                        );
                      }
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
                          if (data == null) {
                            return _missingDataScreenWithText(
                              'Missing grooming data.',
                            );
                          }
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
                                  : _missingDataScreen();
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
                      final event = state.extra as EventItem?;
                      return event != null
                          ? EventDetailsScreen(event: event)
                          : _missingDataScreen();
                    },
                  ),
                  GoRoute(
                    path: 'edit',
                    name: RouteNames.eventEdit,
                    builder: (context, state) {
                      final event = state.extra as EventItem?;
                      return event != null
                          ? AddEventScreen(event: event)
                          : _missingDataScreen();
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
                      : _missingDataScreen();
                },
              ),
              GoRoute(
                path: 'item-details',
                name: RouteNames.wardrobeItemDetails,
                builder: (context, state) {
                  final itemId = state.extra as String?;
                  return itemId != null
                      ? WardrobeItemDetailsScreen(itemId: itemId)
                      : _missingDataScreen();
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
  initialLocation: '/entry',
  routes: appRoutes,
  // 21.2 (M1) declarative auth guard: unauthenticated deep links into
  // the shell land on entry; authenticated users are never forced away
  // (no loops, no network on navigation — see auth_guard.dart).
  redirect: (context, state) => authRedirect(
    state.uri.path,
    isAuthenticated: AuthSession.isAuthenticated,
  ),
);
