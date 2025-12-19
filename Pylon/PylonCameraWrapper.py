import logging
import datetime
import pypylon.pylon
import numpy as np
from pathlib import Path
from os import path, makedirs
from typing import Any, Tuple, Literal
from pypylon import pylon
from pypylon.pylon import ImageFormatConverter, GrabStrategy_LatestImageOnly, GrabResult, TimeoutHandling_ThrowException
from pypylon.pylon import InstantCamera, GrabResult
from pypylon.genicam import INodeMap, IEnumeration, IEnumEntry, INode, IFloat, IInteger, IBoolean, TimeoutException, RuntimeException
from ..CameraEnum import CameraEnum
from ..Core.GrabbedImage import GrabbedImage
from ..Core.FrameProviderAbc import FrameProviderAbc
from ..Core.SettingPersistentCameraAbc import SettingPersistentCameraAbc
from ..Core.PixelFormatEnum import PixelFormatEnum

class PylonCameraWrapper(FrameProviderAbc, SettingPersistentCameraAbc):
    """
    Wrapper for the pypylon camera. Supports the most common camera settings.
    Implements the FrameProviderAbc interface.
    """

    def __init__(self, camera: InstantCamera, output_pixel_format:PixelFormatEnum = PixelFormatEnum.BGR8, camera_pixel_format:PixelFormatEnum = PixelFormatEnum.BayerGR8, logger: logging.Logger | None = None):

        self.__camera: InstantCamera = InstantCamera(camera)
        self.__node_map: INodeMap | None = None
        self.__camera_name: str = ""
        self.__output_pixel_format = output_pixel_format
        self.__camera_pixel_format = camera_pixel_format

        self.__pylon_image_converter = ImageFormatConverter()
        self.__pylon_image_converter.SetOutputPixelFormat(PylonCameraWrapper.get_pylon_pixel_format(output_pixel_format))

        self.__logger:logging.Logger = logger if logger is not None else logging.getLogger(__name__)

    def start_camera_streaming(self) -> None | Exception:

        try:
            self.__camera.StartGrabbing(GrabStrategy_LatestImageOnly)
        except RuntimeException as e:
            self.__logger.error("Failed to start camera streaming: %s", e)
            return e

        self.__logger.info("Camera started streaming")
        return None

    def stop_camera_streaming(self) -> None | Exception:

        try:
            self.__camera.StopGrabbing()
        except RuntimeException as e:
            self.__logger.error("Failed to stop camera streaming: %s", e)
            return e

        self.__logger.info("Camera stopped streaming")
        return None

    def get_camera_info(self) -> dict:
        """Get camera information as a dictionary."""
        device_info: pypylon.pylon.DeviceInfo = self.__camera.GetDeviceInfo()
        return {
            "name": device_info.GetFriendlyName(),
            "model_name": device_info.GetModelName(),
            "vendor_name": device_info.GetVendorName(),
            "device_class": device_info.GetDeviceClass(),
            "serial_number": device_info.GetSerialNumber(),
            "device_version": device_info.GetDeviceVersion(),
        }

    def initialize_camera(self) -> None | Exception:

        try:
            self.__camera.Open()
        except RuntimeException as e:
            self.__logger.error("Failed to open camera: %s", e)
            return e

        self.__node_map = self.__camera.GetNodeMap()
        if not isinstance(self.__node_map, INodeMap):
            self.__logger.error("Failed to get camera node map")
            return RuntimeException("Failed to get node map")

        try:
            self.__camera_name = self.__camera.GetDeviceInfo().GetFriendlyName()
        except RuntimeException as e:
            self.__logger.error("Failed to get camera name: %s", e)
            return e

        try:
            self.__camera.PixelFormat.Value = PylonCameraWrapper.get_pylon_pixel_format_str(self.__camera_pixel_format)
        except ValueError as e:
            self.__logger.error("Failed to set camera pixel format: %s", e)
            return e

        return None

    def deinitialize_camera(self) -> None | Exception:
        try:
            self.__camera.Close()
        except RuntimeException as e:
            self.__logger.error("Failed to close camera: %s", e)
            return e

        try:
            self.__camera.DestroyDevice()
        except RuntimeException as e:
            self.__logger.error("Failed to destroy camera: %s", e)
            return e

        self.__logger.info("Camera deinitialized")
        return None


    def log_camera_info(self):
        """Log camera information to the logger."""
        camera_info = self.get_camera_info()
        for key, value in camera_info.items():
            self.__logger.info("%s: %s", key.replace('_', ' ').title(), value)

    def get_frame(self) -> GrabbedImage | Exception:

        grab_image_result: GrabResult | None = None
        image:np.ndarray = np.array([])
        GRAB_TIMEOUT_MS = 5000
        try:
            grab_image_result = self.__camera.RetrieveResult(GRAB_TIMEOUT_MS, TimeoutHandling_ThrowException)

            if not grab_image_result.IsValid():
                grab_image_result = RuntimeError("Grab result is garbage collected bebefore usage.")

            if not grab_image_result.GrabSucceeded():
                grab_image_result = RuntimeError("Failed to grab image.")

            converted_image:np.ndarray | None = self.__pylon_image_converter.Convert(grab_image_result).GetArray()
            image = converted_image if converted_image is not None else image
            if image.ndim == 2:
                image = np.expand_dims(image, axis = 2) # to ensure that array has channel dimension even if it is grayscale

        except TimeoutException:
            grab_image_result = TimeoutError("Timeout while grabbing image.")

        except RuntimeError as e:
            grab_image_result = e

        finally:
            if isinstance(grab_image_result, GrabResult):
                grab_image_result.Release()


        return GrabbedImage.create(
            img = image,
            timestamp = datetime.datetime.now(),
            camera = CameraEnum.Pylon,
            pixel_format = self.__output_pixel_format,
            additional_info = {
                "camera_name": self.__camera_name
            }
        )

    def save_camera_settings(self, file_path:str | Path) -> Exception | None:
        """
        Saves the camera settings to a file.
        Returns an exception if an error occurs and returns None if successful.

        Parameter:
            file_path: the path to the .pfs file to save the camera settings to.
        """
        assert isinstance(file_path, (str, Path)), "file_path must be an instance of string or Path"
        
        if isinstance(file_path, Path):
            file_path = str(file_path)

        if not file_path.endswith(".pfs"):
            self.__logger.warning("File path does not end with .pfs: %s", file_path)

        # Create the directory if it does not exist
        if not path.exists(path.dirname(file_path)):
            try:
                makedirs(path.dirname(file_path))
            except Exception as e:
                self.__logger.error("Error creating directory %s: %s", path.dirname(file_path), e)
                return e

        try:
            pylon.FeaturePersistence.Save(file_path, self.__node_map)
        except Exception as e:
            self.__logger.error("Error saving camera settings to %s: %s", file_path, e)
            return e

        self.__logger.info("Camera settings saved to %s", file_path)
        return None

    def load_camera_settings_from_file(self, file_path:str) -> Exception | None:
        """
        Loads the camera settings from a file.
        Returns an exception if an error occurs and returns None if successful.

        Parameter:
            file_path: the path to the .pfs file to load the camera settings from.
        """
        try:
            pylon.FeaturePersistence.Load(file_path, self.__node_map)
        except Exception as e:
            self.__logger.error("Error loading camera settings from %s: %s", file_path, e)
            return e
        
        self.__logger.info("Camera settings loaded from %s", file_path)
        return None

    def load_camera_settings_from_string(self, settings_string: str) -> Exception | None:
        try:
            pylon.FeaturePersistence.LoadFromString(settings_string, self.__node_map)
        except Exception as e:
            self.__logger.error("Error loading camera settings from string: %s", e)
            return e
        
        self.__logger.info("Camera settings loaded from string")
        return None

    @property
    def camera_pixel_format(self) -> PixelFormatEnum:
        return self.__camera_pixel_format

    @camera_pixel_format.setter
    def camera_pixel_format(self, new_value: PixelFormatEnum):
        assert isinstance(new_value, PixelFormatEnum), "New value must be an instance of PixelFormatEnum"

        self.__camera_pixel_format = new_value
        self.__camera.PixelFormat = PylonCameraWrapper.get_pylon_pixel_format(new_value)

    @property
    def camera_name(self) -> str:
        return self.__camera_name

    @property
    def fps(self) -> float | Exception:
        """
        Returns the current frames per second.
        Returns the value if successful, or an exception if an error occurs.
        """
        frame_rate = self.__read_node("AcquisitionFrameRate")
        assert isinstance(frame_rate, (float, Exception)), "Frame rate must be a float or an exception"
        return frame_rate

    @fps.setter
    def fps(self, new_value: float) -> None:
        """
        Sets the new frames per second. Not valid when acquisition_frame_rate_enable is false.
        Raises an exception if an error occurs.
        """
        result = self.__write_float_node("AcquisitionFrameRate", new_value)
        if result is not None:
            raise result

    @property
    def acquisition_frame_rate_enable(self) -> bool | Exception:
        """
        Returns the current acquisition frame rate enable. Not valid when camera is streaming.
        Returns the value if successful, or an exception if an error occurs.
        """
        enable = self.__read_node("AcquisitionFrameRateEnable")
        assert isinstance(enable, (bool, Exception)), "Acquisition frame rate enable must be a bool or an exception"
        return enable

    @acquisition_frame_rate_enable.setter
    def acquisition_frame_rate_enable(self, new_value: bool) -> None:
        """
        Sets the new acquisition frame rate enable. Not valid when camera is streaming.
        Raises an exception if an error occurs.
        """
        assert isinstance(new_value, bool), "New value must be a bool"

        result = self.__write_bool_node("AcquisitionFrameRateEnable", new_value)
        if result is not None:
            raise result

    @property
    def acquisition_frame_rate(self) -> float | Exception:
        """
        Returns the current acquisition frame rate.
        Returns the value if successful, or an exception if an error occurs.
        """
        frame_rate = self.__read_node("AcquisitionFrameRate")
        assert isinstance(frame_rate, (float, Exception)), "Acquisition frame rate must be a float or an exception"
        return frame_rate

    @acquisition_frame_rate.setter
    def acquisition_frame_rate(self, new_value: float) -> None:
        """
        Sets the new acquisition frame rate. Not valid when acquisition_frame_rate_enable is disabled
        Raises an exception if an error occurs.
        """
        result = self.__write_float_node("AcquisitionFrameRate", new_value)
        if result is not None:
            raise result

    @property
    def gain_auto(self) -> str | Exception:
        """
        Returns the current gain auto.
        Returns the value if successful, or an exception if an error occurs. Can be "Continuous", "Off" or "Once"
        """
        gain_auto = self.__read_node("GainAuto")
        assert isinstance(gain_auto, (str, Exception)), "Gain auto must be a string or an exception"
        return gain_auto

    @gain_auto.setter
    def gain_auto(self, new_value: Literal["Continuous", "Off", "Once"]) -> None:
        """
        Sets the new gain auto.
        Raises an exception if an error occurs.
        """
        assert new_value in ("Continuous", "Off", "Once"), "New value must be either Continuous, Off or Once"

        result = self.__write_enum_node("GainAuto", new_value)
        if result is not None:
            raise result

    @property
    def output_pixel_format(self) -> PixelFormatEnum | Exception:
        """
        Returns the current pixel format. Not valid when camera is streaming.
        Returns the value if successful, or an exception if an error occurs.
        """
        assert isinstance(self.__output_pixel_format, (PixelFormatEnum, Exception)), "Output pixel format must be an instance of PixelFormatEnum or an exception"
        return self.__output_pixel_format

    @output_pixel_format.setter
    def output_pixel_format(self, new_value: PixelFormatEnum) -> None:
        """
        Sets the new pixel format. Not valid when camera is streaming.
        Raises an exception if an error occurs.
        """
        self.__output_pixel_format = new_value
        result = self.__write_enum_node("PixelFormat", PylonCameraWrapper.get_pylon_pixel_format_str(new_value))
        if result is not None:
            raise result

    @property
    def image_width(self) -> int | Exception:
        """
        Returns the current image width obtained by get_frame() or an exception if an error occurs.
        """
        width = self.__read_node("Width")
        assert isinstance(width, (int, Exception)), "Image width must be an int or an exception"
        return width

    @image_width.setter
    def image_width(self, new_value: int) -> None:
        """
        Sets the new image width.
        Raises an exception if an error occurs.
        """
        assert isinstance(new_value, int), "New value must be an int"

        result = self.__write_int_node("Width", new_value)
        if result is not None:
            raise result

    @property
    def image_height(self) -> int | Exception:
        """
        Returns the current image height obtained by get_frame() or an exception if an error occurs.
        """
        height = self.__read_node("Height")
        assert isinstance(height, (int, Exception)), "Image height must be an int or an exception"
        return height

    @image_height.setter
    def image_height(self, new_value: int) -> None:
        """
        Sets the new image height.
        Raises an exception if an error occurs.
        """
        assert isinstance(new_value, int), "New value must be an int"

        result = self.__write_int_node("Height", new_value)
        if result is not None:
            raise result

    @property
    def gain(self) -> float | Exception:
        """
        Returns the current gain.
        Returns the value if successful, or an exception if an error occurs.
        """
        gain = self.__read_node("Gain")
        assert isinstance(gain, (float, Exception)), "Gain must be a float or an exception"
        return gain

    @gain.setter
    def gain(self, new_value: float) -> None:
        """
        Sets the new gain.
        Raises an exception if an error occurs.
        """
        result = self.__write_float_node("Gain", new_value)
        if result is not None:
            raise result

    @property
    def gamma(self) -> float | Exception:
        """
        Returns the current gamma.
        Returns the value if successful, or an exception if an error occurs.
        """
        gamma = self.__read_node("Gamma")
        assert isinstance(gamma, (float, Exception)), "Gamma must be a float or an exception"
        return gamma

    @gamma.setter
    def gamma(self, new_value: float) -> None:
        """
        Sets the new gamma.
        Raises an exception if an error occurs.
        """
        result = self.__write_float_node("Gamma", new_value)
        if result is not None:
            raise result

    @property
    def shutter_mode(self) -> str | Exception:
        """
        Returns the current shutter mode. Can be "Rolling" or "GlobalResetRelease"
        Returns the value if successful, or an exception if an error occurs.
        """
        shutter_mode = self.__read_node("SensorShutterMode")
        assert isinstance(shutter_mode, (str, Exception)), "Shutter mode must be a string or an exception"
        return shutter_mode

    @shutter_mode.setter
    def shutter_mode(self, new_value: str) -> None:
        """
        Sets the new shutter mode. Can be "Rolling" or "GlobalResetRelease"
        Raises an exception if an error occurs.
        """
        result = self.__write_enum_node("SensorShutterMode", new_value)
        if result is not None:
            raise result

    @property
    def balance_ratio(self) -> float | Exception:
        """
        Returns the current balance ratio. Not valid if BalanceWhiteAuto is enabled.
        Returns the value if successful, or an exception if an error occurs.
        """
        balance_ratio = self.__read_node("BalanceRatio")
        assert isinstance(balance_ratio, (float, Exception)), "Balance ratio must be a float or an exception"
        return balance_ratio

    @balance_ratio.setter
    def balance_ratio(self, new_value: float) -> None:
        """
        Sets the new balance ratio. Not valid if BalanceWhiteAuto is enabled.
        Raises an exception if an error occurs.
        """
        result = self.__write_float_node("BalanceRatio", new_value)
        if result is not None:
            raise result

    @property
    def exposure_time(self) -> float | Exception:
        """
        Returns the current exposure time in microseconds. Not valid if ExposureAuto is enabled.
        Returns the value if successful, or an exception if an error occurs.
        """
        exposure_time = self.__read_node("ExposureTime")
        assert isinstance(exposure_time, (float, Exception)), "Exposure time must be a float or an exception"
        return exposure_time

    @exposure_time.setter
    def exposure_time(self, new_value: float) -> None:
        """
        Sets the new exposure time in microseconds. Not valid if ExposureAuto is enabled.
        Raises an exception if an error occurs.
        """
        result = self.__write_float_node("ExposureTime", new_value)
        if result is not None:
            raise result

    @property
    def exposure_auto(self) -> str | Exception:
        """
        Returns which state of auto exposure is currently set. Can be "Continuous", "Off" or "Once"
        Returns the value if successful, or an exception if an error occurs.
        """
        exposure_auto = self.__read_node("ExposureAuto")
        assert isinstance(exposure_auto, (str, Exception)), "Exposure auto must be a string or an exception"
        return exposure_auto

    @exposure_auto.setter
    def exposure_auto(self, new_value: Literal["Continuous", "Off", "Once"]) -> None:
        """
        Sets the new state of auto exposure. Can be "Continuous", "Off" or "Once"
        Raises an exception if an error occurs.
        """
        result = self.__write_enum_node("ExposureAuto", new_value)
        if result is not None:
            raise result

    @property
    def balance_white_auto(self) -> str | Exception:
        """
        Returns which state of auto white balance is currently set. Can be "On", "Off" or "Once"
        Returns the value if successful, or an exception if an error occurs.
        """
        balance_white_auto = self.__read_node("BalanceWhiteAuto")
        assert isinstance(balance_white_auto, (str, Exception)), "Balance white auto must be a string or an exception"
        return balance_white_auto

    @balance_white_auto.setter
    def balance_white_auto(self, new_value: Literal["Continuous", "Off", "Once"]) -> None:
        """
        Sets the new state of auto white balance. Can be "Continuous", "Off" or "Once"
        Raises an exception if an error occurs.
        """
        result = self.__write_enum_node("BalanceWhiteAuto", new_value)
        if result is not None:
            raise result

    @property
    def balance_ratio_selector(self) -> str | Exception:
        """
        Returns the current white balance ratio option.
        Returns the value if successful, or an exception if an error occurs.
        """
        balance_ratio_selector = self.__read_node("BalanceRatioSelector")
        assert isinstance(balance_ratio_selector, (str, Exception)), "Balance ratio selector must be a string or an exception"
        return balance_ratio_selector

    @balance_ratio_selector.setter
    def balance_ratio_selector(self, new_value: Literal["Red", "Green", "Blue"]) -> None:
        """
        Sets the new white balance ratio option. Causes error if BalanceWhiteAuto is enabled.
        Raises an exception if an error occurs.

        Parameter:
            new_value: new balance ratio option. Must be either "Red", "Green" or "Blue"
        """
        assert isinstance(new_value, str), "New value must be a string"
        assert new_value in ("Red", "Green", "Blue"), "New value must be either Red, Green or Blue"

        result = self.__write_enum_node("BalanceRatioSelector", new_value)
        if result is not None:
            raise result

    def __get_node(self, node_name:str) -> INode | Exception:
        """
        Acquires the node from node map using the node name.
        Returns the node if successful, or an exception if an error occurs.
        """
        try:
            if self.__node_map is None:
                return RuntimeError("Cannot access camera setting because node map is not initialized")
            node:INode = self.__node_map.GetNode(node_name)
            return node
        except Exception as e:
            return e

    def __read_node(self, node_name:str) -> float | int | bool | str | Exception:
        """
        Returns the value of a float node.
        Returns the value if successful, or an exception if an error occurs.
        """
        try:
            node_result = self.__get_node(node_name)
            if isinstance(node_result, Exception):
                return node_result
            node: INode = node_result
            return node.Value

        except Exception as e:
            return e

    def __write_bool_node(self, node_name:str, new_value:bool) -> Exception | None:
        """
        Writes the value of the bool node.
        Returns None if successful, or an exception if an error occurs.
        """
        try:
            node_result = self.__get_node(node_name)
            if isinstance(node_result, Exception):
                return node_result
            node:IBoolean = node_result
            node.SetValue(new_value)
            return None
            
        except Exception as e:
            return e

    def __write_float_node(self, node_name:str, new_value:float) -> Exception | None:
        """
        Writes the value of the float node.
        Returns None if successful, or an exception if an error occurs.
        """
        try:
            node_result = self.__get_node(node_name)
            if isinstance(node_result, Exception):
                return node_result
            node:IFloat = node_result
            minimal_allowed_value:float = node.GetMin()
            maximal_allowed_value:float = node.GetMax()
            
            if not (minimal_allowed_value <= new_value <= maximal_allowed_value):
                return ValueError(f"Invalid value: {new_value}. Must be between {minimal_allowed_value} and {maximal_allowed_value}")
            
            node.SetValue(new_value)
            return None

        except Exception as e:
            return e

    def __write_int_node(self, node_name:str, new_value:int) -> Exception | None:
        """
        Writes the value of the int node.
        Returns None if successful, or an exception if an error occurs.
        """
        try:
            node_result = self.__get_node(node_name)
            if isinstance(node_result, Exception):
                return node_result
            node:IInteger = node_result
            node.SetValue(new_value)
            return None
            
        except Exception as e:
            return e

    def __write_enum_node(self, node_name:str, new_value:str) -> Exception | None:
        """
        Writes the value of the enum node.
        Returns None if successful, or an exception if an error occurs.
        """
        try:
            node_result = self.__get_node(node_name)
            if isinstance(node_result, Exception):
                return node_result
            node:IEnumeration = node_result
            valid_entries: Tuple[IEnumEntry] = node.GetEntries()
            
            if new_value not in (e.Symbolic for e in valid_entries):
                return ValueError(f"Invalid value: {new_value}. Can only be one of {[e.Symbolic for e in valid_entries]}")
            
            node.SetValue(new_value)
            return None
            
        except Exception as e:
            return e
    
    @staticmethod
    def get_pylon_pixel_format(pixel_format: PixelFormatEnum) -> Any:

        assert isinstance(pixel_format, PixelFormatEnum), "Pixel format must be an instance of PixelFormatEnum"

        match pixel_format:
            case PixelFormatEnum.BGR8:
                return pylon.PixelType_BGR8packed
            
            case PixelFormatEnum.RGB8:
                return pylon.PixelType_RGB8packed
            
            case PixelFormatEnum.MONO8:
                return pylon.PixelType_Mono8

            case PixelFormatEnum.BayerGR8:
                return pylon.PixelType_BayerGR8

            case PixelFormatEnum.BayerBG8:
                return pylon.PixelType_BayerBG8

            case PixelFormatEnum.BayerGB8:
                return pylon.PixelType_BayerGB8

            case PixelFormatEnum.BayerRG8:
                return pylon.PixelType_BayerRG8

    @staticmethod
    def get_pylon_pixel_format_str(pixel_format: PixelFormatEnum) -> str:
        """
        Summary:
            Returns the pylon pixel format string for the given pixel format.

        Returns:
            The pylon pixel format string for the given pixel format.

        Raises:
            ValueError: If the pixel format is not an entry in the PixelFormatEnum enum.
        """

        assert isinstance(pixel_format, PixelFormatEnum), "Pixel format must be an instance of PixelFormatEnum"

        match pixel_format:
            case PixelFormatEnum.BGR8:
                return "BGR8"
            
            case PixelFormatEnum.RGB8:
                return "RGB8"
            
            case PixelFormatEnum.MONO8:
                return "Mono8"
                
            case PixelFormatEnum.BayerGR8:
                return "BayerGR8"

            case PixelFormatEnum.BayerBG8:
                return "BayerBG8"

            case PixelFormatEnum.BayerRG8:
                return "BayerRG8"

            case PixelFormatEnum.BayerGB8:
                return "BayerGB8"

        raise ValueError(f"Invalid pixel format: {pixel_format}")

def create_first_instance_pylon_camera(camera_pixel_format: PixelFormatEnum = PixelFormatEnum.BGR8, output_pixel_format: PixelFormatEnum = PixelFormatEnum.BGR8, logger: logging.Logger | None = None) -> PylonCameraWrapper | None:
    """
    Creates the first instance of a pylon camera.
    Returns the camera if successful, or None if an error occurs.
    """

    assert ImageFormatConverter.IsSupportedInputFormat(PylonCameraWrapper.get_pylon_pixel_format(camera_pixel_format)), f"Camera pixel format {camera_pixel_format} is not supported by the image converter"
    assert ImageFormatConverter.IsSupportedOutputFormat(PylonCameraWrapper.get_pylon_pixel_format(output_pixel_format)), f"Output pixel format {output_pixel_format} is not supported by the image converter"

    camera: PylonCameraWrapper | None = None
    logger = logger if logger is not None else logging.getLogger(__name__)

    try:
        pylon_camera = pypylon.pylon.TlFactory.GetInstance().CreateFirstDevice()
        camera = PylonCameraWrapper(pylon_camera, output_pixel_format, camera_pixel_format, logger)
    except pypylon.pylon.RuntimeException as e:
        logger.error("Error initializing pylon camera: %s", e)

    return camera