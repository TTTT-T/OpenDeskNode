"""FastAPI application and versioned LAN admin/dashboard API."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from .calendar import MarketSessionClock
from .config import GatewayConfig
from .logging_config import configure_logging
from .repository import (
    DEFAULT_NAMES,
    DEFAULT_SYMBOLS,
    RepositoryError,
    SQLiteRepository,
    validate_device_id,
    validate_symbol,
)
from .schemas import (
    DeviceCreateRequest,
    DeviceUpdateRequest,
    ReorderRequest,
    SymbolConfirmRequest,
    SymbolResolveRequest,
    WatchlistSaveRequest,
)
from .service import StockGatewayService


WEB_INDEX = Path(__file__).resolve().parent / "web" / "index.html"


def _not_found(device_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "DEVICE_NOT_FOUND", "message": "unknown device: %s" % device_id},
    )


def create_app(
    config: Optional[GatewayConfig] = None,
    repository: Optional[SQLiteRepository] = None,
    providers: Optional[Any] = None,
    market_clock: Optional[MarketSessionClock] = None,
    service: Optional[StockGatewayService] = None,
) -> FastAPI:
    runtime_config = config or GatewayConfig.from_env()
    if service is None:
        runtime_config.ensure_local_directories()
        repo = repository or SQLiteRepository(runtime_config.database_path)
        repo.initialize()
        if repo.count_devices() == 0:
            repo.create_device(
                "device-a",
                "Device A",
                DEFAULT_SYMBOLS,
                DEFAULT_NAMES,
            )
        runtime_service = StockGatewayService(
            repository=repo,
            config=runtime_config,
            providers=providers,
            market_clock=market_clock,
        )
    else:
        runtime_service = service
        repo = runtime_service.repository

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        configure_logging(runtime_config.log_path)
        await runtime_service.start()
        try:
            yield
        finally:
            await runtime_service.stop()
            repo.close()

    app = FastAPI(
        title="Stock Gateway",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.service = runtime_service
    app.state.config = runtime_config

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def admin_page() -> HTMLResponse:
        return HTMLResponse(WEB_INDEX.read_text(encoding="utf-8"))

    @app.get("/healthz")
    def healthz() -> Any:
        return runtime_service.health()

    @app.get("/api/v1/devices")
    def list_devices() -> Any:
        devices = runtime_service.repository.list_devices()
        return {
            "schema_version": 1,
            "devices": [
                {
                    **device.to_dict(),
                    "watchlist": [
                        slot.to_dict()
                        for slot in runtime_service.repository.get_watchlist(device.device_id)
                    ],
                }
                for device in devices
            ],
        }

    @app.post("/api/v1/devices", status_code=201)
    def create_device(payload: DeviceCreateRequest) -> Any:
        symbols = payload.symbols or list(DEFAULT_SYMBOLS)
        names = [None, None, None, None]
        if symbols == list(DEFAULT_SYMBOLS):
            names = list(DEFAULT_NAMES)
        try:
            device = runtime_service.repository.create_device(
                payload.device_id, payload.name, symbols, names
            )
        except ValueError as exc:
            code = "DEVICE_EXISTS" if "already exists" in str(exc) else "DEVICE_INVALID"
            raise HTTPException(status_code=409, detail={"code": code, "message": str(exc)})
        return {
            "schema_version": 1,
            "device": device.to_dict(),
            "watchlist": [
                slot.to_dict()
                for slot in runtime_service.repository.get_watchlist(device.device_id)
            ],
        }

    @app.get("/api/v1/devices/{device_id}")
    def get_device(device_id: str) -> Any:
        try:
            device = runtime_service.repository.get_device(device_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_DEVICE_ID", "message": str(exc)})
        if device is None:
            raise _not_found(device_id)
        return {
            "schema_version": 1,
            "device": device.to_dict(),
            "watchlist": [
                slot.to_dict()
                for slot in runtime_service.repository.get_watchlist(device_id)
            ],
        }

    @app.patch("/api/v1/devices/{device_id}")
    def update_device(device_id: str, payload: DeviceUpdateRequest) -> Any:
        try:
            device = runtime_service.repository.update_device_name(device_id, payload.name)
        except KeyError:
            raise _not_found(device_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_DEVICE", "message": str(exc)})
        return {"schema_version": 1, "device": device.to_dict()}

    @app.delete("/api/v1/devices/{device_id}")
    def delete_device(device_id: str) -> Any:
        try:
            runtime_service.repository.delete_device(device_id)
        except KeyError:
            raise _not_found(device_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_DEVICE_ID", "message": str(exc)})
        return {"schema_version": 1, "deleted": device_id}

    @app.get("/api/v1/devices/{device_id}/watchlist")
    def get_watchlist(device_id: str) -> Any:
        try:
            slots = runtime_service.repository.get_watchlist(device_id)
        except KeyError:
            raise _not_found(device_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_DEVICE_ID", "message": str(exc)})
        return {"schema_version": 1, "device_id": device_id, "slots": [slot.to_dict() for slot in slots]}

    @app.post("/api/v1/devices/{device_id}/watchlist")
    def save_watchlist(device_id: str, payload: WatchlistSaveRequest) -> Any:
        try:
            slots = runtime_service.repository.save_watchlist(
                device_id, payload.symbols, payload.names
            )
        except KeyError:
            raise _not_found(device_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_WATCHLIST", "message": str(exc)})
        return {"schema_version": 1, "device_id": device_id, "saved": True, "slots": [slot.to_dict() for slot in slots]}

    @app.post("/api/v1/devices/{device_id}/watchlist/reorder")
    def reorder_watchlist(device_id: str, payload: ReorderRequest) -> Any:
        try:
            slots = runtime_service.repository.reorder_watchlist(
                device_id, payload.slot_order
            )
        except KeyError:
            raise _not_found(device_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_ORDER", "message": str(exc)})
        return {"schema_version": 1, "device_id": device_id, "saved": True, "slots": [slot.to_dict() for slot in slots]}

    @app.get("/api/v1/symbols/resolve")
    def resolve_symbol(symbol: str = Query(..., min_length=6, max_length=6, pattern=r"^[0-9]{6}$")) -> Any:
        try:
            ref = runtime_service.resolve_symbol(symbol)
        except Exception as exc:
            raise HTTPException(status_code=502, detail={"code": "PROVIDER_UNAVAILABLE", "message": str(exc)[:500]})
        return {
            "schema_version": 1,
            "symbol": {
                "code": ref.code,
                "exchange": ref.exchange,
                "provider_symbol": ref.provider_symbol,
                "name": ref.name,
                "confirmed": bool(ref.name),
            },
        }

    @app.post("/api/v1/symbols/resolve")
    def resolve_symbol_post(payload: SymbolResolveRequest) -> Any:
        return resolve_symbol(payload.symbol)

    @app.post("/api/v1/symbols/confirm")
    def confirm_symbol(payload: SymbolConfirmRequest) -> Any:
        return {
            "schema_version": 1,
            "confirmed": True,
            "symbol": {"code": payload.symbol, "name": payload.name},
        }

    @app.get("/api/v1/dashboard/{device_id}")
    def dashboard(
        device_id: str,
        intraday_samples: Optional[int] = Query(None, ge=2, le=64),
    ) -> Any:
        try:
            return runtime_service.dashboard(
                device_id,
                touch_access=True,
                intraday_samples=intraday_samples,
            )
        except KeyError:
            raise _not_found(device_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_DEVICE_ID", "message": str(exc)})

    @app.get("/api/v1/devices/{device_id}/preview")
    def preview(device_id: str) -> Any:
        try:
            return runtime_service.dashboard(device_id, touch_access=False)
        except KeyError:
            raise _not_found(device_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_DEVICE_ID", "message": str(exc)})

    @app.get("/api/v1/devices/{device_id}/status")
    def device_status(device_id: str) -> Any:
        try:
            return runtime_service.status(device_id)
        except KeyError:
            raise _not_found(device_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_DEVICE_ID", "message": str(exc)})

    @app.get("/api/v1/status")
    def gateway_status() -> Any:
        return runtime_service.status()

    return app


app = create_app()
