"""Data processor service group implementation for AutoMCP verification."""

import datetime
import json
from typing import Any, Dict, List, Optional, Union

from mcp.types import TextContent as Context
from pydantic import BaseModel, Field

from automcp.group import MockContext, ServiceGroup
from automcp.operation import operation


# Input/Output Schemas
class DataItem(BaseModel):
    """Schema for a single data item with flexible content."""

    id: str = Field(..., description="Unique identifier for the data item")
    value: Any = Field(..., description="The value of the data item")
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Optional metadata for the data item"
    )


class ProcessingParameters(BaseModel):
    """Schema for data processing parameters."""

    filter_fields: Optional[List[str]] = Field(
        None, description="Fields to include in the output"
    )
    transform_case: Optional[str] = Field(
        None, description="Case transformation ('upper', 'lower', or None)"
    )
    aggregate: Optional[bool] = Field(
        False, description="Whether to aggregate numeric values"
    )
    sort_by: Optional[str] = Field(None, description="Field to sort by")
    sort_order: Optional[str] = Field("asc", description="Sort order ('asc' or 'desc')")


class DataProcessingSchema(BaseModel):
    """Schema for data processing operation."""

    data: List[DataItem] = Field(..., description="List of data items to process")
    parameters: ProcessingParameters = Field(
        default_factory=ProcessingParameters,
        description="Parameters for processing the data",
    )


class ReportFormat(BaseModel):
    """Schema for report formatting options."""

    title: str = Field("Data Processing Report", description="Title of the report")
    include_summary: bool = Field(
        True, description="Whether to include a summary section"
    )
    include_timestamp: bool = Field(True, description="Whether to include a timestamp")
    format_type: str = Field(
        "text", description="Output format type ('text', 'markdown', 'html')"
    )


class ReportGenerationSchema(BaseModel):
    """Schema for report generation operation."""

    processed_data: Dict[str, Any] = Field(
        ..., description="The processed data to generate a report for"
    )
    format: ReportFormat = Field(
        default_factory=ReportFormat, description="Formatting options for the report"
    )


class SchemaDefinition(BaseModel):
    """Schema for defining a validation schema."""

    type: str = Field(
        ..., description="Schema type (e.g., 'object', 'array', 'string')"
    )
    properties: Optional[Dict[str, Dict[str, Any]]] = Field(
        None, description="Properties for object types"
    )
    required: Optional[List[str]] = Field(
        None, description="Required properties for object types"
    )
    items: Optional[Dict[str, Any]] = Field(None, description="Schema for array items")
    format: Optional[str] = Field(None, description="Format for string types")
    minimum: Optional[float] = Field(None, description="Minimum value for number types")
    maximum: Optional[float] = Field(None, description="Maximum value for number types")
    pattern: Optional[str] = Field(None, description="Regex pattern for string types")


class SchemaValidationRequestSchema(BaseModel):
    """Schema for schema validation operation."""

    data: Any = Field(..., description="The data to validate")
    schema: SchemaDefinition = Field(..., description="The schema to validate against")


class ValidationError(BaseModel):
    """Schema for validation error details."""

    path: str = Field(..., description="Path to the error location in the data")
    message: str = Field(..., description="Error message")


class ValidationResult(BaseModel):
    """Schema for validation result."""

    valid: bool = Field(..., description="Whether the data is valid against the schema")
    errors: Optional[List[ValidationError]] = Field(
        None, description="List of validation errors if any"
    )


class DataProcessorGroup(ServiceGroup):
    """Service group for data processing operations.

    This group demonstrates:
    1. Pydantic schema validation for inputs
    2. Progress reporting using Context
    3. Multiple operation types for data processing
    """

    @operation(schema=DataProcessingSchema)
    async def process_data(self, data_schema=None, **kwargs) -> dict:
        """Process JSON data according to specified parameters.

        Args:
            data_schema: A DataProcessingSchema object if passed positionally
            **kwargs: Additional keyword arguments including data and parameters

        Returns:
            dict: The processed data
        """
        print(f"DEBUG: process_data received data_schema={data_schema}, kwargs={kwargs}")
        
        # Extract data items and parameters
        items = []
        params_dict = {}
        
        # Case 1: Data passed via positional DataProcessingSchema
        if data_schema is not None and hasattr(data_schema, 'data') and hasattr(data_schema, 'parameters'):
            items = data_schema.data
            params_dict = data_schema.parameters
        # Case 2: Data passed via kwargs
        else:
            items = kwargs.get("data", [])
            params_dict = kwargs.get("parameters", {})
        
        # Ensure data items are DataItem objects
        data_items = []
        for item_data in items:
            if isinstance(item_data, dict):
                data_items.append(DataItem(**item_data))
            else:
                data_items.append(item_data)
                
        # Ensure parameters is a ProcessingParameters object
        if isinstance(params_dict, dict):
            params = ProcessingParameters(**params_dict)
        else:
            params = params_dict
            
        # Create a context
        ctx = MockContext()
        ctx.info(
            f"Processing {len(data_items)} data items with parameters: {params}"
        )

        # Process the data
        processed_items = []
        total_items = len(data_items)

        for i, item in enumerate(data_items):
            # Report progress
            await ctx.report_progress(i + 1, total_items)

            # Process the item
            processed_item = self._process_item(item, params)
            processed_items.append(processed_item)

        # Perform aggregation if requested
        result = {"processed_items": processed_items}
        if params.aggregate:
            result["aggregated"] = self._aggregate_data(processed_items)

        ctx.info("Data processing completed successfully")
        return result

    def _process_item(
        self, item: DataItem, params: ProcessingParameters
    ) -> Dict[str, Any]:
        """Process a single data item according to the parameters."""
        processed = {"id": item.id}

        # Add value with possible transformation
        if isinstance(item.value, str) and params.transform_case:
            if params.transform_case.lower() == "upper":
                processed["value"] = item.value.upper()
            elif params.transform_case.lower() == "lower":
                processed["value"] = item.value.lower()
            else:
                processed["value"] = item.value
        else:
            processed["value"] = item.value

        # Add metadata if present
        if item.metadata:
            if params.filter_fields:
                # Only include specified fields
                filtered_metadata = {
                    k: v for k, v in item.metadata.items() if k in params.filter_fields
                }
                processed["metadata"] = filtered_metadata
            else:
                processed["metadata"] = item.metadata

        return processed

    def _aggregate_data(self, processed_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate numeric values in the processed data."""
        numeric_values = []
        for item in processed_items:
            if isinstance(item["value"], (int, float)):
                numeric_values.append(item["value"])

        if not numeric_values:
            return {}

        return {
            "count": len(numeric_values),
            "sum": sum(numeric_values),
            "average": sum(numeric_values) / len(numeric_values),
            "min": min(numeric_values),
            "max": max(numeric_values),
        }

    @operation(schema=ReportGenerationSchema)
    async def generate_report(
        self, config=None, **kwargs
    ) -> str:
        """Generate a formatted report from processed data.

        Args:
            config: A ReportGenerationSchema object if passed positionally
            **kwargs: Additional keyword arguments including processed_data and format

        Returns:
            str: The formatted report as a string
        """
        print(f"DEBUG: generate_report received config={config}, kwargs={kwargs}")
        
        # Extract processed_data and format
        processed_data = {}
        format_data = None
        
        # Case 1: Data passed via positional ReportGenerationSchema
        if config is not None and hasattr(config, 'processed_data') and hasattr(config, 'format'):
            processed_data = config.processed_data
            format_data = config.format
        # Case 2: Data passed via kwargs
        else:
            # Extract from direct kwargs
            processed_data = kwargs.get("processed_data", {})
            format_dict = kwargs.get("format", {})
            
            # Ensure format is a ReportFormat object
            if isinstance(format_dict, dict):
                format_data = ReportFormat(**format_dict)
            else:
                format_data = format_dict or ReportFormat()
        
        # Create a context for progress reporting
        ctx = MockContext()
        ctx.info(f"Generating report with format: {format_data}")

        # Extract data from processed_data
        processed_items = processed_data.get("processed_items", [])
        aggregated_data = processed_data.get("aggregated", {})

        # Start building the report
        await ctx.report_progress(1, 3)
        report_lines = []

        # Generate report based on format type
        format_type = format_data.format_type.lower()

        # Add title
        if format_type == "markdown":
            report_lines.append(f"# {format_data.title}")
            report_lines.append("")
        elif format_type == "html":
            report_lines.append(f"<h1>{format_data.title}</h1>")
        else:  # text
            report_lines.append(format_data.title)
            report_lines.append("=" * len(format_data.title))

        # Add timestamp if requested
        if format_data.include_timestamp:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if format_type == "markdown":
                report_lines.append(f"**Generated:** {timestamp}")
                report_lines.append("")
            elif format_type == "html":
                report_lines.append(f"<p><strong>Generated:</strong> {timestamp}</p>")
            else:  # text
                report_lines.append(f"Generated: {timestamp}")
                report_lines.append("")

        await ctx.report_progress(2, 3)

        # Add summary if requested
        if format_data.include_summary and processed_items:
            if format_type == "markdown":
                report_lines.append("## Summary")
                report_lines.append("")
                report_lines.append(f"**Total items:** {len(processed_items)}")
                if aggregated_data:
                    report_lines.append("")
                    report_lines.append("### Aggregated Data")
                    report_lines.append("")
                    for key, value in aggregated_data.items():
                        report_lines.append(f"- **{key}:** {value}")
                report_lines.append("")
            elif format_type == "html":
                report_lines.append("<h2>Summary</h2>")
                report_lines.append(
                    f"<p><strong>Total items:</strong> {len(processed_items)}</p>"
                )
                if aggregated_data:
                    report_lines.append("<h3>Aggregated Data</h3>")
                    report_lines.append("<ul>")
                    for key, value in aggregated_data.items():
                        report_lines.append(f"<li><strong>{key}:</strong> {value}</li>")
                    report_lines.append("</ul>")
            else:  # text
                report_lines.append("Summary")
                report_lines.append("-------")
                report_lines.append(f"Total items: {len(processed_items)}")
                if aggregated_data:
                    report_lines.append("")
                    report_lines.append("Aggregated Data:")
                    for key, value in aggregated_data.items():
                        report_lines.append(f"  {key}: {value}")
                report_lines.append("")

        # Add data items
        if processed_items:
            if format_type == "markdown":
                report_lines.append("## Data Items")
                report_lines.append("")
                for item in processed_items:
                    report_lines.append(f"### Item: {item.get('id')}")
                    report_lines.append(f"- **Value:** {item.get('value')}")
                    if "metadata" in item and item["metadata"]:
                        report_lines.append("- **Metadata:**")
                        for meta_key, meta_value in item["metadata"].items():
                            report_lines.append(f"  - {meta_key}: {meta_value}")
                    report_lines.append("")
            elif format_type == "html":
                report_lines.append("<h2>Data Items</h2>")
                for item in processed_items:
                    report_lines.append(f"<div class='item'>")
                    report_lines.append(f"<h3>Item: {item.get('id')}</h3>")
                    report_lines.append(
                        f"<p><strong>Value:</strong> {item.get('value')}</p>"
                    )
                    if "metadata" in item and item["metadata"]:
                        report_lines.append("<div class='metadata'>")
                        report_lines.append("<p><strong>Metadata:</strong></p>")
                        report_lines.append("<ul>")
                        for meta_key, meta_value in item["metadata"].items():
                            report_lines.append(f"<li>{meta_key}: {meta_value}</li>")
                        report_lines.append("</ul>")
                        report_lines.append("</div>")
                    report_lines.append("</div>")
            else:  # text
                report_lines.append("Data Items")
                report_lines.append("---------")
                for item in processed_items:
                    report_lines.append(f"Item: {item.get('id')}")
                    report_lines.append(f"Value: {item.get('value')}")
                    if "metadata" in item and item["metadata"]:
                        report_lines.append("Metadata:")
                        for meta_key, meta_value in item["metadata"].items():
                            report_lines.append(f"  {meta_key}: {meta_value}")
                    report_lines.append("")

        await ctx.report_progress(3, 3)
        ctx.info("Report generation completed successfully")

        # Join report lines based on format
        separator = "\n" if format_type != "html" else ""
        return separator.join(report_lines)

    @operation(schema=SchemaValidationRequestSchema)
    async def validate_schema(self, request=None, **kwargs) -> ValidationResult:
        """Validate input data against a specified schema.

        Args:
            request: A SchemaValidationRequestSchema object if passed positionally
            **kwargs: Additional keyword arguments including data and schema

        Returns:
            ValidationResult: The validation result containing success status and any error messages
        """
        print(f"DEBUG: validate_schema received request={request}, kwargs={kwargs}")
        
        # Extract data and schema (handling both positional and keyword args)
        data = None
        schema_obj = None
        
        # Case 1: Data passed via positional SchemaValidationRequestSchema
        if request is not None and hasattr(request, 'data') and hasattr(request, 'schema'):
            data = request.data
            schema_obj = request.schema
        # Case 2: Data passed via kwargs
        else:
            data = kwargs.get("data")
            schema_dict = kwargs.get("schema")
            
            # Ensure schema is a SchemaDefinition object
            if isinstance(schema_dict, dict):
                schema_obj = SchemaDefinition(**schema_dict)
            else:
                schema_obj = schema_dict
        
        print(f"DEBUG: Using data={data}, schema={schema_obj}")
        
        # Handle validation
        errors = []

        # Validate the data against the schema
        try:
            self._validate_data_against_schema(data, schema_obj, "", errors)
            valid = len(errors) == 0
        except Exception as e:
            print(f"DEBUG: Validation error: {e}")
            errors.append(
                ValidationError(path="", message=f"Validation error: {str(e)}")
            )
            valid = False

        result = ValidationResult(valid=valid, errors=errors if errors else None)
        print(f"DEBUG: Validation result: {result}")
        return result

    def _validate_data_against_schema(
        self,
        data: Any,
        schema: SchemaDefinition,
        path: str,
        errors: List[ValidationError],
    ) -> None:
        """Recursively validate data against a schema definition."""
        # Check type
        schema_type = schema.type.lower()

        if schema_type == "object":
            if not isinstance(data, dict):
                errors.append(
                    ValidationError(
                        path=path, message=f"Expected object, got {type(data).__name__}"
                    )
                )
                return

            # Check required properties
            if schema.required:
                for required_prop in schema.required:
                    if required_prop not in data:
                        errors.append(
                            ValidationError(
                                path=(
                                    f"{path}.{required_prop}" if path else required_prop
                                ),
                                message=f"Required property '{required_prop}' is missing",
                            )
                        )

            # Validate properties
            if schema.properties:
                for prop_name, prop_schema in schema.properties.items():
                    if prop_name in data:
                        prop_path = f"{path}.{prop_name}" if path else prop_name
                        # Create a SchemaDefinition from the property schema
                        prop_schema_def = SchemaDefinition(**prop_schema)
                        self._validate_data_against_schema(
                            data[prop_name], prop_schema_def, prop_path, errors
                        )

        elif schema_type == "array":
            if not isinstance(data, list):
                errors.append(
                    ValidationError(
                        path=path, message=f"Expected array, got {type(data).__name__}"
                    )
                )
                return

            # Validate array items
            if schema.items:
                items_schema = SchemaDefinition(**schema.items)
                for i, item in enumerate(data):
                    item_path = f"{path}[{i}]" if path else f"[{i}]"
                    self._validate_data_against_schema(
                        item, items_schema, item_path, errors
                    )

        elif schema_type == "string":
            if not isinstance(data, str):
                errors.append(
                    ValidationError(
                        path=path, message=f"Expected string, got {type(data).__name__}"
                    )
                )
                return

            # Validate format
            if schema.format == "email" and "@" not in data:
                errors.append(
                    ValidationError(path=path, message="Invalid email format")
                )

            # Validate pattern
            if schema.pattern and not self._matches_pattern(data, schema.pattern):
                errors.append(
                    ValidationError(
                        path=path,
                        message=f"String does not match pattern: {schema.pattern}",
                    )
                )

        elif schema_type in ["number", "integer"]:
            if not isinstance(data, (int, float)):
                errors.append(
                    ValidationError(
                        path=path, message=f"Expected number, got {type(data).__name__}"
                    )
                )
                return

            if schema_type == "integer" and not isinstance(data, int):
                errors.append(
                    ValidationError(
                        path=path,
                        message=f"Expected integer, got {type(data).__name__}",
                    )
                )
                return

            # Validate minimum
            if schema.minimum is not None and data < schema.minimum:
                errors.append(
                    ValidationError(
                        path=path,
                        message=f"Value {data} is less than minimum {schema.minimum}",
                    )
                )

            # Validate maximum
            if schema.maximum is not None and data > schema.maximum:
                errors.append(
                    ValidationError(
                        path=path,
                        message=f"Value {data} is greater than maximum {schema.maximum}",
                    )
                )

        elif schema_type == "boolean":
            if not isinstance(data, bool):
                errors.append(
                    ValidationError(
                        path=path,
                        message=f"Expected boolean, got {type(data).__name__}",
                    )
                )

        elif schema_type == "null":
            if data is not None:
                errors.append(
                    ValidationError(
                        path=path, message=f"Expected null, got {type(data).__name__}"
                    )
                )

    def _matches_pattern(self, data: str, pattern: str) -> bool:
        """Simple pattern matching for string validation."""
        import re

        try:
            return bool(re.match(pattern, data))
        except Exception:
            return False
