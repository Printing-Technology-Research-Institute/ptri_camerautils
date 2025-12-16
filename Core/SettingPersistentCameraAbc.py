from abc import ABC, abstractmethod

class SettingPersistentCameraAbc(ABC):

    @abstractmethod
    def load_camera_settings_from_string(self, settings_string:str) -> Exception | None:
        """
        Loads the camera settings from a string describing the camera settings.
        """

    @abstractmethod
    def load_camera_settings_from_file(self, file_path:str) -> Exception | None:
        """
        Loads the camera settings from a file.
        """

    @abstractmethod
    def save_camera_settings(self, file_path:str) -> Exception | None:
        """
        Saves the camera settings to a file.
        """