import json

from rest_framework import parsers


class NestedMultiPartParser(parsers.MultiPartParser):
    """A parser for parsing nested data fields as well as
    uploaded multipart data
    See <https://www.django-rest-framework.org/api-guide/parsers/#custom-parsers>
    """

    def parse(self, stream, media_type=None, parser_context=None):
        result = super().parse(stream, media_type, parser_context)

        data = {}

        # Loop over every field
        for key, value in result.data.items():
            # In order to send array of tags, clients must set the field as:
            # '[tags]', i.e., the field name must be surrounded with [ and ].
            if '[' in key and ']' in key:
                # This means this is an array field
                left_bracket_index = key.index('[')
                right_bracket_index = key.index(']')
                key_value = key[left_bracket_index + 1: right_bracket_index]
                json_value = json.loads(value)
                data[key_value] = json_value
            else:
                data[key] = value

        return parsers.DataAndFiles(data, result.files)
