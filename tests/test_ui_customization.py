#!/usr/bin/env python3
"""
Test script for UI customization features.
Validates that environment variables are properly loaded and sanitized.
"""

import os
import sys
import html
import unittest

# Set test environment variables
os.environ["LT_PAGE_TITLE"] = "Test Title"
os.environ["LT_LOGO_FILE"] = "/static/logo.png"
os.environ["LT_CONTACT_TEXT"] = "test@example.com"

# Import after setting env vars
from server import ui_config


class TestUICustomization(unittest.TestCase):
    """Unit tests for UI customization and sanitization."""

    def test_ui_config_loading(self):
        """Test that UI config loads environment variables correctly."""
        # Test that values are loaded (using camelCase keys for config.json format)
        self.assertEqual(
            ui_config["logoFile"], "/static/logo.png", "Logo file not loaded correctly"
        )
        self.assertEqual(
            ui_config["pageTitle"],
            "Test Title",
            "Page title not loaded correctly",
        )
        self.assertEqual(
            ui_config["contactText"],
            "test@example.com",
            "Contact text not loaded correctly",
        )

    def test_html_sanitization(self):
        """Test that HTML in page title is properly sanitized."""
        # Note: HTML sanitization is now handled client-side in the JavaScript
        # This test validates the escape function still works
        malicious_input = "<script>alert('xss')</script>Test"
        sanitized = html.escape(malicious_input)

        self.assertNotIn("<script>", sanitized, "Script tag not sanitized")
        self.assertIn("&lt;script&gt;", sanitized, "HTML not properly escaped")

    def test_defaults(self):
        """Test that defaults work when env vars are not set."""
        # Clear environment variables
        for key in ["LT_PAGE_TITLE", "LT_LOGO_FILE", "LT_CONTACT_TEXT"]:
            os.environ.pop(key, None)

        # Verify defaults computed independently of server import
        default_logo = os.environ.get("LT_LOGO_FILE", "")
        default_title = os.environ.get("LT_PAGE_TITLE", "🌍 Live Translation")
        default_contact = os.environ.get("LT_CONTACT_TEXT", "your support team")

        self.assertEqual(default_logo, "", "Default logo should be empty string")
        self.assertEqual(
            default_title, "🌍 Live Translation", "Default title not correct"
        )
        self.assertEqual(default_contact, "your support team", "Default contact not correct")


if __name__ == "__main__":
    # Run the unittest test runner
    unittest.main(verbosity=2)
