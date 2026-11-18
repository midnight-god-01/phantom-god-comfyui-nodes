import unittest

from features import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS


class FeatureRegistryTests(unittest.TestCase):
    def test_all_workflow_nodes_are_registered(self):
        expected = {
            "PhantomGodConcatenateText",
            "PhantomGodEnvironmentManager",
            "PhantomGodMultiLoraModelOnly",
        }
        self.assertTrue(expected.issubset(NODE_CLASS_MAPPINGS))
        self.assertTrue(expected.issubset(NODE_DISPLAY_NAME_MAPPINGS))

    def test_multi_lora_node_has_model_only_contract_and_search_aliases(self):
        node = NODE_CLASS_MAPPINGS["PhantomGodMultiLoraModelOnly"]
        self.assertEqual(node.RETURN_TYPES, ("MODEL",))
        self.assertEqual(node.FUNCTION, "apply")
        self.assertIn("model", node.INPUT_TYPES()["required"])
        aliases = {alias.casefold() for alias in node.SEARCH_ALIASES}
        self.assertIn("lora", aliases)
        self.assertIn("multi lora loader", aliases)


if __name__ == "__main__":
    unittest.main()
