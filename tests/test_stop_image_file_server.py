import sys
import logging
import time
from pathlib import Path

__project_root: Path = Path(__file__).parent.parent.parent
if str(__project_root) not in sys.path:
    sys.path.insert(0, str(__project_root))

from CameraEmulation.TcpFrameProviders.ImageFileAsFrameSource import ImageFileServer

def main() -> None:

    image_file_server: ImageFileServer = ImageFileServer(
        image_path_root = Path(__file__).parent / "img",
        repeat = True,
        port = 6008,
        chunk_size = 6000,
        client_read_timeout = 4.0,
        frame_rate = 30.0,
        logger = logging.getLogger(__name__)
    )

    image_file_server.start_server()
    image_file_server.request_next_image()
    image_file_server.request_next_image()
    image_file_server.request_next_image()
    image_file_server.request_next_image()
    print("Server started. Waiting for 3 seconds...")
    time.sleep(3)
    print("Stopping server...")
    image_file_server.request_server_stop()
    image_file_server.wait_for_server_stop()

if __name__ == "__main__":
    main()