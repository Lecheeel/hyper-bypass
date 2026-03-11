# Xiaomi HyperOS BootLoader Bypass

绕过小米 HyperOS 社区版 BootLoader 解锁的账号绑定限制。

## 功能特点

- 支持中国版与国际版 ROM
- 自动检测设备，引导完成绑定流程
- 可指定 ADB 路径或使用内置 `libraries` 目录

## 环境要求

- **Python 3.9+**
- **ADB**（Android platform-tools）
- Python 依赖：`pycryptodome`、`requests`

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 ADB

任选其一：

- 将 [platform-tools](https://developer.android.com/studio/releases/platform-tools) 加入系统 PATH
- 或将 ADB 可执行文件放入 `libraries` 目录：
  - Windows：`libraries/adb.exe`
  - macOS：`libraries/adb-darwin`（从 platform-tools 的 `adb` 重命名）
  - Linux：`libraries/adb`

### 3. 运行脚本

```bash
python bypass.py
```

或使用启动脚本：

- Windows：双击 `bypass.cmd` 或在 CMD 中运行
- Linux / macOS：`./bypass.sh`

## 命令行选项

```
python bypass.py [选项]

  -g, --global      使用国际版 API（非中国版 ROM）
  -p, --adb-path    指定 adb 可执行文件路径
  -v, --verbose     详细输出
```

示例：

```bash
python bypass.py --global                              # 国际版 ROM
python bypass.py -p "C:\platform-tools\adb.exe"         # 自定义 ADB 路径
```

## 设备准备

1. 连续点击 **设置 → 关于手机 → MIUI 版本** 开启开发者选项
2. 在开发者选项中开启 **OEM 解锁**、**USB 调试**、**USB 调试（安全设置）**
3. 登录有效的小米账号
4. 使用 USB 连接手机与电脑
5. 勾选「始终允许此计算机调试」并确认
6. 运行脚本并按提示操作

## 免责声明

解锁 BootLoader 后可能产生：

- 软硬件故障或损坏
- 数据丢失
- 保修失效
- TEE 相关功能永久损坏
- 设备或账号被封禁

## 常见问题

| Q | A |
|------|------|
| 解锁工具仍提示等待 168/360 小时？ | 本工具仅绕过 HyperOS 限制，MIUI 等待时间仍适用 |
| 设备显示「无法验证，请稍后再试」？ | 正常现象，脚本会拦截设备请求，以脚本输出为准 |
| 错误 401 | 账号凭证过期，请在设备上重新登录 |
| 错误 20086 | 设备凭证过期，请重启设备 |
| 错误 30001 | 设备被小米强制验证，暂无解决方案 |
| 错误 86015 | 签名无效，请重试 |

## 致谢

基于 [NekoYuzu (MlgmXyysd)](https://github.com/MlgmXyysd) 的 [Xiaomi-BootLoader-Bypass](https://github.com/MlgmXyysd/Xiaomi-BootLoader-Bypass) 原项目。

## 作者

**[Lecheel](https://github.com/Lecheeel)**

---

如果本项目对你有帮助，欢迎 Star ⭐