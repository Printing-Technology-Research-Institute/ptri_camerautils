import sys
from pathlib import Path

# add folder containing "camera_utils" to sys.path so it can be imported by
# > from camerautils.LocalServerCameraEmulation.TcpServer.ServerCameraEmulation import ImageFileServer
__project_root: Path = Path(__file__).parent.parent.parent.parent
if str(__project_root) not in sys.path:
    sys.path.insert(0, str(__project_root))