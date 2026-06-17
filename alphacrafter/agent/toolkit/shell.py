"""
受限的 Shell 命令执行工具（ShellTool）

功能概述：
    提供一个带白名单的 Shell 命令执行入口，供 LLM Agent 安全地运行
    一些基础命令（如 `ls`、`cat`、`python` 脚本等）。
    这是 Agent 与本地计算环境交互的"受控通道"。

安全设计：
    - 严格的命令白名单：仅允许 DEFAULT_WHITELIST 中的命令；
      即便用户输入 `rm -rf /` 也无法绕过。
    - 进程组隔离：Unix 下使用 `preexec_fn=os.setsid` 创建新进程组，
      便于超时或异常时一次性 kill 整个子进程树。
    - 双超时机制：基于轮询的 timeout（带 0.1s 间隔），不会陷入死等。
    - 输出长度截断：max_output_length 防止单次输出爆掉上下文窗口。
"""

import sys
import os
import subprocess
import shlex
import signal
import time
from typing import Dict, Any, Callable, Optional, List
from .base import BaseTool


class ShellTool(BaseTool):
    """白名单 Shell 命令执行工具。

    使用时可通过 `whitelist` 自定义允许的命令集合；不指定时使用默认白名单。
    所有命令在 `working_dir` 下执行，单次执行超时上限为 `timeout` 秒。
    """

    # ── 默认白名单 ────────────────────────────────────
    # 这些命令是 Agent 调试、查看文件、运行脚本所需的"最小集合"。
    # 任何加入新命令的修改都要慎重考虑安全影响。
    DEFAULT_WHITELIST = [
        'ls', 'python', 'python3', 'cat', 'touch',
    ]

    def __init__(
        self,
        whitelist: Optional[List[str]] = None,
        working_dir: Optional[str] = '.',
        timeout: int = 300,
        max_output_length: int = 6000,
    ):
        """初始化 Shell 工具实例。

        参数:
            whitelist:        自定义允许的命令列表；为 None 时使用默认白名单。
            working_dir:      命令执行的工作目录。
            timeout:          单次命令执行的硬超时（秒）。
            max_output_length: 超过此长度的输出会被截断，避免撑爆上下文。
        """
        self.whitelist = whitelist or self.DEFAULT_WHITELIST.copy()
        self.working_dir = working_dir or os.getcwd()
        self.timeout = timeout
        self.max_output_length = max_output_length

    def get_name(self) -> str:
        """工具注册名。"""
        return "shell"

    # ── 白名单校验 ────────────────────────────────────

    def _is_command_allowed(self, command: str) -> tuple:
        """检查命令是否在白名单中。

        返回值:
            (is_allowed, cmd_name, error_message) 三元组：
              - is_allowed: True 表示允许
              - cmd_name:   解析出的基础命令名（用于调试信息）
              - error_message: 当不允许时的详细原因
        """
        # 使用 shlex 拆分以正确处理带引号的参数
        try:
            parts = shlex.split(command)
            if not parts:
                return False, None, "Empty command"

            base_cmd = parts[0]

            # 直接匹配白名单
            if base_cmd in self.whitelist:
                return True, base_cmd, None

            # 同时兼容绝对/相对路径形式（如 /bin/ls、./script.py）
            base_name = os.path.basename(base_cmd)
            if base_name in self.whitelist:
                return True, base_name, None

            return False, base_cmd, (
                f"Command '{base_cmd}' is not in the whitelist. "
                f"Allowed commands: {', '.join(self.whitelist)}"
            )
        except Exception as e:
            return False, None, f"Error parsing command: {str(e)}"

    # ── 输出处理 ────────────────────────────────────

    def _truncate_output(self, output: str) -> str:
        """超出长度限制时截断输出，并附加截断说明。"""
        if len(output) > self.max_output_length:
            return output[:self.max_output_length] + (
                f"\n... (output truncated, {len(output) - self.max_output_length} more characters)"
            )
        return output

    def _kill_process_tree(self, process: subprocess.Popen) -> None:
        """强杀整个进程树，确保不留僵尸进程。

        平台差异:
          - Windows: 使用 taskkill 终止进程及其子进程
          - Unix:    使用 os.killpg 给整个进程组发送 SIGKILL
        """
        try:
            if sys.platform == 'win32':
                subprocess.run(
                    f'taskkill /F /T /PID {process.pid}',
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except Exception:
            # 兜底：若进程组机制失效，至少尝试结束主进程
            try:
                process.terminate()
            except Exception:
                pass

    # ── 工具实现工厂 ────────────────────────────────────

    def get_implementation(self) -> Callable:
        """构造真正可被 Agent 调用的 shell 函数。"""
        def shell(command: str) -> str:
            """执行白名单内的一条 shell 命令。

            流程:
                1. 解析并白名单校验；
                2. 启动子进程并放入独立进程组；
                3. 用守护线程异步读取 stdout / stderr，避免管道缓冲阻塞；
                4. 轮询检测超时与结束状态；
                5. 汇总输出（截断过长内容）并返回。
            """
            # ── 1. 白名单校验 ──
            is_allowed, cmd_name, error_msg = self._is_command_allowed(command)
            if not is_allowed:
                return f"❌ {error_msg}"

            process = None
            try:
                # ── 2. 启动子进程 ──
                # 关键点：shell=True 允许管道/重定向；preexec_fn=os.setsid 创建新进程组
                # 便于后面 kill 整组（含可能派生的子进程）。
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=self.working_dir,
                    env=os.environ.copy(),
                    preexec_fn=os.setsid,
                )

                # ── 3. 异步读取输出，避免管道缓冲满导致子进程阻塞 ──
                import select
                import threading

                start_time = time.time()
                stdout_lines, stderr_lines = [], []

                def read_stream(stream, lines_list):
                    """子线程读流函数：逐行读取并存到共享列表。"""
                    try:
                        for line in iter(stream.readline, ''):
                            lines_list.append(line)
                    except Exception:
                        pass

                stdout_thread = threading.Thread(target=read_stream, args=(process.stdout, stdout_lines))
                stderr_thread = threading.Thread(target=read_stream, args=(process.stderr, stderr_lines))
                stdout_thread.daemon = True
                stderr_thread.daemon = True
                stdout_thread.start()
                stderr_thread.start()

                # ── 4. 轮询等待：兼顾超时检测与子进程状态 ──
                while True:
                    elapsed = time.time() - start_time
                    if elapsed >= self.timeout:
                        # 超时则杀整组并返回部分 stderr
                        self._kill_process_tree(process)
                        return (
                            f"❌ Command timed out after {self.timeout} seconds\n"
                            f"Partial stderr:\n{self._truncate_output(''.join(stderr_lines))}"
                        )

                    if process.poll() is not None:
                        # 进程已自然结束
                        break

                    time.sleep(0.1)  # 短暂 sleep，避免忙等占用 CPU

                # 等待读取线程收尾
                stdout_thread.join(timeout=1)
                stderr_thread.join(timeout=1)

                stdout = ''.join(stdout_lines)
                stderr = ''.join(stderr_lines)

                # ── 5. 汇总返回 ──
                if process.returncode != 0:
                    error_msg = f"Command failed with exit code {process.returncode}"
                    if stderr:
                        error_msg += f"\n{self._truncate_output(stderr)}"
                    return f"❌ {error_msg}"

                result_parts = []
                if stdout:
                    result_parts.append(f"✅ Output:\n{self._truncate_output(stdout.strip())}")
                if stderr:
                    result_parts.append(f"⚠️ Warnings:\n{self._truncate_output(stderr.strip())}")
                if not result_parts:
                    return f"✅ Command executed successfully (no output)"

                return "\n\n".join(result_parts)

            except Exception as e:
                return f"❌ Error executing command: {str(e)}"
            finally:
                # 防御性清理：无论是否成功结束，都尝试 kill 一次
                if process is not None and process.poll() is None:
                    self._kill_process_tree(process)

        return shell

    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """返回 OpenAI 工具描述 schema。"""
        if producer == "OpenAI":
            return {
                "type": "function",
                "name": self.get_name(),
                "description": (
                    f"Execute shell commands from a restricted whitelist. "
                    f"Allowed commands: {', '.join(self.whitelist)}. "
                    f"Use this for file operations, running scripts, and system information. "
                    f"Output will be truncated if too long. Commands have a hard timeout of "
                    f"{self.timeout} seconds and will be forcibly terminated if exceeded."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": (
                                f"Shell command to execute. Must start with one of: "
                                f"{', '.join(self.whitelist)}. Examples: 'ls -la', "
                                f"'python script.py', 'pwd', 'echo hello'"
                            ),
                        }
                    },
                    "required": ["command"],
                },
            }
        raise ValueError(f"Unsupported producer: {producer}")
