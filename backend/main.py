"""FastAPI entry point: uvicorn backend.main:app from the repository root."""

import asyncio
import logging
import os
from datetime import date
from threading import Event
from time import perf_counter

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from .agents.orchestrator import OrchestratorAgent
from .agents.cancellation import check_cancelled, scan_cancel_event
from .agents.scout import default_scouts
from .data.loader import region_catalog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ScanRequest(BaseModel):
    regions: list[str] = Field(min_length=1, max_length=5)
    date_range: tuple[date, date]

    @field_validator("regions")
    @classmethod
    def nonempty_regions(cls, regions):
        if any(not region.strip() for region in regions):
            raise ValueError("regions must contain nonempty names")
        return regions

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.date_range[0] > self.date_range[1]:
            raise ValueError("date_range start must not follow end")
        return self


def create_app(scouts=(), *, series_loader=None, pc_alpha=0.2) -> FastAPI:
    """Create an application with configured scouts and optional data retrieval."""
    app = FastAPI(title="GAIA")
    origins = os.getenv("GAIA_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    origins = [origin.strip().rstrip("/") for origin in origins]
    app.add_middleware(CORSMiddleware, allow_origins=origins,
                       allow_methods=["GET"], allow_headers=["*"])
    app.state.scouts = list(scouts)
    app.state.series_loader = series_loader

    @app.get("/health")
    async def health():
        return {"status": "ok", "scouts": len(app.state.scouts)}

    @app.get("/regions")
    async def regions():
        return {"regions": region_catalog(), "date_range": ["2000-01-01", "2025-12-31"],
                "source": "Cached NASA Giovanni regional averages"}

    @app.websocket("/ws/scan")
    async def scan(websocket: WebSocket):
        if websocket.headers.get("origin") and websocket.headers["origin"] not in origins:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        cancel_event = Event()
        cancel_token = scan_cancel_event.set(cancel_event)
        region = None
        completed = False
        cancelled = False
        client_disconnected = False
        tasks = []

        def disconnected():
            nonlocal client_disconnected
            if not client_disconnected:
                client_disconnected = True
                logger.info("client disconnected")
            cancel_event.set()

        async def send_json(message):
            check_cancelled()
            await websocket.send_json(message)

        try:
            try:
                request = ScanRequest.model_validate(await websocket.receive_json())
            except (ValidationError, ValueError) as error:
                await send_json({"type": "error", "message": str(error)})
                await websocket.close(code=1008)
                return

            region = ",".join(request.regions)
            started = perf_counter()
            logger.info("scan start region=%s", region)
            orchestrator = OrchestratorAgent(
                app.state.scouts,
                status_callback=send_json,
                series_loader=app.state.series_loader,
                pc_alpha=pc_alpha,
            )

            async def pipeline():
                nonlocal completed
                discoveries = await orchestrator.run_scan(request.regions, request.date_range)
                await send_json({"type": "status", "agent": "orchestrator",
                                           "status": "causal_started"})
                links = await asyncio.to_thread(orchestrator.run_causal_discovery, discoveries)
                # Avoid pandas/numpy objects on the wire. Preserve the original arrays
                # and source metadata for the chart; never serialize PCMCI internals.
                observations = [{key: value for key, value in item.items() if key != "timeseries"}
                                for item in discoveries if "values" in item]
                await send_json({"type": "complete", "discovery_count": len(discoveries),
                                           "links": links, "discoveries": observations,
                                           **orchestrator.causal_metadata,
                                           "method": "PCMCI · ParCorr · lag 1–6 months · BH FDR q < 0.05",
                                           "preprocessing": "Monthly climatology removed, linearly detrended, standardized"})
                completed = True
                logger.info("scan done region=%s links=%d in %.3fs", region, len(links), perf_counter() - started)

            async def watch_disconnect():
                while True:
                    if (await websocket.receive())["type"] == "websocket.disconnect":
                        disconnected()
                        return

            work = asyncio.create_task(pipeline())
            disconnect_task = asyncio.create_task(watch_disconnect())
            tasks = [work, disconnect_task]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if disconnect_task in done:
                return
            await work
            await websocket.close(code=1000)
        except WebSocketDisconnect:
            disconnected()
        except asyncio.CancelledError:
            cancelled = True
            raise
        except ValueError as error:
            if not cancel_event.is_set():
                try:
                    await send_json({"type": "error", "message": str(error)})
                    await websocket.close(code=1008)
                except WebSocketDisconnect:
                    disconnected()
        except Exception:
            logger.exception("Scan failed")
            try:
                if not cancel_event.is_set():
                    await send_json({"type": "error", "message": "Scan failed"})
                    await websocket.close(code=1011)
            except (WebSocketDisconnect, RuntimeError):
                pass
        finally:
            cancel_event.set()
            if region is not None and not completed and (client_disconnected or cancelled):
                logger.info("scan cancelled region=%s", region)
            for task in tasks:
                if not task.done():
                    task.cancel()
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                scan_cancel_event.reset(cancel_token)
                logger.info("connection closed")

    return app


app = create_app(default_scouts(), pc_alpha=float(os.getenv("GAIA_PCMCI_PC_ALPHA", "0.2")))
