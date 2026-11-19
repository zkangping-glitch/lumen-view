# Lumen View

轻量的 Windows 图片查看与编辑器。Python + Qt 原生界面，无浏览器运行时；跟随系统浅色／深色外观，默认以图片为主，进入编辑后再显示工具。

![浏览界面](docs/modern-browse.png)

## 浏览与编辑

- JPEG、PNG、GIF、WebP、AVIF、HEIC、JXL、TIFF、PSD、SVG、相机 RAW 等格式。
- 滚轮缩放、拖动平移、前后翻页、全屏和幻灯片。
- 点击“编辑”或按 `Ctrl+E`：亮度、对比度、饱和度、旋转、水平翻转。
- 裁剪支持原始比例、1:1、16:9、4:5，以画面中心裁剪。
- 撤销／重做，按住查看原图；取消编辑还原原图。
- 保存副本支持 JPEG、PNG、WebP；所有编辑均不修改原图。

![编辑界面](docs/modern-editor.png)

## GIF 编辑

![GIF 时间轴](docs/modern-gif.png)

- 横向帧缩略图展示全部帧，支持选中、删除、在当前帧后添加外部图片，以及将当前帧导出为 PNG。
- 调整、裁剪、旋转和翻转可选择作用于当前帧或全部帧；支持 0.5×／1×／1.5×／2× 调速。
- 导出 GIF 或动画 WebP，保留帧时长和循环次数。
- 转成静态格式时，可选择当前帧或第一帧。
- GIF 仅支持 256 色和二值透明；半透明效果推荐导出动画 WebP。
- GIF 编辑预览按需生成，不预先复制整段编辑后的动画；复杂画面的预览帧率取决于处理速度，导出按设定时长编码。

## Windows 启动

从 GitHub Actions 的 `LumenView-Windows` 构建产物下载 `LumenView-Setup.exe`。安装器为当前用户安装，不要求管理员权限；应用已包含 Python、Qt 与图片解码依赖，无需另外配置运行环境。构建产物同时提供免安装的 `LumenView-portable.zip`。

安装器目前未做代码签名，Windows SmartScreen 可能显示“未知发布者”。确认文件来自本仓库的构建记录后，可选择“更多信息 → 仍要运行”。

### 从源码运行

需要 **64 位 Python 3.12**。仓库不包含 `.pylibs` 依赖目录，首次使用先安装：

```powershell
py -3.12 tools/fetch_libs.py
.\LumenView.cmd
```

安装器调用 pip，读取固定版本的 `requirements.txt`，失败返回非零状态。依赖安装到项目内 `.pylibs`。

或创建独立开发环境：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e . pytest
.venv\Scripts\python -m lumenview "D:\photos\photo.gif"
```

### 构建 Windows 安装器

```powershell
python -m pip install -e . -r requirements.txt "pyinstaller>=6.16,<7"
python tools/make_icon.py
pyinstaller --noconfirm --clean packaging/LumenView.spec
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" packaging\LumenView.iss
```

安装文件输出到 `dist\installer\LumenView-Setup.exe`。GitHub Actions 会在 Linux／Windows 测试通过后自动执行同样的独立应用打包、启动冒烟测试与安装器构建。

## 快捷键

| 操作 | 快捷键 |
| --- | --- |
| 打开图片／文件夹 | Ctrl+O / Ctrl+Shift+O |
| 前后翻页 | ← / → / 空格 |
| 编辑／保存副本 | Ctrl+E / Ctrl+Shift+S |
| 撤销／重做 | Ctrl+Z / Ctrl+Shift+Z |
| 旋转／翻转 | R / Shift+R / H |
| 适应窗口／实际大小 | 0 / 1 |
| 缩略图栏／全屏／幻灯片 | Tab / F11 / F5 |

## 验证

```powershell
python -m pytest -q
python tools/ui_test.py
python tools/selftest.py
```

测试覆盖静态调色和透明度、GIF／动画 WebP 往返、片段时长、循环次数、原图保护、原子保存失败恢复，以及真实 Qt 窗口中的编辑与后台导出。GitHub Actions 配置 Linux／Windows 两个平台检查。

## 当前边界

- 第一版不含自由拖动裁剪框、文字、涂鸦或逐帧绘画。
- 未做 ICC 色彩管理和 HDR 显示，专业印前／色彩校对请使用专门软件。
- 多页 TIFF 当前显示第一页；SVG 静态渲染，最长边 2048px。
- Pillow／PSD／RAW 主图限制 6400 万像素，动画解码预算 256 MiB；超出时提示错误，不静默截断动画。
- 文件夹最多 5000 张；缩略图按可见区域加载，缓存最多 128 张。
- Windows 应用和安装器未签名；自动构建的启动冒烟测试不能替代 Windows 真机交互验收。

## 代码结构

- `modern.py`：现代界面、编辑状态、时间轴和后台任务。
- `editing.py`：可撤销操作参数、图像变换、GIF 时长处理、原子导出。
- `window.py` / `canvas.py`：原生窗口、异步解码、画布与浏览能力。
- `decoders.py` / `filmstrip.py`：格式分发和按需缩略图。

## 第三方组件

- [PySide6](https://www.qt.io/) — LGPL / 商业双许可
- [Pillow](https://python-pillow.org/) — HPND
- [pillow-heif](https://github.com/bigcat88/pillow_heif) — BSD-3-Clause（libheif / libde265 / x265）
- [pillow-jxl-plugin](https://github.com/Isotope-Labs/pillow-jxl-plugin) — BSD-3-Clause（libjxl）
- [psd-tools](https://github.com/psd-tools/psd-tools) — MIT
- [rawpy](https://github.com/letmaik/rawpy) — MIT（libraw）
