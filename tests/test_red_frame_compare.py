import unittest

from tools.compare_red_frames import compare_frames


class FrameComparisonTests(unittest.TestCase):
    def test_reports_single_pixel_and_its_coordinates(self):
        reference = bytes((0, 1, 2, 3, 0, 1))
        actual = bytes((0, 1, 2, 3, 2, 1))
        self.assertEqual(compare_frames(reference, actual, 3, 2), (1, (1, 1, 0, 2)))


if __name__ == "__main__":
    unittest.main()
