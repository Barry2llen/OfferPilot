from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.repositories import ModelProviderRepository, ModelSelectionRepository
from exceptions import (
    ModelProviderAlreadyExistsError,
    ModelProviderNotFoundError,
    ModelSelectionAlreadyExistsError,
    ModelSelectionNotFoundError,
    UnsupportedModelProviderError,
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
from services import ModelProviderService, ModelSelectionService

router = APIRouter(tags=["model-config"])

_ERROR_DETAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "detail": {
            "type": "string",
            "description": "错误详情描述。",
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


def _selection_response(selection: ModelSelection) -> ModelSelectionResponse:
    if selection.id is None:
        raise ValueError("Persisted model selection id is required.")

    return ModelSelectionResponse(
        id=selection.id,
        provider=_provider_response(selection.provider),
        model_name=selection.model_name,
        supports_image_input=selection.supports_image_input,
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
    summary="列出模型供应商配置",
    description="返回系统中已配置的模型供应商摘要，不回显 API Key 明文。",
    response_description="按名称升序返回模型供应商配置列表。",
)
async def list_model_providers(
    session: Session = Depends(_get_request_db_session),
) -> list[ModelProviderResponse]:
    service = ModelProviderService(ModelProviderRepository(session))
    return [_provider_response(provider) for provider in service.list_all()]


@router.get(
    "/model-providers/{provider_name}",
    response_model=ModelProviderResponse,
    summary="获取模型供应商配置",
    description="根据供应商配置名称返回模型供应商摘要，不回显 API Key 明文。",
    response_description="返回指定模型供应商配置。",
    responses={
        404: _error_response("未找到指定模型供应商配置。", example="Model provider not found: default-openai"),
    },
)
async def get_model_provider(
    provider_name: str = Path(
        ...,
        description="模型供应商配置名称。",
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
    summary="创建模型供应商配置",
    description="创建一条模型供应商配置，用于后续模型选择记录引用。",
    response_description="返回新建模型供应商配置摘要。",
    responses={
        409: _error_response("模型供应商配置名称已存在。", example="Model provider already exists: default-openai"),
        422: _error_response("供应商类型不受支持。", example="Unsupported provider value: DeepSeek"),
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
    summary="更新模型供应商配置",
    description="更新指定模型供应商配置。api_key 省略时保留原值，传 null 时清空。",
    response_description="返回更新后的模型供应商配置摘要。",
    responses={
        404: _error_response("未找到指定模型供应商配置。", example="Model provider not found: default-openai"),
        422: _error_response("供应商类型不受支持。", example="Unsupported provider value: DeepSeek"),
    },
)
async def update_model_provider(
    payload: ModelProviderUpdate,
    provider_name: str = Path(
        ...,
        description="待更新的模型供应商配置名称。",
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
    summary="删除模型供应商配置",
    description="删除指定模型供应商配置。若仍被模型选择引用，将返回冲突错误。",
    response_description="删除成功，无响应体。",
    responses={
        404: _error_response("未找到指定模型供应商配置。", example="Model provider not found: default-openai"),
        409: _error_response("供应商仍被模型选择引用。", example="Model provider is still referenced by model selections."),
    },
)
async def delete_model_provider(
    provider_name: str = Path(
        ...,
        description="待删除的模型供应商配置名称。",
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
    summary="列出模型选择配置",
    description="返回系统中已配置的模型选择列表，并展开其供应商摘要。",
    response_description="按供应商名称、模型名称和 ID 升序返回模型选择列表。",
)
async def list_model_selections(
    session: Session = Depends(_get_request_db_session),
) -> list[ModelSelectionResponse]:
    service = ModelSelectionService(ModelSelectionRepository(session))
    return [_selection_response(selection) for selection in service.list_all()]


@router.get(
    "/model-selections/{selection_id}",
    response_model=ModelSelectionResponse,
    summary="获取模型选择配置",
    description="根据模型选择 ID 返回模型选择配置及其供应商摘要。",
    response_description="返回指定模型选择配置。",
    responses={
        404: _error_response("未找到指定模型选择配置。", example="Model selection not found: 1"),
    },
)
async def get_model_selection(
    selection_id: int = Path(
        ...,
        description="模型选择记录 ID。",
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
    return _selection_response(selection)


@router.post(
    "/model-selections",
    response_model=ModelSelectionResponse,
    summary="创建模型选择配置",
    description="创建一条可被 AI 服务引用的模型选择配置。",
    response_description="返回新建模型选择配置。",
    responses={
        404: _error_response("未找到请求中引用的模型供应商。", example="Model provider not found: missing-provider"),
        409: _error_response("同一供应商下模型名称已存在。", example="Model selection already exists: default-openai/gpt-4o-mini"),
    },
)
async def create_model_selection(
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
        return _selection_response(created)
    except ModelSelectionAlreadyExistsError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ModelProviderNotFoundError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.put(
    "/model-selections/{selection_id}",
    response_model=ModelSelectionResponse,
    summary="更新模型选择配置",
    description="更新指定模型选择配置。未传字段保持原值。",
    response_description="返回更新后的模型选择配置。",
    responses={
        404: _error_response("未找到模型选择或引用的模型供应商。", example="Model selection not found: 1"),
        409: _error_response("同一供应商下模型名称已存在。", example="Model selection already exists: default-openai/gpt-4o-mini"),
    },
)
async def update_model_selection(
    payload: ModelSelectionUpdate,
    selection_id: int = Path(
        ...,
        description="待更新的模型选择记录 ID。",
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
        return _selection_response(updated)
    except ModelSelectionAlreadyExistsError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ModelSelectionNotFoundError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete(
    "/model-selections/{selection_id}",
    status_code=204,
    summary="删除模型选择配置",
    description="删除指定模型选择配置。",
    response_description="删除成功，无响应体。",
    responses={
        404: _error_response("未找到指定模型选择配置。", example="Model selection not found: 1"),
    },
)
async def delete_model_selection(
    selection_id: int = Path(
        ...,
        description="待删除的模型选择记录 ID。",
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
