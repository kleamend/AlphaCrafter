"""
Chat Completions 版 Agent（chat_agent.py）

功能概述：
    面向 OpenAI Chat Completions API（含 OpenAI 兼容端点，如 MiniMax-M3）设计的 Agent。
    支持：
      - 原生工具调用（tools / tool_choice）
      - 多轮 tool 循环（agentic loop）
      - 中断处理（Ctrl-C 优雅退出）
      - 周期性记忆摘要（避免上下文爆掉）
      - 详细日志（JSON 数组追加写）
      - MiniMax 特有参数透传（thinking 开关等）

适用场景：
    - OpenAI Chat Completions 兼容端点（OpenAI 自身、MiniMax-M3、其他第三方）
    - 与 agent.py（Responses API）/ general_agent.py（XML 工具调用）并列

与 agent.py 的关键差异：
    - 调用 self.client.chat.completions.create（而非 responses.create）
    - 工具调用走 OpenAI 原生 tool_calls 协议
    - 工具响应以 role=tool 消息回填（而非 function_call_output 块）
    - assistant 消息需保留完整 tool_calls 结构以维持多轮链路

数据流（单次 run）：
    ┌────────────┐  调用   ┌─────────────────┐
    │ Launcher   │ ─────→ │ ChatAgent.run   │
    └────────────┘         └──────┬──────────┘
                                 │
                ┌────────────────┴────────────────┐
                ▼                                 ▼
        ┌──────────────┐                  ┌──────────────┐
        │ Chat         │  tool_calls      │  Tool 实现    │
        │ Completions  │ ◀──────────────→ │              │
        │ API          │                  │              │
        └──────────────┘                  └──────────────┘
                │                                 │
                └────── role=tool 反馈 ──────────┘
"""

import os
import sys
import json
import signal
import contextlib
from datetime import datetime
from pathlib import Path
from openai import OpenAI
from typing import List, Dict, Any, Optional, Callable

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from ..toolkit.base import BaseTool
from ..skills.base import BaseSkill


# ════════════════════════════════════════════════════════════════════════════════
#   中断处理
# ════════════════════════════════════════════════════════════════════════════════

class InterruptHandler:
    """上下文管理器形式的 SIGINT 中断处理。"""

    def __init__(self):
        self.interrupted = False
        self.original_handler = None

    def __enter__(self):
        self.original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._handler)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        signal.signal(signal.SIGINT, self.original_handler)
        if exc_type is KeyboardInterrupt:
            return True
        return False

    def _handler(self, sig, frame):
        self.interrupted = True
        print("\n\n⚠️  Interrupt received, stopping gracefully...")


# ════════════════════════════════════════════════════════════════════════════════
#   ChatAgent 主类
# ════════════════════════════════════════════════════════════════════════════════

class ChatAgent:
    """基于 OpenAI Chat Completions API 的 Agent（支持原生 tool calling）。"""

    def __init__(
        self,
        model_code: str,
        toolkit: List[BaseTool],
        skills: List[BaseSkill] = None,
        instructions: str = "",
        config_path: str = "../config/models.json",
        log_file: str = "../logs/chat_agent.json",
        summary_interval: int = 20,
        force_tool_call: bool = False,
    ):
        """初始化 ChatAgent。

        参数:
            model_code:       模型标识（如 "MiniMax-M3"）。
            toolkit:          工具列表（BaseTool 子类）。
            skills:           技能列表（BaseSkill 子类）。
            instructions:     system prompt 模板（含 {skills} 占位符）。
            config_path:      模型配置文件路径。
            log_file:         日志文件路径。
            summary_interval: 每隔多少轮迭代做一次记忆摘要。
            force_tool_call:  是否在每轮都强制调用工具。
        """
        self.model_code = model_code
        self.toolkit = toolkit
        self.skills = skills or []
        self.instructions_template = instructions
        self.config_path = config_path
        self.log_file = log_file
        self.summary_interval = summary_interval
        self.force_tool_call = force_tool_call

        # 加载模型配置 & 拿到 producer
        self.model_config = self._load_model_config()
        self.producer = self.model_config.get("producer", "OpenAI")

        # 初始化 OpenAI 客户端（长超时便于处理多步推理）
        # Chat Completions 是 OpenAI SDK 的标准入口，base_url 可指向任意 OpenAI 兼容端点
        # （如 https://api.minimaxi.com/v1）
        self.client = OpenAI(
            api_key=os.getenv("API_KEY"),
            base_url=os.getenv("API_URL"),
            timeout=1800,
        )

        # 把工具的描述与实现解耦注册
        self.tools = [tool.get_description(producer=self.producer) for tool in toolkit]
        self.function_map = {tool.get_name(): tool.get_implementation() for tool in toolkit}

        # 把 skills 与系统指令合并为最终 system prompt
        self.instructions = self._build_instructions()

        print(f"✅ ChatAgent initialized with model: {model_code} (producer={self.producer})")
        print(f"📦 Loaded tools: {list(self.function_map.keys())}")
        print(f"📚 Loaded skills: {[skill.get_name() for skill in self.skills]}")
        print(f"⚙️ Summary interval: {summary_interval} iterations")
        print(f"⚙️ Force tool call: {force_tool_call}")

        self._append_log({
            "event": "agent_init",
            "model": model_code,
            "producer": self.producer,
            "tools": list(self.function_map.keys()),
            "skills": [skill.get_name() for skill in self.skills],
            "instructions_length": len(self.instructions),
            "summary_interval": summary_interval,
            "force_tool_call": force_tool_call,
            "timestamp": datetime.now().isoformat(),
        })

    # ── 日志辅助 ────────────────────────────────────

    def _load_existing_logs(self) -> List[Dict[str, Any]]:
        """从日志文件加载已有记录（保持 JSON 数组结构）。"""
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
                    print(f"⚠️ Warning: {self.log_file} does not contain a list, starting fresh")
                    return []
            except (json.JSONDecodeError, IOError) as e:
                print(f"⚠️ Warning: Could not read existing log file: {e}, starting fresh")
                return []
        return []

    def _append_log(self, entry: Dict[str, Any]):
        """追加一条日志（保持 JSON 数组结构 + 自动创建目录）。"""
        existing_logs = self._load_existing_logs()
        existing_logs.append(entry)
        log_dir = Path(self.log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(existing_logs, f, indent=2, ensure_ascii=False, default=str)

    # ── 指令构建 ────────────────────────────────────

    def _build_instructions(self) -> str:
        """把 skills 信息注入到 system prompt 模板。

        模板使用 `{skills}` 占位符；若不存在则退化为追加。
        """
        if not self.instructions_template:
            return ""

        if self.skills:
            skills_text = "\n\nAvailable Skills:\n"
            for skill in self.skills:
                skills_text += f"Name: {skill.get_name()}\n"
                skills_text += f"Description: {skill.get_description()}\n"
                skills_text += f"Details: {skill.get_details()}\n"
        else:
            skills_text = "\n\nNo skills available."

        try:
            return self.instructions_template.format(skills=skills_text)
        except KeyError:
            return self.instructions_template + skills_text

    # ── 配置 & 成本 ────────────────────────────────────

    def _load_model_config(self) -> Dict[str, Any]:
        """从 JSON 加载模型配置。"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                all_configs = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"❌ Model config file not found: {self.config_path}")
        except json.JSONDecodeError:
            raise ValueError(f"❌ Invalid JSON format in config file: {self.config_path}")

        if self.model_code not in all_configs:
            available = list(all_configs.keys())
            raise ValueError(
                f"❌ Model '{self.model_code}' not found in config. "
                f"Available models: {available}"
            )
        return all_configs[self.model_code]

    def _calculate_costs(self, input_tokens: int, output_tokens: int) -> Dict[str, float]:
        """根据模型配置计算 token 费用（按百万 token 单价）。"""
        cost_per_million_input = self.model_config.get("cost", {}).get("input", 0)
        cost_per_million_output = self.model_config.get("cost", {}).get("output", 0)
        input_cost = input_tokens * cost_per_million_input / 1_000_000
        output_cost = output_tokens * cost_per_million_output / 1_000_000
        return {
            "input_cost": round(input_cost, 8),
            "output_cost": round(output_cost, 8),
            "total_cost": round(input_cost + output_cost, 8),
        }

    def _log_metadata(self, result: Dict[str, Any], iteration: int):
        """记录一次迭代的元数据到日志。"""
        metadata = {
            "event": "iteration_complete",
            "timestamp": datetime.now().isoformat(),
            "iteration": iteration,
            "model": self.model_code,
            "output_text": result.get("output_text", ""),
            "input_tokens": result.get("input_tokens", 0),
            "output_tokens": result.get("output_tokens", 0),
            "total_cost": result.get("total_cost", 0),
            "tool_calls": [
                {
                    "name": tc["name"],
                    "arguments": tc["arguments"],
                    "call_id": tc["call_id"],
                } for tc in result.get("tool_calls", [])
            ],
            "interrupted": result.get("interrupted", False),
        }
        self._append_log(metadata)

    # ── 记忆摘要 ────────────────────────────────────

    def _summarize(self, current_messages: List[Dict[str, Any]]):
        """对当前 messages 做一次摘要，避免上下文无限增长。

        返回值:
            (summary_text, cost_info)
        """
        try:
            MEMORY_INSTRUCTION = """You are a helpful assistant that produces step summaries.
Keep the summary concise, but explicitly include:
- Key historical information that informs current decisions
- Critical context that would otherwise be lost in a brief recap
- The logical flow of recent actions and tool calls"""

            response = self.client.chat.completions.create(
                model=self.model_code,
                messages=[
                    {"role": "system", "content": MEMORY_INSTRUCTION},
                    {
                        "role": "user",
                        "content": (
                            "Please summarize the following conversation:\n\n"
                            f"{json.dumps(current_messages, default=str)}"
                        ),
                    },
                ],
            )

            usage = getattr(response, "usage", None)
            input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
            output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
            costs = self._calculate_costs(input_tokens, output_tokens)

            summary_text = response.choices[0].message.content or ""
            self._append_log({
                "event": "memory_summary",
                "timestamp": datetime.now().isoformat(),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "input_cost": costs["input_cost"],
                "output_cost": costs["output_cost"],
                "total_cost": costs["total_cost"],
                "summary_length": len(summary_text),
            })
            print(f"📝 Memory summary generated - {output_tokens} tokens, ${costs['total_cost']:.6f}")
            return summary_text, costs

        except Exception as e:
            print(f"Failed to generate summary: {e}")
            return "Step completed.", {"input_cost": 0, "output_cost": 0, "total_cost": 0}

    # ── 单次模型调用 ────────────────────────────────────

    def get_response(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """调用 Chat Completions API 并解析 tool_calls。

        返回值:
            output_text / input_tokens / output_tokens / total_cost / tool_calls / finish_reason
        """
        print(f"📤 API Request - {len(messages)} messages")

        tool_choice = "required" if self.force_tool_call else "auto"

        # 准备 API 调用参数
        create_kwargs: Dict[str, Any] = {
            "model": self.model_code,
            "messages": messages,
        }
        if self.tools:
            create_kwargs["tools"] = self.tools
            create_kwargs["tool_choice"] = tool_choice

        # MiniMax-M3 等 OpenAI 兼容端点经常带有 "thinking" 等私有参数；
        # OpenAI Python SDK 的 extra_body 会透传到 JSON body，不会破坏其它字段。
        extra_body: Dict[str, Any] = {}
        if self.producer == "MiniMax":
            # M3 默认开 adaptive thinking；Agent 场景下关闭可节省 token、加快 tool 循环
            extra_body["thinking"] = {"type": "disabled"}
        if extra_body:
            create_kwargs["extra_body"] = extra_body

        response = self.client.chat.completions.create(**create_kwargs)

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        costs = self._calculate_costs(input_tokens, output_tokens)

        choice = response.choices[0]
        message = choice.message
        output_text = message.content or ""
        finish_reason = choice.finish_reason

        # 解析 OpenAI 原生 tool_calls
        tool_calls: List[Dict[str, Any]] = []
        raw_tool_calls = getattr(message, "tool_calls", None) or []
        for tc in raw_tool_calls:
            try:
                arguments = (
                    json.loads(tc.function.arguments)
                    if tc.function.arguments else {}
                )
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append({
                "name": tc.function.name,
                "arguments": arguments,
                "call_id": tc.id,
            })

        result = {
            "messages": messages,
            "output_text": output_text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_cost": costs["total_cost"],
            "tool_calls": tool_calls,
            "finish_reason": finish_reason,
            "interrupted": False,
        }

        print(f"📥 API Response - {output_tokens} tokens, ${costs['total_cost']:.6f}")
        if tool_calls:
            print(f"🔧 Tool calls: {[tc['name'] for tc in tool_calls]}")
        return result

    # ── assistant 消息回填（多轮 tool 链路） ─────────────────────────

    def _build_assistant_message_for_history(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """从 result 构造一条 OpenAI 风格的 assistant 消息以回填历史。

        必须保留完整 tool_calls 结构（id / type / function.name / function.arguments），
        否则下一轮的 tool result 无法与对应的 call 对应。
        """
        msg: Dict[str, Any] = {
            "role": "assistant",
            "content": result.get("output_text") or "",
        }
        if result.get("tool_calls"):
            msg["tool_calls"] = [
                {
                    "id": tc["call_id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                    },
                }
                for tc in result["tool_calls"]
            ]
        return msg

    # ── 运行上下文（run 维度的日志） ─────────────────────────

    @contextlib.contextmanager
    def _run_context(self):
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        start_time = datetime.now()
        self._append_log({
            "event": "run_start",
            "run_id": run_id,
            "timestamp": start_time.isoformat(),
            "model": self.model_code,
        })
        try:
            yield run_id
        finally:
            duration = (datetime.now() - start_time).total_seconds()
            self._append_log({
                "event": "run_end",
                "run_id": run_id,
                "duration_seconds": round(duration, 2),
                "timestamp": datetime.now().isoformat(),
            })

    # ════════════════════════════════════════════════════════════════════════════════
    #   主循环
    # ════════════════════════════════════════════════════════════════════════════════

    def run(
        self,
        initial_messages: List[Dict[str, Any]],
        max_iterations: int = 100,
        finish_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """运行多轮 tool-calling 循环。

        每轮:
          1. 调 get_response()
          2. 若有 tool_call，把 assistant 消息（含 tool_calls 字段）入栈；
             再依次执行并把每条 tool result（role=tool）追加
          3. 达到 summary_interval 时做一次记忆摘要（追加 system 消息）
          4. 若 finish_check() 返回 True 或被中断则结束

        返回值:
            {
                "success": bool,
                "input":  最后一轮 messages,
                "output_text": 最后一轮模型输出,
                "interrupted": bool,
            }
        """
        with InterruptHandler() as handler, self._run_context():
            current_messages = list(initial_messages)
            iteration = 0
            total_cost = 0.0
            all_tool_calls: List[Dict[str, Any]] = []
            last_result: Optional[Dict[str, Any]] = None
            tools_used: set = set()

            print("=" * 60)
            print("🚀 CHAT AGENT RUN STARTED")
            print("=" * 60)

            while iteration < max_iterations and not handler.interrupted:
                iteration += 1
                print(f"\n{'─' * 40}")
                print(f"🔄 Iteration {iteration}/{max_iterations}")
                print(f"{'─' * 40}")

                result = self.get_response(current_messages)
                result["interrupted"] = handler.interrupted
                last_result = result
                self._log_metadata(result, iteration)
                total_cost += result["total_cost"]
                all_tool_calls.extend(result["tool_calls"])

                if finish_check and finish_check():
                    print("✅ Finish condition met")
                    break
                if not result["tool_calls"] or handler.interrupted:
                    if handler.interrupted:
                        print("⏹️ Run interrupted by user")
                    else:
                        print("✅ No more tool calls required - ending run")
                    break

                print(f"⚙️ Executing {len(result['tool_calls'])} tool call(s)...")

                # 把 assistant 消息（含 tool_calls）入栈
                current_messages.append(self._build_assistant_message_for_history(result))

                # 逐个执行 tool_call 并回填 role=tool 消息
                for tool_call in result["tool_calls"]:
                    if handler.interrupted:
                        print("⏹️ Interrupted during tool execution")
                        break

                    func_name = tool_call["name"]
                    arguments = tool_call["arguments"]
                    call_id = tool_call["call_id"]
                    print(f"  ▶️ {func_name}({json.dumps(arguments, ensure_ascii=False)})")

                    if func_name not in self.function_map:
                        error_msg = f"Unknown tool function: {func_name}"
                        print(f"  ❌ {error_msg}")
                        self._append_log({
                            "event": "tool_error",
                            "timestamp": datetime.now().isoformat(),
                            "iteration": iteration,
                            "tool": func_name,
                            "error": error_msg,
                        })
                        raise ValueError(error_msg)

                    func = self.function_map[func_name]
                    try:
                        output = func(**arguments)
                        output_str = (
                            json.dumps(output, ensure_ascii=False, default=str)
                            if not isinstance(output, str) else output
                        )
                        truncated = "...[truncated]" if len(output_str) > 1000 else ""
                        print(f"  ✅ {func_name} output: {output_str[:1000]}{truncated}")
                    except Exception as e:
                        output_str = f"Tool execution error: {str(e)}"
                        print(f"  ❌ {func_name} failed: {e}")
                        self._append_log({
                            "event": "tool_error",
                            "timestamp": datetime.now().isoformat(),
                            "iteration": iteration,
                            "tool": func_name,
                            "error": str(e),
                        })

                    # 回填 role=tool 消息
                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": output_str,
                    })

                # 周期性记忆摘要（追加 system 消息，保留历史）
                if iteration % self.summary_interval == 0:
                    print(f"📝 Reached {iteration} iterations, generating summary...")
                    summary, memory_costs = self._summarize(current_messages)
                    total_cost += memory_costs["total_cost"]
                    self._append_log({
                        "event": "interval_summary",
                        "timestamp": datetime.now().isoformat(),
                        "iteration": iteration,
                        "summary": summary,
                        "interval": self.summary_interval,
                        "tools_executed_in_interval": [tc["name"] for tc in result["tool_calls"]],
                    })
                    current_messages.append({
                        "role": "system",
                        "content": (
                            f"Progress summary after {iteration} iterations: {summary}\n\n"
                            "Continue with the task."
                        ),
                    })
                    truncated = "...[truncated]" if len(summary) > 1000 else ""
                    print(f"📋 Interval summary: {summary[:1000]}{truncated}")

            if iteration >= max_iterations and not handler.interrupted:
                print(f"⚠️ Max iterations ({max_iterations}) reached")

            print("\n" + "=" * 60)
            print("📊 RUN SUMMARY")
            print("=" * 60)
            print(f"Iterations: {iteration}")
            print(f"Total cost: ${total_cost:.6f}")
            print(f"Total tool calls: {len(all_tool_calls)}")
            if all_tool_calls:
                tools_used = set(tc['name'] for tc in all_tool_calls)
                print(f"Tools used: {tools_used}")
            print("=" * 60)

            final_state = {
                "success": last_result is not None,
                "input": current_messages,
                "output_text": last_result.get("output_text") if last_result else None,
                "interrupted": handler.interrupted,
            }
            self._append_log({
                "event": "run_complete",
                "timestamp": datetime.now().isoformat(),
                "total_iterations": iteration,
                "total_cost": total_cost,
                "total_tool_calls": len(all_tool_calls),
                "tools_used": list(tools_used) if all_tool_calls else [],
                "final_state": final_state,
            })
            print(f"🚀 ChatAgent run completed.")
            return final_state
