import unittest
from unittest.mock import patch, mock_open, MagicMock
import json
import os
import monitor


class TestDetectFieldChanges(unittest.TestCase):
    def test_no_changes(self):
        prev_info = {"rent": "$3,200", "available": "3/15/2026", "concessions": "NONE", "net_rent": "$3,200"}
        info = {"rent": "$3,200", "available": "3/15/2026", "concessions": "NONE", "net_rent": "$3,200"}
        changed, unchanged = monitor.detect_field_changes(prev_info, info)
        self.assertEqual(changed, [])
        self.assertEqual(set(unchanged), {"rent", "available", "concessions", "net_rent"})

    def test_rent_changed(self):
        prev_info = {"rent": "$3,200", "available": "3/15/2026", "concessions": "NONE", "net_rent": "$3,200"}
        info = {"rent": "$3,300", "available": "3/15/2026", "concessions": "NONE", "net_rent": "$3,300"}
        changed, unchanged = monitor.detect_field_changes(prev_info, info)
        self.assertEqual(changed, ["rent", "net_rent"])
        self.assertEqual(set(unchanged), {"available", "concessions"})

    def test_multiple_fields_changed(self):
        prev_info = {"rent": "$3,200", "available": "3/15/2026", "concessions": "NONE", "net_rent": "$3,200"}
        info = {"rent": "$3,300", "available": "4/1/2026", "concessions": "NONE", "net_rent": "$3,300"}
        changed, unchanged = monitor.detect_field_changes(prev_info, info)
        self.assertEqual(set(changed), {"rent", "available", "net_rent"})
        self.assertEqual(unchanged, ["concessions"])

    def test_all_fields_changed(self):
        prev_info = {"rent": "$3,200", "available": "3/15/2026", "concessions": "NONE", "net_rent": "$3,200"}
        info = {"rent": "$3,500", "available": "4/1/2026", "concessions": "1 month free", "net_rent": "$3,250"}
        changed, unchanged = monitor.detect_field_changes(prev_info, info)
        self.assertEqual(set(changed), {"rent", "available", "concessions", "net_rent"})
        self.assertEqual(unchanged, [])

    def test_empty_values(self):
        prev_info = {"rent": "", "available": "", "concessions": "", "net_rent": ""}
        info = {"rent": "$3,200", "available": "3/15/2026", "concessions": "NONE", "net_rent": "$3,200"}
        changed, unchanged = monitor.detect_field_changes(prev_info, info)
        self.assertEqual(set(changed), {"rent", "available", "concessions", "net_rent"})
        self.assertEqual(unchanged, [])


class TestFormatFieldChangeMessage(unittest.TestCase):
    def test_single_field_change(self):
        changed = ["rent"]
        unchanged = ["available", "concessions", "net_rent"]
        prev_info = {"rent": "$3,200", "bed_bath": "1/1"}
        info = {"rent": "$3,300", "bed_bath": "1/1", "available": "3/15/2026", "concessions": "NONE", "net_rent": "$3,300"}

        msg = monitor.format_field_change_message("1205", changed, unchanged, prev_info, info)

        self.assertIn(":money_with_wings:", msg)
        self.assertIn("Rent changed for 1205", msg)
        self.assertIn("Rent: $3,200 → $3,300", msg)
        self.assertIn("Bed/Bath: 1/1", msg)

    def test_multiple_fields_change(self):
        changed = ["rent", "available"]
        unchanged = ["concessions", "net_rent"]
        prev_info = {"rent": "$3,200", "available": "3/15/2026", "bed_bath": "1/1"}
        info = {"rent": "$3,300", "available": "4/1/2026", "bed_bath": "1/1", "concessions": "NONE", "net_rent": "$3,300"}

        msg = monitor.format_field_change_message("1205", changed, unchanged, prev_info, info)

        self.assertIn(":money_with_wings:", msg)
        self.assertIn(":calendar:", msg)
        self.assertIn("Rent and Available changed for 1205", msg)
        self.assertIn("Rent: $3,200 → $3,300", msg)
        self.assertIn("Available: 3/15/2026 → 4/1/2026", msg)

    def test_three_fields_change(self):
        changed = ["rent", "available", "concessions"]
        unchanged = ["net_rent"]
        prev_info = {"rent": "$3,200", "available": "3/15/2026", "concessions": "NONE", "bed_bath": "1/1"}
        info = {"rent": "$3,300", "available": "4/1/2026", "concessions": "1 month free", "bed_bath": "1/1", "net_rent": "$3,300"}

        msg = monitor.format_field_change_message("1205", changed, unchanged, prev_info, info)

        self.assertIn("Rent, Available, and Concessions changed for 1205", msg)
        self.assertIn("Rent: $3,200 → $3,300", msg)
        self.assertIn("Available: 3/15/2026 → 4/1/2026", msg)
        self.assertIn("Concessions: NONE → 1 month free", msg)


class TestDetectChanges(unittest.TestCase):
    def test_new_unit(self):
        prev_units = {}
        units = {
            "1205": {
                "bed_bath": "1/1",
                "rent": "$3,200",
                "available": "3/15/2026",
                "concessions": "NONE",
                "net_rent": "$3,200"
            }
        }
        messages = monitor.detect_changes(prev_units, units)

        self.assertEqual(len(messages), 1)
        self.assertIn(":new:", messages[0])
        self.assertIn("New 1-bedroom unit 1205", messages[0])
        self.assertIn("Rent: $3,200", messages[0])

    def test_removed_unit(self):
        prev_units = {
            "1205": {
                "bed_bath": "1/1",
                "rent": "$3,200",
                "available": "3/15/2026",
                "concessions": "NONE",
                "net_rent": "$3,200"
            }
        }
        units = {}
        messages = monitor.detect_changes(prev_units, units)

        self.assertEqual(len(messages), 1)
        self.assertIn(":x:", messages[0])
        self.assertIn("Unit 1205 is no longer available", messages[0])

    def test_field_changed(self):
        prev_units = {
            "1205": {
                "bed_bath": "1/1",
                "rent": "$3,200",
                "available": "3/15/2026",
                "concessions": "NONE",
                "net_rent": "$3,200"
            }
        }
        units = {
            "1205": {
                "bed_bath": "1/1",
                "rent": "$3,300",
                "available": "3/15/2026",
                "concessions": "NONE",
                "net_rent": "$3,300"
            }
        }
        messages = monitor.detect_changes(prev_units, units)

        self.assertEqual(len(messages), 1)
        self.assertIn("Rent changed for 1205", messages[0])
        self.assertIn("Rent: $3,200 → $3,300", messages[0])

    def test_no_changes(self):
        prev_units = {
            "1205": {
                "bed_bath": "1/1",
                "rent": "$3,200",
                "available": "3/15/2026",
                "concessions": "NONE",
                "net_rent": "$3,200"
            }
        }
        units = {
            "1205": {
                "bed_bath": "1/1",
                "rent": "$3,200",
                "available": "3/15/2026",
                "concessions": "NONE",
                "net_rent": "$3,200"
            }
        }
        messages = monitor.detect_changes(prev_units, units)

        self.assertEqual(len(messages), 0)

    def test_multiple_changes(self):
        prev_units = {
            "1205": {
                "bed_bath": "1/1",
                "rent": "$3,200",
                "available": "3/15/2026",
                "concessions": "NONE",
                "net_rent": "$3,200"
            },
            "1502": {
                "bed_bath": "1/1",
                "rent": "$2,800",
                "available": "4/1/2026",
                "concessions": "NONE",
                "net_rent": "$2,800"
            }
        }
        units = {
            "1205": {
                "bed_bath": "1/1",
                "rent": "$3,300",
                "available": "3/15/2026",
                "concessions": "NONE",
                "net_rent": "$3,300"
            },
            "1807": {
                "bed_bath": "1/1",
                "rent": "$2,900",
                "available": "5/1/2026",
                "concessions": "NONE",
                "net_rent": "$2,900"
            }
        }
        messages = monitor.detect_changes(prev_units, units)

        # Should have: 1205 changed, 1502 removed, 1807 new
        self.assertEqual(len(messages), 3)
        self.assertTrue(any("Rent changed for 1205" in msg for msg in messages))
        self.assertTrue(any("Unit 1502 is no longer available" in msg for msg in messages))
        self.assertTrue(any("New 1-bedroom unit 1807" in msg for msg in messages))


class TestStateManagement(unittest.TestCase):
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_load_state_exists(self, mock_file, mock_exists):
        mock_exists.return_value = True
        test_data = '{"1205": {"bed_bath": "1/1", "rent": "$3,200", "available": "3/15/2026", "concessions": "NONE", "net_rent": "$3,200"}}'

        with patch("builtins.open", mock_open(read_data=test_data)):
            state = monitor.load_state()
            self.assertEqual(state, {"1205": {"bed_bath": "1/1", "rent": "$3,200", "available": "3/15/2026", "concessions": "NONE", "net_rent": "$3,200"}})

    @patch("os.path.exists")
    def test_load_state_not_exists(self, mock_exists):
        mock_exists.return_value = False
        state = monitor.load_state()
        self.assertEqual(state, {})

    @patch("builtins.open", new_callable=mock_open)
    def test_save_state(self, mock_file):
        units = {"1205": {"bed_bath": "1/1", "rent": "$3,200", "available": "3/15/2026", "concessions": "NONE", "net_rent": "$3,200"}}
        monitor.save_state(units)

        mock_file.assert_called_once_with(monitor.STATE_FILE, "w")
        handle = mock_file()
        # Get all write calls and join them
        write_calls = [call[0][0] for call in handle.write.call_args_list]
        written_data = "".join(write_calls)
        saved_data = json.loads(written_data)
        self.assertEqual(saved_data, units)


class TestSendSlack(unittest.TestCase):
    @patch("requests.post")
    def test_send_slack_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        messages = ["Test message"]
        monitor.send_slack(messages, "http://webhook.url")

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertEqual(call_args[0][0], "http://webhook.url")
        self.assertEqual(call_args[1]["json"]["text"], "Test message")

    @patch("requests.post")
    def test_send_slack_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        messages = ["Test message"]
        monitor.send_slack(messages, "http://webhook.url")

        mock_post.assert_called_once()

    @patch("requests.post")
    def test_send_slack_empty_messages(self, mock_post):
        monitor.send_slack([], "http://webhook.url")
        mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
