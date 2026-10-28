"""Tests for the answer of the image agent: parsing the criteria and the watcher's own verdict (BL-034).

Run: cd watcher && python3 -m unittest -v test_answer
"""

import unittest

import answer


class ParseTests(unittest.TestCase):

    def test_header_then_blank_line_then_description(self):
        parsed = answer.parse('whiteboard_visible: yes\nboard_fill_percent: 85\nis_board_camera: yes\n\n## Text\nHELLO')
        self.assertTrue(parsed.visible)
        self.assertEqual(parsed.fill, 85)
        self.assertTrue(parsed.camera)
        self.assertEqual(parsed.body, '## Text\nHELLO')

    def test_description_without_a_blank_line_still_parses(self):
        parsed = answer.parse('whiteboard_visible: yes\nboard_fill_percent: 85\nis_board_camera: yes\nHELLO')
        self.assertEqual(parsed.body, 'HELLO')

    def test_no_stops_after_the_header(self):
        parsed = answer.parse('whiteboard_visible: no\nboard_fill_percent: 0\nis_board_camera: no')
        self.assertFalse(parsed.visible)
        self.assertFalse(parsed.camera)
        self.assertEqual(parsed.body, '')

    def test_keys_and_words_are_case_insensitive_and_spaces_tolerated(self):
        parsed = answer.parse('  Whiteboard_Visible: YES \nBOARD_FILL_PERCENT: 90%\nIs_Board_Camera: Yes\n\nx')
        self.assertTrue(parsed.visible)
        self.assertEqual(parsed.fill, 90)
        self.assertEqual(parsed.body, 'x')

    def test_fill_out_of_range_or_unparsable_is_none(self):
        self.assertIsNone(answer.parse('whiteboard_visible: yes\nboard_fill_percent: lots\n\nx').fill)
        self.assertIsNone(answer.parse('whiteboard_visible: yes\nboard_fill_percent: 150\n\nx').fill)
        self.assertIsNone(answer.parse('whiteboard_visible: yes\n\nx').fill)

    def test_missing_conclusion_is_none(self):
        self.assertIsNone(answer.parse('whiteboard_visible: yes\nboard_fill_percent: 80\n\nx').camera)

    def test_missing_whiteboard_line_is_an_error(self):
        with self.assertRaises(ValueError):
            answer.parse('This is a whiteboard with notes.')

    def test_whiteboard_line_that_is_not_yes_or_no_is_an_error(self):
        with self.assertRaises(ValueError):
            answer.parse('whiteboard_visible: maybe\n\nx')

    def test_empty_answer_is_an_error(self):
        with self.assertRaises(ValueError):
            answer.parse('   \n')


class VerdictTests(unittest.TestCase):

    def parsed(self, visible=True, fill=90, body='x'):
        return answer.Answer(visible, fill, True, body)

    def test_check_off_ignores_fill(self):
        self.assertEqual(answer.verdict(self.parsed(fill=None), 0), (True, 'ok'))
        self.assertEqual(answer.verdict(self.parsed(fill=3), 0), (True, 'ok'))

    def test_fill_at_or_above_the_minimum_passes(self):
        self.assertEqual(answer.verdict(self.parsed(fill=80), 80), (True, 'ok'))

    def test_fill_below_the_minimum_fails_with_the_value(self):
        self.assertEqual(answer.verdict(self.parsed(fill=79), 80), (False, 'board fill 79 below 80'))

    def test_missing_fill_fails_when_the_check_is_on(self):
        self.assertEqual(answer.verdict(self.parsed(fill=None), 80), (False, 'board fill missing'))

    def test_no_whiteboard_fails_whatever_the_fill(self):
        self.assertEqual(answer.verdict(self.parsed(visible=False, fill=99), 0), (False, 'not a whiteboard'))

    def test_empty_description_fails(self):
        self.assertEqual(answer.verdict(self.parsed(body=''), 0), (False, 'describe: empty description'))

    def test_the_agents_conclusion_does_not_decide(self):
        said_yes = answer.Answer(True, 50, True, 'x')
        self.assertEqual(answer.verdict(said_yes, 80)[0], False)


if __name__ == '__main__':
    unittest.main()
