from abc import ABC, abstractmethod
from .GrabbedImage import GrabbedImage
from .PixelFormatEnum import PixelFormatEnum

class FrameProviderAbc(ABC):

    @property
    @abstractmethod
    def camera_name(self) -> str:
        """
        Returns the name of the camera.
        """

    @property
    @abstractmethod
    def image_width(self) -> int | Exception:
        """
        Returns the width of the image obtained by get_frame() or an exception if an error occurs.
        """

    @property
    @abstractmethod
    def image_height(self) -> int | Exception:
        """
        Returns the height of the image obtained by get_frame() or an exception if an error occurs.
        """

    @property
    @abstractmethod
    def camera_pixel_format(self) -> PixelFormatEnum | Exception:
        """
        Returns the pixel format of the image obtained by get_frame() or an exception if an error occurs.
        """

    @property
    @abstractmethod
    def fps(self) -> float | Exception:
        """
        Returns the frames per second of the camera or an exception if an error occurs.
        """

    @abstractmethod
    def get_frame(self) -> GrabbedImage | Exception:
        """
        Returns the next frame from the camera. If successfull, returns an instance of GrabbedImage. 
        Otherwise, returns an exception.
        """

    @abstractmethod
    def deinitialize_camera(self) -> None:
        """
        Deinitialize the camera. This will close the camera and release the resources.
        """

    @abstractmethod
    def initialize_camera(self) -> None:
        """
        Initialize the camera. This will open the camera and initialize the resources.
        """

    @abstractmethod
    def start_camera_streaming(self) -> None:
        """
        Start streaming frames from the camera. The camera will become ready to provide frames.
        But much of the configuration options will be disabled.
        """

    @abstractmethod
    def stop_camera_streaming(self) -> None:
        """
        Stop streaming frames from the camera. This might enable some of the configuration options that were not available
        when the camera was streaming.
        """