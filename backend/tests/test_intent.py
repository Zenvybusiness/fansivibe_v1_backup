from app.ai import intent


def test_greeting():
    assert intent.classify("hi") == intent.INTENT_GREETING
    assert intent.classify("Hello!") == intent.INTENT_GREETING


def test_thanks():
    assert intent.classify("thanks!") == intent.INTENT_THANKS


def test_navigate():
    assert intent.classify("open my wardrobe") == intent.INTENT_NAVIGATE
    assert intent.classify("take me to discover") == intent.INTENT_NAVIGATE


def test_outfit_intent():
    assert intent.classify("what should I wear?") == intent.INTENT_OUTFIT
    assert intent.classify("suggest an outfit for a date") == intent.INTENT_OUTFIT


def test_hairstyle_intent():
    assert intent.classify("best hairstyle for me") == intent.INTENT_HAIRSTYLE


def test_grooming_intent():
    assert intent.classify("which beard style suits me") == intent.INTENT_GROOMING
    assert intent.classify("glasses recommendations") == intent.INTENT_GROOMING


def test_wardrobe_intent():
    assert intent.classify("show my wardrobe") == intent.INTENT_WARDROBE
    assert intent.classify("what do I own") == intent.INTENT_WARDROBE


def test_unknown_short_message():
    assert intent.classify("yes") == intent.INTENT_CLARIFY


def test_detect_occasion():
    assert intent.detect_occasion("what should I wear to work") == "office"
    assert intent.detect_occasion("date night outfit") == "date"
    assert intent.detect_occasion("casual look please") == "casual"
    assert intent.detect_occasion("just a normal day") is None
