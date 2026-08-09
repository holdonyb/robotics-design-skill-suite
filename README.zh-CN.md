# Robotics Design Skill Suite

[English](README.md)

一套面向 Codex 的证据门控机器人设计 skill suite，覆盖系统需求、CAD、标准件、DXF、URDF、SDF、SRDF、ROS 2 工程、Gazebo 仿真、结构保真的产品效果图、可视化审查和验证闭环。

本仓库采用薄封装：只维护原创的总路由、验证合同和安装器；第三方 skills 根据 [`manifest.json`](manifest.json) 中的完整 commit 固定版本下载，不把上游源码整包复制进仓库。

## 包含内容

| 层级 | Skills |
|---|---|
| 系统路由 | `robotics-design` |
| 机械工件 | `cad`、`step-parts`、`dxf`、`cad-viewer` |
| 机器人描述 | `urdf`、`sdf`、`srdf` |
| 软件与仿真 | `ros2-engineering-skills`、`ros2-sim` |

## 安装

需要 Git 与 Python 3.11+。

```bash
git clone https://github.com/holdonyb/robotics-design-skill-suite.git
cd robotics-design-skill-suite
python scripts/install.py --dry-run
python scripts/install.py
```

默认安装到 `${CODEX_HOME}/skills`；未设置 `CODEX_HOME` 时使用 `~/.codex/skills`。也可以指定目标：

```bash
python scripts/install.py --dest /path/to/codex/skills
```

安装器不会覆盖已有 skill 目录。请先审查或移动旧版本。安装后新建一个 Codex 任务，让 skill 自动发现刷新。

## 使用

```text
$robotics-design 设计一台室内移动机械臂，从需求、CAD、URDF、SDF、ROS 2 到仿真验证完整执行。
```

也可以直接调用工件负责人：

```text
$urdf 审查这个机器人描述的坐标系、轴、限位、惯量和消费者加载问题。
$sdf 创建 Gazebo Harmonic 世界，并列出所有没有执行的验证门禁。
```

## 结构保真的机器人效果图

0.2.0 版禁止图像生成模型悄悄改写机器人的机构。拓扑与姿态必须由 CAD、URDF、SDF 或等价的确定性模型负责；生成图只允许改变材质、表面处理、颜色、光照、背景和不接触机器人的环境内容。

目标动作必须先在上游模型中设定，再输出能够看清关节与接口标志点的确定性参考图，最后才做 image-to-image 外观增强。只有源文件哈希和关节/接口标志点集合都通过清单校验，效果图才能升级为正式资产：

```bash
python skills/robotics-design/scripts/validate_visual_manifest.py path/to/visual_manifest.json
```

完整规则见 [`visualization-contract.md`](skills/robotics-design/references/visualization-contract.md)。画面看起来合理或附带免责声明，都不能证明拓扑、轴线、接口和姿态正确。

## 可选 CAD 运行时

安装 skill 不会修改 Python 环境。CAD 生成建议使用隔离的 Python 3.12+；DXF 还需要 `ezdxf`。

```bash
python3.12 -m venv .venv-robotics-design
.venv-robotics-design/bin/python -m pip install -e ~/.codex/skills/cad/scripts/packages/cadpy ezdxf
```

Windows 使用环境中的 `Scripts/python.exe`。平台说明见 [`runtime.md`](skills/robotics-design/references/runtime.md)。

## 验证

```bash
python -m compileall -q scripts tests skills/robotics-design/scripts
python -m unittest discover -s tests -v
python scripts/validate.py
python scripts/install.py --dry-run
```

测试覆盖清单完整性、固定 commit、确定性安装计划、离线 fixture 安装、许可证保留、Codex frontmatter 规范化、拒绝覆盖、ZIP 路径穿越保护、公开内容卫生、机器人效果图行为、源文件哈希、允许的外观变化，以及关节/接口标志点的严格晋级门禁。

## 能力边界

这套 suite 改善工程工作流，但不会认证机器人。生成或仿真的工件不能证明负载、稳定性、制动距离、续航、现场可靠性、人机共融安全或法规合规。真实机器人运动必须具备明确授权、受控测试区、可触达急停、功率/力矩/速度限制、命令超时和分阶段调试。

ROS 2 实时仿真需要安装 ROS 2 Jazzy 与 Gazebo Harmonic 的 Linux 环境。承诺仿真结果前必须运行已安装的 `ros2-sim/scripts/env_check.sh`。

## 供应链与许可证

精确来源见 [`manifest.json`](manifest.json) 和 [`source-lock.md`](skills/robotics-design/references/source-lock.md)。安装器通过 HTTPS 下载完整 commit 对应的归档，并把上游许可证放进每个安装后的第三方 skill。

本仓库原创内容使用 MIT 许可证。第三方组件保留其各自许可证，详见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

贡献方式见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。更新上游来源必须重新审计、测试并更新来源记录，不能只替换 commit。
