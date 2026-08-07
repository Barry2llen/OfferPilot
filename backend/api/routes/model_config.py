from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agent.compaction import DefaultContextBudgetPolicy
from db.repositories import (
    ContextCompactionSettingsRepository,
    ModelProviderRepository,
    ModelSelectionRepository,
)
from exceptions import (
    ModelProviderAlreadyExistsError,
    ModelProviderNotFoundError,
    ModelSelectionAlreadyExistsError,
    ModelSelectionNotFoundError,
    UnsupportedModelProviderError,
)
from schemas.context_compaction import (
    ContextCompactionSettingsResponse,
    ContextCompactionSettingsUpdate,
)
from schemas.model_provider import (
    ModelProvider,
    ModelProviderCreate,
    ModelProviderResponse,
    ModelProviderUpdate,
)
from schemas.model_selection import (
    ModelSelection,
    ModelSelectionCreate,
    ModelSelectionResponse,
    ModelSelectionUpdate,
)
from services import (
    ContextCompactionSettingsService,
    ModelProviderService,
    ModelSelectionService,
)

router = APIRouter(tags=["model-config"])

_ERROR_DETAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "detail": {
            "type": "string",
            "description": "Description of the error.",
        }
    },
    "required": ["detail"],
}


def _error_response(description: str, *, example: str) -> dict:
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": _ERROR_DETAIL_SCHEMA,
                "example": {"detail": example},
            }
        },
    }


def _get_request_db_session(request: Request) -> Generator[Session, None, None]:
    session = request.app.state.database.get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def _provider_response(provider: ModelProvider) -> ModelProviderResponse:
    return ModelProviderResponse(
        provider=provider.provider,
        name=provider.name,
        base_url=provider.base_url,
        has_api_key=provider.api_key is not None,
    )


def _selection_response(
    selection: ModelSelection,
    request: Request,
) -> ModelSelectionResponse:
    if selection.id is None:
        raise ValueError("Persisted model selection id is required.")

    return ModelSelectionResponse(
        id=selection.id,
        provider=_provider_response(selection.provider),
        model_name=selection.model_name,
        supports_image_input=selection.supports_image_input,
        context_window_tokens=DefaultContextBudgetPolicy(
            request.app.state.config.context_compaction
        ).resolve_max_context_tokens(selection),
    )


def _commit_or_rollback(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Model provider is still referenced by model selections.",
        ) from error
    except Exception:
        session.rollback()
        raise


@router.get(
    "/model-providers",
    response_model=list[ModelProviderResponse],
    summary="List model providers",
    description="Return configured model provider summaries without exposing API keys.",
    response_description="Returns model providers ordered by name.",
)
async def list_model_providers(
    session: Session = Depends(_get_request_db_session),
) -> list[ModelProviderResponse]:
    service = ModelProviderService(ModelProviderRepository(session))
    return [_provider_response(provider) for provider in service.list_all()]


@router.get(
    "/context-compaction-settings",
    response_model=ContextCompactionSettingsResponse,
    summary="Get context compaction settings",
    description=(
        "Return the optional auto-compaction model selection. A null selection "
        "follows the model selected for the current conversation."
    ),
    response_description="Returns the current context compaction setting.",
)
async def get_context_compaction_settings(
    session: Session = Depends(_get_request_db_session),
) -> ContextCompactionSettingsResponse:
    service = ContextCompactionSettingsService(
        ContextCompactionSettingsRepository(session),
        ModelSelectionRepository(session),
    )
    return service.get()


@router.patch(
    "/context-compaction-settings",
    response_model=ContextCompactionSettingsResponse,
    summary="Update context compaction settings",
    description=(
        "Set the optional auto-compaction model selection, or pass null to "
        "follow the model selected for the current conversation."
    ),
    response_description="Returns the updated context compaction setting.",
    responses={
        404: _error_response(
            "The requested model selection was not found.",
            example="Model selection not found: 1",
        ),
    },
)
async def update_context_compaction_settings(
    payload: ContextCompactionSettingsUpdate,
    session: Session = Depends(_get_request_db_session),
) -> ContextCompactionSettingsResponse:
    service = ContextCompactionSettingsService(
        ContextCompactionSettingsRepository(session),
        ModelSelectionRepository(session),
    )
    try:
        updated = service.update(payload.model_selection_id)
        _commit_or_rollback(session)
        return updated
    except ModelSelectionNotFoundError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get(
    "/model-providers/{provider_name}",
    response_model=ModelProviderResponse,
    summary="Get model provider details",
    description="Return a model provider summary by name without exposing its API key.",
    response_description="Returns the requested model provider.",
    responses={
        404: _error_response(
            "The requested model provider was not found.",
            example="Model provider not found: default-openai",
        ),
    },
)
async def get_model_provider(
    provider_name: str = Path(
        ...,
        description="Model provider configuration name.",
        examples=["default-openai"],
    ),
    session: Session = Depends(_get_request_db_session),
) -> ModelProviderResponse:
    service = ModelProviderService(ModelProviderRepository(session))
    provider = service.get_by_name(provider_name)
    if provider is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model provider not found: {provider_name}",
        )
    return _provider_response(provider)


@router.post(
    "/model-providers",
    response_model=ModelProviderResponse,
    summary="Create a model provider",
    description="Create a model provider configuration for later model selection references.",
    response_description="Returns the new model provider summary.",
    responses={
        409: _error_response(
            "A model provider with this name already exists.",
            example="Model provider already exists: default-openai",
        ),
        422: _error_response(
            "The provider type is not supported.",
            example="Unsupported provider value: Unknown",
        ),
    },
)
async def create_model_provider(
    payload: ModelProviderCreate,
    session: Session = Depends(_get_request_db_session),
) -> ModelProviderResponse:
    service = ModelProviderService(ModelProviderRepository(session))
    try:
        created = service.create(
            ModelProvider(
                provider=payload.provider,
                name=payload.name,
                base_url=payload.base_url,
                api_key=payload.api_key,
            )
        )
        _commit_or_rollback(session)
        return _provider_response(created)
    except ModelProviderAlreadyExistsError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    except UnsupportedModelProviderError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.put(
    "/model-providers/{provider_name}",
    response_model=ModelProviderResponse,
    summary="Update a model provider",
    description="Update a model provider. Omit api_key to keep it, or pass null to clear it.",
    response_description="Returns the updated model provider summary.",
    responses={
        404: _error_response(
            "The requested model provider was not found.",
            example="Model provider not found: default-openai",
        ),
        422: _error_response(
            "The provider type is not supported.",
            example="Unsupported provider value: Unknown",
        ),
    },
)
async def update_model_provider(
    payload: ModelProviderUpdate,
    provider_name: str = Path(
        ...,
        description="Model provider configuration name to update.",
        examples=["default-openai"],
    ),
    session: Session = Depends(_get_request_db_session),
) -> ModelProviderResponse:
    service = ModelProviderService(ModelProviderRepository(session))
    existing = service.get_by_name(provider_name)
    if existing is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model provider not found: {provider_name}",
        )

    try:
        updated = service.update(
            ModelProvider(
                provider=payload.provider or existing.provider,
                name=provider_name,
                base_url=(
                    payload.base_url
                    if "base_url" in payload.model_fields_set
                    else existing.base_url
                ),
                api_key=(
                    payload.api_key
                    if "api_key" in payload.model_fields_set
                    else existing.api_key
                ),
            )
        )
        _commit_or_rollback(session)
        return _provider_response(updated)
    except UnsupportedModelProviderError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.delete(
    "/model-providers/{provider_name}",
    status_code=204,
    summary="Delete a model provider",
    description="Delete a model provider. Deletion conflicts while model selections still reference it.",
    response_description="Deleted successfully with no response body.",
    responses={
        404: _error_response(
            "The requested model provider was not found.",
            example="Model provider not found: default-openai",
        ),
        409: _error_response(
            "The provider is still referenced by model selections.",
            example="Model provider is still referenced by model selections.",
        ),
    },
)
async def delete_model_provider(
    provider_name: str = Path(
        ...,
        description="Model provider configuration name to delete.",
        examples=["default-openai"],
    ),
    session: Session = Depends(_get_request_db_session),
) -> Response:
    service = ModelProviderService(ModelProviderRepository(session))
    try:
        deleted = service.delete(provider_name)
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Model provider is still referenced by model selections.",
        ) from error
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Model provider not found: {provider_name}",
        )
    _commit_or_rollback(session)
    return Response(status_code=204)


@router.get(
    "/model-selections",
    response_model=list[ModelSelectionResponse],
    summary="List model selections",
    description=(
        "Return configured model selections with expanded provider summaries and "
        "resolved context window capacities."
    ),
    response_description="Returns model selections ordered by provider name, model name, and ID.",
)
async def list_model_selections(
    request: Request,
    session: Session = Depends(_get_request_db_session),
) -> list[ModelSelectionResponse]:
    service = ModelSelectionService(ModelSelectionRepository(session))
    return [_selection_response(selection, request) for selection in service.list_all()]


@router.get(
    "/model-selections/{selection_id}",
    response_model=ModelSelectionResponse,
    summary="Get model selection details",
    description=(
        "Return a model selection, its provider summary, and its resolved context "
        "window capacity by ID."
    ),
    response_description="Returns the requested model selection.",
    responses={
        404: _error_response(
            "The requested model selection was not found.",
            example="Model selection not found: 1",
        ),
    },
)
async def get_model_selection(
    request: Request,
    selection_id: int = Path(
        ...,
        description="Model selection record ID.",
        examples=[1],
    ),
    session: Session = Depends(_get_request_db_session),
) -> ModelSelectionResponse:
    service = ModelSelectionService(ModelSelectionRepository(session))
    selection = service.get_by_id(selection_id)
    if selection is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model selection not found: {selection_id}",
        )
    return _selection_response(selection, request)


@router.post(
    "/model-selections",
    response_model=ModelSelectionResponse,
    summary="Create a model selection",
    description="Create a model selection that can be referenced by AI services.",
    response_description="Returns the new model selection with its resolved context window capacity.",
    responses={
        404: _error_response(
            "The referenced model provider was not found.",
            example="Model provider not found: missing-provider",
        ),
        409: _error_response(
            "The model name already exists for this provider.",
            example="Model selection already exists: default-openai/gpt-4o-mini",
        ),
    },
)
async def create_model_selection(
    request: Request,
    payload: ModelSelectionCreate,
    session: Session = Depends(_get_request_db_session),
) -> ModelSelectionResponse:
    provider_service = ModelProviderService(ModelProviderRepository(session))
    selection_service = ModelSelectionService(ModelSelectionRepository(session))
    provider = provider_service.get_by_name(payload.provider_name)
    if provider is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model provider not found: {payload.provider_name}",
        )

    try:
        created = selection_service.create(
            ModelSelection(
                provider=provider,
                model_name=payload.model_name,
                supports_image_input=payload.supports_image_input,
            )
        )
        _commit_or_rollback(session)
        return _selection_response(created, request)
    except ModelSelectionAlreadyExistsError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ModelProviderNotFoundError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.put(
    "/model-selections/{selection_id}",
    response_model=ModelSelectionResponse,
    summary="Update a model selection",
    description="Update a model selection. Omitted fields keep their current values.",
    response_description="Returns the updated model selection with its resolved context window capacity.",
    responses={
        404: _error_response(
            "The model selection or referenced provider was not found.",
            example="Model selection not found: 1",
        ),
        409: _error_response(
            "The model name already exists for this provider.",
            example="Model selection already exists: default-openai/gpt-4o-mini",
        ),
    },
)
async def update_model_selection(
    request: Request,
    payload: ModelSelectionUpdate,
    selection_id: int = Path(
        ...,
        description="Model selection record ID to update.",
        examples=[1],
    ),
    session: Session = Depends(_get_request_db_session),
) -> ModelSelectionResponse:
    provider_service = ModelProviderService(ModelProviderRepository(session))
    selection_service = ModelSelectionService(ModelSelectionRepository(session))
    existing = selection_service.get_by_id(selection_id)
    if existing is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model selection not found: {selection_id}",
        )

    provider_name = payload.provider_name or existing.provider.name
    provider = provider_service.get_by_name(provider_name)
    if provider is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model provider not found: {provider_name}",
        )

    try:
        updated = selection_service.update(
            ModelSelection(
                id=selection_id,
                provider=provider,
                model_name=payload.model_name or existing.model_name,
                supports_image_input=(
                    payload.supports_image_input
                    if payload.supports_image_input is not None
                    else existing.supports_image_input
                ),
            )
        )
        _commit_or_rollback(session)
        return _selection_response(updated, request)
    except ModelSelectionAlreadyExistsError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ModelSelectionNotFoundError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete(
    "/model-selections/{selection_id}",
    status_code=204,
    summary="Delete a model selection",
    description="Delete a model selection.",
    response_description="Deleted successfully with no response body.",
    responses={
        404: _error_response(
            "The requested model selection was not found.",
            example="Model selection not found: 1",
        ),
    },
)
async def delete_model_selection(
    selection_id: int = Path(
        ...,
        description="Model selection record ID to delete.",
        examples=[1],
    ),
    session: Session = Depends(_get_request_db_session),
) -> Response:
    service = ModelSelectionService(ModelSelectionRepository(session))
    deleted = service.delete(selection_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Model selection not found: {selection_id}",
        )
    _commit_or_rollback(session)
    return Response(status_code=204)
