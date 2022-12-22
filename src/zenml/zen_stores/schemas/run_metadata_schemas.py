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
"""SQLModel implementation of pipeline run metadata tables."""


from typing import Optional
from uuid import UUID

from sqlalchemy import TEXT, Column
from sqlmodel import Field, Relationship

from zenml.models.run_metadata_models import (
    RunMetadataRequestModel,
    RunMetadataResponseModel,
)
from zenml.zen_stores.schemas.artifact_schemas import ArtifactSchema
from zenml.zen_stores.schemas.base_schemas import BaseSchema
from zenml.zen_stores.schemas.component_schemas import StackComponentSchema
from zenml.zen_stores.schemas.pipeline_run_schemas import PipelineRunSchema
from zenml.zen_stores.schemas.project_schemas import ProjectSchema
from zenml.zen_stores.schemas.schema_utils import build_foreign_key_field
from zenml.zen_stores.schemas.step_run_schemas import StepRunSchema
from zenml.zen_stores.schemas.user_schemas import UserSchema


class RunMetadataSchema(BaseSchema, table=True):
    """SQL Model for run metadata."""

    __tablename__ = "run_metadata"

    pipeline_run_id: Optional[UUID] = build_foreign_key_field(
        source=__tablename__,
        target=PipelineRunSchema.__tablename__,
        source_column="pipeline_run_id",
        target_column="id",
        ondelete="CASCADE",
        nullable=True,
    )
    pipeline_run: "PipelineRunSchema" = Relationship(
        back_populates="run_metadata"
    )

    step_run_id: Optional[UUID] = build_foreign_key_field(
        source=__tablename__,
        target=StepRunSchema.__tablename__,
        source_column="step_run_id",
        target_column="id",
        ondelete="CASCADE",
        nullable=True,
    )
    step_run: "StepRunSchema" = Relationship(back_populates="run_metadata")

    artifact_id: Optional[UUID] = build_foreign_key_field(
        source=__tablename__,
        target=ArtifactSchema.__tablename__,
        source_column="artifact_id",
        target_column="id",
        ondelete="CASCADE",
        nullable=True,
    )
    artifact: "ArtifactSchema" = Relationship(back_populates="run_metadata")

    stack_component_id: Optional[UUID] = build_foreign_key_field(
        source=__tablename__,
        target=StackComponentSchema.__tablename__,
        source_column="stack_component_id",
        target_column="id",
        ondelete="SET NULL",
        nullable=True,
    )
    stack_component: "StackComponentSchema" = Relationship(
        back_populates="run_metadata"
    )

    user_id: Optional[UUID] = build_foreign_key_field(
        source=__tablename__,
        target=UserSchema.__tablename__,
        source_column="user_id",
        target_column="id",
        ondelete="SET NULL",
        nullable=True,
    )
    user: "UserSchema" = Relationship(back_populates="run_metadata")

    project_id: UUID = build_foreign_key_field(
        source=__tablename__,
        target=ProjectSchema.__tablename__,
        source_column="project_id",
        target_column="id",
        ondelete="CASCADE",
        nullable=False,
    )
    project: "ProjectSchema" = Relationship(back_populates="run_metadata")

    key: str
    value: str = Field(sa_column=Column(TEXT, nullable=False))

    def to_model(self) -> "RunMetadataResponseModel":
        """Convert a `RunMetadataSchema` to a `RunMetadataResponseModel`.

        Returns:
            The created `RunMetadataResponseModel`.
        """
        return RunMetadataResponseModel(
            id=self.id,
            pipeline_run_id=self.pipeline_run_id,
            step_run_id=self.step_run_id,
            artifact_id=self.artifact_id,
            stack_component_id=self.stack_component_id,
            key=self.key,
            value=self.value,
            project=self.project.to_model(),
            user=self.user.to_model(),
            created=self.created,
            updated=self.updated,
        )

    @classmethod
    def from_request(
        cls, request: "RunMetadataRequestModel"
    ) -> "RunMetadataSchema":
        """Create a `RunMetadataSchema` from a `RunMetadataRequestModel`.

        Args:
            request: The request model to create the schema from.

        Returns:
            The created `RunMetadataSchema`.
        """
        return cls(
            project_id=request.project,
            user_id=request.user,
            pipeline_run_id=request.pipeline_run_id,
            step_run_id=request.step_run_id,
            artifact_id=request.artifact_id,
            stack_component_id=request.stack_component_id,
            key=request.key,
            value=request.value,
        )
