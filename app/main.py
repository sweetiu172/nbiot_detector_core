import os
import io
import json
import joblib
import numpy as np
import pandas as pd
import logging
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from sklearn.preprocessing import RobustScaler
import lightgbm

# --- OpenTelemetry Imports ---
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk._logs import LoggerProvider as OtelSDKLoggerProvider
from opentelemetry.sdk._logs._internal.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.trace import Status, StatusCode

# --- Application Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "saved_assets")

MODEL_PATH = os.path.join(ASSETS_DIR, "lgbm_nbiot_model.joblib")
SCALER_PATH = os.path.join(ASSETS_DIR, "lgbm_nbiot_scaler.gz")
FEATURE_LIST_PATH = os.path.join(ASSETS_DIR, "lgbm_features.json")

# OTEL Configuration
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "nbiot-detector-api")
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://localhost:4318/v1/traces")
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", "http://localhost:4318/v1/logs")

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] - %(message)s")
logger = logging.getLogger(__name__)

# --- Global Variables ---
lgbm_model: lightgbm = None
scaler: RobustScaler = None
feature_list: List[str] = None
tracer: trace.Tracer = None
otel_sdk_logger_provider: OtelSDKLoggerProvider = None

# --- Pydantic Models ---
class NetworkFeaturesInput(BaseModel):
    features: List[float]

class PredictionResponse(BaseModel):
    prediction_label: int
    status: str
    probability_attack: float

# --- Lifespan Event Handler (Loads assets at startup) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global lgbm_model, scaler, feature_list, tracer, otel_sdk_logger_provider

    # 1. Configure OpenTelemetry (Tracing and Logging)
    resource = Resource(attributes={"service.name": OTEL_SERVICE_NAME})
    
    # Configure Tracing
    trace_provider = TracerProvider(resource=resource)
    otlp_trace_exporter = OTLPSpanExporter(endpoint=OTEL_EXPORTER_OTLP_TRACES_ENDPOINT)
    trace_processor = BatchSpanProcessor(otlp_trace_exporter)
    trace_provider.add_span_processor(trace_processor)
    trace.set_tracer_provider(trace_provider)
    tracer = trace.get_tracer(__name__)
    logger.info(f"OTEL Tracing configured. Service: {OTEL_SERVICE_NAME}, Endpoint: {OTEL_EXPORTER_OTLP_TRACES_ENDPOINT}")

    # Configure Logging SDK
    otel_sdk_logger_provider = OtelSDKLoggerProvider(resource=resource)
    otlp_log_exporter = OTLPLogExporter(endpoint=OTEL_EXPORTER_OTLP_LOGS_ENDPOINT)
    log_processor = BatchLogRecordProcessor(otlp_log_exporter)
    otel_sdk_logger_provider.add_log_record_processor(log_processor)
    set_logger_provider(otel_sdk_logger_provider)
    
    # Instrument Python's standard logging
    LoggingInstrumentor().instrument(set_logging_format=True)
    logger.info(f"OTEL Logging instrumentor configured. Log Endpoint: {OTEL_EXPORTER_OTLP_LOGS_ENDPOINT}")
    
    # 2. Load ML Assets
    logger.info("Application startup: Loading ML assets...")
    try:
        with open(FEATURE_LIST_PATH, 'r') as f:
            feature_list = json.load(f)
        logger.info(f"Feature list with {len(feature_list)} features loaded successfully.")
        
        scaler = joblib.load(SCALER_PATH)
        logger.info("Scaler loaded successfully.")
        
        lgbm_model = joblib.load(MODEL_PATH)
        logger.info("LightGBM model loaded successfully.")
    except Exception as e:
        logger.error("CRITICAL: Failed to load ML assets.", exc_info=True)
        raise RuntimeError("Could not load ML assets") from e

    logger.info("Lifespan: Startup tasks completed successfully.")
    yield
    # === Shutdown ===
    logger.info("Lifespan: Initiating shutdown procedures.")
    if trace_provider:
        logger.info("Shutting down OpenTelemetry trace provider.")
        trace_provider.shutdown()
    if otel_sdk_logger_provider:
        logger.info("Shutting down OpenTelemetry logger provider.")
        otel_sdk_logger_provider.shutdown()
    logger.info("Lifespan: Shutdown complete.")

# Initialize FastAPI app
app = FastAPI(
    title="N-BaIoT Botnet Detector API (LightGBM)",
    lifespan=lifespan
)

# Instrument FastAPI for OpenTelemetry
FastAPIInstrumentor.instrument_app(app)

# --- API Endpoints ---
@app.get("/", summary="Root Endpoint", include_in_schema=False)
def read_root():
    return {"message": "N-BaIoT Botnet Detector API with LightGBM model is running."}

@app.post("/predict", response_model=PredictionResponse, summary="Predict a Single Instance")
def predict_single(data: NetworkFeaturesInput):
    current_span = trace.get_current_span()
    if not all([lgbm_model, scaler, feature_list]):
        raise HTTPException(status_code=503, detail="Model assets not loaded.")
    
    if len(data.features) != len(feature_list):
        raise HTTPException(status_code=400, detail=f"Expected {len(feature_list)} features, but got {len(data.features)}")

    try:
        features_np = np.array(data.features).reshape(1, -1)
        scaled_features = scaler.transform(features_np)
        
        # predict_proba returns [[P(benign), P(attack)]]
        probability_attack = lgbm_model.predict_proba(scaled_features)[0][1]
        
        threshold = 0.5  # Adjust this threshold based on your precision/recall needs
        prediction_label = 1 if probability_attack > threshold else 0
        status_message = "Attack" if prediction_label == 1 else "Benign"
        
        current_span.set_attribute("prediction.label", status_message)
        current_span.set_attribute("prediction.probability", probability_attack)

        return PredictionResponse(
            prediction_label=prediction_label,
            status=status_message,
            probability_attack=probability_attack
        )
    except Exception as e:
        logger.error("Error during single prediction", exc_info=True)
        current_span.record_exception(e)
        current_span.set_status(Status(StatusCode.ERROR, "Error during prediction"))
        raise HTTPException(status_code=500, detail="An unexpected error occurred during prediction.")


@app.post("/predict_batch", response_model=List[PredictionResponse], summary="Predict a Batch from a CSV File")
async def predict_batch(file: UploadFile = File(...)):
    current_span = trace.get_current_span()
    if not all([lgbm_model, scaler, feature_list]):
        raise HTTPException(status_code=503, detail="Model assets not loaded.")
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a CSV.")

    try:
        contents = await file.read()
        
        # Specific handling for CSV parsing errors
        try:
            df = pd.read_csv(io.BytesIO(contents), header=None)
        except pd.errors.EmptyDataError:
            logger.warning("Attempted to process an empty CSV for batch prediction.")
            raise HTTPException(status_code=400, detail="CSV file is empty or contains no data rows.")
        except pd.errors.ParserError as pe:
            logger.warning(f"CSV parsing error for batch: {str(pe)}")
            raise HTTPException(status_code=400, detail="Error parsing CSV file. Ensure it's valid CSV with numerical data and no header.")

        current_span.set_attribute("batch.row_count", len(df))

        if df.shape[1] != len(feature_list):
            raise HTTPException(status_code=400, detail=f"CSV has incorrect column count. Expected {len(feature_list)}, got {df.shape[1]}.")
        
        # Enforce correct feature order
        df.columns = feature_list
        features_np = df[feature_list].values
        
        scaled_features = scaler.transform(features_np)
        
        probabilities_batch = lgbm_model.predict_proba(scaled_features)
        
        predictions = []
        threshold = 0.5
        for prob in probabilities_batch:
            prob_attack = prob[1]
            label = 1 if prob_attack > threshold else 0
            status = "Attack" if label == 1 else "Benign"
            predictions.append(
                PredictionResponse(prediction_label=label, status=status, probability_attack=prob_attack)
            )
        return predictions

    except HTTPException as http_exc:
        # If we raised a specific HTTPException (like a 400), let it pass through
        raise http_exc
    except Exception as e:
        # Catch any other unexpected errors and return a 500
        logger.error("Error during batch prediction", exc_info=True)
        current_span.record_exception(e)
        current_span.set_status(Status(StatusCode.ERROR, "Unexpected error processing batch file"))
        raise HTTPException(status_code=500, detail="An unexpected server error occurred while processing the batch file.")