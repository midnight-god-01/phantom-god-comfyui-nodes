"""Unlimited-input text concatenation node with removable fields."""

import re

_DYNAMIC_TEXT_INPUT = re.compile(r"^text_(\d+)$")


class _DynamicTextInputs(dict):
    """Declare the first two optional inputs and accept later text_N fields."""

    def __init__(self):
        schema = ("STRING", {"default": "", "multiline": True})
        super().__init__({"text_1": schema, "text_2": schema})

    def __contains__(self, key):
        if not isinstance(key, str):
            return False
        match = _DYNAMIC_TEXT_INPUT.fullmatch(key)
        return match is not None and int(match.group(1)) >= 1

    def __missing__(self, key):
        # ComfyUI's get_input_info() checks membership and then indexes the
        # optional mapping. Dynamic names therefore need a real schema value.
        if key in self:
            return ("STRING", {"default": "", "multiline": True})
        raise KeyError(key)


class PhantomGodConcatenateText:
    """Join any number of text fields using a configurable delimiter."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "delimiter": ("STRING", {"default": " ", "multiline": False}),
            },
            "optional": _DynamicTextInputs(),
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "concatenate"
    CATEGORY = "Phantom God/Text"
    DESCRIPTION = (
        "Join any number of text fields. Add fields as needed and remove an "
        "individual field with its matching remove control. Every field is optional."
    )

    def concatenate(self, delimiter=" ", text_1="", text_2="", **dynamic_inputs):
        """Concatenate any supplied text_N values in numeric order."""
        values = {1: text_1, 2: text_2}

        for name, value in dynamic_inputs.items():
            match = _DYNAMIC_TEXT_INPUT.fullmatch(name)
            if match is None:
                continue
            values[int(match.group(1))] = value

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
