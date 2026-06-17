"""
通用版 Agent（general_agent.py）

功能概述：
    与 agent.py 同等结构，但面向"老式 Chat Completions API"或不支持原生
    function calling 的模型。工具调用通过在 system prompt 中规定
    <tool_call>{...}</tool_call> XML 标签，并从模型回复里解析出来。

适用场景：
    - 不支持 OpenAI 工具调用协议的模型（自托管 / 第三方 OpenAI 兼容）
    - 需要把工具调用以纯文本形式调试 / 日志的场景

与 agent.py 的关键差异：
    - 调用 self.client.chat.completions.create（而非 responses.create）
    - 工具描述以纯文本形式注入到 system prompt
    - 解析模型回复中的 <tool_call>...</tool_call> 块
    - 工具响应以 <tool_response> XML 形式追加
"""

import os
import sys
import json
import signal
import contextlib
import re
from datetime import datetime
from openai import OpenAI
from typing import List, Dict, Any, Optional, Callable, Union, Tuple
from pathlib import Path

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from ..toolkit.base import BaseTool
from ..skills.base import BaseSkill


# ════════════════════════════════════════════════════════════════════════════════
#   中断处理（与 agent.py 同）
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
        print("\n\n⚠️ Interrupt received, stopping gracefully...")


# ════════════════════════════════════════════════════════════════════════════════
#   General Agent 主类
# ════════════════════════════════════════════════════════════════════════════════

class Agent:
    """基于 Chat Completions + XML 工具调用约定的通用 Agent。"""

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
        """初始化通用 Agent。

        参数: 含义与 agent.py 中相同。
        """
        self.model_code = model_code
        self.toolkit = toolkit
        self.skills = skills or []
        self.instructions_template = instructions
        self.config_path = config_path
        self.log_file = log_file
        self.summary_interval = summary_interval
        self.force_tool_call = force_tool_call

        self.log_entries = []
        self.model_config = self._load_model_config()
        self.producer = self.model_config.get("producer", "OpenAI")

        # 长超时：多步推理可能很久
        self.client = OpenAI(
            api_key=os.getenv("API_KEY"),
            base_url=os.getenv("API_URL"),
            timeout=1800,
        )

        # 工具描述以文本形式注入；function_map 仍按 name 索引
        self.tool_descriptions = self._build_tool_descriptions()
        self.function_map = {tool.get_name(): tool.get_implementation() for tool in toolkit}

        # system prompt = 原始 instructions + 工具说明 + 技能说明
        self.instructions = self._build_instructions()

        print(f"✅ Agent initialized with model: {model_code}")
        print(f"📦 Loaded tools: {list(self.function_map.keys())}")
        print(f"📚 Loaded skills: {[skill.get_name() for skill in self.skills]}")
        print(f"⚙️ Summary interval: {summary_interval} iterations")
        print(f"⚙️ Force tool call: {force_tool_call}")

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
        """读取已有日志（保持 JSON 数组结构）。"""
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
        """追加一条日志。"""
        existing_logs = self._load_existing_logs()
        existing_logs.append(entry)
        log_dir = Path(self.log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(existing_logs, f, indent=2, ensure_ascii=False, default=str)

    # ── 工具描述构造（与 agent.py 不同的关键点） ─────────────────────

    def _build_tool_descriptions(self) -> str:
        """把所有工具描述拼成一段文本（不依赖原生 tools 协议）。

        输出包含:
          1. 每个工具的名称 + 描述
          2. 工具调用约定（<tool_call>{json}</tool_call>）
          3. 若 force_tool_call=True，附加强制调用提示
        """
        if not self.toolkit:
            return "No tools available."

        tools_text = "Available Tools:\n\n"
        for i, tool in enumerate(self.toolkit, 1):
            tool_desc = tool.get_description(producer=self.producer)
            tools_text += f"{i}. {tool.get_name()}\n"
            tools_text += f"   Description: {str(tool_desc)}\n"
            tools_text += "\n"

        tools_text += """
Tool Calling Instructions:
When you need to use a tool, you MUST respond with a tool call in the following format:
<tool_call>
{
  "name": "tool_name",
  "arguments": {
    "param1": value1,
    "param2": value2
  }
}
</tool_call>

You can include explanatory text before or after the tool call. After you receive the tool response, continue with your task based on the result.
"""
        if self.force_tool_call:
            tools_text += "\nIMPORTANT: You MUST make at least one tool call in each response.\n"
        return tools_text

    def _build_instructions(self) -> str:
        """拼接 system prompt：原始 instructions + 工具说明 + 技能说明。"""
        if not self.instructions_template:
            instructions = ""
        else:
            instructions = self.instructions_template

        if self.skills:
            skills_text = "\n\nAvailable Skills:\n"
            for skill in self.skills:
                skills_text += f"Name: {skill.get_name()}\n"
                skills_text += f"Description: {skill.get_description()}\n"
                skills_text += f"Details: {skill.get_details()}\n"
        else:
            skills_text = "\n\nNo skills available."

        tools_text = self._build_tool_descriptions()
        return instructions + tools_text + skills_text

    # ── 解析 <tool_call> XML ─────────────────────────

    def _parse_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """从模型回复中解析 <tool_call>...</tool_call> 块。

        期望块内是合法 JSON: {"name": "...", "arguments": {...}}
        解析失败会跳过对应块但不影响其它块。
        """
        tool_calls = []
        pattern = r'<tool_call>\s*(.*?)\s*</tool_call>'
        matches = re.findall(pattern, text, re.DOTALL)

        for i, match in enumerate(matches):
            try:
                tool_data = json.loads(match.strip())
                if "name" not in tool_data:
                    print(f"⚠️ Tool call missing 'name' field: {match}")
                    continue
                tool_calls.append({
                    "name": tool_data["name"],
                    "arguments": tool_data.get("arguments", {}),
                    "call_id": f"call_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}",
                })
            except json.JSONDecodeError as e:
                print(f"⚠️ Failed to parse tool call JSON: {e}")
                print(f"   Raw content: {match}")
                continue
        return tool_calls

    # ── 模型配置 / 成本（同 agent.py） ─────────────────────────

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
        """计算 token 费用。"""
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
        """记录一次迭代的元数据。"""
        metadata = {
            "event": "iteration_complete",
            "timestamp": datetime.now().isoformat(),
            "iteration": iteration,
            "model": self.model_code,
            "output": result.get("output_text", ""),
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

    def _summarize(self, current_messages: List[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
        """对当前消息列表做一次摘要，避免上下文无限增长。"""
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
                    {"role": "user", "content": f"Please summarize the following conversation:\n\n{json.dumps(current_messages, default=str)}"},
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

    def get_response(self, messages: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """调用 Chat Completions API 并解析 tool_call。

        返回值:
            (result, assistant_message) 元组
              - result: 包含 output_text / tokens / cost / tool_calls 等
              - assistant_message: 用于回填到 messages 的助手消息
        """
        print(f"📤 API Request - {len(messages)} messages")

        chat_messages = []
        print(f"📜 System instructions length: {len(self.instructions)} characters")
        if self.instructions:
            chat_messages.append({"role": "system", "content": self.instructions})
        for msg in messages:
            chat_messages.append(msg)

        response = self.client.chat.completions.create(
            model=self.model_code,
            messages=chat_messages,
        )

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        costs = self._calculate_costs(input_tokens, output_tokens)

        output_text = response.choices[0].message.content or ""
        finish_reason = response.choices[0].finish_reason

        # 解析 XML 工具调用
        tool_calls = self._parse_tool_calls(output_text)

        assistant_message = {
            "role": "assistant",
            "content": output_text,
        }

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
        return result, assistant_message

    # ── 运行上下文 ────────────────────────────────────

    @contextlib.contextmanager
    def _run_context(self):
        """run 维度的日志上下文。"""
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
        """运行通用 Agent 的多轮 tool-calling 循环。

        与 agent.py 的差别：
          - 用 chat.completions 替代 responses
          - 用 <tool_response> XML 块回填工具结果
          - 记忆摘要以 system 角色追加（而非清空 input）
        """
        with InterruptHandler() as handler, self._run_context():
            current_messages = initial_messages.copy()
            iteration = 0
            total_cost = 0
            all_tool_calls = []
            last_result = None

            print("=" * 60)
            print("🚀 AGENT RUN STARTED")
            print("=" * 60)

            while iteration < max_iterations and not handler.interrupted:
                iteration += 1
                print(f"\n{'─' * 40}")
                print(f"🔄 Iteration {iteration}/{max_iterations}")
                print(f"{'─' * 40}")

                result, assistant_message = self.get_response(current_messages)
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

                # 把 assistant 消息加入上下文
                current_messages.append(assistant_message)

                # 执行工具调用并打包为 <tool_response> XML
                tool_responses = []
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
                        print(f"  ✅ {func_name} output: {output_str[:1000]}...[truncated]")
                        tool_responses.append({
                            "tool_name": func_name,
                            "call_id": call_id,
                            "response": output_str,
                        })
                    except Exception as e:
                        output_str = f"Tool execution error: {str(e)}"
                        print(f"  ❌ {func_name} failed: {e}")
                        tool_responses.append({
                            "tool_name": func_name,
                            "call_id": call_id,
                            "response": output_str,
                            "error": True,
                        })
                        self._append_log({
                            "event": "tool_error",
                            "timestamp": datetime.now().isoformat(),
                            "iteration": iteration,
                            "tool": func_name,
                            "error": str(e),
                        })

                # 把工具响应打包到 user 角色的 XML 消息中
                if tool_responses:
                    tool_response_text = ""
                    for resp in tool_responses:
                        tool_response_text += f"\n<tool_response>\n"
                        tool_response_text += json.dumps({
                            "name": resp["tool_name"],
                            "call_id": resp["call_id"],
                            "response": resp["response"],
                        }, ensure_ascii=False, indent=2)
                        tool_response_text += f"\n</tool_response>\n"
                    current_messages.append({
                        "role": "user",
                        "content": f"Tool execution results:{tool_response_text}",
                    })

                # 周期性记忆摘要（以 system 消息注入，保留历史）
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
                        "content": f"Progress summary after {iteration} iterations: {summary}\n\nContinue with the task.",
                    })
                    print(f"📋 Interval summary: {summary[:1000]}...[truncated]")

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

            print(f"🚀 Agent run completed.")
            return final_state
