# 参与 Mycelium 开发（贡献指南）

感谢你参与贡献。Mycelium 是一种加密订阅源分发协议，把订阅源伪装成文件托管平台上的普通文件。仓库很小，代码刻意保持紧凑——动手修改某个包之前，请先读 `docs/` 下对应模块的文档（英文为必需，其他语言翻译可选）。

## 贡献流程 Contributing workflow

本项目遵循标准的 GitHub fork-and-pull 协作模式。所有改动都通过 pull request 合并到 `main`——绝不直接向 `main` 推送。

1. **Fork 仓库。** 用 GitHub 的「Fork」按钮在你自己账号下复制一份，再克隆到本地：

   ```text
   git clone https://github.com/<你的用户名>/Mycelium.git
   cd Mycelium
   git remote add upstream https://github.com/demoliisher/Mycelium.git
   ```

   注意：上面这个*开发用* fork 是普通的 GitHub 协作方式。不要把它和 Mycelium 的 `fork` 发布模式混淆——那是一种产品功能（把订阅源伪装成复刻仓库），与提交代码无关。

2. **创建主题分支。** 每个逻辑改动一个分支，从最新的 `main` 切出：

   ```text
   git fetch upstream
   git checkout -b fix/你的分支名 upstream/main
   ```

3. **使用 Conventional Commits 提交。** 沿用现有风格（`feat:`、`fix:`、`docs:`……），详见下方「版本与发布」。

4. **推送前跑完整门禁**（见「提交前检查」）：`ruff`、`pytest`、`mdlint`、`mdtables` 必须全部通过。

5. **推送并提交 pull request。** 把分支推到你自己的 fork，向 `demoliisher/Mycelium:main` 提交 PR。在描述里简要说明改动内容、动机与测试方式；若修复某个 issue，请引用它（如 `Closes #123`）。保持 PR 小而聚焦——一个 PR 只做一件事，远比混杂多项改动容易评审。

6. **评审。** 维护者会评审你的 PR，可能要求修改——请在 PR 讨论串中回复，并向同一分支追加提交；分支被评审过后**不要 force-push**（优先追加提交而非改写历史）。PR 合并后请删除该主题分支。

提交请使用一致且公开的身份。较大或涉及设计的改动，先开 issue 讨论方案再动手写代码；首次贡献者欢迎从 good-first-issue 开始。

## 环境准备

- Python **≥ 3.12**。
- 项目用 `uv` 管理（仓库已提交 `uv.lock`）。安装项目与开发工具链：

  ```text
  uv sync
  ```

  dev 组提供 `ruff`、`pytest`、`markdownlint-rs`（`mdlint`）、`buf`、`protoc-gen-py`。以下命令统一使用 `uv run`——从项目环境解析对应工具，必要时先自动同步环境，无需手动激活 venv。

## 代码风格

- **`uv run ruff check .`** 必须零告警通过（默认规则集）。
- `src/mycelium/protocol/feed_pb.py` 是**生成代码**，禁止手改。唯一事实来源是 `src/mycelium/protocol/feed.proto`；修改 proto 后用 `uv run buf generate` 重新生成（配置见 `buf.gen.yaml`），并提交重新生成的文件。代码中以 `from . import feed_pb as pb` 方式导入。

## 测试

- **`uv run pytest`** 必须全部通过（当前共 150 个用例；`testpaths` 配置在 `pyproject.toml`）。

## 文档

模块文档统一放在 `docs/` 下，镜像包结构：**下设模块的包**拆成「包总览 + 模块文档」——包总览为 `README.md`（如 `docs/crypto/README.md`），各模块一个文档、以模块名命名（如 `docs/crypto/Hash.md`）；播种者的平台文档独立成 `docs/interface/sower/<平台名>.md`。**无下设模块的包**保持单文件（如 `docs/interface/picker.md`）。英文文件是**必须**的——它是事实来源。其他语言的翻译**可选**：欢迎添加或更新翻译（简体中文使用 `<模块名>_zh-Hans.md` 命名，其他语言沿用同样的 `<语言标签>` 后缀规则）。已有翻译版本时，须与英文原文保持同步。

每次文档改动必须通过：

1. **Markdown 检查，含两条指令** —— 先运行 `uv run mdlint check --config mdlint.toml .`（markdownlint-rs 按仓库配置检查），再运行 `uv run python scripts/mdtables.py`（GFM 表格列对齐检查，即 MD060 `aligned` 样式，感知 CJK 双宽）。markdownlint-rs 配置有两点说明：MD033（内联 HTML）与 MD030（列表标记间距）是**有意禁用**的（MD030 因为 markdownlint-rs 把行首 `**` 误解析为 `*` 列表标记——不要为了绕开规则改写正文：行首加粗就用 `**...**`，内联 HTML 可用于任何需要 HTML 实现的高级功能，不限于表格——GitCode 权限表（HTML 表格，rowspan 合并的级别列、彩色读写禁推荐）只是其中一例）；MD013（行长）**完全禁用**——正文按自然长行书写，因为把（尤其中文）文本折行到固定宽度，渲染时会多出额外空格。改过任何表格后，先运行 `uv run python scripts/mdtables.py --fix` 就地重新对齐，再检查。

写作约定：

- 正文不折行，按自然段落书写（渲染不产生额外空格）。
- 表格使用 GFM 管道语法，列按视觉宽度对齐（东亚全宽字符按两列计），由对齐工具维护。
- 指向翻译版本的链接使用 `<语言标签>` 后缀，如 `*_zh-Hans.md`。
- **中文引号统一使用方引号「」『』**——「」优先，嵌套时用『』（如「他说『你好』」）。

## 版本与发布 Versioning & releases

- 版本遵循**语义化版本**（`major.minor.patch`）。
- 提交信息遵循 **Conventional Commits** 规范（`feat:`、`fix:`、`docs:`……）。
- 项目更新日志存放在两处镜像：`examples/eg_changelog.py` 的 `entries` 列表（每个版本一个 `(version, entry)` 元组）与 `README.md` 的「Changelog」章节。两处都要更新，然后运行 `uv run python examples/eg_changelog.py` 重新生成随仓库提交的示例文件 `examples/ChangeLog.dat`。
- 推送前先审计将要发布的内容——推送会让历史永久化。检查提交作者身份与历史中的每个标识符（用户名、邮箱、账号名、托管路径）。保持身份隔离：强审查地区平台的标识符，绝不能出现在弱审查地区的平台上。若有泄露漏过，在分支被进一步共享前重写历史并强推。

## 提交前检查

一条命令跑完全部把关并自动修复（代码风格、测试、Markdown 检查、表格对齐）：

| 检查项        | 命令                              |
| ------------- | --------------------------------- |
| 完整门禁      | `uv run python scripts/gate.py`   |
