#  Copyright (c) ZenML GmbH 2022. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.
"""Models representing stack components."""

from typing import TYPE_CHECKING, Any, ClassVar, Dict, List, Type, Union, \
    Optional
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, Field, PrivateAttr, validator

from zenml.enums import StackComponentType
from zenml.logger import get_logger
from zenml.models.base_models import (
    ShareableRequestModel,
    ShareableResponseModel,
    update_model,
)
from zenml.models.constants import STR_FIELD_MAX_LENGTH
from zenml.models.filter_models import ShareableProjectScopedFilterModel
from zenml.utils import secret_utils

if TYPE_CHECKING:
    from sqlmodel import SQLModel
    from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList

logger = get_logger(__name__)


# ---- #
# BASE #
# ---- #
class ComponentBaseModel(BaseModel):
    """Base model for stack components."""

    name: str = Field(
        title="The name of the stack component.",
        max_length=STR_FIELD_MAX_LENGTH,
    )
    type: StackComponentType = Field(
        title="The type of the stack component.",
    )

    flavor: str = Field(
        title="The flavor of the stack component.",
        max_length=STR_FIELD_MAX_LENGTH,
    )

    configuration: Dict[str, Any] = Field(
        title="The stack component configuration.",
    )


# -------- #
# RESPONSE #
# -------- #


class ComponentResponseModel(ComponentBaseModel, ShareableResponseModel):
    """Response model for stack components."""

    ANALYTICS_FIELDS: ClassVar[List[str]] = ["type", "flavor"]


# ------ #
# FILTER #
# ------ #


class ComponentFilterModel(ShareableProjectScopedFilterModel):
    """Model to enable advanced filtering of all ComponentModels.

    The Component Model needs additional scoping. As such the `_scope_user`
    field can be set to the user that is doing the filtering. The
    `generate_filter()` method of the baseclass is overwritten to include the
    scoping.
    """

    is_shared: Union[bool, str] = Query(
        None, description="If the stack is shared or private"
    )
    name: str = Query(
        None,
        description="Name of the stack component",
    )
    flavor: str = Query(
        None,
        description="Flavor of the stack component",
    )
    type: str = Query(
        None,
        description="Type of the stack component",
    )
    project_id: Union[UUID, str] = Query(
        None, description="Project of the stack"
    )
    user_id: Union[UUID, str] = Query(None, description="User of the stack")

    _scope_type: str = PrivateAttr(None)

    def set_scope_type(self, component_type: str) -> None:
        """Set the type of component on which to perform the filtering to scope the response."""
        self._scope_type = component_type

    def _scope_filter(self, table: Type["SQLModel"]) -> Optional[Union["BinaryExpression", "BooleanClauseList"]]:
        """A Stack Components can also be scoped by type to narrow by type.

        The resulting filter from this method will be the union of the scoping
        filter with the user provided filters.

        Args:
            table: The Table that is being queried from.

        Returns:
            A list of all scope filters that will be conjuncted with the other
                filters
        """
        from sqlalchemy import and_
        from sqlmodel import or_

        scope_filter = []
        if self._scope_user:
            scope_filter.append(
                or_(
                    getattr(table, "user_id") == self._scope_user,
                    getattr(table, "is_shared") is True,
                )
            )
        if self._scope_project:
            scope_filter.append(
                getattr(table, "project_id") == self._scope_project
            )
        if self._scope_type:
            scope_filter.append(getattr(table, "type") == self._scope_type)

        if scope_filter:
            return and_(*scope_filter)
        else:
            return None


# ------- #
# REQUEST #
# ------- #


class ComponentRequestModel(ComponentBaseModel, ShareableRequestModel):
    """Request model for stack components."""

    ANALYTICS_FIELDS: ClassVar[List[str]] = ["type", "flavor"]

    @validator("name")
    def name_cant_be_a_secret_reference(cls, name: str) -> str:
        """Validator to ensure that the given name is not a secret reference.

        Args:
            name: The name to validate.

        Returns:
            The name if it is not a secret reference.

        Raises:
            ValueError: If the name is a secret reference.
        """
        if secret_utils.is_secret_reference(name):
            raise ValueError(
                "Passing the `name` attribute of a stack component as a "
                "secret reference is not allowed."
            )
        return name


# ------ #
# UPDATE #
# ------ #


@update_model
class ComponentUpdateModel(ComponentRequestModel):
    """Update model for stack components."""
