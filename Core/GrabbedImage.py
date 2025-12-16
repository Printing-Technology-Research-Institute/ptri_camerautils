import numpy as np
import datetime
from dataclasses import dataclass
from typing import Any
from .PixelFormatEnum import PixelFormatEnum
from ..CameraEnum import CameraEnum

@dataclass(slots = True)
class GrabbedImage:
    image: np.ndarray
    timestamp: datetime.datetime
    camera: CameraEnum
    pixel_format: PixelFormatEnum
    additional_info: dict[str, Any]

    @staticmethod
    def create(img: np.ndarray, timestamp: datetime.datetime, camera: CameraEnum, pixel_format: PixelFormatEnum, additional_info: dict[str, Any]) -> "GrabbedImage":

        assert isinstance(img, np.ndarray), "Image must be a numpy array"
        assert isinstance(timestamp, datetime.datetime), "Timestamp must be a datetime object"
        assert isinstance(camera, (int, CameraEnum)), "Camera must be an instance of CameraEnum"
        assert isinstance(pixel_format, (int, PixelFormatEnum)), "Pixel format must be an instance of PixelFormatEnum"
        assert isinstance(additional_info, dict), "Additional info must be a dictionary"

        assert img.ndim == 3, "Image must be a 3D numpy array, [height, width, channels] even if it is grayscale"
        return GrabbedImage(img, timestamp, camera, pixel_format, additional_info)