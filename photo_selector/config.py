import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent

class AppConfig:
    APP_NAME = "选片包生成工具"
    APP_VERSION = "1.0.0"
    
    SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}
    SUPPORTED_RAW_EXTENSIONS = {'.raw', '.cr2', '.nef', '.arw', '.dng', '.rw2'}
    
    DEFAULT_THUMBNAIL_SIZE = (800, 600)
    DEFAULT_WATERMARK_TEXT = "摄影工作室"
    DEFAULT_MAX_SELECTION = 50
    DEFAULT_EXPIRE_DAYS = 30
    DEFAULT_NAMING_PATTERN = "{client}_{date}_{index:04d}"
    
    THUMBNAIL_QUALITY = 85
    JPEG_QUALITY = 90

def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / relative_path
    return BASE_DIR / relative_path
