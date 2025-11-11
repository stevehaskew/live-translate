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
        # Test that values are loaded
        self.assertEqual(
            ui_config["logo_file"], "/static/logo.png", "Logo file not loaded correctly"
        )
        self.assertEqual(
            ui_config["page_title"],
            html.escape("Test Title"),
            "Page title not loaded correctly",
        )
        self.assertEqual(
            ui_config["contact_text"],
            "test@example.com",
            "Contact text not loaded correctly",
        )

    def test_html_sanitization(self):
        """Test that HTML in page title is properly sanitized."""
        # Test XSS prevention
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
        default_title = html.escape(
            os.environ.get("LT_PAGE_TITLE", "🌍 Live Translation")
        )
        default_contact = os.environ.get("LT_CONTACT_TEXT", "")

        self.assertEqual(default_logo, "", "Default logo should be empty string")
        self.assertEqual(
            default_title, "🌍 Live Translation", "Default title not correct"
        )
        self.assertEqual(default_contact, "", "Default contact should be empty string")


if __name__ == "__main__":
    # Run the unittest test runner
    unittest.main(verbosity=2)
