#
# Copyright (c) 2023 Airbyte, Inc., all rights reserved.
#

import copy
from abc import abstractmethod
from typing import Any, Dict, List, Optional

from airbyte_cdk.sources.file_based.config.file_based_stream_config import FileBasedStreamConfig
from airbyte_cdk.sources.utils import schema_helpers
from pydantic import AnyUrl, BaseModel, Field


class AbstractFileBasedSpec(BaseModel):
    """
    Used during spec; allows the developer to configure the cloud provider specific options
    that are needed when users configure a file-based source.
    """

    start_date: Optional[str] = Field(
        title="Start Date",
        description="UTC date and time in the format 2017-01-25T00:00:00.000000Z. Any file modified before this date will not be replicated.",
        examples=["2021-01-01T00:00:00.000000Z"],
        format="date-time",
        pattern="^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}.[0-9]{6}Z$",
        pattern_descriptor="YYYY-MM-DDTHH:mm:ss.SSSSSSZ",
        order=1,
    )

    streams: List[FileBasedStreamConfig] = Field(
        title="The list of streams to sync",
        description='Each instance of this configuration defines a <a href="https://docs.airbyte.com/cloud/core-concepts#stream">stream</a>. Use this to define which files belong in the stream, their format, and how they should be parsed and validated. When sending data to warehouse destination such as Snowflake or BigQuery, each stream is a separate table.',
        order=10,
    )

    @classmethod
    @abstractmethod
    def documentation_url(cls) -> AnyUrl:
        """
        :return: link to docs page for this source e.g. "https://docs.airbyte.com/integrations/sources/s3"
        """

    @classmethod
    def schema(cls, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """
        Generates the mapping comprised of the config fields
        """
        schema = super().schema(*args, **kwargs)
        transformed_schema = copy.deepcopy(schema)
        schema_helpers.expand_refs(transformed_schema)
        cls.replace_enum_allOf_and_anyOf(transformed_schema)
        cls.add_legacy_format(transformed_schema)

        return transformed_schema

    @staticmethod
    def replace_enum_allOf_and_anyOf(schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        allOfs are not supported by the UI, but pydantic is automatically writing them for enums.
        Unpacks the enums under allOf and moves them up a level under the enum key
        anyOfs are also not supported by the UI, so we replace them with the similar oneOf, with the
        additional validation that an incoming config only matches exactly one of a field's types.
        """
        # this will need to add ["anyOf"] once we have more than one format type and loop over the list of elements
        objects_to_check = schema["properties"]["streams"]["items"]["properties"]["format"]
        if "additionalProperties" in objects_to_check:
            objects_to_check["additionalProperties"]["oneOf"] = objects_to_check["additionalProperties"].pop("anyOf", [])
            for format in objects_to_check["additionalProperties"]["oneOf"]:
                for key in format["properties"]:
                    object_property = format["properties"][key]
                    if "allOf" in object_property and "enum" in object_property["allOf"][0]:
                        object_property["enum"] = object_property["allOf"][0]["enum"]
                        object_property.pop("allOf")

        properties_to_change = ["primary_key", "input_schema"]
        for property_to_change in properties_to_change:
            schema["properties"]["streams"]["items"]["properties"][property_to_change]["oneOf"] = schema["properties"]["streams"]["items"][
                "properties"
            ][property_to_change].pop("anyOf")
        return schema

    @staticmethod
    def add_legacy_format(schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Because we still need to allow for configs using the legacy format (like source-s3) where file format options
        are at the top level and not mapped from file_type -> format options, the json schema used to validate the
        config must be adjusted to support the generic mapping object. Once configs no longer adhere to the old
        format we can remove this change.
        """
        legacy_format_options = {
            "title": "Legacy Format",
            # Explicitly require this field to make it mutually exclusive (oneOf) with the new format mapping file_type -> format
            "required": ["filetype"],
            "type": "object",
            "properties": {"filetype": {"title": "Filetype", "type": "string"}},
        }
        csv_format_options = schema["properties"]["streams"]["items"]["properties"]["format"]
        union_format = {"oneOf": [csv_format_options, legacy_format_options]}
        schema["properties"]["streams"]["items"]["properties"]["format"] = union_format
        return schema
