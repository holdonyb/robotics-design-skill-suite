# Robotics Design Skill Suite

[English](README.md)

一套面向 Codex 的证据门控机器人设计 skill suite，覆盖系统需求、CAD、标准件、DXF、URDF、SDF、SRDF、ROS 2 工程、Gazebo 仿真、结构保真的产品效果图、可追溯任务动画、专利感知架构、可视化审查和验证闭环。

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

如需记录某台机器的专用 Python 运行时，可传入已有解释器，让安装器生成 host overlay，而不把本机路径写进公共源码：

```bash
python scripts/install.py --host-runtime-python /path/to/python3.12
```

它只会在暂存安装中生成 `references/host-runtime.md`；仓库中的 runtime 与 source lock 仍保持可移植。

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

## 物理可信门禁

0.3.0 版在常规仿真或训练之前增加封闭、机器可读的设计契约。它把带明确单位的物理量绑定到证据，把组件逐项绑定到左右驱动及各关节责任，把每个分析输入锁定到期望物理维度，校验工件哈希、URDF 责任量与受限声明式 JSON 观察量漂移，并为驱动、电池/续航、静态稳定性、机械臂重力/抱闸保持以及保守稳态绕组热占空比输出确定性诊断与有符号裕量。

```bash
python skills/robotics-design/scripts/validate_design_contract.py path/to/design-contract.json --report evidence.json
```

退出码 `0` 只表示声明的契约在当前证据等级下通过了已经实现的解析筛选。缺失或占位部件、过期证据、非法单位、不完整的执行器/载荷路径、缺少架构推导的分析覆盖以及失败或不确定的分析都会阻止晋级。仿真不能补上缺失的电机、减速器、轴承、驱动器、制动器、供电保护部件，也不能替代缺失的连续或热能力证据。

[`reference/mobile-manipulator`](reference/mobile-manipulator) 是“差速底盘 + 六轴机械臂”的回归工装，包含 32 个关键故障变体。其中的组件额定值都是工程假设，不是制造或采购推荐；在精确部件和更强证据替换所有影响结论的占位项之前，它会故意保持不可晋级。完整约束见 [`physical-plausibility-contract.md`](skills/robotics-design/references/physical-plausibility-contract.md)。

## 有边界的设计假设

0.4 版增加确定性的有限设计空间、硬不确定性与反例搜索、可见 Pareto
front、责任正确的修复 lineage，以及事务式证据包。每个规范解析后的
候选都必须经过 0.3 的契约与物理门禁；内容 alias 共享同一份证据。候选
数和阶段执行数是硬预算。

```bash
python skills/robotics-design/scripts/generate_design_hypotheses.py reference/mobile-manipulator/hypothesis-space.json --out ../v040-reference --seed 20260813
```

退出码 `0` 表示至少一个候选被接受，`1` 表示有限评估完成但没有候选被
接受，`2` 表示输入非法或执行/发布安全失败。打印的 `manifest_sha256`
需要保存在证据包之外。`pareto.json` 面向晋级；`screening-pareto.json`
只是对“解析分析通过、唯一 blocker 为组件占位”的候选做非晋级比较。
这些计算证据不能证明仿真或实机性能。完整规则见
[`hypothesis-engine-contract.md`](skills/robotics-design/references/hypothesis-engine-contract.md)
与公开的 [`hypothesis benchmark`](reference/mobile-manipulator/hypothesis-benchmark.md)。

## 仿真、回放与训练边界

0.5 版增加了封闭的仿真入场回执、十个确定性参考场景、带外部回执的规范
trace 包、独立平面动力学交叉检查、受限标定，以及只能产生仿真证据的策略
回调边界。

```bash
python skills/robotics-design/scripts/validate_simulation_bundle.py \
  --reference-root reference/mobile-manipulator
```

退出码 `0` 表示全部场景通过的有效便携式合成回放；`1` 表示有效但包含失败
或不确定场景的基准；`2` 表示输入被篡改/非法或安全失败。它不是 Gazebo live
运行，绝不授权硬件晋级。独立的 Linux Jazzy/Harmonic 工作流才会实际加载
Gazebo、ros2_control、MoveIt 和 Nav2，并在失败时保留日志和包清单。详情见
[`simulation benchmark`](reference/mobile-manipulator/simulation-benchmark.md)。v0.5 候选版在
`ced7dc3` 上已有两条保留的 consumer-gate 成功记录；它只是集成证据，绝不构成硬件晋级。

## 工程冻结边界

v0.6 工程冻结门禁记录哈希绑定的供应商快照、受控工件引用、危害、安全功能链路、验证与检查项，以及计划中的硬件测试卡。它只为未来工程评审提供输入，绝不构成采购、制造、通电或运动授权。

```bash
python skills/robotics-design/scripts/validate_engineering_freeze.py \
  --package reference/mobile-manipulator/engineering-freeze/freeze-package.json
```

退出码 `0` 代表完整的审查包，`1` 代表输入有效但仍有开放工程缺口，`2` 代表输入非法或被篡改。`procurement_authorized` 与 `motion_authorized` 永远为 `false`。参考包会刻意返回 `1`，因为尚未有选定供应商部件、受控图纸或获授权的硬件测试条件。

## 原始台架证据接收

v0.7 只在未来部件测量同时提供原始本地 CSV、哈希、精确单位/列和时间戳、仪器校准快照、已批准的记录测试卡、场地/操作者元数据及部件/需求边时接收它。

```bash
python skills/robotics-design/scripts/validate_bench_evidence.py \
  --index reference/mobile-manipulator/bench-evidence/intake-index.json
```

空的参考索引会以 `awaiting_authorization` 返回退出码 `1`，它不是台架结果。验证器没有设备接口，绝不授权采购、通电或运动。

## 结构保真的机器人效果图

0.2.0 版禁止图像生成模型悄悄改写机器人的机构。拓扑与姿态必须由 CAD、URDF、SDF 或等价的确定性模型负责；生成图只允许改变材质、表面处理、颜色、光照、背景和不接触机器人的环境内容。

目标动作必须先在上游模型中设定，再输出能够看清关节与接口标志点的确定性参考图，最后才做 image-to-image 外观增强。只有源文件哈希和关节/接口标志点集合都通过清单校验，效果图才能升级为正式资产：

```bash
python skills/robotics-design/scripts/validate_visual_manifest.py path/to/visual_manifest.json
```

完整规则见 [`visualization-contract.md`](skills/robotics-design/references/visualization-contract.md)。画面看起来合理或附带免责声明，都不能证明拓扑、轴线、接口和姿态正确。

## 可追溯任务动画

任务动画由一个确定性模型、一条验收后的轨迹和一份物理/接触状态 trace 共同驱动。用于工程证据的机器人关节运动不能手工打关键帧。每个可发布动画都要记录源文件哈希、规范关节顺序、必须运动的关节、任务阶段、接触状态、载荷工况、违规计数和独立审查证据。

```bash
python skills/robotics-design/scripts/validate_mission_animation_manifest.py path/to/mission_manifest.json
```

完整约束见 [`mission-animation-contract.md`](skills/robotics-design/references/mission-animation-contract.md)。视频成功渲染只证明帧存在，不能单独证明动力学、接触真实性、可控性或硬件性能。

## 专利感知架构

专利研究和竞品启发设计必须先经过来源研究与逐要素 claim chart，再冻结架构。选中的差异原则会转成正向设计要求、禁止组合、责任工件和漂移测试。这是工程设计规避筛查，不是法律意见或 FTO 结论；法律结论仍由具备资质的律师负责。

证据层级、claim chart、审查包和法律边界见 [`patent-design-around.md`](skills/robotics-design/references/patent-design-around.md)。

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

测试覆盖清单完整性、固定 commit、事务式安装、host overlay、bytecode 排除、许可证保留、Codex frontmatter 规范化、拒绝覆盖、ZIP 路径穿越保护、公开内容卫生、物理契约/单位/证据/逐责任组件绑定、确定性分析报告、有限假设、不确定性/反例、Pareto front、修复责任、清单绑定证据包、参考 benchmark、URDF 漂移、32 个关键物理故障、视觉源文件哈希与 landmark 门禁、任务轨迹/接触 trace，以及专利感知路由边界。

## 能力边界

这套 suite 改善工程工作流，但不会认证机器人，也不提供法律意见。生成或仿真的工件不能证明负载、稳定性、制动距离、续航、现场可靠性、人机共融安全或法规合规；专利感知约束也不能证明不侵权或已完成 FTO。真实机器人运动必须具备明确授权、受控测试区、可触达急停、功率/力矩/速度限制、命令超时和分阶段调试。

ROS 2 实时仿真需要安装 ROS 2 Jazzy 与 Gazebo Harmonic 的 Linux 环境。承诺仿真结果前必须运行已安装的 `ros2-sim/scripts/env_check.sh`。

## 供应链与许可证

精确来源见 [`manifest.json`](manifest.json) 和 [`source-lock.md`](skills/robotics-design/references/source-lock.md)。安装器通过 HTTPS 下载完整 commit 对应的归档，并把上游许可证放进每个安装后的第三方 skill。

本仓库原创内容使用 MIT 许可证。第三方组件保留其各自许可证，详见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

贡献方式见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。更新上游来源必须重新审计、测试并更新来源记录，不能只替换 commit。
