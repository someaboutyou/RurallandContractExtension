# 授权系统实现文档

## 概述

本系统实现了基于RSA签名的软件授权机制，用于控制农村土地承包延期系统的数据访问范围。

## 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                        授权流程                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   授权工具（本地）                    Web系统（服务器）             │
│   ┌─────────────────┐            ┌─────────────────┐            │
│   │ 私钥 (保密)      │            │ 公钥 (可公开)    │            │
│   │ license_gen     │            │ license_val     │            │
│   └────────┬────────┘            └────────┬────────┘            │
│            │                              │                     │
│            │  用私钥签名授权文件            │  用公钥验证签名      │
│            ▼                              ▼                     │
│   ┌─────────────────┐            ┌─────────────────┐            │
│   │ license.dat     │ ──发给用户──→│ license.dat     │            │
│   │ (签名+数据)     │            │ (验证通过)       │            │
│   └─────────────────┘            └─────────────────┘            │
│                                                                 │
│   关键：即使用户看到验证器代码（公钥），也无法伪造授权文件           │
│        因为签名需要私钥，而私钥只在授权工具中                      │
└─────────────────────────────────────────────────────────────────┘
```

## 文件结构

### 授权工具（E:\Work\RurallandContractExtensionLic）

```
RurallandContractExtensionLic/
├── main.py              # 主程序入口
├── start.bat            # Windows启动脚本
├── requirements.txt     # Python依赖
├── licenses.db          # 授权记录数据库（自动生成）
├── keys/                # 密钥目录
│   ├── private_key.pem  # 私钥（用于签名）
│   └── public_key.pem   # 公钥（用于验证）
├── src/                 # 源代码
│   ├── __init__.py
│   ├── crypto_utils.py      # 加密工具
│   ├── database.py          # 数据库操作
│   ├── gui.py               # GUI界面
│   └── license_generator.py # 授权文件生成
├── test_license.py      # 单元测试
└── test_integration.py  # 集成测试
```

### Web系统（backend/app/core/license）

```
backend/app/core/license/
├── __init__.py
├── license_models.py      # 授权数据模型
├── machine_fingerprint.py # 机器码生成
├── license_validator.py   # 授权文件验证
└── middleware.py           # 授权检查中间件
```

## 使用流程

### 1. 部署授权工具

```bash
# 进入授权工具目录
cd E:\Work\RurallandContractExtensionLic

# 安装依赖
pip install -r requirements.txt

# 启动工具
python main.py
# 或双击 start.bat
```

### 2. 获取机器码

用户首次访问Web系统时，会显示机器码。或访问：
```
GET /api/v1/license/machine-code
```

返回示例：
```json
{
  "data": {
    "machine_code": "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4",
    "message": "请将此机器码发送给授权方获取授权文件"
  }
}
```

### 3. 生成授权文件

1. 启动授权工具
2. 输入机器码（32位）
3. 输入区域码（6/9/12位）
4. 设置有效期
5. 点击"生成授权文件"
6. 保存文件并发送给用户

### 4. 部署授权文件

用户将授权文件放到：
```
backend/storage/license.dat
```

### 5. 验证授权

访问：
```
GET /api/v1/license/status
```

返回示例：
```json
{
  "data": {
    "status": "valid",
    "is_valid": true,
    "region_code": "321324100",
    "region_name": "test_town",
    "region_level": "town",
    "issued_at": "2024-01-01T00:00:00",
    "expires_at": "2025-01-01T00:00:00",
    "features": ["survey", "request", "contract"]
  }
}
```

## 授权范围

| 区域码长度 | 级别 | 说明 |
|-----------|------|------|
| 6位 | 区县级 | 可访问整个区县的数据 |
| 9位 | 镇级 | 可访问某个镇的数据 |
| 12位 | 村级 | 可访问某个村的数据 |

## 安全机制

### 1. RSA签名

- 使用2048位RSA密钥对
- 私钥用于签名授权文件
- 公钥用于验证签名
- 即使公钥泄露，也无法伪造授权文件

### 2. 机器码绑定

- 授权文件包含机器码
- 验证时检查机器码是否匹配
- 防止授权文件被复制到其他机器

### 3. 有效期控制

- 支持设置有效期
- 过期后需要重新授权
- 支持永久授权

### 4. 数据拦截

- ORM查询自动过滤
- 写入操作自动校验
- 确保数据不越权

## 测试

### 运行单元测试

```bash
cd E:\Work\RurallandContractExtensionLic
python test_license.py
```

### 运行集成测试

```bash
cd E:\Work\RurallandContractExtensionLic
python test_integration.py
```

## 注意事项

1. **私钥安全**：私钥文件（`private_key.pem`）必须妥善保管，不要泄露
2. **授权文件**：授权文件生成后会自动保存到数据库，便于追溯
3. **区域码**：区域码必须是6位（区县）、9位（镇）或12位（村）
4. **机器码**：机器码是32位大写字母和数字的组合

## 故障排除

### 授权文件不存在

检查 `backend/storage/license.dat` 是否存在。

### 机器码不匹配

确保授权文件是针对当前服务器生成的。

### 授权已过期

联系授权方重新生成授权文件。

### 签名验证失败

授权文件可能被篡改，请重新获取。

## 扩展功能

### 添加新功能

在生成授权文件时，可以指定功能列表：
```python
features = ["survey", "request", "contract", "new_feature"]
```

### 多区域授权

当前设计支持单区域授权。如需多区域授权，需要修改授权文件格式和验证逻辑。

## 更新日志

- 2024-01-01: 初始版本，支持基本授权功能
