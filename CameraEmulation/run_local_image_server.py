import sys
from pathlib import Path

__project_root: Path = Path(__file__).parent.parent.parent
if str(__project_root) not in sys.path:
    sys.path.insert(0, str(__project_root))

import argparse
import logging
from pathlib import Path
from logging import Logger
from argparse import Namespace, ArgumentParser
from ptri_camerautils.CameraEmulation.TcpFrameProviders.ImageFileAsFrameSource import ImageFileServer, ImageFileServerShell


def _str2bool(v: str) -> bool:
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

def parse_commandline_args() -> Namespace:

        
    parser = ArgumentParser(prog = "Image File Server", formatter_class = argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--path", help = "path to the directory containing images", type = Path, required = True)
    parser.add_argument("--port", help = "local server port number", type = int, default = 6008)
    parser.add_argument("--recursive", help = "whether to recursivly load the image files in the child directory of specified path.", type = _str2bool, default = True)
    parser.add_argument("--log-level", help = "log level", type = int, default = logging.INFO)
    parser.add_argument("--clienttimeout", help = "read timeout for a client connection in seconds.", type = float, default = 4.0)
    parser.add_argument("--chunksize", help = "number of bytes to receive per chunk.", type = int, default = 6000)
    parser.add_argument("--framerate", help = "set the maximum frequency that the server can respond with an image to simulate a camera streaming.", type = float, default = 30.0)

    return parser.parse_args()

def main() -> None:
    arguments: Namespace = parse_commandline_args()
    logger: Logger = logging.getLogger("ImgFileServer")
    logger.setLevel(arguments.log_level)
    logger.handlers.clear()
    console_handler: logging.StreamHandler = logging.StreamHandler()
    console_handler.setLevel(arguments.log_level)
    logger.addHandler(console_handler)
    logger.info("Image path set to: %s", arguments.path)
    logger.debug("Provide images in child directory: %s", arguments.recursive)
    logger.info("Set listening port: %d", arguments.port)

    image_file_server: ImageFileServer = ImageFileServer(arguments.path, arguments.recursive, arguments.port, arguments.chunksize, arguments.clienttimeout, arguments.framerate, logger)
    image_file_server_shell: ImageFileServerShell = ImageFileServerShell(image_file_server, logger)
    image_file_server_shell.start_server_and_shell()

if __name__ == "__main__":
    main()