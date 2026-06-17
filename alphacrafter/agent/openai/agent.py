"""
OpenAI Responses API 版 Agent（agent.py）

功能概述：
    面向 OpenAI Responses API 设计的 Agent。
    支持：
      - 工具调用（tools / tool_choice）
      - 多轮 tool 循环（agentic loop）
      - 中断处理（Ctrl-C 优雅退出）
      - 周期性记忆摘要（避免上下文爆掉）
      - 详细日志（JSON 数组追加写）

数据流（单次 run）：
    ┌────────────┐  调用   ┌────────────┐
    │ Launcher   │ ─────→ │ Agent.run  │
    └────────────┘         └──────┬─────┘
                                 │
                ┌────────────────┴─────────────────┐
                ▼                                  ▼
        ┌────────────┐                       ┌────────────┐
        │ Responses  │  function_call       │  Tool 实   │
        │ API        │ ◀──────────────────→ │  现        │
        └────────────┘                       └────────────┘
                │                                  │
                └─── function_call_output ────────┘
"""

import os
import sys
import json
import signal
import contextlib
from datetime import datetime
from openai import OpenAI
from typing import List, Dict, Any, Optional, Callable, Union, Tuple
from pathlib import Path

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from ..toolkit.base import BaseTool
from ..skills.base import BaseSkill


# ════════════════════════════════════════════════════════════════════════════════
#   中断处理
# ════════════════════════════════════════════════════════════════════════════════

class InterruptHandler:
    """用上下文管理器的方式把 SIGINT 处理替换成"标记中断"。

    进入 with 时注册自定义 handler；退出时恢复原 handler。
    任何一轮迭代都可以通过 `self.interrupted` 检查是否要中止。
    """

    def __init__(self):
        self.interrupted = False
        self.original_handler = None

    def __enter__(self):
        # 保存原 handler 并替换为自定义 _handler
        self.original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._handler)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # 退出时恢复原 handler，吞掉 KeyboardInterrupt 以便优雅退出
        signal.signal(signal.SIGINT, self.original_handler)
        if exc_type is KeyboardInterrupt:
            return True
        return False

    def _handler(self, sig, frame):
        self.interrupted = True
        print("\n\n⚠️  Interrupt received, stopping gracefully...")


# ════════════════════════════════════════════════════════════════════════════════
#   Agent 主类
# ════════════════════════════════════════════════════════════════════════════════

class Agent:
    """OpenAI Responses API 版本的 Agent。"""

    def __init__(
        self,
        model_code: str,
        toolkit: List[BaseTool],
        skills: List[BaseSkill] = None,
        instructions: str = "",
        config_path: str = "../config/models.json",
        log_file: str = "../logs/agent.json",
        summary_interval: int = 20,
        force_tool_call: bool = False,
    ):
        """初始化 Agent。

        参数:
            model_code:       模型标识（如 "gpt-5"）。
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
        self.client = OpenAI(
            api_key=os.getenv("API_KEY"),
            base_url=os.getenv("API_URL"),
            timeout=1800,
        )

        # 把工具的描述与实现解耦注册
        self.tools = [tool.get_description(producer=self.producer) for tool in toolkit]
        self.function_map = {tool.get_name(): tool.get_implementation() for tool in toolkit}

        # 把 skills 注入到 system prompt
        self.instructions = self._build_instructions()

        print(f"✅ Agent initialized with model: {model_code}")
        print(f"📦 Loaded tools: {list(self.function_map.keys())}")
        print(f"📚 Loaded skills: {[skill.get_name() for skill in self.skills]}")
        print(f"⚙️ Summary interval: {summary_interval} iterations")
        print(f"⚙️ Force tool call: {force_tool_call}")

        # 记录 agent_init 事件到日志
        self._append_log({
            "event": "agent_init",
            "model": model_code,
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
                    else:
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
            instructions = self.instructions_template.format(skills=skills_text)
        except KeyError:
            # 模板里没有 {skills} 占位符，改为追加
            instructions = self.instructions_template + skills_text

        return instructions

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
            "output": result.get("output", []),
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

    def _summarize(self, current_input: List[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
        """调用模型对当前上下文做一次摘要（控制上下文长度）。

        返回值:
            (summary_text, cost_info)
        """
        try:
            MEMORY_INSTRUCTION = """You are a helpful assistant that produces step summaries.
    Keep the summary concise, but explicitly include:
    - Key historical information that informs current decisions
    - Critical context that would otherwise be lost in a brief recap
    - The logical flow of recent actions and tool calls"""

            response = self.client.responses.create(
                model=self.model_code,
                input=current_input,
                instructions=MEMORY_INSTRUCTION,
            )

            usage = getattr(response, "usage", {})
            input_tokens = getattr(usage, "input_tokens", 0)
            output_tokens = getattr(usage, "output_tokens", 0)
            costs = self._calculate_costs(input_tokens, output_tokens)

            self._append_log({
                "event": "memory_summary",
                "timestamp": datetime.now().isoformat(),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "input_cost": costs["input_cost"],
                "output_cost": costs["output_cost"],
                "total_cost": costs["total_cost"],
                "summary_length": len(response.output_text),
            })

            print(f"📝 Memory summary generated - {output_tokens} tokens, ${costs['total_cost']:.6f}")
            return response.output_text, costs

        except Exception as e:
            print(f"Failed to generate summary: {e}")
            return "Step completed.", {"input_cost": 0, "output_cost": 0, "total_cost": 0}

    # ── 单次模型调用 ────────────────────────────────────

    def get_response(self, input: List[Dict[str, Any]]) -> Dict[str, Any]:
        """调用 OpenAI Responses API，返回结构化结果。

        返回值字段:
            input/output/output_text/input_tokens/output_tokens/total_cost/tool_calls/interrupted
        """
        print(f"📤 API Request - {len(input)} messages")

        # force_tool_call 时使用 required，否则让模型自选
        tool_choice = "required" if self.force_tool_call else "auto"

        response = self.client.responses.create(
            model=self.model_code,
            tools=self.tools,
            input=input,
            instructions=self.instructions,
            parallel_tool_calls=False,
            tool_choice=tool_choice,
        )

        usage = getattr(response, "usage", {})
        input_tokens = getattr(usage, "input_tokens", 0)
        output_tokens = getattr(usage, "output_tokens", 0)
        costs = self._calculate_costs(input_tokens, output_tokens)

        # 解析 function_call
        tool_calls = []
        for item in response.output:
            if item.type == "function_call":
                tool_calls.append({
                    "name": item.name,
                    "arguments": json.loads(item.arguments) if item.arguments else {},
                    "call_id": item.call_id,
                })

        result = {
            "input": input,
            "output": response.output,
            "output_text": response.output_text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_cost": costs["total_cost"],
            "tool_calls": tool_calls,
            "interrupted": False,
        }

        print(f"📥 API Response - {output_tokens} tokens, ${costs['total_cost']:.6f}")
        if tool_calls:
            print(f"🔧 Tool calls: {[tc['name'] for tc in tool_calls]}")
        return result

    # ── 运行上下文（用于 log run_start / run_end） ─────────────────────────

    @contextlib.contextmanager
    def _run_context(self):
        """run 维度的日志上下文管理器。"""
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
        initial_input: List[Dict[str, Any]],
        max_iterations: int = 100,
        finish_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """运行 Agent 的多轮 tool-calling 循环。

        每轮:
          1. 调 get_response()
          2. 若有 tool_call，则逐个执行并把 function_call_output 追加到 input
          3. 达到 summary_interval 时做一次记忆摘要并清空 input
          4. 若 finish_check() 返回 True 或被中断则结束

        返回值:
            {
                "success": bool,
                "input": 最后一轮 input,
                "output_text": 最后一轮模型输出,
                "interrupted": bool,
            }
        """
        with InterruptHandler() as handler, self._run_context():
            current_input = initial_input.copy()
            iteration = 0
            total_cost = 0
            all_tool_calls = []
            last_result = None

            print("=" * 60)
            print("🚀 AGENT RUN STARTED")
            print("=" * 60)

            # ── 主循环 ──
            while iteration < max_iterations and not handler.interrupted:
                iteration += 1
                print(f"\n{'─' * 40}")
                print(f"🔄 Iteration {iteration}/{max_iterations}")
                print(f"{'─' * 40}")

                result = self.get_response(current_input)
                result["interrupted"] = handler.interrupted
                last_result = result
                self._log_metadata(result, iteration)
                total_cost += result["total_cost"]
                all_tool_calls.extend(result["tool_calls"])

                # finish_check 优先级最高
                if finish_check and finish_check():
                    print("✅ Finish condition met")
                    break

                # 无 tool_call -> 模型认为任务结束
                if not result["tool_calls"] or handler.interrupted:
                    if handler.interrupted:
                        print("⏹️ Run interrupted by user")
                    else:
                        print("✅ No more tool calls required - ending run")
                    break

                print(f"⚙️ Executing {len(result['tool_calls'])} tool call(s)...")

                # 把模型的 function_call 加入上下文
                for item in result["output"]:
                    if item.type == "function_call":
                        current_input.append(item)

                # 依次执行 tool_call 并把结果回填
                for tool_call in result["tool_calls"]:
                    if handler.interrupted:
                        print("⏹️ Interrupted during tool execution")
                        break

                    func_name = tool_call["name"]
                    arguments = tool_call["arguments"]
                    call_id = tool_call["call_id"]
                    print(f"  ▶️ {func_name}({arguments})")

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
                        print(f"  ✅ {func_name} output: \n\n {output}")
                    except Exception as e:
                        output = f"Tool execution error: {str(e)}"
                        print(f"  ❌ {func_name} failed: {e}")
                        self._append_log({
                            "event": "tool_error",
                            "timestamp": datetime.now().isoformat(),
                            "iteration": iteration,
                            "tool": func_name,
                            "error": str(e),
                        })

                    # 把 tool 输出回填到上下文
                    current_input.append({
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps({func_name: output}),
                    })

                # 周期性记忆摘要
                if iteration % self.summary_interval == 0:
                    print(f"📝 Reached {iteration} iterations, generating summary...")
                    summary, memory_costs = self._summarize(current_input)
                    total_cost += memory_costs["total_cost"]
                    self._append_log({
                        "event": "interval_summary",
                        "timestamp": datetime.now().isoformat(),
                        "iteration": iteration,
                        "summary": summary,
                        "interval": self.summary_interval,
                        "tools_executed_in_interval": [tc["name"] for tc in result["tool_calls"]],
                    })
                    # 清空 input，用摘要作为下一轮的起点
                    print(f"🧹 Clearing input and adding interval summary...")
                    current_input = [
                        {
                            "role": "user",
                            "content": f"Progress summary after {iteration} iterations: {summary}\n\nContinue with the task.",
                        }
                    ]
                    print(f"📋 Interval summary: {summary}")

            # 收尾日志与统计
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
                "input": current_input,
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

            print(f"🚀 Agent run completed. Output: {final_state.get('output_text')}")
            return final_state
