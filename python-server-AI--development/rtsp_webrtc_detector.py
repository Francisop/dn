import cv2
import time
import logging
import asyncio
import json
import random
import queue
import torch
import numpy as np
import os
import signal
import sys
import base64
import argparse
from datetime import datetime
from ultralytics import YOLO
from threading import Thread, Event, Lock
from aiohttp import web, web_ws, ClientSession
from aiohttp_cors import setup as cors_setup, ResourceOptions
from av import VideoFrame
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, RTCConfiguration, RTCIceServer

# ==================== CONFIGURATION ====================


# rtmp://192.168.1.237/live/stream1 - test surveillance video
# rtsp://192.168.1.153:1554/live/1 body cam 6070
#rtsp://djiuser_p7GyO68feTrF:Jasonbrown200617@@192.168.1.106:8554/streaming/live/1 small drone 6080
# rtsp://djiuser_p7GyO68feTrF:Jasonbrown200617@@192.168.1.150:8554/streaming/live/1 big drone 6050


class Config:
    """Configuration class - can be initialized from environment variables or drone API data"""
    def __init__(self, drone_data=None):
        """
        Initialize configuration from drone API data or environment variables

        Args:
            drone_data: Dictionary containing drone configuration from API
        """
        if drone_data:
            # ALWAYS use streamUrl from database if it exists - don't construct anything
            stream_url = drone_data.get('streamUrl', '').strip()

            if stream_url and '://' in stream_url:
                # Use streamUrl directly from database
                self.RTSP_URL = stream_url
            else:
                # Fallback only if streamUrl is empty - raise error instead of constructing
                raise ValueError(
                    f"No valid streamUrl found in database for device {drone_data.get('deviceSerialNumber', 'UNKNOWN')}. "
                    "Please ensure streamUrl is set in the database before starting the detector."
                )

            self.STREAM_NAME = drone_data.get('metadata', {}).get('alias') or drone_data.get('deviceName', 'Unknown Drone')
            self.STREAM_DEVICE = drone_data.get('deviceCategory', 'Drone')
            self.DRONE_SERIAL = drone_data.get('deviceSerialNumber', 'UNKNOWN')
            
            # Port assignment: can be based on serial number hash or explicitly set
            # For now, use environment variable or auto-assign based on serial
            self.WEB_SERVER_PORT = int(os.getenv("WEB_SERVER_PORT", str(6000 + hash(self.DRONE_SERIAL) % 1000)))
        else:
            # Fallback to environment variables (backward compatibility)
            self.RTSP_URL = os.getenv("RTSP_URL", "rtsp://djiuser_p7GyO68feTrF:Jasonbrown200617@@192.168.1.106:8554/streaming/live/1")
            self.STREAM_NAME = os.getenv("STREAM_NAME", "RTSP Camera")
            self.STREAM_DEVICE = os.getenv("STREAM_DEVICE", "Drone")
            self.DRONE_SERIAL = os.getenv("DRONE_SERIAL", "UNKNOWN")
            self.WEB_SERVER_PORT = int(os.getenv("WEB_SERVER_PORT", "6080"))

        # Common configuration (from environment variables)
        self.NOTIFICATION_ENDPOINT = os.getenv("NOTIFICATION_ENDPOINT", "http://192.168.1.89:9000/notify")
        self.YOLO_MODEL = os.getenv("YOLO_MODEL", "yolo11l.pt")
        self.CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))
        self.NMS_THRESHOLD = float(os.getenv("NMS_THRESHOLD", "0.45"))

        # Notification cooldown period (seconds) - prevents duplicate notifications
        self.NOTIFICATION_COOLDOWN = float(os.getenv("NOTIFICATION_COOLDOWN", "30.0"))

        # Spatial filtering - distance threshold to consider objects as "same" (in pixels)
        self.SPATIAL_DISTANCE_THRESHOLD = float(os.getenv("SPATIAL_DISTANCE_THRESHOLD", "150.0"))

        # Surveillance-specific classes to detect (COCO dataset class IDs)
        # Priority 1: Use classes from drone data (detectionClasses field contains YOLO class IDs)
        # Priority 2: Fall back to default surveillance classes
        if drone_data and drone_data.get('detectionClasses'):
            # detectionClasses is already an array of integers
            self.SURVEILLANCE_CLASSES = drone_data.get('detectionClasses', [])
        else:
            # Default surveillance classes (all 18 surveillance-specific classes)
            self.SURVEILLANCE_CLASSES = [
                0, 1, 2, 3, 5, 7, 14, 15, 16, 24, 26, 28, 32, 39, 41, 43, 73, 76
            ]

        # Stream processing settings
        self.OUTPUT_WIDTH = int(os.getenv("OUTPUT_WIDTH", "640"))
        self.OUTPUT_HEIGHT = int(os.getenv("OUTPUT_HEIGHT", "480"))
        self.WEB_SERVER_HOST = os.getenv("WEB_SERVER_HOST", "0.0.0.0")
        # Public host for client connections (defaults to localhost, override with actual IP/domain in production)
        self.PUBLIC_HOST = os.getenv("PUBLIC_HOST", "localhost")
        self.RECONNECT_DELAY = int(os.getenv("RECONNECT_DELAY", "5"))
        self.RTSP_TIMEOUT = int(os.getenv("RTSP_TIMEOUT", "10"))
        self.BUFFER_SIZE = int(os.getenv("BUFFER_SIZE", "1"))
        self.WATCHDOG_TIMEOUT = int(os.getenv("WATCHDOG_TIMEOUT", "15"))
        self.CAPTURE_READ_TIMEOUT = int(os.getenv("CAPTURE_READ_TIMEOUT", "5"))
        self.PROCESS_EVERY_N_FRAMES = int(os.getenv("PROCESS_EVERY_N_FRAMES", "1"))


# ==================== DRONE API CLIENT ====================
async def fetch_drone_config(serial_number, api_base_url="http://127.0.0.1:5000/api/v1/drones"):
    """
    Fetch drone configuration from the API

    Args:
        serial_number: Drone serial number to fetch
        api_base_url: Base URL of the drone management API

    Returns:
        tuple: (drone_data dict, is_stream_active bool)

    Raises:
        Exception: If drone not found or API request fails
    """
    url = f"{api_base_url}/sn/{serial_number}"

    async with ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 404:
                    raise Exception(f"Drone with serial number '{serial_number}' not found in database")
                elif response.status != 200:
                    raise Exception(f"API request failed with status {response.status}")

                data = await response.json()
                drone = data.get('data', {}).get('drone', {})

                if not drone:
                    raise Exception("Invalid API response: missing drone data")

                # Check if stream is active
                is_stream_active = drone.get('streamIsOn', False)

                return drone, is_stream_active

        except Exception as e:
            raise Exception(f"Failed to fetch drone configuration: {str(e)}")


async def update_drone_webrtc_url(serial_number, webrtc_url, api_base_url="http://127.0.0.1:5000/api/v1/drones"):
    """
    Update drone's webRTCUrl in the database

    Args:
        serial_number: Drone serial number
        webrtc_url: WebRTC URL (format: http://host:port/sn)
        api_base_url: Base URL of the drone management API

    Returns:
        bool: True if successful, False otherwise
    """
    url = f"{api_base_url}/sn/{serial_number}"

    async with ClientSession() as session:
        try:
            payload = {"webRTCUrl": webrtc_url}
            async with session.patch(url, json=payload) as response:
                if response.status == 200:
                    return True
                else:
                    print(f"Warning: Failed to update webRTCUrl in database (status {response.status})")
                    return False
        except Exception as e:
            print(f"Warning: Failed to update webRTCUrl: {str(e)}")
            return False


# ==================== NOTIFICATION MANAGER ====================
class NotificationManager:
    """Manages object detection notifications with cooldown-based and spatial deduplication"""
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.tracked_objects = {}  # Dict of {track_id: {"time": last_time, "position": (cx, cy), "class": class_name}}
        self.notification_cooldown = self.config.NOTIFICATION_COOLDOWN
        self.spatial_threshold = self.config.SPATIAL_DISTANCE_THRESHOLD
        self.notification_queue = asyncio.Queue()
        self.session = None
        self.last_cleanup_time = time.time()

    async def initialize(self):
        """Initialize aiohttp ClientSession for sending notifications"""
        self.session = ClientSession()
        self.logger.info(f"NotificationManager initialized - endpoint: {self.config.NOTIFICATION_ENDPOINT}")
        self.logger.info(f"Notification cooldown: {self.notification_cooldown}s between duplicate notifications")
        self.logger.info(f"Spatial filtering: {self.spatial_threshold}px distance threshold")

    async def cleanup(self):
        """Cleanup resources"""
        if self.session:
            await self.session.close()

    def cleanup_old_tracks(self):
        """Remove old track IDs from memory to prevent memory leak"""
        now = time.time()
        # Only cleanup every 60 seconds
        if now - self.last_cleanup_time < 60:
            return

        # Remove tracks older than 5 minutes (300 seconds)
        expired_tracks = [
            track_id for track_id, track_data in self.tracked_objects.items()
            if now - track_data["time"] > 300
        ]

        for track_id in expired_tracks:
            del self.tracked_objects[track_id]

        if expired_tracks:
            self.logger.info(f"Cleaned up {len(expired_tracks)} expired track IDs from memory")

        self.last_cleanup_time = now

    def calculate_distance(self, pos1, pos2):
        """Calculate Euclidean distance between two positions"""
        return ((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2) ** 0.5

    def find_nearby_notification(self, class_name, center_position):
        """
        Check if there's a recent notification for the same class nearby
        Returns (is_duplicate, reason) tuple
        """
        now = time.time()

        for track_id, track_data in self.tracked_objects.items():
            # Only compare same object class
            if track_data["class"] != class_name:
                continue

            # Calculate distance between centers
            distance = self.calculate_distance(center_position, track_data["position"])

            # If within spatial threshold
            if distance < self.spatial_threshold:
                time_since_last = now - track_data["time"]

                # If within cooldown period
                if time_since_last < self.notification_cooldown:
                    return True, f"Too close to recent notification (dist: {distance:.1f}px, {time_since_last:.1f}s ago)"

        return False, None

    def is_new_detection(self, track_id, class_name, bbox):
        """
        Check if this detection should trigger a notification
        Uses both cooldown period AND spatial filtering to prevent duplicates

        Returns True if:
        - First time seeing this track ID AND not near any recent notification, OR
        - Cooldown period has expired since last notification for this track
        """
        if track_id is None:
            return False

        now = time.time()

        # Cleanup old tracks periodically
        self.cleanup_old_tracks()

        # Calculate center position from bbox
        x1, y1, x2, y2 = bbox
        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2
        center_position = (center_x, center_y)

        # Check if we've seen this exact track ID before
        if track_id in self.tracked_objects:
            track_data = self.tracked_objects[track_id]
            time_since_last = now - track_data["time"]

            # If cooldown period hasn't passed, don't notify
            if time_since_last < self.notification_cooldown:
                return False
            else:
                # Cooldown expired, update and allow notification
                self.logger.info(f"🔄 Re-notifying for {class_name}#{track_id} (cooldown expired: {time_since_last:.1f}s)")
                self.tracked_objects[track_id] = {
                    "time": now,
                    "position": center_position,
                    "class": class_name
                }
                return True
        else:
            # New track ID - check if there's a similar detection nearby (spatial filtering)
            is_duplicate, reason = self.find_nearby_notification(class_name, center_position)

            if is_duplicate:
                self.logger.debug(f"🚫 Blocking duplicate: {class_name}#{track_id} - {reason}")
                # Still track this ID to prevent future notifications
                self.tracked_objects[track_id] = {
                    "time": now,
                    "position": center_position,
                    "class": class_name
                }
                return False
            else:
                # Truly new detection - allow notification
                self.tracked_objects[track_id] = {
                    "time": now,
                    "position": center_position,
                    "class": class_name
                }
                return True

    def encode_frame_to_base64(self, frame, bbox):
        """Extract bbox region from frame and encode as base64 JPEG"""
        try:
            x1, y1, x2, y2 = bbox
            # Ensure coordinates are within frame bounds
            h, w = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            # Extract bbox region
            bbox_img = frame[y1:y2, x1:x2]

            # Encode as JPEG
            _, buffer = cv2.imencode('.jpg', bbox_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
            base64_str = base64.b64encode(buffer).decode('utf-8')
            return base64_str
        except Exception as e:
            self.logger.error(f"Error encoding frame: {e}")
            return None

    async def send_notification(self, detection_data):
        """Send POST request to notification endpoint"""
        try:
            if not self.session:
                self.logger.warning("NotificationManager session not initialized")
                return

            async with self.session.post(
                self.config.NOTIFICATION_ENDPOINT,
                json=detection_data,
                timeout=5
            ) as response:
                if response.status == 200:
                    self.logger.info(f"✅ Notification sent: {detection_data['object_class']}#{detection_data['track_id']}")
                else:
                    self.logger.warning(f"⚠️ Notification failed: HTTP {response.status}")
        except asyncio.TimeoutError:
            self.logger.error("❌ Notification timeout")
        except Exception as e:
            self.logger.error(f"❌ Notification error: {e}")

    def queue_notification(self, frame, box, class_name, track_id, confidence):
        """Queue a notification for async sending (call from sync context)"""
        # Extract bbox coordinates
        x1, y1, x2, y2 = box

        # Encode frame with bbox
        frame_base64 = self.encode_frame_to_base64(frame, [x1, y1, x2, y2])

        # Prepare detection data
        detection_data = {
            "object_class": class_name,
            "track_id": int(track_id),
            "confidence": float(confidence),
            "timestamp": datetime.now().isoformat(),
            "device_name": self.config.STREAM_NAME,
            "device_type": self.config.STREAM_DEVICE,
            "bbox": {
                "x1": int(x1),
                "y1": int(y1),
                "x2": int(x2),
                "y2": int(y2)
            },
            "frame_base64": frame_base64
        }

        # Queue for async sending (non-blocking)
        try:
            self.notification_queue.put_nowait(detection_data)
        except asyncio.QueueFull:
            self.logger.warning("Notification queue full, dropping notification")


# ==================== VIDEO STREAM TRACK ====================
class YOLOVideoStreamTrack(VideoStreamTrack):
    """WebRTC video stream track with YOLO detection"""
    def __init__(self, detector):
        super().__init__()
        self.detector = detector
        self.last_frame = None

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        frame = None
        while not self.detector.processed_frame_queue.empty():
            try:
                frame = self.detector.processed_frame_queue.get_nowait()
            except queue.Empty:
                break

        if frame is None:
            frame = self.last_frame
        if frame is None:
            frame = np.zeros((self.detector.config.OUTPUT_HEIGHT, self.detector.config.OUTPUT_WIDTH, 3), dtype=np.uint8)
        else:
            self.last_frame = frame

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        av_frame = VideoFrame.from_ndarray(rgb_frame, format="rgb24")
        av_frame.pts = pts
        av_frame.time_base = time_base
        return av_frame


class CleanVideoStreamTrack(VideoStreamTrack):
    """WebRTC video stream track for clean/raw video (zero latency, no processing)"""
    def __init__(self, detector):
        super().__init__()
        self.detector = detector
        self.last_frame = None

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        frame = None

        # Get the most recent frame only (drop all intermediate frames for lowest latency)
        while not self.detector.clean_frame_queue.empty():
            try:
                frame = self.detector.clean_frame_queue.get_nowait()
            except queue.Empty:
                break

        if frame is None:
            frame = self.last_frame
        if frame is None:
            frame = np.zeros((self.detector.config.OUTPUT_HEIGHT, self.detector.config.OUTPUT_WIDTH, 3), dtype=np.uint8)
        else:
            self.last_frame = frame

        # Resize for consistent output
        frame = cv2.resize(frame, (self.detector.config.OUTPUT_WIDTH, self.detector.config.OUTPUT_HEIGHT))
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        av_frame = VideoFrame.from_ndarray(rgb_frame, format="rgb24")
        av_frame.pts = pts
        av_frame.time_base = time_base
        return av_frame


# ==================== DETECTOR CLASS ====================
class WebRTCDetector:
    """RTSP Stream Object Detection with YOLO and WebRTC"""
    def __init__(self, config=None):
        """
        Initialize WebRTC Detector

        Args:
            config: Config instance (if None, creates default Config)
        """
        self.config = config if config else Config()
        self.setup_logging()
        self.logger.info(f"Initializing stream: {self.config.STREAM_NAME}")
        self.logger.info(f"Drone Serial: {self.config.DRONE_SERIAL}")
        self.logger.info("Loading YOLO model...")

        self.model = YOLO(self.config.YOLO_MODEL)
        if torch.cuda.is_available():
            self.device = "cuda"
            self.model.to(self.device)  # Removed .half() to fix tracking dtype error
            self.logger.info(f"Using CUDA: {torch.cuda.get_device_name(0)} (FP32 mode - tracking enabled)")
        else:
            print("CUDA not available, using CPU")
            self.device = "cpu"
            self.model.to(self.device)
            self.logger.warning("CUDA not available — using CPU")

        self.class_colors = {cls: (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
                             for cls in self.model.names.keys()}

        # Log surveillance classes being monitored
        surveillance_class_names = [self.model.names[cls_id] for cls_id in self.config.SURVEILLANCE_CLASSES]
        self.logger.info(f"Monitoring {len(surveillance_class_names)} surveillance classes: {', '.join(surveillance_class_names)}")

        # Initialize notification manager
        self.notification_manager = NotificationManager(self.config, self.logger)

        self.cap = None
        self.cap_lock = Lock()  # Protect cap operations
        self.reconnect_count = 0
        self.peer_connections = set()
        self.clean_peer_connections = set()
        self.stop_event = Event()
        self.restart_capture_event = Event()  # Signal to restart capture

        self.raw_frame_queue = queue.Queue(maxsize=1)
        self.processed_frame_queue = queue.Queue(maxsize=1)
        self.clean_frame_queue = queue.Queue(maxsize=1)  # For clean stream (zero latency)

        self.last_fps_time = time.time()
        self.frame_count = 0
        self.fps = 0.0
        self.last_frame_time = time.time()  # for watchdog
        self.last_capture_time = time.time()  # Track capture thread health
        self.is_healthy = True  # Overall health status
        self.frame_skip_counter = 0  # For frame skipping optimization

    def setup_logging(self):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
        self.logger = logging.getLogger(__name__)

    def connect_to_stream(self):
        """Connect to RTSP stream with timeout protection"""
        try:
            self.logger.info(f"Connecting to RTSP stream...")
            with self.cap_lock:
                if self.cap is not None:
                    self.cap.release()
                    self.cap = None

                # Create capture with timeout settings
                self.cap = cv2.VideoCapture(self.config.RTSP_URL, cv2.CAP_FFMPEG)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, self.config.BUFFER_SIZE)
                # Set read timeout (in milliseconds)
                self.cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.config.RTSP_TIMEOUT * 1000)
                self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.config.CAPTURE_READ_TIMEOUT * 1000)

                if not self.cap.isOpened():
                    raise ConnectionError("Failed to open video stream")

                ret, frame = self.cap.read()
                if not ret or frame is None:
                    raise ConnectionError("Failed to read initial frame")

            self.logger.info("RTSP connected successfully")
            self.reconnect_count = 0
            return True
        except Exception as e:
            self.logger.error(f"Stream connection failed: {e}")
            with self.cap_lock:
                if self.cap:
                    self.cap.release()
                    self.cap = None
            return False

    def draw_boxes(self, frame, results):
        """Draw bounding boxes with tracking IDs and info overlay"""
        boxes = results.boxes
        names = self.model.names
        if boxes is not None and len(boxes) > 0:
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].int().tolist()
                conf = float(box.conf[0])
                cls = int(box.cls[0])

                # Get track ID if available (BoT-SORT)
                track_id = None
                if hasattr(box, 'id') and box.id is not None:
                    track_id = int(box.id[0])

                # Check if this is a new detection and queue notification
                if track_id is not None and self.notification_manager.is_new_detection(track_id, names[cls], [x1, y1, x2, y2]):
                    self.logger.info(f"🆕 New object detected: {names[cls]}#{track_id}")
                    # Queue notification (non-blocking)
                    self.notification_manager.queue_notification(
                        frame=frame.copy(),
                        box=[x1, y1, x2, y2],
                        class_name=names[cls],
                        track_id=track_id,
                        confidence=conf
                    )

                # Build label with track ID
                if track_id is not None:
                    label = f"{names[cls]}#{track_id} {conf*100:.1f}%"
                else:
                    label = f"{names[cls]} {conf*100:.1f}%"

                color = self.class_colors.get(cls, (0, 255, 0))
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
                cv2.rectangle(frame, (x1, y1 - 20), (x1 + w, y1), color, -1)
                cv2.putText(frame, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX,
                            0.5, (0, 0, 0), 1, cv2.LINE_AA)

        # Update FPS
        now = time.time()
        self.frame_count += 1
        if now - self.last_fps_time >= 1.0:
            self.fps = self.frame_count / (now - self.last_fps_time)
            self.last_fps_time = now
            self.frame_count = 0

        # Draw stream info overlay
        cv2.putText(frame, f"{self.config.STREAM_NAME}", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, f"FPS: {self.fps:.1f}", (10, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        return frame

    def process_frame(self, frame):
        """Process frame with YOLO inference and optional ByteTrack object tracking"""
        frame = cv2.resize(frame, (self.config.OUTPUT_WIDTH, self.config.OUTPUT_HEIGHT))
        try:
            with torch.no_grad():
                # Try tracking first, fall back to detection if tracking fails
                try:
                    results = self.model.track(
                        frame,
                        conf=self.config.CONFIDENCE_THRESHOLD,
                        iou=self.config.NMS_THRESHOLD,
                        classes=self.config.SURVEILLANCE_CLASSES,  # Filter to surveillance classes
                        persist=True,
                        tracker="botsort.yaml",  # BoT-SORT for better ID persistence
                        verbose=False,
                        device=self.device
                    )[0]
                except Exception as track_error:
                    # Fall back to regular detection if tracking fails
                    self.logger.warning(f"Tracking failed, using detection only: {track_error}")
                    results = self.model.predict(
                        frame,
                        conf=self.config.CONFIDENCE_THRESHOLD,
                        iou=self.config.NMS_THRESHOLD,
                        classes=self.config.SURVEILLANCE_CLASSES,  # Filter to surveillance classes
                        verbose=False,
                        device=self.device
                    )[0]

            if self.device == "cuda":
                torch.cuda.synchronize()
            frame = self.draw_boxes(frame, results)
            self.is_healthy = True
        except Exception as e:
            self.logger.error(f"Error in inference: {e}")
            self.is_healthy = False
            # Draw error message on frame
            cv2.putText(frame, "INFERENCE ERROR", (10, 100),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
        finally:
            # Always update frame time and clean GPU memory
            self.last_frame_time = time.time()
            if self.device == "cuda":
                try:
                    torch.cuda.empty_cache()
                except:
                    pass
        return frame

    def capture_thread_worker(self):
        """Continuously capture frames from RTSP with timeout protection"""
        while not self.stop_event.is_set():
            # Check if restart requested
            if self.restart_capture_event.is_set():
                self.logger.info("Capture restart requested")
                with self.cap_lock:
                    if self.cap:
                        self.cap.release()
                        self.cap = None
                self.restart_capture_event.clear()

            # Reconnect if needed
            if self.cap is None or not self.cap.isOpened():
                if not self.connect_to_stream():
                    self.reconnect_count += 1
                    self.logger.warning(f"Reconnect attempt #{self.reconnect_count}")
                    time.sleep(self.config.RECONNECT_DELAY)
                    continue

            # Try to read frame with timeout protection
            try:
                with self.cap_lock:
                    if self.cap and self.cap.isOpened():
                        ret, frame = self.cap.read()
                    else:
                        ret, frame = False, None

                if not ret or frame is None:
                    self.logger.warning("Frame read failed — reconnecting...")
                    with self.cap_lock:
                        if self.cap:
                            self.cap.release()
                            self.cap = None
                    time.sleep(1)
                    continue

                # Successfully captured frame
                self.last_capture_time = time.time()

                # Feed frame to AI detection pipeline
                try:
                    self.raw_frame_queue.put_nowait(frame)
                except queue.Full:
                    pass  # Drop old frame

                # Feed frame to clean stream (zero latency - always use fresh frame)
                try:
                    self.clean_frame_queue.put_nowait(frame.copy())
                except queue.Full:
                    pass  # Drop old frame

            except Exception as e:
                self.logger.error(f"Capture error: {e}")
                with self.cap_lock:
                    if self.cap:
                        self.cap.release()
                        self.cap = None
                time.sleep(1)

    def processing_thread_worker(self):
        """Run YOLO inference on captured frames with optional frame skipping"""
        last_processed_frame = None
        while not self.stop_event.is_set():
            try:
                frame = self.raw_frame_queue.get(timeout=1)

                # Frame skipping logic for performance boost
                self.frame_skip_counter += 1
                if self.config.PROCESS_EVERY_N_FRAMES > 1:
                    if self.frame_skip_counter % self.config.PROCESS_EVERY_N_FRAMES != 0:
                        # Skip this frame, but re-use last processed frame with current raw overlay
                        if last_processed_frame is not None:
                            try:
                                self.processed_frame_queue.put_nowait(last_processed_frame)
                            except queue.Full:
                                pass
                        continue

                # Process this frame
                processed = self.process_frame(frame)
                last_processed_frame = processed
                try:
                    self.processed_frame_queue.put_nowait(processed)
                except queue.Full:
                    pass
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Processing error: {e}")

    def watchdog_thread_worker(self):
        """Enhanced watchdog: monitors both capture and processing threads"""
        while not self.stop_event.is_set():
            now = time.time()

            # Check if processing is stale
            if now - self.last_frame_time > self.config.WATCHDOG_TIMEOUT:
                self.logger.warning(f"Watchdog: No processed frames for {int(now - self.last_frame_time)}s")
                self.is_healthy = False
                self.restart_capture_event.set()

            # Check if capture is stale
            if now - self.last_capture_time > self.config.WATCHDOG_TIMEOUT:
                self.logger.warning(f"Watchdog: No captured frames for {int(now - self.last_capture_time)}s")
                self.is_healthy = False
                self.restart_capture_event.set()

            # Check queue health
            if self.raw_frame_queue.qsize() == 0 and self.processed_frame_queue.qsize() == 0:
                if now - self.last_capture_time > 5:
                    self.logger.warning("Watchdog: Queues empty, possible pipeline stall")
                    self.restart_capture_event.set()

            time.sleep(3)

    async def notification_worker(self):
        """Async worker that processes notification queue"""
        self.logger.info("Notification worker started")
        while not self.stop_event.is_set():
            try:
                # Get notification from queue (with timeout to allow checking stop_event)
                detection_data = await asyncio.wait_for(
                    self.notification_manager.notification_queue.get(),
                    timeout=1.0
                )
                # Send notification
                await self.notification_manager.send_notification(detection_data)
            except asyncio.TimeoutError:
                continue  # No notification in queue, check again
            except Exception as e:
                self.logger.error(f"Error in notification worker: {e}")

    async def websocket_handler(self, request):
        """WebSocket handler for AI detection stream"""
        ws = web_ws.WebSocketResponse()
        await ws.prepare(request)
        self.logger.info("WebSocket connected (AI detection stream)")
        async for msg in ws:
            if msg.type == web_ws.WSMsgType.TEXT:
                data = json.loads(msg.data)
                await self.handle_signaling_message(ws, data)
        self.logger.info("WebSocket closed (AI detection stream)")
        return ws

    async def websocket_clean_handler(self, request):
        """WebSocket handler for clean/raw stream (zero latency)"""
        ws = web_ws.WebSocketResponse()
        await ws.prepare(request)
        self.logger.info("WebSocket connected (CLEAN stream)")
        async for msg in ws:
            if msg.type == web_ws.WSMsgType.TEXT:
                data = json.loads(msg.data)
                await self.handle_clean_signaling_message(ws, data)
        self.logger.info("WebSocket closed (CLEAN stream)")
        return ws

    async def handle_signaling_message(self, ws, data):
        """Handle WebRTC signaling for AI detection stream"""
        if data.get("type") == "offer":
            config = RTCConfiguration(iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])])
            pc = RTCPeerConnection(configuration=config)
            self.peer_connections.add(pc)
            # Create a new track instance for each peer connection
            video_track = YOLOVideoStreamTrack(self)
            pc.addTrack(video_track)
            await pc.setRemoteDescription(RTCSessionDescription(sdp=data["sdp"], type=data["type"]))
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            await ws.send_str(json.dumps({"type": "answer", "sdp": pc.localDescription.sdp}))

    async def handle_clean_signaling_message(self, ws, data):
        """Handle WebRTC signaling for clean stream"""
        if data.get("type") == "offer":
            config = RTCConfiguration(iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])])
            pc = RTCPeerConnection(configuration=config)
            self.clean_peer_connections.add(pc)
            # Create a new track instance for each peer connection
            clean_track = CleanVideoStreamTrack(self)
            pc.addTrack(clean_track)
            await pc.setRemoteDescription(RTCSessionDescription(sdp=data["sdp"], type=data["type"]))
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            await ws.send_str(json.dumps({"type": "answer", "sdp": pc.localDescription.sdp}))

    async def health_check_handler(self, request):
        """Health check endpoint for Kubernetes liveness/readiness probes"""
        now = time.time()
        capture_age = now - self.last_capture_time
        processing_age = now - self.last_frame_time

        health_data = {
            "status": "healthy" if self.is_healthy else "unhealthy",
            "stream_name": self.config.STREAM_NAME,
            "fps": round(self.fps, 2),
            "last_capture_seconds_ago": round(capture_age, 2),
            "last_processing_seconds_ago": round(processing_age, 2),
            "reconnect_count": self.reconnect_count,
            "connected_clients_ai": len(self.peer_connections),
            "connected_clients_clean": len(self.clean_peer_connections),
            "is_streaming": self.cap is not None and self.cap.isOpened()
        }

        # Determine HTTP status code
        if self.is_healthy and capture_age < 10 and processing_age < 10:
            status = 200  # Healthy
        elif capture_age < 30 or processing_age < 30:
            status = 503  # Degraded but recovering
        else:
            status = 503  # Unhealthy

        return web.json_response(health_data, status=status)

    async def metrics_handler(self, request):
        """Prometheus-style metrics endpoint"""
        metrics = f"""# HELP stream_fps Current frames per second
# TYPE stream_fps gauge
stream_fps{{stream="{self.config.STREAM_NAME}"}} {self.fps}

# HELP stream_healthy Stream health status (1=healthy, 0=unhealthy)
# TYPE stream_healthy gauge
stream_healthy{{stream="{self.config.STREAM_NAME}"}} {1 if self.is_healthy else 0}

# HELP stream_reconnects Total number of reconnections
# TYPE stream_reconnects counter
stream_reconnects{{stream="{self.config.STREAM_NAME}"}} {self.reconnect_count}

# HELP stream_clients_ai Number of connected WebRTC clients (AI detection)
# TYPE stream_clients_ai gauge
stream_clients_ai{{stream="{self.config.STREAM_NAME}"}} {len(self.peer_connections)}

# HELP stream_clients_clean Number of connected WebRTC clients (clean stream)
# TYPE stream_clients_clean gauge
stream_clients_clean{{stream="{self.config.STREAM_NAME}"}} {len(self.clean_peer_connections)}
"""
        return web.Response(text=metrics, content_type="text/plain")

    async def run_web_server(self):
        app = web.Application()
        cors = cors_setup(app, defaults={"*": ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*", allow_methods="*")})

        # Add routes - using serial number in path
        serial = self.config.DRONE_SERIAL if hasattr(self.config, 'DRONE_SERIAL') else 'UNKNOWN'
        app.router.add_get(f"/{serial}/ai", self.websocket_handler)
        app.router.add_get(f"/{serial}", self.websocket_clean_handler)
        app.router.add_get("/health", self.health_check_handler)
        app.router.add_get("/healthz", self.health_check_handler)  # K8s convention
        app.router.add_get("/metrics", self.metrics_handler)

        for route in list(app.router.routes()):
            cors.add(route)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.config.WEB_SERVER_HOST, self.config.WEB_SERVER_PORT)
        await site.start()
        self.logger.info(f"Server running at http://{self.config.WEB_SERVER_HOST}:{self.config.WEB_SERVER_PORT}")
        self.logger.info(f"  WebRTC (CLEAN): ws://{{host}}:{self.config.WEB_SERVER_PORT}/{serial}")
        self.logger.info(f"  WebRTC (AI):    ws://{{host}}:{self.config.WEB_SERVER_PORT}/{serial}/ai")
        self.logger.info(f"  Health:         http://{{host}}:{self.config.WEB_SERVER_PORT}/health")
        self.logger.info(f"  Metrics:        http://{{host}}:{self.config.WEB_SERVER_PORT}/metrics")

    def start_threads(self):
        Thread(target=self.capture_thread_worker, daemon=True).start()
        Thread(target=self.processing_thread_worker, daemon=True).start()
        Thread(target=self.watchdog_thread_worker, daemon=True).start()
        self.logger.info("Threads started")

    async def cleanup(self):
        """Graceful shutdown"""
        self.logger.info("Cleaning up...")
        self.stop_event.set()

        # Cleanup notification manager
        await self.notification_manager.cleanup()

        # Close WebRTC connections (AI detection)
        for pc in self.peer_connections.copy():
            try:
                await pc.close()
            except:
                pass
        self.peer_connections.clear()

        # Close WebRTC connections (clean stream)
        for pc in self.clean_peer_connections.copy():
            try:
                await pc.close()
            except:
                pass
        self.clean_peer_connections.clear()

        # Release camera
        with self.cap_lock:
            if self.cap:
                try:
                    self.cap.release()
                except:
                    pass
                self.cap = None

        # Clear GPU memory
        if self.device == "cuda":
            try:
                torch.cuda.empty_cache()
            except:
                pass

        self.logger.info("Cleanup complete")

    async def run(self):
        """Main run loop with signal handling"""
        self.logger.info("="*60)
        self.logger.info(f"Starting YOLO WebRTC Detector: {self.config.STREAM_NAME}")
        self.logger.info("="*60)

        # Setup signal handlers for graceful shutdown
        def signal_handler(sig, frame):
            self.logger.info(f"Received signal {sig}, shutting down...")
            self.stop_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Update webRTCUrl in database (if drone serial is available)
        if hasattr(self.config, 'DRONE_SERIAL') and self.config.DRONE_SERIAL != 'UNKNOWN':
            webrtc_url = f"http://{self.config.PUBLIC_HOST}:{self.config.WEB_SERVER_PORT}/{self.config.DRONE_SERIAL}"
            self.logger.info(f"Updating database with WebRTC URL: {webrtc_url}")
            api_url = os.getenv("DRONE_API_URL", "http://127.0.0.1:5000/api/v1/drones")
            await update_drone_webrtc_url(self.config.DRONE_SERIAL, webrtc_url, api_url)

        # Initialize notification manager
        await self.notification_manager.initialize()

        self.start_threads()
        await self.run_web_server()

        # Start notification worker task
        notification_task = asyncio.create_task(self.notification_worker())

        try:
            # Main loop - just keep running
            while not self.stop_event.is_set():
                await asyncio.sleep(1)

                # Log status every 30 seconds
                if int(time.time()) % 30 == 0:
                    self.logger.info(f"Status: FPS={self.fps:.1f}, Healthy={self.is_healthy}, "
                                   f"Clients(AI)={len(self.peer_connections)}, "
                                   f"Clients(Clean)={len(self.clean_peer_connections)}, "
                                   f"Reconnects={self.reconnect_count}")

        except KeyboardInterrupt:
            self.logger.info("Stopped by user (KeyboardInterrupt)")
        except Exception as e:
            self.logger.error(f"Unexpected error in main loop: {e}")
        finally:
            # Cancel notification task
            notification_task.cancel()
            try:
                await notification_task
            except asyncio.CancelledError:
                pass
            await self.cleanup()


# ==================== MAIN ENTRY ====================
async def main():
    """Main entry point"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='RTSP Object Detection System with WebRTC')
    parser.add_argument('--drone-serial', '-s', type=str,
                        help='Drone serial number (fetches config from API)')
    parser.add_argument('--api-url', type=str, default='http://127.0.0.1:5000/api/v1/drones',
                        help='Drone management API base URL')
    parser.add_argument('--skip-stream-check', action='store_true',
                        help='Skip checking if stream is active (start anyway)')

    args = parser.parse_args()

    print("="*60)
    print("RTSP Object Detection System")
    print("YOLOv8 + WebRTC Streaming")
    print("="*60)

    # Initialize config
    config = None

    if args.drone_serial:
        # Fetch configuration from API
        print(f"Fetching configuration for drone: {args.drone_serial}")
        print(f"API URL: {args.api_url}")
        print("-"*60)

        try:
            drone_data, is_stream_active = await fetch_drone_config(args.drone_serial, args.api_url)

            print(f"✓ Drone found: {drone_data.get('deviceName')}")
            print(f"  Alias: {drone_data.get('metadata', {}).get('alias', 'N/A')}")
            print(f"  Category: {drone_data.get('deviceCategory', 'N/A')}")
            print(f"  Stream Status: {'ACTIVE' if is_stream_active else 'INACTIVE'}")

            # Check if stream is active (unless skip flag is set)
            if not is_stream_active and not args.skip_stream_check:
                print("\n⚠ Stream is not active (streamIsOn = false)")
                print("  The stream must be activated before starting this server.")
                print("  Use --skip-stream-check to bypass this check.")
                print("="*60)
                sys.exit(1)

            # Create config from API data
            config = Config(drone_data=drone_data)

        except Exception as e:
            print(f"\n✗ Error: {str(e)}")
            print("\nFalling back to environment variables...")
            config = Config()
    else:
        # No serial number provided - use environment variables
        print("No drone serial number provided")
        print("Using configuration from environment variables")
        config = Config()

    print("-"*60)
    print(f"Stream Name: {config.STREAM_NAME}")
    print(f"Drone Serial: {config.DRONE_SERIAL}")
    print(f"RTSP URL: {config.RTSP_URL[:50]}...")
    print(f"Server Port: {config.WEB_SERVER_PORT}")
    print(f"YOLO Model: {config.YOLO_MODEL}")
    print("="*60)

    # Create and run detector
    detector = WebRTCDetector(config=config)
    await detector.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete")
        sys.exit(0)
