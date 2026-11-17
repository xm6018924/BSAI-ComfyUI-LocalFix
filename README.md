# BSAI LocalFix

百声 AI 整合包的 ComfyUI 启动自愈层。每次 ComfyUI 启动时执行，幂等；任何一步失败只打印一行，绝不影响启动。

Boot-time self-healing layer for the BSAI ComfyUI integration pack. Idempotent, fail-safe: any failure prints one line and never blocks startup.

## 为什么独立成仓库 / Why its own repo

本模块刻意放在各 BSAI 插件目录之外——插件被更新或执行 `git reset --hard origin/main` 时不会把它冲掉。独立成仓库后，C 盘（v43）与 G 盘（Intel XPU 包）共用同一远端，同步与回滚都走 git。

Deliberately kept outside each BSAI plugin repo so plugin updates / hard resets cannot wipe it. With its own repo, the C-drive (v43) and G-drive (Intel XPU pack) installs share one remote; sync and rollback go through git.

## 自愈项 / Self-heal entries

| 函数 | 作用 |
|---|---|
| `_ensure_strata_port_guard` | 启动 BSAI-LLM-Strata 引擎前先释放端口，避免 `port ... already in use` |
| `_ensure_ptd_search_dirs` | 注册 PTD 适配器搜索目录（`models/ptd`、`models/loras/H3/H3加速/PTD`） |
| `_ensure_pinned_hostbuf_headroom` | 接管 `pinned_hostbuf_size`：预留 = 2×模型 + 2GB，避免 aimdo hostbuf 溢出 |
| `_ensure_convert_old_quants_dedup` | 剥离前缀后不再重复注入带前缀的 `comfy_quant` |
| `_ensure_pin_memory_mmap_guard` | `pin_memory` 失败静默 + 负缓存（只读 mmap 权重 `cudaHostRegister` 必失败），消除 `Pin error` 刷屏 |
| `_ensure_custom_node_upstreams` | 给缺 upstream 的自定义节点仓库补 `branch.<X>.remote/merge`，消除 Manager 的 `CUSTOM NODE CHECK: Error` |
| `_ensure_manager_gitcheck_result` | 给 ComfyUI-Manager 的 `git_helper.py` 补缺失的 else 分支（本地领先远端时也输出结果），消除 `Fetch error` 刷屏 |
| `_ensure_manager_pip_blacklist` | 把会卡死启动的 VCS 依赖（`git+…/facebookresearch/sam2`）写进 Manager 的 `pip_blacklist.list` |

## 部署 / Install

放到 `<ComfyUI>/custom_nodes/_BSAI_LocalFix/`。目录名以 `_` 开头，ComfyUI 不作为节点加载，只执行模块级引导代码。

Drop into `<ComfyUI>/custom_nodes/_BSAI_LocalFix/`. The leading underscore keeps ComfyUI from loading it as a node pack; only the module-level bootstrap runs.
