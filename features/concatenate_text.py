"""Unlimited-input text concatenation node."""

import re

_DYNAMIC_TEXT_INPUT = re.compile(r"^text_(\d+)$")


class _DynamicTextInputs(dict):
    """Accept additional text_N inputs created by the frontend extension."""

    def __contains__(self, key):
        if not isinstance(key, str):
            return False
        match = _DYNAMIC_TEXT_INPUT.fullmatch(key)
        return match is not None and int(match.group(1)) > 2

    def __missing__(self, key):
        # ComfyUI's get_input_info() checks membership and then indexes the
        # optional mapping. Supply a STRING schema for dynamically named inputs.
        if key in self:
            return ("STRING", {})
        raise KeyError(key)


class PhantomGodConcatenateText:
    """Join any number of text fields using a configurable delimiter."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "delimiter": ("STRING", {"default": " ", "multiline": False}),
                "text_1": ("STRING", {"default": "", "multiline": True}),
                "text_2": ("STRING", {"default": "", "multiline": True}),
            },
            "optional": _DynamicTextInputs(),
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "concatenate"
    CATEGORY = "Phantom God/Text"

    def concatenate(self, delimiter=" ", text_1="", text_2="", **dynamic_inputs):
        """Concatenate text_1, text_2, and dynamically named text_N values."""
        values = {1: text_1, 2: text_2}

        for name, value in dynamic_inputs.items():
            match = _DYNAMIC_TEXT_INPUT.fullmatch(name)
            if match is None:
                continue
            index = int(match.group(1))
            if index > 2:
                values[index] = value

        pieces = []
        for index in sorted(values):
            value = values[index]
            if value is None:
                continue
            text = str(value)
            if text != "":
                pieces.append(text)

        separator = " " if delimiter is None else str(delimiter)
        return (separator.join(pieces),)


NODE_CLASS_MAPPINGS = {
    "PhantomGodConcatenateText": PhantomGodConcatenateText,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PhantomGodConcatenateText": "Concatenate Text (Phantom God)",
}
