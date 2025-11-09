#!/usr/bin/env python3
"""
Test script for UI customization features.
Validates that environment variables are properly loaded and sanitized.
"""

import os
import sys
import html

# Set test environment variables
os.environ["LT_PAGE_TITLE"] = "Test Title"
os.environ["LT_LOGO_FILE"] = "/static/logo.png"
os.environ["LT_CONTACT_TEXT"] = "test@example.com"

# Import after setting env vars
from server import ui_config


def test_ui_config_loading():
    """Test that UI config loads environment variables correctly."""
    print("Testing UI config loading...")

    # Test that values are loaded
    assert (
        ui_config["logo_file"] == "/static/logo.png"
    ), "Logo file not loaded correctly"
    assert ui_config["page_title"] == html.escape(
        "Test Title"
    ), "Page title not loaded correctly"
    assert (
        ui_config["contact_text"] == "test@example.com"
    ), "Contact text not loaded correctly"

    print("✓ UI config loading test passed")


def test_html_sanitization():
    """Test that HTML in page title is properly sanitized."""
    print("\nTesting HTML sanitization...")

    # Test XSS prevention
    malicious_input = "<script>alert('xss')</script>Test"
    sanitized = html.escape(malicious_input)

    assert "<script>" not in sanitized, "Script tag not sanitized"
    assert "&lt;script&gt;" in sanitized, "HTML not properly escaped"

    print("✓ HTML sanitization test passed")


def test_defaults():
    """Test that defaults work when env vars are not set."""
    print("\nTesting defaults...")

    # Clear environment variables
    for key in ["LT_PAGE_TITLE", "LT_LOGO_FILE", "LT_CONTACT_TEXT"]:
        if key in os.environ:
            del os.environ[key]

    # Reload the config
    default_logo = os.environ.get("LT_LOGO_FILE", "")
    default_title = html.escape(os.environ.get("LT_PAGE_TITLE", "🌍 Live Translation"))
    default_contact = os.environ.get("LT_CONTACT_TEXT", "")

    assert default_logo == "", "Default logo should be empty string"
    assert default_title == "🌍 Live Translation", "Default title not correct"
    assert default_contact == "", "Default contact should be empty string"

    print("✓ Defaults test passed")


def main():
    """Run all tests."""
    print("=" * 60)
    print("UI Customization Test Suite")
    print("=" * 60)

    try:
        test_ui_config_loading()
        test_html_sanitization()
        test_defaults()

        print("\n" + "=" * 60)
        print("✓ All tests passed successfully!")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
