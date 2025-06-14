from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel # Using Pydantic V1 style for now as per your current files
# from pydantic import BaseModel, ConfigDict # For Pydantic V2 style model_config
from typing import List, Dict # Added Dict for type hinting
import joblib
import numpy as np
import pandas as pd
import io # For reading file in memory
import os
import torch
from contextlib import asynccontextmanager # For lifespan manager
import logging # Import Python's standard logging

# Import the model class (explicit relative import)
from .model_definition import MLPDetector

# --- OpenTelemetry Imports ---
from opentelemetry import trace
# For logging, directly import what's needed from _logs (API) and sdk.logs
from opentelemetry._logs import set_logger_provider # API to set the global logger provider
# If you need to get an OTEL logger directly (usually not needed if using standard logging + instrumentor):
# from opentelemetry._logs import get_logger as get_otel_logger

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk._logs import LoggerProvider as OtelSDKLoggerProvider # SDK components for Logs
from opentelemetry.sdk._logs._internal.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter # For OTLP logs
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor # OTEL Logging instrumentor
from opentelemetry.trace import Status, StatusCode # For setting span status

# --- Application Configuration ---
INPUT_SIZE = 115
HIDDEN_SIZE_1 = 128
HIDDEN_SIZE_2 = 64
OUTPUT_SIZE = 1
DROPOUT_RATE = 0.4

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "saved_assets", "best_nbiot_detector.pth")
SCALER_PATH = os.path.join(BASE_DIR, "saved_assets", "nbiot_multi_device_scaler.gz")

# OTEL Configuration
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "nbiot-detector-api")
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://localhost:4318/v1/traces")
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", "http://localhost:4318/v1/logs")

# --- Setup Standard Python Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] [%(module)s:%(lineno)d] - %(message)s", # Added more detail to format
)
logger = logging.getLogger(__name__)

# Global variables
model: MLPDetector = None
scaler = None
device: torch.device = None
tracer: trace.Tracer = None
otel_sdk_logger_provider: OtelSDKLoggerProvider = None


# --- Pydantic Models ---
class NetworkFeaturesInput(BaseModel):
    features: List[float]
    class Config: # Pydantic V1 style
        schema_extra = { "example": { "features": [0.12] * INPUT_SIZE } }
    # For Pydantic V2, use model_config = ConfigDict(...)

class PredictionResponse(BaseModel):
    prediction_label: int
    status: str
    probability_attack: float

# --- Helper Functions with OTEL Decorators ---
# Note: 'scaler', 'device', 'model', 'logger' are used as globals here.
# The decorator will use the global 'tracer' once initialized.

# To use the global tracer in decorators, ensure it's initialized before these functions are defined,
# or get the tracer inside. Using trace.get_tracer(__name__) directly in decorator is safer if tracer global is not yet set.
# If tracer is guaranteed to be set by lifespan before any request hits: @tracer.start_as_current_span(...)
# Otherwise: @trace.get_tracer(__name__).start_as_current_span(...)

@trace.get_tracer(__name__).start_as_current_span("preprocess_single_features")
def _preprocess_single(features_list: List[float]) -> torch.Tensor:
    current_span = trace.get_current_span()
    logger.info(f"Preprocessing {len(features_list)} features for single prediction.")
    current_span.set_attribute("num_input_features", len(features_list))
    try:
        features_np = np.array(features_list).reshape(1, -1)
        scaled_features_np = scaler.transform(features_np) # Uses global scaler
        features_tensor = torch.tensor(scaled_features_np, dtype=torch.float32).to(device) # Uses global device
        current_span.set_attribute("output_tensor_shape", str(features_tensor.shape))
        logger.debug("Preprocessing successful for single prediction.")
        return features_tensor
    except Exception as e:
        logger.error("Error during single feature preprocessing.", exc_info=True)
        current_span.record_exception(e)
        current_span.set_status(Status(StatusCode.ERROR, description=str(e)))
        raise

@trace.get_tracer(__name__).start_as_current_span("run_single_inference")
def _run_single_inference(features_tensor: torch.Tensor) -> Dict[str, float]:
    current_span = trace.get_current_span()
    logger.info("Running single inference.")
    try:
        with torch.no_grad():
            output_logit = model(features_tensor) # Uses global model
            probability_attack = torch.sigmoid(output_logit).item()
        current_span.set_attribute("raw_logit", output_logit.item())
        current_span.set_attribute("probability_attack", probability_attack)
        logger.debug(f"Single inference successful. Probability: {probability_attack:.4f}")
        return {"logit": output_logit.item(), "probability_attack": probability_attack}
    except Exception as e:
        logger.error("Error during single model inference.", exc_info=True)
        current_span.record_exception(e)
        current_span.set_status(Status(StatusCode.ERROR, description=str(e)))
        raise

# --- Lifespan Event Handler ---
@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    global model, scaler, device, tracer, otel_sdk_logger_provider

    # 1. Configure OpenTelemetry Tracing
    # (Ensure OTEL_SERVICE_NAME and OTEL_EXPORTER_OTLP_TRACES_ENDPOINT are available)
    resource = Resource(attributes={"service.name": OTEL_SERVICE_NAME})
    trace_provider = TracerProvider(resource=resource)
    otlp_trace_exporter = OTLPSpanExporter(endpoint=OTEL_EXPORTER_OTLP_TRACES_ENDPOINT)
    trace_processor = BatchSpanProcessor(otlp_trace_exporter)
    trace_provider.add_span_processor(trace_processor)
    trace.set_tracer_provider(trace_provider)
    tracer = trace.get_tracer(__name__) # Initialize the global tracer
    logger.info(f"OTEL Tracing configured. Service: {OTEL_SERVICE_NAME}, Endpoint: {OTEL_EXPORTER_OTLP_TRACES_ENDPOINT}")

    # 2. Configure OpenTelemetry Logging SDK
    otel_sdk_logger_provider = OtelSDKLoggerProvider(resource=resource)
    otlp_log_exporter = OTLPLogExporter(endpoint=OTEL_EXPORTER_OTLP_LOGS_ENDPOINT)
    log_processor = BatchLogRecordProcessor(otlp_log_exporter)
    otel_sdk_logger_provider.add_log_record_processor(log_processor)
    set_logger_provider(otel_sdk_logger_provider) # Set the global OTEL logger provider

    # Instrument Python's standard logging to add trace context
    # It will use the globally set otel_sdk_logger_provider
    LoggingInstrumentor().instrument(set_logging_format=True)
    logger.info(f"OTEL Logging instrumentor configured. Log Endpoint: {OTEL_EXPORTER_OTLP_LOGS_ENDPOINT}")
    
    # 3. Load ML Assets
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Lifespan: Using device: {device}")

    logger.info(f"Lifespan: Loading scaler from {SCALER_PATH}")
    if not os.path.exists(SCALER_PATH):
        logger.critical(f"CRITICAL: Scaler file not found at {SCALER_PATH}")
        raise RuntimeError(f"Scaler file not found at {SCALER_PATH}")
    try:
        scaler = joblib.load(SCALER_PATH)
        logger.info("Lifespan: Scaler loaded successfully.")
    except Exception as e:
        logger.critical("Lifespan: CRITICAL Error loading scaler.", exc_info=True)
        raise RuntimeError(f"Error loading scaler: {e}")

    logger.info(f"Lifespan: Loading model from {MODEL_PATH}")
    if not os.path.exists(MODEL_PATH):
        logger.critical(f"CRITICAL: Model file not found at {MODEL_PATH}")
        raise RuntimeError(f"Model file not found at {MODEL_PATH}")
    try:
        model = MLPDetector(INPUT_SIZE, HIDDEN_SIZE_1, HIDDEN_SIZE_2, OUTPUT_SIZE, DROPOUT_RATE)
        model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
        model.to(device)
        model.eval()
        logger.info("Lifespan: PyTorch model loaded and set to evaluation mode.")
    except Exception as e:
        logger.critical("Lifespan: CRITICAL Error loading PyTorch model.", exc_info=True)
        raise RuntimeError(f"Error loading PyTorch model: {e}")
    
    logger.info("Lifespan: Startup tasks completed successfully.")
    yield
    # === Shutdown ===
    logger.info("Lifespan: Initiating shutdown procedures.")
    if trace_provider: # This is an SDK provider
        logger.info("Shutting down OpenTelemetry trace provider.")
        trace_provider.shutdown()
    if otel_sdk_logger_provider: # This is an SDK provider
        logger.info("Shutting down OpenTelemetry logger provider.")
        otel_sdk_logger_provider.shutdown()
    logger.info("Lifespan: Shutdown complete.")


# Initialize FastAPI app with the lifespan manager
app = FastAPI(
    title="N-BaIoT Botnet Detector API",
    description="API for detecting botnet attacks in IoT network traffic using a pre-trained MLP model. \n\n"
                "The model expects 115 pre-computed statistical features derived from network traffic, "
                "as defined by the N-BaIoT dataset methodology.",
    version="1.0.0",
    lifespan=lifespan
)

# Instrument FastAPI application AFTER app instantiation and route definitions (if any)
# For FastAPIInstrumentor, doing it here is fine.
FastAPIInstrumentor.instrument_app(app)

# --- API Endpoints ---
@app.get("/", summary="Root Endpoint")
async def read_root():
    logger.info("Root endpoint '/' accessed.")
    return {"message": "N-BaIoT Botnet Detector API. Navigate to /docs for API documentation."}

@app.post("/predict/", response_model=PredictionResponse, summary="Predict Single Instance")
async def predict_single_instance(data: NetworkFeaturesInput):
    logger.info(f"Received single prediction request with {len(data.features)} features.")
    # FastAPIInstrumentor creates a span for the endpoint. Get it to add attributes.
    current_endpoint_span = trace.get_current_span()
    current_endpoint_span.set_attribute("num_features_received", len(data.features))

    if model is None or scaler is None:
        logger.error("Model or scaler not loaded during single prediction request.")
        raise HTTPException(status_code=503, detail="Model or scaler not loaded. Server might be starting or encountered an error.")
    
    if len(data.features) != INPUT_SIZE:
        logger.warning(f"Invalid feature count for single prediction: {len(data.features)}, expected {INPUT_SIZE}.")
        current_endpoint_span.set_status(Status(StatusCode.ERROR, "Invalid feature count"))
        raise HTTPException(status_code=400, detail=f"Expected {INPUT_SIZE} features, got {len(data.features)}")

    try:
        # Call helper function for preprocessing (this will create its own span)
        features_tensor = _preprocess_single(data.features)
        
        # Call helper function for inference (this will create its own span)
        inference_result = _run_single_inference(features_tensor)
        probability_attack = inference_result["probability_attack"]
            
        prediction_label = 1 if probability_attack > 0.5 else 0
        status_message = "Attack" if prediction_label == 1 else "Benign"
        current_endpoint_span.set_attribute("prediction_status", status_message)
        logger.info(f"Single prediction successful: {status_message}, probability_attack: {probability_attack:.4f}")

        return PredictionResponse(
            prediction_label=prediction_label,
            status=status_message,
            probability_attack=probability_attack
        )
    except ValueError as ve: # Example: if np.array or scaler.transform raises ValueError not caught by _preprocess_single
        logger.warning(f"ValueError in single prediction endpoint: {str(ve)}", exc_info=True)
        current_endpoint_span.set_status(Status(StatusCode.ERROR, description=str(ve)))
        current_endpoint_span.record_exception(ve)
        raise HTTPException(status_code=422, detail=f"Invalid feature data: {str(ve)}")
    except Exception as e:
        logger.error("Unexpected error during single prediction endpoint.", exc_info=True)
        current_endpoint_span.set_status(Status(StatusCode.ERROR, description=str(e)))
        current_endpoint_span.record_exception(e)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during prediction: {str(e)}")

@app.post("/predict_batch/", response_model=List[PredictionResponse], summary="Predict Batch from CSV File")
async def predict_batch_from_csv(file: UploadFile = File(..., description="CSV file containing rows of 115 features per instance. No header row.")):
    logger.info(f"Received batch prediction request for file: {file.filename}")
    current_endpoint_span = trace.get_current_span() # Get span from FastAPIInstrumentor
    current_endpoint_span.set_attribute("filename", file.filename)

    if model is None or scaler is None:
        logger.error("Model or scaler not loaded during batch prediction request.")
        raise HTTPException(status_code=503, detail="Model or scaler not loaded.")
    if not file.filename.endswith(".csv"):
        logger.warning(f"Invalid file type for batch: {file.filename}")
        current_endpoint_span.set_status(Status(StatusCode.ERROR, "Invalid file type for batch"))
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a CSV file.")

    try:
        with tracer.start_as_current_span("csv_parsing_batch") as csv_span: # Custom span for CSV parsing
            logger.debug("Starting CSV parsing for batch.")
            contents = await file.read()
            try:
                df = pd.read_csv(io.BytesIO(contents), header=None)
            except pd.errors.EmptyDataError:
                logger.warning("Attempted to process an empty CSV for batch prediction.")
                csv_span.set_status(Status(StatusCode.ERROR, "CSV file is empty"))
                raise HTTPException(status_code=400, detail="CSV file is empty.")
            except pd.errors.ParserError as pe:
                logger.warning(f"CSV parsing error for batch: {str(pe)}")
                csv_span.set_status(Status(StatusCode.ERROR, "Error parsing CSV"))
                raise HTTPException(status_code=400, detail="Error parsing CSV file. Ensure it's valid CSV with numerical data and no header.")
            
            csv_span.set_attribute("num_rows_parsed", len(df))
            csv_span.set_attribute("num_cols_parsed", df.shape[1] if not df.empty else 0)
            logger.info(f"Parsed {len(df)} rows from batch CSV '{file.filename}'.")

        if df.empty:
             logger.warning("Batch CSV is empty after parsing.")
             current_endpoint_span.set_status(Status(StatusCode.ERROR, "CSV file is empty or contains no data rows"))
             raise HTTPException(status_code=400, detail="CSV file is empty or contains no data rows.")
        if df.shape[1] != INPUT_SIZE:
            logger.warning(f"Batch CSV from '{file.filename}' has incorrect columns: {df.shape[1]}, expected {INPUT_SIZE}.")
            current_endpoint_span.set_status(Status(StatusCode.ERROR, "Incorrect CSV column count"))
            raise HTTPException(
                status_code=400,
                detail=f"CSV file has incorrect number of columns. Expected {INPUT_SIZE}, got {df.shape[1]}."
            )

        with tracer.start_as_current_span("data_preprocessing_batch") as prep_span: # Custom span
            logger.debug(f"Starting batch data preprocessing for {len(df)} rows.")
            try:
                features_np_batch = df.values.astype(float)
            except ValueError as ve:
                logger.warning(f"Non-numeric data in batch CSV '{file.filename}': {str(ve)}")
                prep_span.set_status(Status(StatusCode.ERROR, "CSV contains non-numeric data"))
                raise HTTPException(status_code=400, detail="CSV contains non-numeric data where numbers are expected.")
            
            scaled_features_np_batch = scaler.transform(features_np_batch)
            features_tensor_batch = torch.tensor(scaled_features_np_batch, dtype=torch.float32).to(device)
            prep_span.set_attribute("batch_size", features_tensor_batch.shape[0])
            logger.info(f"Preprocessed batch of size {features_tensor_batch.shape[0]} from '{file.filename}'.")
        
        predictions_list = []
        with tracer.start_as_current_span("model_inference_batch") as infer_span: # Custom span
            logger.debug(f"Starting batch model inference for {features_tensor_batch.shape[0]} instances.")
            with torch.no_grad():
                output_logits_batch = model(features_tensor_batch)
                probabilities_attack_batch = torch.sigmoid(output_logits_batch)
            infer_span.set_attribute("num_predictions_calculated", len(probabilities_attack_batch))

            for i in range(len(probabilities_attack_batch)):
                prob_attack = probabilities_attack_batch[i].item()
                label = 1 if prob_attack > 0.5 else 0
                status = "Attack" if label == 1 else "Benign"
                predictions_list.append(PredictionResponse(
                    prediction_label=label, status=status, probability_attack=prob_attack
                ))
        current_endpoint_span.set_attribute("num_predictions_returned", len(predictions_list))
        logger.info(f"Batch prediction for '{file.filename}' successful. Returned {len(predictions_list)} predictions.")
        return predictions_list

    except HTTPException as http_exc:
        # Log HTTPExceptions that we raised intentionally for validation, etc.
        logger.warning(f"HTTPException in batch prediction for '{file.filename}': {http_exc.status_code} - {http_exc.detail}")
        current_endpoint_span.set_status(Status(StatusCode.ERROR, description=str(http_exc.detail)))
        raise http_exc # Re-raise to let FastAPI handle it
    except Exception as e:
        logger.error(f"Unexpected error during batch prediction for '{file.filename}'.", exc_info=True)
        current_endpoint_span.set_status(Status(StatusCode.ERROR, description=str(e)))
        current_endpoint_span.record_exception(e)
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred during batch processing: {str(e)}")
    finally:
        if file and hasattr(file, 'close') and callable(file.close):
            await file.close()
