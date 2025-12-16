import socket
import json
import numpy as np
import cv2
import argparse
import sys
from pathlib import Path
from typing import Tuple

if __name__ == "__main__":
    __project_root: Path = Path(__file__).parent.parent.parent.parent
    if str(__project_root) not in sys.path:
        sys.path.append(str(__project_root))

from ptri_camerautils.CameraEmulation.TcpFrameProviders.ImageFileAsFrameSource import ImageFileHeader


def read_header(client_socket: socket.socket) -> ImageFileHeader:
    """
    Summary:
        Reads the JSON header from the server until a newline character is encountered.

    Parameters:
        client_socket: The socket connection to the server.

    Returns:
        An ImageFileHeader object parsed from the JSON string.
    """
    header_bytes: bytes = b""
    while True:
        chunk: bytes = client_socket.recv(1)
        if not chunk:
            raise ConnectionError("Connection closed while reading header")
        header_bytes += chunk
        if chunk == b"\n":
            break
    
    header_json: str = header_bytes.decode("utf-8").strip()
    header_dict: dict = json.loads(header_json)
    return ImageFileHeader(**header_dict)


def read_image_data(client_socket: socket.socket, header: ImageFileHeader) -> np.ndarray:
    """
    Summary:
        Reads the image data from the server based on the header information.

    Parameters:
        client_socket: The socket connection to the server.
        header: The ImageFileHeader containing image dimensions.

    Returns:
        A numpy array containing the image data with shape (height, width, channels).
    """
    total_bytes: int = header.width * header.height * header.channels
    image_bytes: bytes = b""
    
    while len(image_bytes) < total_bytes:
        chunk: bytes = client_socket.recv(min(4096, total_bytes - len(image_bytes)))
        if not chunk:
            raise ConnectionError("Connection closed while reading image data")
        image_bytes += chunk
    
    # * convert bytes to numpy array and reshape
    image_array: np.ndarray = np.frombuffer(image_bytes, dtype = np.uint8)
    image_array = image_array.reshape((header.height, header.width, header.channels))
    
    return image_array


def convert_to_bgr(image: np.ndarray, channel_format: str) -> np.ndarray:
    """
    Summary:
        Converts image from RGB to BGR format if needed for OpenCV display.

    Parameters:
        image: The image array to convert.
        channel_format: The channel format string ("RGB8" or "BGR8").

    Returns:
        The image array in BGR format.
    """
    if channel_format == "RGB8":
        return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    return image


def display_images(host: str, port: int) -> None:
    """
    Summary:
        Connects to the image server and continuously displays received images.

    Parameters:
        host: The server host address.
        port: The server port number.
    """
    window_name: str = "Image Server Display"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    
    try:
        while True:
            client_socket: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                client_socket.connect((host, port))
                
                # * read header
                header: ImageFileHeader = read_header(client_socket)
                
                # * read image data
                image: np.ndarray = read_image_data(client_socket, header)
                
                # * convert to BGR for OpenCV display
                image_bgr: np.ndarray = convert_to_bgr(image, header.channel_format)
                
                # * display image
                cv2.imshow(window_name, image_bgr)
                
                # * wait for key press (1ms) or exit on 'q'
                key: int = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                    
            except ConnectionError as e:
                print(f"Connection error: {e}")
                break
            except Exception as e:
                print(f"Error: {e}")
                break
            finally:
                client_socket.close()
                
    except KeyboardInterrupt:
        print("Interrupted by user")
    finally:
        cv2.destroyAllWindows()


def main() -> None:
    """
    Summary:
        Main entry point for the test script.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description = "Test client for ImageFileServer that displays images using OpenCV"
    )
    parser.add_argument(
        "--host",
        type = str,
        default = "localhost",
        help = "Server host address (default: localhost)"
    )
    parser.add_argument(
        "--port",
        type = int,
        required = True,
        help = "Server port number"
    )
    
    args = parser.parse_args()
    display_images(args.host, args.port)


if __name__ == "__main__":
    main()

