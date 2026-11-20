import unittest

from tools.compare_red_segment import alignment


class SegmentAlignmentTests(unittest.TestCase):
    def test_reports_facing_and_party_mismatch_separately(self):
        original = {'map_id': 38, 'x': 3, 'y': 6, 'sprite_facing_raw': 4, 'party_count': 0, 'badges': 0}
        english = {'place': 'Bedroom', 'column': 3, 'row': 6, 'facing': 'south', 'starter': 'Charmander', 'badge': 0}
        self.assertEqual(alignment(original, english), {'map': True, 'position': True, 'facing': False, 'party_presence': False, 'badges': True})


if __name__ == '__main__':
    unittest.main()
