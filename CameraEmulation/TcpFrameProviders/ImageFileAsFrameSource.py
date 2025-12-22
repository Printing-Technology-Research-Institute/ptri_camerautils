import PIL.Image
import os
import pathlib
import socket
import cmd
import itertools
import PIL
import numpy as np
import threading
import time
import json
import datetime
from overrides import override
from pathlib import Path
from logging import Logger
from typing import Iterable, Iterator, Tuple, Literal, Dict, Any
from typing import NamedTuple
from ...Core.FrameProviderAbc import FrameProviderAbc
from ...Core.GrabbedImage import GrabbedImage
from ...Core.PixelFormatEnum import PixelFormatEnum
from ...CameraEnum import CameraEnum

class ImageFileHeader(NamedTuple):
    width: int
    height: int
    channels: int
    channel_format: Literal["BGR8", "RGB8", "MONO8"]
    image_file_name: str

class ImageServerInfo(NamedTuple):
    fps: float
    image_width: int
    image_height: int
    camera_pixel_format: PixelFormatEnum | int
    image_file_name: str
    camera_name: str
    server_port: int

class _ClientMessage(NamedTuple):
    message: Literal["get_frame", "get_server_info", "next_image"]

class ImageFileClient(FrameProviderAbc):

    def __init__(self, port:int, chunk_size:int, read_timeout:float, logger: Logger):
        """
        Summary:
            Initialize the ImageFileClient.

        Parameters:
            port: The port number to connect to the server.
            chunk_size: The chunk size for reading image data.
            read_timeout: The read timeout in seconds.
            logger: The logger instance for logging.
        """

        assert isinstance(port, int), "port must be an instance of int."
        assert isinstance(chunk_size, int), "chunk_size must be an instance of int."
        assert isinstance(read_timeout, float), "read_timeout must be an instance of float."
        assert isinstance(logger, Logger), "logger must be an instance of Logger."

        self.__port: int = port
        self.__chunk_size: int = chunk_size
        self.__read_timeout: float = read_timeout
        self.__logger: Logger = logger
        self.__socket: socket.socket | None = None
        self.__streaming: bool = False
        self.__image_width: int = 0
        self.__image_height: int = 0
        self.__camera_pixel_format: PixelFormatEnum = PixelFormatEnum.UNKNOWN
        self.__last_frame_time: float = 0.0
        self.__fps: float = 0
        self.__input_chunk_buffer: bytearray = bytearray(self.__chunk_size)
        self.__buffer_lock: threading.Lock = threading.Lock()

    @property
    def camera_name(self) -> str:
        return "ImageFileClient"

    @property
    def image_width(self) -> int:
        """
        Returns the width of the image obtained by get_frame() or an exception if an error occurs.
        """
        return self.__image_width

    @property
    def image_height(self) -> int:
        """
        Returns the height of the image obtained by get_frame() or an exception if an error occurs.
        """
        return self.__image_height

    @property
    def fps(self) -> float | Exception:
        """
        Returns the frames per second of the camera or an exception if an error occurs.
        """
        return self.__fps
    
    @property
    def camera_pixel_format(self) -> PixelFormatEnum | Exception:
        """
        Returns the pixel format of the image obtained by get_frame() or an exception if an error occurs.
        """
        return self.__camera_pixel_format

    @override
    def initialize_camera(self) -> None | Exception:
        """
        Summary:
            Initialize the camera. Connect to the server, read 1 frame from it and disconnect.
        """

        if self.__streaming:
            self.__logger.warning("Streaming already started.")
            return RuntimeError("Streaming already started.")

        if self.__socket is not None:
            self.__logger.warning("Socket already connected.")
            return RuntimeError("Socket already connected.")

        try:
            self.start_camera_streaming() # connect to server, request server information and disconnect
            if self.__socket is None:
                return ConnectionError("Socket not connected. Cannot request server information.")

            server_info: ImageServerInfo | Exception = self.__request_server_info(self.__socket)
            if isinstance(server_info, Exception):
                return server_info

            self.__fps = server_info.fps
            self.__image_width = server_info.image_width
            self.__image_height = server_info.image_height
            self.__camera_pixel_format = server_info.camera_pixel_format

        except Exception as e:
            self.__logger.error("Failed to start camera streaming: %s", e)
            return e

        finally: 
            self.stop_camera_streaming() # disconnect from server until start_camera_streaming is called

        return None 

    @override
    def deinitialize_camera(self) -> None | Exception:
        """
        Summary:
            Deinitialize the camera. Close the socket.
        """
        close_socket_error: None | Exception = self.__close_socket()

        self.__fps = 0
        self.__image_width = 0
        self.__image_height = 0
        self.__camera_pixel_format = PixelFormatEnum.UNKNOWN
        self.__last_frame_time = 0.0
        
        return close_socket_error

    @override
    def start_camera_streaming(self) -> None | Exception:
        """
        Summary:
            Start streaming frames from the camera by establishing a persistent connection to the server.
        """
        if self.__streaming:
            self.__logger.warning("Streaming already started.")
            return RuntimeError("Streaming already started.")

        if self.__socket is not None:
            self.__logger.warning("Socket already connected.")
            return RuntimeError("Socket already connected.")

        try:
            self.__socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.__socket.settimeout(self.__read_timeout)
            self.__socket.connect(("localhost", self.__port))
            self.__streaming = True
            self.__logger.info("Connected to server on port %d", self.__port)
        except Exception as e:
            self.__logger.error("Failed to connect to server on port %d: %s", self.__port, str(e))
            self.__close_socket()
            return e

        return None

    def request_next_image(self) -> None | Exception:
        """
        Summary:
            Ask the server to start sending another image.
        Note:
            This is different from get_frame() as the server sends the data of the same image when get_frame() is called.
        """

        if not self.__streaming:
            self.__logger.warning("Streaming not started. Please call start_camera_streaming first.")
            return RuntimeError("Streaming not started. Please call start_camera_streaming first.")
        
        if self.__socket is None:
            self.__logger.warning("Not connected to server. Connection may have been closed.")
            return ConnectionError("Not connected to server. Connection may have been closed.")
        
        try:
            request_message: _ClientMessage = _ClientMessage(message = "next_image")
            request_json: str = json.dumps(request_message._asdict())
            request_bytes: bytes = (request_json + "\n").encode("utf-8")
            self.__socket.sendall(request_bytes)
        except socket.timeout:
            return TimeoutError("Timeout while requesting next image.")
        except json.JSONDecodeError as e:
            return ValueError(f"Failed to parse request JSON: {str(e)}")
        except Exception as e:
            return RuntimeError(f"Error requesting next image: {str(e)}")
        
        return None

    @override
    def stop_camera_streaming(self) -> None | Exception:
        """
        Summary:
            Stop streaming frames from the camera.
        """
        if not self.__streaming:
            self.__logger.warning("Streaming not started.")
            return RuntimeError("Streaming not started.")

        self.__streaming = False
        close_socket_error: None | Exception = self.__close_socket()
        if isinstance(close_socket_error, Exception):
            return close_socket_error

        self.__logger.info("Camera streaming stopped.")
        return None

    @override
    def get_frame(self) -> GrabbedImage | Exception:
        """
        Summary:
            Returns the next frame from the camera. Sends a request message to the server and reads the frame response.
            The connection remains open between calls.

        Returns:
            GrabbedImage instance if successful, Exception otherwise.
        """

        assert self.__streaming, "Streaming not started. Please call start_camera_streaming first."
        if not self.__streaming:
            return RuntimeError("Streaming not started. Please call start_camera_streaming first.")

        if self.__socket is None:
            return ConnectionError("Not connected to server. Connection may have been closed.")

        try:
            # Send request message to server
            request_message: _ClientMessage = _ClientMessage(message = "get_frame")
            request_json: str = json.dumps(request_message._asdict())
            request_bytes: bytes = (request_json + "\n").encode("utf-8")
            self.__socket.sendall(request_bytes)

            # Read header line (JSON + newline) - read in chunks for efficiency
            header_bytes: bytes = b""
            BUFFER_SIZE: int = 1024
            image_data_prefix: bytes = b""
            MAX_HEADER_SIZE: int = 65536  # Maximum header size to prevent infinite loops
            
            while True:
                if len(header_bytes) > MAX_HEADER_SIZE:
                    return ValueError("Header size exceeds maximum allowed size.")
                
                with self.__buffer_lock:
                    self.__input_chunk_buffer[:] = itertools.repeat(0, len(self.__input_chunk_buffer))
                    read_size: int = min(BUFFER_SIZE, self.__chunk_size)
                    bytes_received: int = self.__socket.recv_into(self.__input_chunk_buffer, read_size)
                
                if bytes_received == 0:
                    return ConnectionError("Server closed connection.")
                
                chunk: bytes = bytes(self.__input_chunk_buffer[:bytes_received])
                
                # Header ends with a new line character
                # Check if newline is in the chunk
                newline_index: int = chunk.find(b"\n")
                if newline_index == -1:
                    header_bytes += chunk
                    continue

                # Found newline - header ends here
                header_bytes += chunk[:newline_index + 1]
                # Save any data after newline as part of image data
                image_data_prefix = chunk[newline_index + 1:]
                break

            # Parse header
            header_str: str = header_bytes.decode("utf-8").strip()
            header_dict: Dict[str, Any] = json.loads(header_str)
            image_header: ImageFileHeader = ImageFileHeader(**header_dict)

            self.__logger.debug("Image header: %s", image_header)

            # Read image data
            total_bytes: int = image_header.width * image_header.height * image_header.channels
            image_bytes: bytearray = bytearray(image_header.height * image_header.width * image_header.channels)
            image_bytes[:len(image_data_prefix)] = image_data_prefix

            # account for the image data prefix already read from the previous chunk
            bytes_read: int = len(image_data_prefix)

            while bytes_read < total_bytes:
                
                image_read_size: int = min(self.__chunk_size, total_bytes - bytes_read)
                with self.__buffer_lock:
                    self.__input_chunk_buffer[:] = itertools.repeat(0, len(self.__input_chunk_buffer))
                    image_bytes_received_count: int = self.__socket.recv_into(self.__input_chunk_buffer, image_read_size)
                
                    if image_bytes_received_count == 0:
                        return ConnectionError("Server closed connection while reading image data.")
                    
                    image_bytes[bytes_read:bytes_read + image_bytes_received_count] = self.__input_chunk_buffer[:image_bytes_received_count]
                    bytes_read += image_bytes_received_count

            # Convert bytes to numpy array
            image_array: np.ndarray = np.frombuffer(image_bytes, dtype = np.uint8)
            image_array = image_array.reshape((image_header.height, image_header.width, image_header.channels))

            # Convert channel format string to PixelFormatEnum
            pixel_format: PixelFormatEnum = PixelFormatEnum[image_header.channel_format]

            current_time: float = time.time()
            self.__fps = 1.0 / (current_time - self.__last_frame_time)
            self.__last_frame_time = current_time

            # Create GrabbedImage
            return GrabbedImage.create(
                img = image_array,
                timestamp = datetime.datetime.now(),
                camera = CameraEnum.Pylon,  # Using Pylon as placeholder, may need to add new enum value
                pixel_format = pixel_format,
                additional_info = {
                    "source": "ImageFileClient",
                    "port": self.__port,
                    "image_file_name": image_header.image_file_name
                }
            )

        except socket.timeout:
            return TimeoutError("Timeout while reading from server.")
        except json.JSONDecodeError as e:
            return ValueError(f"Failed to parse header JSON: {str(e)}")
        except Exception as e:
            return RuntimeError(f"Error reading frame: {str(e)}")

    def __close_socket(self) -> None | Exception:
        """
        Summary:
            Close the socket.
        """
        try:
            if self.__socket is not None:
                self.__socket.close()
                self.__socket = None
        except Exception as e:
            return RuntimeError(f"Error closing socket: {str(e)}")

    def __request_server_info(self, client_socket: socket.socket) -> ImageServerInfo | Exception:
        """
        Summary:
            Requests the server info from the server.

        Parameters:
            client_socket: The socket connection to the server.

        Returns:
            ImageServerInfo if successful, Exception otherwise.
        """
        request_message: _ClientMessage = _ClientMessage(message = "get_server_info")
        request_json: str = json.dumps(request_message._asdict())
        request_bytes: bytes = (request_json + "\n").encode("utf-8")

        try:
            client_socket.sendall(request_bytes)
        except ConnectionError as e:
            self.__logger.error("Error occured when requesting server information. %s", e.strerror)
            return ConnectionError(e, e.strerror)

        response_byte_array: bytearray = bytearray(int(self.__chunk_size * 1.5))
        bytes_read: int = 0
            
        with self.__buffer_lock:
            while True:
                self.__input_chunk_buffer[:] = itertools.repeat(0, len(self.__input_chunk_buffer))
                bytes_received_count: int = client_socket.recv_into(self.__input_chunk_buffer, self.__chunk_size)
                
                if bytes_received_count == 0:
                    self.__logger.error("Server closed connection while reading server information.")
                    return ConnectionError("Server closed connection while reading server information.")
                
                # Header ends with a new line character
                # Check if newline is in the chunk
                newline_index: int = self.__input_chunk_buffer.find(b"\n")
                if newline_index == -1:
                    response_byte_array[bytes_read:bytes_read + bytes_received_count] = self.__input_chunk_buffer[:bytes_received_count]
                    bytes_read += bytes_received_count
                    continue
                
                # Found newline - header ends here
                response_byte_array[bytes_read:bytes_read + bytes_received_count] = self.__input_chunk_buffer[:bytes_received_count]
                bytes_read += bytes_received_count
                break
        
        response_dict: Dict[str, Any]
        try:
            # -1 to remove the newline character
            response_dict = json.loads(response_byte_array[: bytes_read - 1].decode("utf-8"))
            response_dict["camera_pixel_format"] = PixelFormatEnum(response_dict["camera_pixel_format"])
            server_info: ImageServerInfo = ImageServerInfo(**response_dict)
        except json.JSONDecodeError as e:
            self.__logger.error("Failed to parse server information JSON: %s", str(e))
            return e
        except KeyError as e:
            self.__logger.error("Key error in server information: %s", str(e))
            return e

        self.__logger.debug("Server info: %s", server_info)
        return server_info

class ImageFileServer:

    def __init__(self, image_path_root:pathlib.Path, repeat:bool, port:int, chunk_size:int, client_read_timeout:float, frame_rate:float | int, logger: Logger):
        """
        Summary:
            Initialize the ImageFileServer.

        Parameters:
            image_path_root: The root path of the image files.
            repeat: Whether to repeat the image files.
            port: The port number to listen on.
            chunk_size: The chunk size for reading image data.
            client_read_timeout: The read timeout in seconds.
            frame_rate: The frame rate to send frames at.
            logger: The logger instance for logging.
        """

        assert isinstance(image_path_root, pathlib.Path), "image_path_root must be an instance of pathlib.Path."
        assert isinstance(repeat, bool), "repeat must be an instance of bool."
        assert isinstance(port, int), "port must be an instance of int."
        assert isinstance(chunk_size, int), "chunk_size must be an instance of int."
        assert isinstance(client_read_timeout, float), "client_read_timeout must be an instance of float."
        assert isinstance(frame_rate, (float, int)), "frame_rate must be an instance of int or float."
        assert frame_rate > 0, "frame_rate must be greater than 0."
        assert isinstance(logger, Logger), "logger must be an instance of Logger."

        self.__frame_rate:float = float(frame_rate)
        self.__image_path_root:pathlib.Path = image_path_root
        self.__repeat:bool = repeat
        self.__image_file_name_gen:Iterator[pathlib.Path] | None = None
        self.__port:int = port
        self.__current_image_path:Path | None = None
        self.__image_shape:Tuple[int, int, int] = (0, 0, 0)
        self.__chunk_size:int = chunk_size
        self.__output_buffer:bytes | None = None
        self.__client_read_timeout:float = client_read_timeout
        self.__logger: Logger = logger

        self.__server_stop_requested:bool = False
        self.__server_socket: socket.socket | None = None
        self.__handle_client_thread: threading.Thread | None = None

    @property
    def current_image_path(self) -> pathlib.Path | None:
        """
        Summary:
            Returns the current image path.
        """
        return self.__current_image_path

    @property
    def image_path_root(self) -> pathlib.Path:
        """
        Summary:
            Returns the image path root.
        """
        return self.__image_path_root

    @property
    def repeat(self) -> bool:
        """
        Summary:
            Returns the repeat flag.
        """
        return self.__repeat

    @property
    def port(self) -> int:
        """
        Summary:
            Returns the port number.
        """
        return self.__port

    def start_server(self) -> bool:
        """
        Summary:
            Starts the server and listen on specified port.

        Description:
            This method starts the server thread. If any error is encountered when initializing the server, 
            this method returns False and the server is not started.

        Returns:
            True when the server runs and stops without issue. False upon encountering any error.
        """

        self.__logger.debug("Starting server...")

        if not self.__init_file_name_generator():
            self.__logger.error("Unable to find any image in %s or its subdirectories.?", self.__image_path_root)
            self.__set_server_stop_request_flag()
            return False

        if not self.__read_image_from_generator():
            self.__logger.error("Failed to read image at path %s", self.__current_image_path)
            self.__set_server_stop_request_flag()
            return False
        
        self.__handle_client_thread = threading.Thread(target = self.__server_loop)
        self.__handle_client_thread.start()
        return True

    def wait_for_server_stop(self) -> None:
        """
        Summary:
            Blocks until the server thread finishes.
        """
        if self.__handle_client_thread is not None:
            self.__handle_client_thread.join()

    def is_server_stop_requested(self) -> bool:
        """
        Summary:
            Returns whether the server stop has been requested.
        """
        return self.__server_stop_requested

    def request_next_image(self) -> bool:
        """
        Summary:
            Move on to the next image.
        
        Returns:
            True if successful, False otherwise.
        """
        result = self.__read_image_from_generator()
        if result:
            self.__logger.info("Serving image %s", self.__current_image_path)
        return result

    def request_server_stop(self) -> None:
        """
        Summary:
            Request the server to stop.
        """
        self.__set_server_stop_request_flag()

    def __server_loop(self) -> None:

        self.__server_socket = socket.socket(socket.AddressFamily.AF_INET, socket.SocketKind.SOCK_STREAM)

        # * any server socket operation must be done within 3 second otherwise a timeout exception will be raised
        self.__server_socket.settimeout(3)

        try:
            self.__server_socket.bind(("localhost", self.__port))
            self.__server_socket.listen(1) # Only allow 1 connection at a time
            self.__logger.info("Server listening on port %d", self.__port)

        except OSError:
            # * error handling if socket fails to bind to specified port
            self.__logger.error("Cannot open port %d on %s", self.__port, "localhost")
            self.__set_server_stop_request_flag()
            if isinstance(self.__server_socket, socket.socket):
                self.__server_socket.close()
            return
        
        # * break infinite loop if stop is requested
        # * since self.__server_socket.timeout = 3 second, stop request is checked every 3 seconds
        self.__logger.info("Server loop started.")
        while not self.__server_stop_requested:

            # * if no connection is established within 3 second, a timeout exception is thrown and the infinite loop is re-run
            try:
                client_socket: socket.socket
                client_address: str
                client_port: int
                (client_socket, (client_address, client_port)) = self.__server_socket.accept()
            except TimeoutError:
                self.__logger.debug("No connection established after 3 second.")
                continue

            try:
                client_socket.settimeout(self.__client_read_timeout)
                self.__logger.info("Client connected from %s:%d", client_address, client_port)
                self.__handle_client_connection(client_socket)

            except TimeoutError:
                self.__logger.warning("Client timeout")

            except BrokenPipeError:
                self.__logger.warning("Client disconnected.")

            except ConnectionResetError:
                self.__logger.warning("Client is gone!")

            except Exception as e:
                self.__logger.error("Error handling client: %s", str(e))

            finally:
                if client_socket is not None:
                    try:
                        client_socket.close()
                    except Exception:
                        pass
                    self.__logger.debug("Client connection closed.")
        
        self.__logger.debug("Server loop terminated.")
        return None

    def __handle_client_connection(self, client_socket: socket.socket) -> None:
        """
        Summary:
            Handles a persistent client connection, reading requests and sending frames.

        Parameters:
            client_socket: The socket connection to the client.
        """
        frame_interval: float = 1.0 / self.__frame_rate
        # Initialize to allow first frame to be sent immediately
        last_frame_time: float = time.time() - frame_interval

        while not self.__server_stop_requested:
            try:
                # Read client request
                request: _ClientMessage | None = self.__read_client_request(client_socket)
                self.__logger.debug("Client request: %s", request)

                # Client closed connection
                if request is None:
                    break

                if request.message == "get_frame":
                    # Calculate time to wait based on frame rate
                    current_time: float = time.time()
                    time_since_last_frame: float = current_time - last_frame_time
                    
                    if time_since_last_frame < frame_interval:
                        # Wait until enough time has passed
                        wait_time: float = frame_interval - time_since_last_frame
                        time.sleep(wait_time)

                    # Send frame to client
                    self.__logger.debug("Sending frame data to client.")
                    self.__write_image_and_header_to_client(client_socket)

                elif request.message == "get_server_info":
                    # Send server info to client
                    self.__logger.debug("Sending server info to client.")
                    self.__write_server_info_to_client(client_socket)
                    last_frame_time = time.time()

                elif request.message == "next_image":
                    # Request next image from server
                    self.__logger.debug("Requesting next image from server.")
                    if not self.__read_image_from_generator():
                        self.__logger.info("Failed to read image at path %s", self.__current_image_path)
                        continue
                    self.__logger.info("Serving image %s", self.__current_image_path)
                    last_frame_time = time.time()

                else:
                    self.__logger.warning("Invalid client request: %s", request.message)
                    continue

            except socket.timeout:
                self.__logger.warning("Timeout while waiting for client request.")
                continue
            except BrokenPipeError:
                self.__logger.info("Client disconnected.")
                break
            except ConnectionResetError:
                self.__logger.info("Client connection reset.")
                break
            except Exception as e:
                self.__logger.error("Error handling client request: %s", str(e))
                break

    def __read_client_request(self, client_socket: socket.socket) -> _ClientMessage | None:
        """
        Summary:
            Reads a client request message from the socket.

        Parameters:
            client_socket: The socket connection to the client.

        Returns:
            _ClientMessage if successful, None if connection closed.
        """
        request_bytes: bytes = b""
        buffer_size: int = 1024

        while True:
            chunk: bytes = client_socket.recv(buffer_size)
            if not chunk:
                return None

            # Check if newline is in the chunk
            newline_index: int = chunk.find(b"\n")
            if newline_index != -1:
                # Found newline - request ends here
                request_bytes += chunk[:newline_index + 1]
                break
            else:
                # No newline yet, add to request
                request_bytes += chunk

        # Parse request
        request_str: str = request_bytes.decode("utf-8").strip()
        request_dict: Dict[str, Any] = json.loads(request_str)
        return _ClientMessage(**request_dict)

    def __init_file_name_generator(self) -> bool:

        if not os.path.isdir(self.__image_path_root):
            self.__logger.error("File path %s does not exist.", self.__image_path_root)
            return False
        
        self.__image_file_name_gen = ImageFileServer.__get_image_file_name_generator(self.__image_path_root)
        self.__logger.debug("File path %s initialized successfully.", self.__image_path_root)
        return True

    def __set_server_stop_request_flag(self):
        """
        Summary:
            Set the stop requested flag and terminate server loop.
        """
        self.__logger.info("Server stop requested.")
        self.__server_stop_requested = True
        
    def __write_server_info_to_client(self, client_socket:socket.socket) -> None:
        """
        Summary:
            Sends the FPS to the client.
        """

        server_info: ImageServerInfo = ImageServerInfo(
            fps = self.__frame_rate,
            image_width = self.__image_shape[1],
            image_height = self.__image_shape[0],
            camera_pixel_format = PixelFormatEnum.RGB8.value,
            image_file_name = self.__current_image_path.stem if self.__current_image_path is not None else "No Image Loaded",
            camera_name = "ImageFileServer",
            server_port = self.__port
        )
        server_info_json: str = json.dumps(server_info._asdict())
        server_info_bytes: bytes = (server_info_json + "\n").encode("utf-8")
        client_socket.sendall(server_info_bytes)

    def __write_image_and_header_to_client(self, client_socket:socket.socket) -> None:
        """
        Summary:
            Sends image header as JSON string followed by image data to the client.
            This method should be called after waiting for the appropriate frame interval.

        Parameters:
            client_socket: The socket connection to the client.
        """

        assert self.__output_buffer is not None, "Please call read_image_from_generator in advance."
        assert self.__current_image_path is not None, "Please call read_image_from_generator in advance."

        # * extract image dimensions from shape (height, width, channels)
        height: int = self.__image_shape[0]
        width: int = self.__image_shape[1]
        channels: int = self.__image_shape[2] if len(self.__image_shape) == 3 else 1
        
        # * create image header and convert to JSON
        # * PIL images are RGB by default, so use RGB8 format
        image_header: ImageFileHeader = ImageFileHeader(
            width = width,
            height = height,
            channels = channels,
            channel_format = "RGB8",
            image_file_name = self.__current_image_path.name
        )
        header_json: str = json.dumps(image_header._asdict())
        header_bytes: bytes = (header_json + "\n").encode("utf-8")
        self.__logger.debug("Sending header: %s", header_bytes)
        
        # * send the JSON header first, followed by a newline delimiter
        client_socket.sendall(header_bytes)

        # * send the image data chunk by chunk. The last chunk may be smaller
        chunk_start:int = 0
        chunk_end:int = chunk_start + self.__chunk_size
        while chunk_start < len(self.__output_buffer):
            chunk_end = np.min((chunk_start + self.__chunk_size, len(self.__output_buffer)))
            client_socket.sendall(self.__output_buffer[chunk_start: chunk_end])
            chunk_start += self.__chunk_size

    def __read_image_from_generator(self) -> bool:
        """
        Summary:
            Iterates over self.__image_file_name_gen, requesting a new image file path to load the image from and loads it into self.__output_buffer. Terminates server loop if
            self.__repeat=False and all images are loaded.

        Returns:
            True when image is successfully loaded and False if all images are loaded and self.__repeat=False.
        """

        assert self.__image_file_name_gen is not None, "Please call init_file_name_generator in advance."

        try:
            self.__current_image_path = next(self.__image_file_name_gen)
        except StopIteration:
            self.__logger.info("All image served.")

            # * quit application if all images served and not recursive
            if not self.__repeat:
                self.__set_server_stop_request_flag()
                # FIXME: application doesn't break when all image served
                return False

            self.__logger.info("Repeating all available images.")
            self.__init_file_name_generator()
            self.__current_image_path = next(self.__image_file_name_gen)

        image:np.ndarray = np.array(PIL.Image.open(str(self.__current_image_path)))
        self.__output_buffer = image.tobytes()
        self.__image_shape = image.shape
        return True

    @staticmethod
    def __get_image_file_name_generator(image_path_root:str | pathlib.Path, skip_pattern:Iterable[str] | None = None) -> Iterator[pathlib.Path]:
        """
        Summary:
            Returns a generator that yeilds image paths. Only paths to files with extension ".jpg" or ".png" will be yeilded.

        Parameters:
            image_path_root: path to a directory containing image files.
            skip_pattern: a set of strings. If the path to an image file contains any of the string in skip_pattern, it will not be yeilded.

        Returns:
            A generator that yeilds Path objects of image files.
        """

        # * skip this entry if its path contains exclude_pattern
        skip_pattern = {} if skip_pattern is None else set(skip_pattern)
        for root, _, files in os.walk(image_path_root):

            for file in files:

                file_path: Path = Path(os.path.join(root, file))

                if any(pattern in str(file_path.absolute()) for pattern in skip_pattern):
                    continue
                if not os.path.isfile(file_path):
                    continue

                entry_extension: str = file_path.suffix
                if not entry_extension == ".jpg" and not entry_extension == ".png":
                    continue
                
                yield file_path

class ImageFileServerShell(cmd.Cmd):

    def __init__(self, image_file_server: ImageFileServer, logger: Logger):
        """
        Summary:
            Initialize the ImageFileServerShell.

        Parameters:
            image_file_server: The ImageFileServer instance to control.
            logger: The logger instance for logging.
        """
        assert isinstance(image_file_server, ImageFileServer), "image_file_server must be an instance of ImageFileServer."
        assert isinstance(logger, Logger), "logger must be an instance of Logger."

        self.intro = "Welcome to the image file server console. Type ? to list available commands."
        self.prompt = "(ImageServer)\t"
        super(ImageFileServerShell, self).__init__()

        self.__image_file_server: ImageFileServer = image_file_server
        self.__logger: Logger = logger

    def emptyline(self):
        """Handle empty line input - move to next image."""
        self.do_next(None)

    def do_next(self, _):
        """Move on to the next image."""
        self.__image_file_server.request_next_image()

    def do_exit(self, _):
        """Stop server and quit application."""
        self.__image_file_server.request_server_stop()
        return True

    def do_EOF(self, _):
        """Stop server and quit application."""
        self.__image_file_server.request_server_stop()
        return True

    def do_quit(self, _):
        """Stop server and quit application."""
        self.__image_file_server.request_server_stop()
        return True
    
    def do_show(self, _) -> None:
        """Open the current image in an image view app on the device."""
        current_image_path = self.__image_file_server.current_image_path
        if current_image_path is None:
            self.__logger.warning("No image currently loaded.")
            return
        current_image: PIL.Image.ImageFile.ImageFile = PIL.Image.open(str(current_image_path))
        current_image.show()

    def do_status(self, _):
        """Print the port server is listening on and the file currently serving."""
        self.__logger.critical(
            """
            Port: %d
            CurrentImage: %s
            ImagePathRoot: %s
            Repeat: %r""", 
            self.__image_file_server.port, 
            self.__image_file_server.current_image_path, 
            self.__image_file_server.image_path_root, 
            self.__image_file_server.repeat)

    def start_server_and_shell(self) -> bool:
        """
        Summary:
            Starts the server and command shell interface.

        Description:
            This method starts 2 asynchronous threads, one for the command shell interface and the other for server. 
            Execution on main thread is blocked until the server thread returns, which is when the user inputs "exit" 
            or "quit" in the command shell. If any error is encountered when initializing the server, this method 
            returns False and the server is not started.

        Returns:
            True when the server runs and stops without issue. False upon encountering any error.
        """
        if not self.__image_file_server.start_server():
            return False

        # * block the main thread until self.cmdloop ends.
        # * self.cmdloop ends when any method returns True when server loop is active.
        try:
            self.cmdloop()
        except KeyboardInterrupt:
            self.__image_file_server.request_server_stop()

        # * block the main thread until server thread finishes
        # * server thread finishes when server stop is requested and server stops properly.
        self.__image_file_server.wait_for_server_stop()
        return True