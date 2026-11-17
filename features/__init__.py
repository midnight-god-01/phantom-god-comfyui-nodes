"""Automatic registry for Phantom God feature modules.

Add a new Python node feature by creating a module in this directory that
exports NODE_CLASS_MAPPINGS and, optionally, NODE_DISPLAY_NAME_MAPPINGS.
The package loader discovers each module automatically.
"""

from importlib import import_module
from pkgutil import iter_modules

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}


def _merge_feature_mapping(target, source, mapping_name, module_name):
    for node_name, node_class in source.items():
        if node_name in target:
            raise ValueError(
                f"Duplicate {mapping_name} key {node_name!r} in feature {module_name!r}."
            )
        target[node_name] = node_class


for feature in sorted(iter_modules(__path__), key=lambda item: item.name):
    if feature.name.startswith("_") or feature.ispkg:
        continue

    module = import_module(f"{__name__}.{feature.name}")
    _merge_feature_mapping(
        NODE_CLASS_MAPPINGS,
        getattr(module, "NODE_CLASS_MAPPINGS", {}),
        "NODE_CLASS_MAPPINGS",
        feature.name,
    )
    _merge_feature_mapping(
        NODE_DISPLAY_NAME_MAPPINGS,
        getattr(module, "NODE_DISPLAY_NAME_MAPPINGS", {}),
        "NODE_DISPLAY_NAME_MAPPINGS",
        feature.name,
    )


__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
