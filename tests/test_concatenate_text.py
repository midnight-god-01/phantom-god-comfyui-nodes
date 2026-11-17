import unittest

from features.concatenate_text import (
    NODE_CLASS_MAPPINGS,
    PhantomGodConcatenateText,
)


class ConcatenateTextTests(unittest.TestCase):
    def setUp(self):
        self.node = PhantomGodConcatenateText()

    def test_joins_two_default_fields_with_space(self):
        self.assertEqual(
            self.node.concatenate(text_1="hello", text_2="world"),
            ("hello world",),
        )

    def test_joins_dynamic_fields_in_numeric_order(self):
        self.assertEqual(
            self.node.concatenate(
                delimiter=" | ",
                text_1="one",
                text_2="two",
                text_10="ten",
                text_3="three",
                text_4="four",
            ),
            ("one | two | three | four | ten",),
        )

    def test_ignores_empty_fields_without_extra_delimiters(self):
        self.assertEqual(
            self.node.concatenate(
                delimiter=", ",
                text_1="first",
                text_2="",
                text_3="",
                text_4="last",
            ),
            ("first, last",),
        )

    def test_supports_newline_delimiter(self):
        self.assertEqual(
            self.node.concatenate(
                delimiter="\n",
                text_1="line one",
                text_2="line two",
                text_3="line three",
            ),
            ("line one\nline two\nline three",),
        )

    def test_dynamic_schema_accepts_only_extra_text_fields(self):
        optional = PhantomGodConcatenateText.INPUT_TYPES()["optional"]
        self.assertIn("text_3", optional)
        self.assertIn("text_100", optional)
        self.assertNotIn("not_a_text_field", optional)
        self.assertNotIn("text_1", optional)

    def test_dynamic_input_lookup_returns_a_string_schema(self):
        optional = PhantomGodConcatenateText.INPUT_TYPES()["optional"]
        self.assertEqual(optional["text_3"], ("STRING", {}))
        self.assertEqual(optional["text_100"], ("STRING", {}))
        with self.assertRaises(KeyError):
            optional["not_a_text_field"]

    def test_exports_node_mapping(self):
        self.assertIs(
            NODE_CLASS_MAPPINGS["PhantomGodConcatenateText"],
            PhantomGodConcatenateText,
        )


if __name__ == "__main__":
    unittest.main()
