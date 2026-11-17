"""BSAI LocalFix —— 仓库外的启动自愈引导。

放置位置刻意选在 BSAI 各插件仓库之外（独立目录），
因此不会被插件的更新 / `git reset --hard origin/main` 冲掉。
自 2026-11-17 起本目录自成仓库（BSAI-ComfyUI-LocalFix，C/G 双盘同一远端），
跨盘/跨机同步与回滚走 git，不再依赖手工复制。

职责：每次 ComfyUI 启动时，把"必须长期存在"的本地修复补回插件目录。
目前只有一项：保证 BSAI-LLM-Strata 的模型管理器 (Strata/bsai_model_manager.py)
带有「启动引擎前先释放端口」的自愈逻辑，避免 server.py 报
"port ... is already in use"。

幂等：已带修复（插件自带 `def free_port(` 或本引导注入的标记）时不做任何事。
"""

import os

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}


def _custom_nodes_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


GUARD_MARKER = "# ==== BSAI LocalFix"

# 自包含注入块：定义在模块末尾（main() 之前），把模块级 start_strata 包一层，
# 启动目标端口对应引擎前先清掉占用端口的残留进程。只追加、不改动原逻辑。
GUARD_BLOCK = '''# ==== BSAI LocalFix: 引擎启动前端口占用自愈（自动注入，勿手改）====
def _bsai_pids_on_port(port):
    import subprocess as _sp
    pids = set()
    try:
        out = _sp.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True).stdout
    except Exception:
        return pids
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper() == "TCP" and parts[3].upper() == "LISTENING":
            if parts[1].rsplit(":", 1)[-1] == str(port):
                try:
                    pids.add(int(parts[4]))
                except ValueError:
                    pass
    return pids


def _bsai_free_port(port, timeout=15):
    import subprocess as _sp, time as _t
    deadline = _t.time() + timeout
    while _t.time() < deadline:
        pids = _bsai_pids_on_port(port)
        if not pids:
            return True
        for pid in pids:
            try:
                _sp.run(["taskkill", "/f", "/t", "/pid", str(pid)], capture_output=True)
            except Exception:
                pass
        _t.sleep(1)
    return not _bsai_pids_on_port(port)


_BSAI_DEFAULT_PORT = globals().get("STRATA_PORT", 8080)
_BSAI_MODEL_PORTS = {
    "flint": globals().get("FLINT_PORT", 8082),
    "deepseek": globals().get("DEEPSEEK_PORT", 8083),
}
_bsai_start_strata_inner = start_strata


def start_strata(model_name):
    try:
        _bsai_free_port(_BSAI_MODEL_PORTS.get(model_name, _BSAI_DEFAULT_PORT))
    except Exception:
        pass
    return _bsai_start_strata_inner(model_name)
# ==== BSAI LocalFix end ====
'''


def _ensure_strata_port_guard():
    mgr = os.path.join(_custom_nodes_dir(), "BSAI-LLM-Strata",
                       "Strata", "bsai_model_manager.py")
    if not os.path.isfile(mgr):
        return
    try:
        with open(mgr, encoding="utf-8") as f:
            src = f.read()
    except Exception as e:
        print(f"[BSAI LocalFix] 读取模型管理器失败: {e}")
        return
    if GUARD_MARKER in src or "def free_port(" in src:
        return                      # 已有修复，无需处理
    anchor = 'if __name__ == "__main__"'
    idx = src.rfind(anchor)
    if idx < 0:
        print("[BSAI LocalFix] 未找到注入锚点，跳过")
        return
    try:
        with open(mgr, "w", encoding="utf-8") as f:
            f.write(src[:idx] + GUARD_BLOCK + "\n\n" + src[idx:])
        print("[BSAI LocalFix] 已注入 Strata 模型管理器端口自愈补丁")
    except Exception as e:
        print(f"[BSAI LocalFix] 注入失败: {e}")


try:
    _ensure_strata_port_guard()
except Exception as e:                                    # 绝不因引导失败影响 ComfyUI 启动
    print(f"[BSAI LocalFix] 引导异常(已忽略): {e}")


# ---- BSAI LocalFix: PTD 适配器搜索目录自愈 ----
# 让 ComfyUI-PTD / ComfyUI-PTD-Compact 的 get_filename_list("ptd") 也能列出
# models/loras/H3/H3加速/PTD 下的适配器 (int8/bf16), 不必把它们塞进 models/ptd。
# 幂等, 且**不改任何插件文件** —— 因此插件 git 更新不会冲掉它。
_PTD_SUBDIRS = ("ptd", os.path.join("loras", "H3", "H3\u52a0\u901f", "PTD"))


def _ensure_ptd_search_dirs():
    try:
        import folder_paths
    except Exception:
        return
    try:
        base = getattr(folder_paths, "models_dir", None)
        if not base:
            return
        for rel in _PTD_SUBDIRS:
            p = os.path.join(base, rel)
            if not os.path.isdir(p):
                continue
            try:
                cur = folder_paths.folder_names_and_paths.get("ptd", ([], set()))[0]
            except Exception:
                cur = []
            if p not in cur:
                folder_paths.add_model_folder_path("ptd", p)
                print(f"[BSAI LocalFix] \u5df2\u6ce8\u518c PTD \u9002\u914d\u5668\u76ee\u5f55: {p}")
    except Exception as e:
        print(f"[BSAI LocalFix] PTD \u76ee\u5f55\u6ce8\u518c\u8df3\u8fc7: {e}")

try:
    _ensure_ptd_search_dirs()
except Exception as e:                                    # 绝不因引导失败影响启动
    print(f"[BSAI LocalFix] PTD 引导异常(已忽略): {e}")


# ---- BSAI LocalFix: ComfyUI 核心运行期补丁（只改内存，不动 core 文件，升级后自动重新生效）----
# 1) pinned_hostbuf_size：aimdo 的 HostBuffer 预留上限是「2×模型大小」(量化模型按量化后的实际存储算)。
#    采样时被反量化的权重会膨胀到约 2×(int8→bf16)，再叠加对齐 / bias / 补丁开销就略微越界，
#    aimdo 于是刷 "[ERROR] aimdo: src/hostbuf.c:...hostbuf_grow: requested ... beyond reserved host buffer"，
#    并逐个放弃 pin（功能不受损，走 _steal_pin 回退，但丢性能且刷屏）。
#    改为「2×模型大小 + 2GB」——该值只是 HostBuffer 的虚拟映射上限，不是立即提交的内存，
#    真实占用仍由 extend() 逐块提交、并由 TOTAL_PINNED_MEMORY / ensure_pin_budget 控制。
# 2) convert_old_quants：键带 model.diffusion_model. 前缀、带 _quantization_metadata 的老格式量化文件，
#    在 comfy/sd.py 的 load_diffusion_model_state_dict 里会被转换两次；第二次会把带前缀的 comfy_quant
#    重新塞回「已剥离前缀」的 state_dict，这些键匹配不到模块，只会被 load_model_weights 报成
#    "[WARNING] unet unexpected: [...comfy_quant]"。这里让转换幂等：已有无前缀等价键时丢掉重复键，
#    量化参数（含 convrot）仍由剥离前缀后的正确键生效，模型加载行为不变。

_PINNED_HOSTBUF_HEADROOM = 2 * 1024 ** 3
_QUANT_KEY_PREFIXES = ("model.diffusion_model.", "diffusion_model.", "model.")


def _ensure_pinned_hostbuf_headroom():
    from comfy import model_management as mm
    if getattr(mm.pinned_hostbuf_size, "_bsai_patched", False):
        return

    def _bsai_pinned_hostbuf_size(size):
        reserve = max(0, int(size) * 2 + _PINNED_HOSTBUF_HEADROOM)
        if mm.args.high_ram:
            return reserve
        return max(0, min(reserve, int(mm.MAX_PINNED_MEMORY * 2)))

    _bsai_pinned_hostbuf_size._bsai_patched = True
    mm.pinned_hostbuf_size = _bsai_pinned_hostbuf_size
    print("[BSAI LocalFix] 已接管 pinned_hostbuf_size：预留 = 2×模型 + 2GB（避免 aimdo hostbuf 溢出）")


def _ensure_convert_old_quants_dedup():
    import comfy.utils as cu
    if getattr(cu.convert_old_quants, "_bsai_dedup", False):
        return

    _orig_convert = cu.convert_old_quants

    def _bsai_convert_old_quants(state_dict, model_prefix="", metadata={}):
        sd, md = _orig_convert(state_dict, model_prefix, metadata)
        for k in [k for k in sd if k.endswith(".comfy_quant")]:
            base = k[: -len(".comfy_quant")]
            for pref in _QUANT_KEY_PREFIXES:
                if base.startswith(pref) and (base[len(pref):] + ".comfy_quant") in sd:
                    del sd[k]
                    break
        return sd, md

    _bsai_convert_old_quants._bsai_dedup = True
    cu.convert_old_quants = _bsai_convert_old_quants
    print("[BSAI LocalFix] 已接管 convert_old_quants：剥离前缀后不再重复注入带前缀的 comfy_quant")


# 3) pin_memory：aimdo 装载（main.py:319 置 aimdo_enabled=True）走 comfy/utils.py 的
#    load_safetensors → comfy_aimdo.ModelMMAP，权重是**只读文件映射**里的内存视图
#    (storage 上带 _comfy_tensor_mmap_refs / _comfy_tensor_file_slice)。
#    CUDA 无法把只读文件页锁成 pinned 内存 —— 实测 8MB 只读 mmap 的 cudaHostRegister
#    返回 rc=2 (cudaErrorMemoryAllocation)，而同一文件可写映射、匿名内存、重复注册
#    分别返回 0 / 0 / 712，说明不是页对齐、不是重复注册、不是显存不足。
#    low-vram 装载时 model_patcher.pin_weight_to_device 会对每个 offloaded 权重调用它，
#    于是每个权重刷一行 "[WARNING] Pin error."（H3 Refine 二采实测 28 条）。
#    处理：这类权重本来就无法锁页，直接跳过（行为与失败回退完全一致：不 pin），
#    不再做注定失败的 cudaHostRegister，也不再刷 warning。


def _ensure_pin_memory_mmap_guard():
    """接管 comfy.model_management.pin_memory：注册失败一律静默 + 负缓存。

    背景（本机 cudart 返回码实测）：aimdo 打开后 load_safetensors 走 ModelMMAP，
    权重是**只读**文件映射视图；对只读映射页做 cudaHostRegister 必然返回
    cudaErrorMemoryAllocation(2)。core 的 pin_memory 在 model_management.py:1697
    对每个失败张量 logging.warning("Pin error.")，于是一次加载刷出上百行。

    这里不是简单屏蔽日志，而是重写这一步：
      1) 先做与 core 完全相同的准入判断(类型/CPU/已锁/连续/大小/headroom)；
      2) 按 (data_ptr, nbytes) 缓存结果 —— 成功进白名单, 失败进负缓存,
         同一块内存第二次直接返回, 不再重复尝试注册;
      3) 已知 aimdo 只读映射(storage 带 _comfy_tensor_mmap_refs / _comfy_tensor_file_slice)
         连尝试都不做;
      4) 仍失败时调用 discard_cuda_async_error() 清掉异步错误，不打印。
    返回 False 的语义与 core 失败分支完全一致：这些权重不锁页，走普通 H2D。
    """
    from comfy import model_management as mm
    from comfy import memory_management as cmem
    import torch
    if getattr(mm.pin_memory, "_bsai_pin_guard", False):
        return

    _orig_pin_memory = mm.pin_memory
    _neg = {}      # (ptr, size) -> False  注册必然失败的内存块
    _pos = {}      # (ptr, size) -> True   已成功锁页
    _state = {"fail": 0, "skip_mmap": 0, "reported_fail": False}

    def _bsai_pin_memory(tensor, evict_active=True):
        try:
            if mm.MAX_PINNED_MEMORY <= 0:
                return False
            if type(tensor).__name__ not in mm.PINNING_ALLOWED_TYPES:
                return False
            if not mm.is_device_cpu(tensor.device):
                return False
            if tensor.is_pinned():
                return False
            if not tensor.is_contiguous():
                return False
            size = int(tensor.nbytes)
            ptr = int(tensor.data_ptr())
            if ptr == 0 or size <= 0:
                return False
            key = (ptr, size)
            if key in _pos:
                return True
            if key in _neg:
                return False
            try:
                storage = tensor.untyped_storage()
            except Exception:
                storage = None
            if storage is not None and (
                    getattr(storage, "_comfy_tensor_mmap_refs", None) is not None
                    or getattr(storage, "_comfy_tensor_file_slice", None) is not None):
                _neg[key] = False
                _state["skip_mmap"] += 1
                return False
            cmem.extra_ram_release(cmem.RAM_CACHE_HEADROOM)
            if not mm.ensure_pin_registerable(size, evict_active=evict_active):
                return False
            if torch.cuda.cudart().cudaHostRegister(ptr, size, 1) == 0:
                mm.PINNED_MEMORY[ptr] = size
                mm.TOTAL_PINNED_MEMORY += size
                _pos[key] = True
                return True
            # 注册失败(通常是只读映射锁不了页): 清异步错误, 静默, 负缓存
            mm.discard_cuda_async_error()
            _neg[key] = False
            _state["fail"] += 1
            if not _state["reported_fail"]:
                _state["reported_fail"] = True
                print("[BSAI LocalFix] pin_memory: 部分权重注册 cudaHostRegister 失败"
                      "(aimdo 只读 mmap 页锁不下来 cudaErrorMemoryAllocation), "
                      "已静默跳过并按内存块缓存结果, 不再逐条刷 Pin error", flush=True)
            return False
        except Exception:
            return False

    _bsai_pin_memory._bsai_pin_guard = True
    _bsai_pin_memory._bsai_original = _orig_pin_memory
    _bsai_pin_memory._bsai_stats = _state
    mm.pin_memory = _bsai_pin_memory
    print("[BSAI LocalFix] 已接管 pin_memory：失败静默 + 负缓存（彻底消除 Pin error 刷屏）")


def _ensure_custom_node_upstreams(root=None):
    """给缺少上游跟踪分支的自定义节点仓库补 `branch.<X>.remote/merge`。

    现象（ComfyUI-Manager 启动自检刷屏）：
        \\x1b[2K\\rFetching: <path>
        'NoneType' object has no attribute 'remote_name'
        CUSTOM NODE CHECK: Error

    根因（Manager 的 glob/manager_core.py:2061 __win_check_git_update → 子进程
    `python git_helper.py --check <path>` → git_helper.py:97）：

        remote_name = current_branch.tracking_branch().remote_name

    仓库有 origin、分支是 main，但本地没有 `branch.main.remote/merge` 配置时，
    `tracking_branch()` 返回 None，`.remote_name` 直接抛 AttributeError；异常被
    gitcheck 的 except 接住，打印异常文本后再打印 `CUSTOM NODE CHECK: Error`。
    而 manager_core 只在输出里找 `CUSTOM NODE CHECK: True/False`，找不到就打印
    `Fetch error: <path>` —— 于是一个节点三行噪音。

    这类仓库是本整合包的安装方式造成的（`git remote add origin <镜像>` + 手动
    checkout，不走 `git clone`，因此 git 不会自动配置 upstream）。

    这里在启动时按 `.git/config` 纯文本补齐（不开 git 进程、不碰 .git 之外的东西）：
      - 已有 `[branch "..."]` 段落的一律跳过（不覆盖用户/工具的既有配置）；
      - HEAD 为游标（detached）跳过；
      - 只在存在 `[remote "..."]` 时补，把当前分支的上游指向该 remote 的同名分支。
    补齐后 git_helper 能正常走到 "CUSTOM NODE CHECK: True/False"，噪音消失。
    """
    import os
    import re as _re

    root = root or os.path.join(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    if not os.path.isdir(root):
        return 0
    fixed = []
    try:
        names = sorted(os.listdir(root))
    except Exception:
        return 0
    for name in names:
        cfg_path = os.path.join(root, name, ".git", "config")
        head_path = os.path.join(root, name, ".git", "HEAD")
        if not (os.path.isfile(cfg_path) and os.path.isfile(head_path)):
            continue
        try:
            with open(cfg_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            if "[branch " in text or "[branch \"" in text:
                continue
            with open(head_path, "r", encoding="utf-8", errors="replace") as f:
                head = f.read().strip()
            m = _re.match(r"ref:\s*refs/heads/(.+)$", head)
            if not m:
                continue
            branch = m.group(1).strip()
            remotes = _re.findall(r'\[remote\s+"([^"]+)"\]', text)
            if not remotes:
                continue
            remote = "origin" if "origin" in remotes else remotes[0]
            if not text.endswith("\n"):
                text += "\n"
            text += f'[branch "{branch}"]\n\tremote = {remote}\n\tmerge = refs/heads/{branch}\n'
            with open(cfg_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            fixed.append(f"{name} -> {remote}/{branch}")
        except Exception:
            continue
    if fixed:
        print(f"[BSAI LocalFix] 已补齐 {len(fixed)} 个自定义节点仓库的上游跟踪分支"
              f"(消除 Manager 的 CUSTOM NODE CHECK: Error 刷屏): "
              f"{', '.join(fixed[:6])}{' ...' if len(fixed) > 6 else ''}", flush=True)
    return len(fixed)


def _ensure_manager_gitcheck_result(root=None):
    """给 ComfyUI-Manager 的 git_helper.py 补一个缺失的 else 分支（防 Manager 升级后复发）。

    git_helper.py::gitcheck 判断「本地是否落后远端」时：

        if commit_hash != remote_commit_hash:
            ...
            if commit_date < remote_commit_date:
                print("CUSTOM NODE CHECK: True")
        else:
            print("CUSTOM NODE CHECK: False")

    本地提交**比缓存里的 origin/main 更新**（有未推送提交）时两个分支都不命中，
    于是什么都不打印；manager_core.__win_check_git_update 找不到 True/False，
    就打印 `Fetch error: <path>` + 子进程原始输出 —— 就是日志里
    `[2KFetch error: ...` 那一串。补上 else（本地领先 = 没有可更新内容 = False）。
    """
    import os

    base = root or os.path.join(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(base, "ComfyUI-Manager", "git_helper.py")
    if not os.path.isfile(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            text = f.read()
    except Exception:
        return 0
    if "BSAI-fix:" in text:
        return 0
    old = ('            if commit_date < remote_commit_date:\n'
           '                print("CUSTOM NODE CHECK: True")\n'
           '        else:\n'
           '            print("CUSTOM NODE CHECK: False")\n')
    new = ('            if commit_date < remote_commit_date:\n'
           '                print("CUSTOM NODE CHECK: True")\n'
           '            else:\n'
           '                # BSAI-fix: 本地领先远端(有未推送提交)时原代码不输出任何标记,\n'
           '                # manager_core 找不到 True/False 就打印 "Fetch error: <path>" 刷屏。\n'
           '                # 本地领先意味着没有可更新的内容, 语义上等同 False。\n'
           '                print(f"BSAI NOTE: local ahead of {remote_name}/{branch_name}")\n'
           '                print("CUSTOM NODE CHECK: False")\n'
           '        else:\n'
           '            print("CUSTOM NODE CHECK: False")\n')
    if old not in text:
        return 0
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text.replace(old, new, 1))
    except Exception:
        return 0
    print("[BSAI LocalFix] 已修补 ComfyUI-Manager git_helper: 本地领先远端时也返回 "
          "CUSTOM NODE CHECK 结果（消除 Fetch error 刷屏）", flush=True)
    return 1


try:
    _ensure_pinned_hostbuf_headroom()
except Exception as e:                                    # 绝不因引导失败影响启动
    print(f"[BSAI LocalFix] pinned_hostbuf_size 补丁异常(已忽略): {e}")

try:
    _ensure_convert_old_quants_dedup()
except Exception as e:                                    # 绝不因引导失败影响启动
    print(f"[BSAI LocalFix] convert_old_quants 补丁异常(已忽略): {e}")

try:
    _ensure_pin_memory_mmap_guard()
except Exception as e:                                    # 绝不因引导失败影响启动
    print(f"[BSAI LocalFix] pin_memory 补丁异常(已忽略): {e}")

try:
    _ensure_custom_node_upstreams()
except Exception as e:                                    # 绝不因引导失败影响启动
    print(f"[BSAI LocalFix] 自定义节点上游补全异常(已忽略): {e}")

try:
    _ensure_manager_gitcheck_result()
except Exception as e:                                    # 绝不因引导失败影响启动
    print(f"[BSAI LocalFix] Manager gitcheck 补丁异常(已忽略): {e}")


def _ensure_manager_pip_blacklist(user_root=None):
    """把「启动会卡死的 VCS 依赖」写进 ComfyUI-Manager 的 pip 黑名单。

    现象（2026-11-17 09:38 启动实测）：
        [ComfyUI-Manager] Starting dependency installation/(de)activation for the extension
        Install: pip packages for '...\\custom_nodes\\comfyui-impact-pack'
        Collecting git+https://github.com/facebookresearch/sam2
          Installing build dependencies: still running...
        然后永远不动 —— 主程序连 8181 都不监听。

    根因：
      impact-pack 的 requirements.txt 里是**未锁提交**的
      `git+https://github.com/facebookresearch/sam2`（pip 每次启动都会重新 clone +
      重新编译，即使 sam2 已经装好）；而 SAM2 的 pyproject.toml 声明
      `build-system requires = ["setuptools>=61.0", "torch>=2.5.1"]`，
      pip 的 build isolation 会为此在临时目录里**再下载一整个 torch/torchvision**。
    实测卡死证据：pip 子进程跑 7.2 min 只有 2.1s CPU、8 秒 I/O 增量 0 字节、
    build-env 目录 0.0MB、连接挂在 CDN 443 上不动。本机 sam2 及 impact-pack
    的 10 个依赖全部已安装，这次安装是纯冗余。

    处置：在 Manager 的 `pip_blacklist.list` 里加入该行的**原样字符串**。
    Manager 的 manager_util.pip_block_reason() 对没有包名的 VCS 需求走
    「spec.strip() in blacklist」精确匹配（已用 Manager 自身代码验证返回
    'blacklisted'），所以启动时只会打印
    `skip black listed pip installation: 'git+https://...'`，不再联网。

    写盘位置按 Manager 自己的判定逻辑（prestartup_script.py:92-95）：
      有 system user API → <user>/__manager ；否则 <user>/default/ComfyUI-Manager。
    这里用目录是否存在来判定，两条路径都探测，命中的那个写入；都不存在则按
    新版布局创建 <user>/__manager。
    """
    import os

    entries = ("git+https://github.com/facebookresearch/sam2",)

    def _user_dir():
        if user_root:
            return user_root
        try:
            import folder_paths as _fp
            if hasattr(_fp, "get_user_directory"):
                return _fp.get_user_directory()
        except Exception:
            pass
        # 兜底：本文件位于 <ComfyUI>/custom_nodes/_BSAI_LocalFix/__init__.py
        comfy_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        return os.path.join(comfy_root, "user")

    base_user = _user_dir()
    if not base_user or not os.path.isdir(base_user):
        return 0

    candidates = [os.path.join(base_user, "__manager"),
                  os.path.join(base_user, "default", "ComfyUI-Manager")]
    target_dir = None
    for cand in candidates:
        if os.path.isdir(cand):
            target_dir = cand
            break
    if target_dir is None:
        target_dir = candidates[0]

    path = os.path.join(target_dir, "pip_blacklist.list")
    existing = []
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                existing = [ln.strip() for ln in f.read().splitlines() if ln.strip()]
        except Exception:
            return 0
    missing = [e for e in entries if e not in existing]
    if not missing:
        return 0
    try:
        os.makedirs(target_dir, exist_ok=True)
        body = "\n".join(existing + missing) + "\n"
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
    except Exception as e:
        print(f"[BSAI LocalFix] pip 黑名单写入失败(已忽略): {e}")
        return 0
    print(f"[BSAI LocalFix] 已写入 Manager pip 黑名单 ({len(missing)} 条) -> {path}: "
          f"跳过会卡死启动的 VCS 依赖安装 "
          f"(pip build isolation 会为它重复下载整个 torch)", flush=True)
    return len(missing)


try:
    _ensure_manager_pip_blacklist()
except Exception as e:                                    # 绝不因引导失败影响启动
    print(f"[BSAI LocalFix] Manager pip 黑名单补丁异常(已忽略): {e}")
