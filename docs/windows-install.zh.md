# Windows 安装说明

适用于 Windows 10 / 11。安装一次即可，之后每个新案件只需建一个配置文件。
English version: [windows-install.md](windows-install.md)

## 一、需要准备的软件

| 软件 | 用途 | 是否必需 |
|---|---|---|
| Python 3.9 或更新版本 | 运行脚本 | 必需 |
| Python 依赖包（PyMuPDF、numpy、openpyxl、Pillow、RapidOCR） | 读写 PDF、图像处理、生成 Excel、中英文 OCR | 必需 |
| LibreOffice（免费） | 把 Word 译文（.docx）转成 PDF | 有 Word 文件时需要；也可用已安装的 Microsoft Word 代替 |
| 支持 `SKILL.md` 技能的 AI 助手 | 按技能流程逐页复核并调用脚本 | 使用技能时需要；脚本本身也可单独在命令行运行 |

## 二、安装步骤

### 第 1 步：安装 Python

1. 打开 <https://www.python.org/downloads/windows/>，下载最新的 Python 3（64 位）安装程序。
2. 运行安装程序，第一个界面务必勾选 **Add python.exe to PATH**，然后点 **Install Now**。
3. 按 Win 键输入 `cmd` 打开“命令提示符”，输入下面的命令，能看到版本号即成功：

   ```
   python --version
   ```

   如提示“不是内部或外部命令”，请重新运行安装程序选择 **Modify** 并勾选 *Add Python to environment variables*，或改用 `py` 命令。

### 第 2 步：安装 Python 依赖包

```
python -m pip install --upgrade pip
python -m pip install pymupdf numpy openpyxl pillow rapidocr_onnxruntime
```

国内网络较慢时可使用清华镜像：

```
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pymupdf numpy openpyxl pillow rapidocr_onnxruntime
```

`rapidocr_onnxruntime` 是 OCR 组件，已自带中英文识别模型，无需另外下载。

### 第 3 步：安装 LibreOffice（处理 Word 文件用）

1. 打开 <https://www.libreoffice.org/download/download/>，下载 Windows 64 位版本，按默认选项安装（默认路径 `C:\Program Files\LibreOffice`），脚本会自动找到。
2. 不想装 LibreOffice、但电脑已有 Microsoft Word 时，可改为：`python -m pip install docx2pdf`。
3. 附件中没有 Word 文件时可跳过本步。

### 第 4 步：安装技能

1. 下载本仓库（GitHub 页面 **Code → Download ZIP** 后解压，或 `git clone`），确保文件夹名为 `bpi-public-versions`，其中直接包含 `SKILL.md`、`scripts\`、`references\`。
2. 把整个文件夹复制到所用 AI 助手的技能（skills）目录，具体位置见该助手的说明；或在助手设置中导入。
3. 重新启动 AI 助手，使其加载技能。

### 第 5 步：检查环境

进入一个案件文件夹（例如 `D:\案件\某案`），在资源管理器地址栏输入 `cmd` 回车打开命令提示符，运行（把 `<技能目录>` 换成实际路径）：

```
python "<技能目录>\bpi-public-versions\scripts\bpi.py" init
python "<技能目录>\bpi-public-versions\scripts\bpi.py" doctor
```

`init` 会在案件文件夹生成 `bpi_config.json`；`doctor` 逐项显示 `[ok]` 或缺少的组件。看到 `OCR backend: rapidocr` 和 `ready` 即安装成功。

## 三、新案件如何使用

1. 把附件放进案件文件夹下的一个子文件夹，每个项目一个子文件夹（例如 `205.轧钢项目`）。
2. 用记事本打开 `bpi_config.json`，填写：
   - `source_dir`：附件文件夹名；
   - `out_bpi` / `out_public`：输出文件夹名；
   - `header_left`：页眉左侧文字，如 `EAPA Case No. xxxx | Exhibit xx`（只能用英文）；
   - `own_company_regex`：本方公司的中英文名称、地址、电话等，用 `|` 分隔（这些信息保持公开）。
3. 对 AI 助手说：“请用 bpi-public-versions 技能，为 `D:\案件\某案` 里的附件制作 BPI 版和 Public 版”，并提供要求文件（如 RFI）。
4. 助手会依次：阅读要求文件 → 摸底附件并报告问题文件 → 与您确认括号口径 → 先做样例给您审阅 → 全量制作 → 防泄露复查 → 交付 BPI 版、Public 版文件夹和 `BCI Log.xlsx`。

## 四、常见问题

- **中文显示乱码**：先运行 `chcp 65001`，或在系统环境变量中新增 `PYTHONUTF8=1`。
- **“pip 不是内部命令”**：一律使用 `python -m pip …`；仍不行改用 `py -m pip …`。
- **OCR 速度**：RapidOCR 在普通笔记本上约每页 1–3 秒，3,000 页需数小时；结果缓存在 `_work\ocr`，只需运行一次。
- **不要中途换电脑重新 OCR**：不同电脑 / 识别引擎的错字不同，已写好的复核修改可能对不上。需要换电脑时，把整个案件文件夹（含 `_work`）一起拷走。
- **杀毒软件拦截**：首次运行若被拦截，请将 Python 和案件文件夹加入信任列表。
- **文件过大**：若提交系统限制单个文件大小，可在 `bpi_config.json` 中把 `dpi` 改为 150、`jpeg_quality` 改为 70 后重新生成。
- **路径过长报错**：把案件文件夹放在较短路径下（如 `D:\案件\`），或在 Windows 中启用长路径支持。
