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

from fastapi import APIRouter, Depends, HTTPException

from zenml.constants import METADATA_CONFIG, VERSION_1
from zenml.zen_server.utils import (
    authorize,
    error_detail,
    error_response,
    zen_store,
)

router = APIRouter(
    prefix=VERSION_1 + METADATA_CONFIG,
    tags=["metadata_config"],
    dependencies=[Depends(authorize)],
    responses={401: error_response},
)


@router.get(
    "/",
    response_model=str,
    responses={401: error_response, 404: error_response, 422: error_response},
)
async def get_metadata_config() -> str:
    """Gets the metadata config.

    Returns:
        The metadata config.

    Raises:
        401 error: when not authorized to login
        404 error: when trigger does not exist
        422 error: when unable to validate input
    """
    try:
        return zen_store.get_metadata_config()
    except NotAuthorizedError as error:
        raise HTTPException(status_code=401, detail=error_detail(error))
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=error_detail(error))
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error_detail(error))