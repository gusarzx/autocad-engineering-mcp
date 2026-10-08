"""Derive flat typed tool signatures from the same validated batch models."""

import inspect
from typing import Annotated

from mcp.types import ToolAnnotations

from ..core.models import Result


def annotations(read_only=False, destructive=False):
    return ToolAnnotations(
        readOnlyHint=read_only,
        destructiveHint=destructive,
        idempotentHint=read_only,
        openWorldHint=False,
    )


def model_tool(server, name, model, handler, description):
    """One source of truth for direct tool and batch schemas; no untyped **kwargs schema."""

    def tool(**kwargs) -> Result:
        dry_run = kwargs.pop("dry_run", False)
        return handler(model.model_validate(kwargs), dry_run)

    parameters = []
    hints = {"return": Result, "dry_run": bool}
    for key, field in model.model_fields.items():
        if key == "type":
            continue
        annotation = (
            Annotated[field.annotation, *field.metadata] if field.metadata else field.annotation
        )
        hints[key] = annotation
        default = (
            inspect.Parameter.empty
            if field.is_required()
            else field.get_default(call_default_factory=True)
        )
        parameters.append(
            inspect.Parameter(
                key, inspect.Parameter.KEYWORD_ONLY, default=default, annotation=annotation
            )
        )
    parameters.append(
        inspect.Parameter("dry_run", inspect.Parameter.KEYWORD_ONLY, default=False, annotation=bool)
    )
    tool.__name__ = name
    tool.__doc__ = description
    tool.__annotations__ = hints
    tool.__signature__ = inspect.Signature(parameters, return_annotation=Result)
    server.add_tool(
        tool,
        name=name,
        description=description,
        annotations=annotations(destructive="delete" in name),
    )
