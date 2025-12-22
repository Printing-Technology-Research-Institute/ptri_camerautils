# ptri_camerautils

`ptri_camerautils` 是一個用於相機操作的 Python 工具庫，提供統一的介面來處理不同類型的相機，包括實體 Pylon 相機和透過 TCP 連線模擬的相機。

## 功能特色

- **統一的相機介面**：透過 `FrameProviderAbc` 抽象基類提供一致的相機操作介面
- **Pylon 相機支援**：完整的 Basler Pylon 相機封裝，支援多種相機設定
- **相機模擬**：透過 TCP 伺服器模擬相機，可用於開發和測試
- **多種像素格式**：支援 BGR8、RGB8、MONO8 以及多種 Bayer 格式

## 安裝方式
此套件尚未發布於pypl，請在您的程式庫中，以submodule方式下載原始碼並用pip安裝。下列指令將會下載原始碼至```ptri_camerautils```資較夾中，可以視需求決定是否需要額外安裝basler相機的後端pypylon。
```powershell
git submodule add https://github.com/Printing-Technology-Research-Institute/ptri_camerautils.git ptri_camerautils

# 不支援basler相機
pip install ./ptri_camerautils

# 加入basler相機支援
pip install ./ptri_camerautils[pypylon]
```

> [!WARNING]
> 目前已知pip<=24在安裝此套件時會出問題，請先用python -m pip install --upgrade pip先升級至25版以上，載安裝此套件。

## 模組結構

### Core 模組

核心抽象類別和資料結構：

- **`FrameProviderAbc`**：相機幀提供者的抽象基類，定義了所有相機實作必須遵循的介面
- **`GrabbedImage`**：封裝擷取的影像資料，包含影像陣列、時間戳記、相機類型、像素格式和額外資訊
- **`PixelFormatEnum`**：像素格式列舉，支援 BGR8、RGB8、MONO8 以及多種 Bayer 格式
- **`SettingPersistentCameraAbc`**：相機設定持久化的抽象基類。可以繼承此類別，並針對特定相機廠牌的API，實作相關的函數。

### Pylon 模組

Basler Pylon 相機的封裝實作：

- **`PylonCameraWrapper`**：Pylon 相機的封裝類別，實作 `FrameProviderAbc` 和 `SettingPersistentCameraAbc` 介面
- **`create_first_instance_pylon_camera`**：工廠函數，建立第一個可用的 Pylon 相機實例

> [!WARNING]
> 目前此套件仍正在開發中，尚未完全通過測試。

#### 支援的相機設定

`PylonCameraWrapper` 提供以下相機設定的讀寫功能：

- 影像尺寸（寬度、高度）
- 像素格式（相機和輸出格式）
- 幀率（FPS）
- 曝光時間和自動曝光
- 增益和自動增益
- 白平衡和自動白平衡
- Gamma 值
- 快門模式

### CameraEmulation 模組

透過 TCP 連線模擬相機的功能：

- **`ImageFileClient`**：客戶端類別，連接到影像伺服器並接收影像幀
- **`ImageFileServer`**：伺服器類別，從檔案系統讀取影像並透過 TCP 傳送給客戶端
- **`run_local_image_server`**：命令列腳本，用於啟動本地影像伺服器

## 使用範例

### 使用 Pylon 相機

```python
import logging
from ptri_camerautils.Pylon import create_first_instance_pylon_camera
from ptri_camerautils.Core.PixelFormatEnum import PixelFormatEnum

# 建立相機實例
camera = create_first_instance_pylon_camera(
    camera_pixel_format = PixelFormatEnum.BayerGR8,
    output_pixel_format = PixelFormatEnum.BGR8,
    logger = logging.getLogger(__name__)
)

if camera is not None:
    # 初始化相機
    camera.initialize_camera()
    
    # 載入相機設定（可選）
    camera.load_camera_settings_from_file("camera_settings.pfs")
    
    # 設定相機參數
    camera.exposure_time = 10000.0  # 微秒
    camera.gain = 1.5
    
    # 開始串流
    camera.start_camera_streaming()
    
    # 擷取幀
    frame = camera.get_frame()
    if isinstance(frame, GrabbedImage):
        image = frame.image
        timestamp = frame.timestamp
        # 處理影像...
    
    # 停止串流
    camera.stop_camera_streaming()
    
    # 儲存相機設定（可選）
    camera.save_camera_settings("camera_settings.pfs")
    
    # 釋放資源
    camera.deinitialize_camera()
```

### 使用影像檔案伺服器（模擬相機）

#### 啟動伺服器

```bash
python -m ptri_camerautils.CameraEmulation.run_local_image_server \
    --path /path/to/images \
    --port 6008 \
    --recursive True \
    --framerate 30.0
```

#### 使用客戶端

```python
import logging
from ptri_camerautils.CameraEmulation.TcpFrameProviders.ImageFileAsFrameSource import ImageFileClient

# 建立客戶端
client = ImageFileClient(
    port = 6008,
    chunk_size = 4096,
    read_timeout = 5.0,
    logger = logging.getLogger(__name__)
)

# 初始化（連接到伺服器並取得資訊）
client.initialize_camera()

# 開始串流
client.start_camera_streaming()

# 擷取幀
frame = client.get_frame()
if isinstance(frame, GrabbedImage):
    image = frame.image
    # 處理影像...

# 停止串流
client.stop_camera_streaming()

# 釋放資源
client.deinitialize_camera()
```

## 依賴套件

- `pypylon`：用於 Pylon 相機支援
- `numpy`：用於影像資料處理
- `Pillow`：用於影像檔案讀取（CameraEmulation 模組）
- `overrides`：用於方法覆寫標記

## 注意事項

1. **相機串流狀態**：某些相機設定（如像素格式、影像尺寸）只能在相機未處於串流狀態時修改
2. **錯誤處理**：`get_frame()` 方法可能返回 `Exception` 而非 `GrabbedImage`，使用時請檢查返回類型
3. **資源管理**：使用完相機後務必呼叫 `deinitialize_camera()` 以釋放資源
4. **像素格式轉換**：Pylon 相機支援自動像素格式轉換，可設定 `camera_pixel_format` 和 `output_pixel_format` 為不同格式

## 測試

測試檔案位於 `tests/` 目錄下，包含：

- `test_image_file_client.py`：影像檔案客戶端的測試腳本

執行測試前請確保已安裝所有依賴套件。
