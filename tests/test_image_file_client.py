import cv2
import argparse
import logging
import time
import numpy as np
from dep.ptri_camerautils.CameraEmulation.TcpFrameProviders.ImageFileAsFrameSource import ImageFileClient
from dep.ptri_camerautils.Core.GrabbedImage import GrabbedImage
from dep.ptri_camerautils.Core.PixelFormatEnum import PixelFormatEnum
from dep.ptri_loggingutils.ColoredConsoleFormatter import ColoredConsoleLoggerFactorySingleton


def convert_image_for_display(grabbed_image: GrabbedImage) -> np.ndarray:
    """
    Summary:
        Converts a GrabbedImage to BGR format for OpenCV display.

    Parameters:
        grabbed_image: The GrabbedImage to convert.

    Returns:
        A numpy array in BGR format suitable for cv2.imshow.
    """
    image: np.ndarray = grabbed_image.image

    # Handle grayscale images (MONO8)
    if grabbed_image.pixel_format == PixelFormatEnum.MONO8:
        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        return image

    # Handle RGB8 - convert to BGR for OpenCV
    if grabbed_image.pixel_format == PixelFormatEnum.RGB8:
        return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    # BGR8 is already in correct format for OpenCV
    if grabbed_image.pixel_format == PixelFormatEnum.BGR8:
        return image

    # For other formats, return as-is (may not display correctly)
    return image


def display_frames(client: ImageFileClient, frame_interval_ms: int = 33) -> None:
    """
    Summary:
        Periodically reads frames from the client and displays them in an OpenCV window.

    Parameters:
        client: The ImageFileClient instance to read frames from.
        frame_interval_ms: The interval between frame reads in milliseconds, default 33 (approximately 30 FPS).
    """
    window_name: str = "ImageFileClient Display"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    logger: logging.Logger = logging.getLogger(__name__)

    frame_count: int = 0
    error_count: int = 0

    try:
        logger.info("Starting frame display loop. Press 'q' to quit.")
        while True:
            # Get frame from client
            result: GrabbedImage | Exception = client.get_frame()

            if isinstance(result, Exception):
                error_count += 1
                logger.warning("Error getting frame: %s", str(result))
                time.sleep(frame_interval_ms / 1000.0)
                continue

            # Convert image for display
            display_image: np.ndarray = convert_image_for_display(result)
            frame_count += 1

            # Display image
            cv2.imshow(window_name, display_image)

            # Log frame info periodically
            if frame_count % 1 == 0:
                logger.info(
                    "Frames displayed: %d, Errors: %d, Image: %s",
                    frame_count,
                    error_count,
                    result.additional_info.get("image_file_name", "unknown")
                )

            # Wait for key press or frame interval
            key: int = cv2.waitKey(frame_interval_ms) & 0xFF
            if key == ord("q"):
                logger.info("Quit key pressed. Exiting.")
                break

    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    except Exception as e:
        logger.error("Unexpected error: %s", str(e))
        raise
    finally:
        cv2.destroyAllWindows()
        logger.info("Display window closed. Total frames: %d, Total errors: %d", frame_count, error_count)


def main() -> None:
    """
    Summary:
        Main entry point for the ImageFileClient test script.
    """
    # Setup logging
    logger: logging.Logger
    handler: logging.StreamHandler
    logger, handler = ColoredConsoleLoggerFactorySingleton.instance().create_logger(__name__)

    # Parse arguments
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description = "Test script for ImageFileClient that displays frames using OpenCV"
    )
    parser.add_argument(
        "--port",
        type = int,
        required = True,
        help = "Server port number to connect to"
    )
    parser.add_argument(
        "--chunk-size",
        type = int,
        default = 4096,
        help = "Chunk size for reading image data, default 4096"
    )
    parser.add_argument(
        "--read-timeout",
        type = int,
        default = 5,
        help = "Read timeout in seconds, default 5"
    )
    parser.add_argument(
        "--frame-interval",
        type = int,
        default = 10,
        help = "Frame interval in milliseconds (approximately 1 FPS), default 1"
    )

    args: argparse.Namespace = parser.parse_args()

    # Create client
    logger.info("Creating ImageFileClient with port=%d, chunk_size=%d, read_timeout=%d",
                args.port, args.chunk_size, args.read_timeout)
    client: ImageFileClient = ImageFileClient(
        port = args.port,
        chunk_size = args.chunk_size,
        read_timeout = args.read_timeout,
        logger = logger
    )

    try:
        # Initialize camera (does nothing but good practice)
        client.initialize_camera()

        # Start streaming (connect to server)
        logger.info("Connecting to server on port %d...", args.port)
        client.start_camera_streaming()

        # Display frames
        display_frames(client, args.frame_interval)

    except Exception as e:
        logger.error("Error during execution: %s", str(e))
        raise
    finally:
        # Stop streaming (disconnect from server)
        logger.info("Disconnecting from server...")
        client.stop_camera_streaming()

        # Deinitialize camera (does nothing but good practice)
        client.deinitialize_camera()
        logger.info("Test completed.")


if __name__ == "__main__":
    main()

