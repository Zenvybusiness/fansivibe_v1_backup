import 'package:flutter/material.dart';

class EventType {
  const EventType({required this.id, required this.name, required this.icon});

  final String id;
  final String name;
  final IconData icon;

  static const List<EventType> mockTypes = [
    EventType(id: 'casual', name: 'Casual', icon: Icons.wb_sunny_outlined),
    EventType(id: 'formal', name: 'Formal', icon: Icons.diamond_outlined),
    EventType(
      id: 'business',
      name: 'Business',
      icon: Icons.business_center_outlined,
    ),
    EventType(
      id: 'date',
      name: 'Date Night',
      icon: Icons.favorite_outline_rounded,
    ),
    EventType(id: 'party', name: 'Party', icon: Icons.nightlife_rounded),
    EventType(id: 'travel', name: 'Travel', icon: Icons.flight_outlined),
    EventType(
      id: 'workout',
      name: 'Workout',
      icon: Icons.fitness_center_outlined,
    ),
    EventType(id: 'other', name: 'Other', icon: Icons.event_outlined),
  ];
}

class UserEvent {
  const UserEvent({
    required this.id,
    required this.name,
    required this.date,
    required this.time,
    required this.eventType,
    this.hasOutfitRecommendation = false,
  });

  final String id;
  final String name;
  final String date;
  final String time;
  final EventType eventType;
  final bool hasOutfitRecommendation;

  static const List<UserEvent> mockEvents = [
    UserEvent(
      id: '1',
      name: 'Company Gala',
      date: 'Aug 15, 2026',
      time: '7:00 PM',
      eventType: EventType(
        id: 'formal',
        name: 'Formal',
        icon: Icons.diamond_outlined,
      ),
      hasOutfitRecommendation: true,
    ),
    UserEvent(
      id: '2',
      name: 'Weekend Brunch',
      date: 'Jul 20, 2026',
      time: '10:30 AM',
      eventType: EventType(
        id: 'casual',
        name: 'Casual',
        icon: Icons.wb_sunny_outlined,
      ),
      hasOutfitRecommendation: false,
    ),
    UserEvent(
      id: '3',
      name: 'Client Presentation',
      date: 'Jul 25, 2026',
      time: '2:00 PM',
      eventType: EventType(
        id: 'business',
        name: 'Business',
        icon: Icons.business_center_outlined,
      ),
      hasOutfitRecommendation: false,
    ),
    UserEvent(
      id: '4',
      name: 'Anniversary Dinner',
      date: 'Aug 5, 2026',
      time: '8:00 PM',
      eventType: EventType(
        id: 'date',
        name: 'Date Night',
        icon: Icons.favorite_outline_rounded,
      ),
      hasOutfitRecommendation: true,
    ),
  ];
}
