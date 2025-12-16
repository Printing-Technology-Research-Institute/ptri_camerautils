"""
Test script for ImageFileClient.

Summary:
    This script instantiates an ImageFileClient, connects to an image server,
    reads frames continuously, and displays them in an OpenCV window.
    Logs "image read" to console with INFO level for each frame read.

Usage:
    python test_image_file_client.py --port 6008
    python test_image_file_client.py --port 6008 --chunk_size 4096 --timeout 5.0
"""

import argparse
import cv2
import logging
import sys
from pathlib import Path

# Add project root to sys.path for imports
__project_root: Path = Path(__file__).parent.parent.parent.parent
if str(__project_root) not in sys.path:
    sys.path.insert(0, str(__project_root))

from ptri_camerautils.CameraEmulation.TcpFrameProviders.ImageFileAsFrameSource import ImageFileClient
from ptri_camerautils.Core.GrabbedImage import GrabbedImage
from ptri_camerautils.Core.PixelFormatEnum import PixelFormatEnum
from ptri_loggingutils.ColoredConsoleFormatter import ColoredLoggingFormatter


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Setup a logger with colored console output.

    Parameters:
        name: The name of the logger.
        level: The logging level. Default is INFO.

    Return value:
        A configured Logger instance.
    """
    logger: logging.Logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()

    console_handler: logging.StreamHandler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(ColoredLoggingFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(console_handler)

    return logger


def display_images_from_client(port: int, chunk_size: int, timeout: float) -> None:
    """
    Connect to image server using ImageFileClient and display frames in OpenCV window.

    Summary:
        Creates an ImageFileClient instance, initializes it, starts streaming,
        and continuously reads frames to display. Logs "image read" for each
        successfully read frame.

    Parameters:
        port: The port number to connect to the server.
        chunk_size: The chunk size for reading image data.
        timeout: The read timeout in seconds.
    """
    logger: logging.Logger = setup_logger("ImageFileClient", logging.INFO)

    # Create ImageFileClient instance
    client: ImageFileClient = ImageFileClient(
        port = port,
        chunk_size = chunk_size,
        read_timeout = timeout,
        logger = logger
    )

    window_name: str = "ImageFileClient Test"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    try:
        # Initialize and start streaming
        logger.info("Initializing camera client on port %d", port)
        client.initialize_camera()

        logger.info("Starting camera streaming")
        client.start_camera_streaming()

        logger.info("Camera initialized. Image size: %dx%d, Format: %s",
                    client.image_width, client.image_height, client.camera_pixel_format)

        # Continuously read and display frames
        while True:
            frame_result: GrabbedImage | Exception = client.get_frame()

            if isinstance(frame_result, Exception):
                logger.error("Error reading frame: %s", frame_result)
                break

            # Log successful frame read
            logger.info("image read")

            # Convert to BGR for OpenCV display if needed
            image = frame_result.image
            if frame_result.pixel_format == PixelFormatEnum.RGB8:
                image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

            # Display the image
            cv2.imshow(window_name, image)

            # Wait for key press (1ms) or exit on 'q' or ESC
            key: int = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == 27:  # 'q' or ESC
                logger.info("User requested exit")
                break

    except KeyboardInterrupt:
        logger.info("Interrupted by user")

    except Exception as e:
        logger.error("Unexpected error: %s", e)

    finally:
        # Cleanup
        logger.info("Stopping camera streaming")
        client.stop_camera_streaming()
        client.deinitialize_camera()
        cv2.destroyAllWindows()
        logger.info("Cleanup completed")


def main() -> None:
    """
    Main entry point for the test script.

    Summary:
        Parses command line arguments and starts the image display loop.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description = "Test client for ImageFileServer using ImageFileClient class"
    )
    parser.add_argument(
        "--port",
        type = int,
        default = 6008,
        help = "Server port number (default: 6008)"
    )
    parser.add_argument(
        "--chunk_size",
        type = int,
        default = 1024,
        help = "Chunk size for reading image data (default: 1024)"
    )
    parser.add_argument(
        "--timeout",
        type = float,
        default = 5.0,
        help = "Read timeout in seconds (default: 5.0)"
    )

    args = parser.parse_args()
    display_images_from_client(args.port, args.chunk_size, args.timeout)


if __name__ == "__main__":
    main()
