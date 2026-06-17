"""
AlphaCrafter 主入口（main.py）

功能概述：
    启动 Miner / Screener / Trader 三 Agent 循环的工作流执行器。
    每一轮 cycle 顺序执行三个 Agent：
        Miner  -> 挖掘 / 验证 alpha 因子，落地到 factors/*.json
        Screener -> 评估市场风格，挑选有效因子组成 ensemble
        Trader ->  根据 ensemble 写 strategy.py，调用 step / backtest 验证

数据流（一次 cycle）：
    ┌──────────┐   上下文    ┌──────────┐
    │ Launcher │ ─────────→ │  Miner   │  -> factors/*.json
    └────┬─────┘            └────┬─────┘
         │                       │
         │ 上下文（含 miner 输出）│
         ▼                       ▼
    ┌──────────┐            ┌──────────┐
    │ Trader   │ ←───────── │ Screener │  -> factor ensemble
    └────┬─────┘            └──────────┘
         │
         │  step / backtest
         ▼
    account.json / date.json

支持模式:
    --session_id  :  sandbox 下的会话目录（必填）
    --max-cycles  :  最大循环次数（默认 300）
    --resume      :  从断点日志继续
"""

import os
import sys
import json
import argparse
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field, asdict
from dotenv import load_dotenv

from agent.openai.agent import Agent

from agent.instructions import (
    QUANTITATIVE_TRADING_INSTRUCTION_A,
    MINER_INSTRUCTION,
    SCREENER_INSTRUCTION,
    TRADER_INSTRUCTION,
)
from agent.toolkit import (
    ReadFileTool, WriteFileTool, ShellTool,
    GetStockDataTool, GetIndexDataTool, StepTool,
    BacktestTool, SearchFactorTool, GetFinancialStatementsTool, GetNewsTool,
)
from agent.skills import (
    QuantitativeTradingSkill,
    FactorMiningSkill,
    FactorScreeningSkill,
    StrategyRegistrationSkill,
    PositionManagementSkill,
)

from alphacrafter.sim.utils import finish_check, get_account_dict, get_date_str

load_dotenv()


# ════════════════════════════════════════════════════════════════════════════════
#   循环记录数据类
# ════════════════════════════════════════════════════════════════════════════════

@dataclass
class CycleRecord:
    """单个 cycle 的三个 Agent 输出快照。

    字段:
        cycle:           cycle 序号
        miner_output:    Miner Agent 文本输出
        screener_output: Screener Agent 文本输出
        trader_output:   Trader Agent 文本输出
        timestamp:       记录时间
    """
    cycle: int
    miner_output: str = ""
    screener_output: str = ""
    trader_output: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# ════════════════════════════════════════════════════════════════════════════════
#   Launcher 主类
# ════════════════════════════════════════════════════════════════════════════════

class Launcher:
    """编排 Miner / Screener / Trader 三 Agent 循环的工作流执行器。"""

    def __init__(self, session_id: str, max_cycles: int = 300, resume: bool = False):
        """初始化 Launcher。

        参数:
            session_id: session 目录名（位于 sandbox/ 下）
            max_cycles: 最大 cycle 数（默认 300）
            resume:     是否从历史日志恢复
        """
        self.session_id = session_id
        self.max_cycles = max_cycles
        self.resume = resume
        self.workspace_path = None

        # Agent 实例（运行时填充）
        self.miner_agent = None
        self.screener_agent = None
        self.trader_agent = None

        # 全部 cycle 的历史记录
        self.cycle_records: List[CycleRecord] = []

        # 各 Agent 与 workflow 的日志路径
        self.log_path = "../logs/workflow.json"
        self.miner_log_path = "../logs/miner_agent.json"
        self.screener_log_path = "../logs/screener_agent.json"
        self.trader_log_path = "../logs/trader_agent.json"

        # resume 模式下用：保存每个 Agent 上一次的输入
        self.last_miner_input = None
        self.last_screener_input = None
        self.last_trader_input = None

    # ── 工作区与日志初始化 ───────────────────────────

    def _get_session_workspace(self) -> str:
        """定位已存在的 session 工作区。

        期望的目录结构: alphacrafter/sandbox/{session_id}/workspace/
        """
        base_dir = os.path.dirname(os.path.dirname(__file__))
        sandbox_path = os.path.join(base_dir, 'alphacrafter/sandbox')
        session_path = os.path.join(sandbox_path, self.session_id)
        workspace_path = os.path.join(session_path, 'workspace')

        if not os.path.exists(session_path):
            raise FileNotFoundError(f"Session directory not found: {session_path}")
        if not os.path.exists(workspace_path):
            raise FileNotFoundError(f"Workspace directory not found: {workspace_path}")

        print(f"Using existing session: {self.session_id}")
        print(f"Workspace path: {workspace_path}")
        return workspace_path

    def _setup_workspace(self):
        """切到 workspace 目录，并把该目录加入 sys.path。"""
        os.chdir(self.workspace_path)
        if self.workspace_path not in sys.path:
            sys.path.insert(0, self.workspace_path)

        print(f"\nWorking in: {self.workspace_path}")
        print("\nCurrent workspace contents:")
        for item in os.listdir('.'):
            print(f"  - {item}")

    # ── resume 相关：恢复 Agent 的"上一次输入" ─────────────────────

    def _load_last_input_from_agent_log(self, agent_log_path: str) -> Optional[List[Dict[str, str]]]:
        """从单个 Agent 的日志里抽"最后一次成功 run 的 input"。

        用于 resume：让 Agent 接着上次的对话继续。
        """
        if not os.path.exists(agent_log_path):
            return None

        try:
            with open(agent_log_path, 'r', encoding='utf-8') as f:
                entries = json.load(f)
                if not isinstance(entries, list):
                    entries = [entries]
        except Exception as e:
            print(f"Error reading {agent_log_path}: {e}")
            return None

        # 倒序找最近一次 run_complete 且 success=True 的记录
        for entry in reversed(entries):
            if entry.get('event') == 'run_complete':
                final_state = entry.get('final_state', {})
                if final_state.get('success') and final_state.get('input'):
                    return self._aggregate_input_to_user_message(final_state['input'])
        return None

    def _aggregate_input_to_user_message(self, input_array: List) -> List[Dict[str, str]]:
        """把 input 数组打包成单条 user 消息，附"你正在从上次继续"提示。

        简化处理：直接转字符串，不逐字段拆解。
        """
        if not input_array:
            return [{"role": "user", "content": ""}]
        aggregated_content = "you are resuming from the previous session: " + str(input_array)
        return [{"role": "user", "content": aggregated_content}]

    def _load_previous_workflow_state(self) -> Optional[int]:
        """从 workflow.json 找"最后一个完整 cycle"序号。

        完整 cycle = 三个阶段 (miner / screener / trader) 都 success=True。
        """
        if not os.path.exists(self.log_path):
            print("No previous workflow log found. Starting fresh.")
            return None

        try:
            with open(self.log_path, 'r', encoding='utf-8') as f:
                entries = json.load(f)
                if not isinstance(entries, list):
                    entries = [entries]
        except Exception as e:
            print(f"Error reading workflow log: {e}")
            return None

        if not entries:
            return None

        # 按 cycle 分组
        cycles = {}
        for entry in entries:
            cycle_num = entry.get('cycle')
            if cycle_num not in cycles:
                cycles[cycle_num] = {'miner': None, 'screener': None, 'trader': None}
            phase = entry.get('phase')
            if phase in cycles[cycle_num]:
                cycles[cycle_num][phase] = entry

        # 找最后一个"三阶段都成功"的 cycle
        last_complete_cycle = None
        for cycle_num in sorted(cycles.keys()):
            cycle_data = cycles[cycle_num]
            if (cycle_data['miner'] and cycle_data['miner'].get('success')
                and cycle_data['screener'] and cycle_data['screener'].get('success')
                and cycle_data['trader'] and cycle_data['trader'].get('success')):
                last_complete_cycle = cycle_num

        if last_complete_cycle is not None:
            print(f"Found previous workflow state. Last complete cycle: {last_complete_cycle}")

            # 重建内存中的 cycle_records
            for cycle_num in sorted(cycles.keys()):
                if cycle_num <= last_complete_cycle:
                    cycle_data = cycles[cycle_num]
                    record = CycleRecord(cycle=cycle_num)
                    record.miner_output = cycle_data['miner'].get('output_text', '') if cycle_data['miner'] else ''
                    record.screener_output = cycle_data['screener'].get('output_text', '') if cycle_data['screener'] else ''
                    record.trader_output = cycle_data['trader'].get('output_text', '') if cycle_data['trader'] else ''
                    self.cycle_records.append(record)
            return last_complete_cycle
        else:
            print("No complete cycles found in previous workflow. Starting fresh.")
            return None

    def _load_resume_inputs(self):
        """在 Agent 初始化之前从日志加载各 Agent 的"上一次输入"。

        注意：必须先于 Agent 初始化，因为 Agent init 会重写日志文件。
        """
        if not self.resume:
            return

        print("\n" + "=" * 60)
        print("📂 LOADING RESUME INPUTS FROM LOGS")
        print("=" * 60)

        self.last_miner_input = self._load_last_input_from_agent_log(self.miner_log_path)
        self.last_screener_input = self._load_last_input_from_agent_log(self.screener_log_path)
        self.last_trader_input = self._load_last_input_from_agent_log(self.trader_log_path)

        if self.last_miner_input:
            print(f"✅ Loaded last miner input from {self.miner_log_path}")
        else:
            print(f"⚠️ No previous miner input found")
        if self.last_screener_input:
            print(f"✅ Loaded last screener input from {self.screener_log_path}")
        else:
            print(f"⚠️ No previous screener input found")
        if self.last_trader_input:
            print(f"✅ Loaded last trader input from {self.trader_log_path}")
        else:
            print(f"⚠️ No previous trader input found")

    # ── Agent 工厂 ───────────────────────────

    def _create_miner_agent(self) -> Agent:
        """构造 Miner Agent：负责 alpha 因子挖掘与验证。"""
        toolkit = [
            ReadFileTool(),
            WriteFileTool(),
            ShellTool(),
            SearchFactorTool(),
        ]
        skills = [QuantitativeTradingSkill(), FactorMiningSkill()]

        # 通用市场背景知识（CSI300 简介）
        ADDITIONAL_INFO = """
Here are some market index references:

CSI300 (000300.SH) is the CSI 300 Index, a capitalization-weighted stock market index designed to replicate the performance of the top 300 stocks traded on the Shanghai and Shenzhen stock exchanges. It is the primary benchmark for the Chinese A-share market, similar to the S&P 500 in the US. The index covers approximately 60% of the total market capitalization of the A-share market and is widely used for institutional investment benchmarking, index funds, and derivatives such as futures and options.
"""

        return Agent(
            model_code="gpt-5.3-codex",
            toolkit=toolkit,
            skills=skills,
            instructions=QUANTITATIVE_TRADING_INSTRUCTION_A + "\n\n" + MINER_INSTRUCTION + "\n\n" + ADDITIONAL_INFO,
            config_path="../config/models.json",
            log_file="../logs/miner_agent.json",
            summary_interval=15,
            force_tool_call=False,
        )

    def _create_screener_agent(self) -> Agent:
        """构造 Screener Agent：负责市场风格评估与因子 ensemble 构造。"""
        toolkit = [
            ShellTool(),
            GetStockDataTool(),
            GetIndexDataTool(),
            SearchFactorTool(),
            GetFinancialStatementsTool(),
            GetNewsTool(),
        ]
        skills = [FactorScreeningSkill()]

        ADDITIONAL_INFO = """
Here are some market index references:

CSI300 (000300.SH) is the CSI 300 Index, a capitalization-weighted stock market index designed to replicate the performance of the top 300 stocks traded on the Shanghai and Shenzhen stock exchanges. It is the primary benchmark for the Chinese A-share market, similar to the S&P 500 in the US. The index covers approximately 60% of the total market capitalization of the A-share market and is widely used for institutional investment benchmarking, index funds, and derivatives such as futures and options.
"""

        return Agent(
            model_code="gpt-5.3-codex",
            toolkit=toolkit,
            skills=skills,
            instructions=QUANTITATIVE_TRADING_INSTRUCTION_A + "\n\n" + SCREENER_INSTRUCTION + "\n\n" + ADDITIONAL_INFO,
            config_path="../config/models.json",
            log_file="../logs/screener_agent.json",
            summary_interval=15,
            force_tool_call=False,
        )

    def _create_trader_agent(self) -> Agent:
        """构造 Trader Agent：把 ensemble 落成 strategy.py 并验证/执行。"""
        toolkit = [
            ReadFileTool(),
            WriteFileTool(),
            BacktestTool(),
            StepTool(),
        ]
        skills = [QuantitativeTradingSkill(), StrategyRegistrationSkill(), PositionManagementSkill()]

        ADDITIONAL_INFO = """
Here are some market index references:

000300.SH is the CSI 300 Index, a capitalization-weighted stock market index designed to replicate the performance of the top 300 stocks traded on the Shanghai and Shenzhen stock exchanges. It is the primary benchmark for the Chinese A-share market, similar to the S&P 500 in the US. The index covers approximately 60% of the total market capitalization of the A-share market and is widely used for institutional investment benchmarking, index funds, and derivatives such as futures and options.
"""

        return Agent(
            model_code="gpt-5.3-codex",
            toolkit=toolkit,
            skills=skills,
            instructions=QUANTITATIVE_TRADING_INSTRUCTION_A + "\n\n" + TRADER_INSTRUCTION + "\n\n" + ADDITIONAL_INFO,
            config_path="../config/models.json",
            log_file="../logs/trader_agent.json",
            summary_interval=15,
            force_tool_call=False,
        )

    # ── Agent 单阶段执行 ───────────────────────────

    def _run_agent_phase(self, agent: Agent, context: str, phase_name: str, max_iterations: int = 100) -> Dict[str, Any]:
        """普通模式：执行一次 Agent 阶段，传入 user context。"""
        print(f"\n{'=' * 60}")
        print(f"🔬 {phase_name.upper()} PHASE")
        print(f"{'=' * 60}")

        input_messages = [{"role": "user", "content": context}] if context else [{"role": "user", "content": ""}]
        result = agent.run(input_messages, max_iterations=max_iterations, finish_check=finish_check)

        print(f"\n{'=' * 60}")
        print(f"🔬 {phase_name.upper()} PHASE COMPLETED")
        print(f"{'=' * 60}")
        return result

    def _run_agent_phase_with_resume(
        self,
        agent: Agent,
        last_input: Optional[List[Dict[str, str]]],
        context: str,
        phase_name: str,
        max_iterations: int = 100,
    ) -> Dict[str, Any]:
        """resume 模式：若提供了 last_input，则用它继续；否则走普通路径。"""
        if self.resume and last_input:
            print(f"\n{'=' * 60}")
            print(f"🔬 {phase_name.upper()} PHASE - RESUMING FROM LAST INPUT")
            print(f"{'=' * 60}")
            print(f"Using last input from previous run")
            result = agent.run(last_input, max_iterations=max_iterations, finish_check=finish_check)
            print(f"\n{'=' * 60}")
            print(f"🔬 {phase_name.upper()} PHASE COMPLETED (RESUMED)")
            print(f"{'=' * 60}")
            return result
        else:
            return self._run_agent_phase(agent, context, phase_name, max_iterations)

    # ── 终止条件 ───────────────────────────

    def _should_terminate(self, result: Dict[str, Any]) -> bool:
        """判断本轮 cycle 是否应该立即结束。

        触发条件:
          - 用户 Ctrl-C（interrupted）
          - Agent 运行失败
          - finish_check 返回 True（仿真到最后一个交易日）
        """
        if result.get("interrupted", False):
            print("⏹️ Interrupted by user")
            return True
        if not result.get("success", False):
            print("❌ Phase failed")
            return True
        try:
            if finish_check():
                print("✅ finish_check returned True")
                return True
        except Exception:
            pass
        return False

    # ── workflow 日志 ───────────────────────────

    def _log_workflow_entry(self, cycle: int, phase: str, result: Dict[str, Any]):
        """追加一条 workflow 日志（保持 JSON 数组结构）。"""
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

        entries = []
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, 'r', encoding='utf-8') as f:
                    entries = json.load(f)
                    if not isinstance(entries, list):
                        entries = [entries]
            except Exception:
                entries = []

        entries.append({
            "cycle": cycle,
            "phase": phase,
            "timestamp": datetime.now().isoformat(),
            "success": result.get("success", False),
            "interrupted": result.get("interrupted", False),
            "output_text": result.get("output_text", ""),
        })

        with open(self.log_path, 'w', encoding='utf-8') as f:
            json.dump(entries, f, indent=2, ensure_ascii=False, default=str)

    # ── 上下文构造：把上一个 cycle 的输出喂给下一个 Agent ─────────────────────

    def _build_miner_context(self) -> str:
        """Miner 上下文：账户/日期 + 上一 cycle 的 miner & screener 输出。"""
        context_parts = []

        # 账户 / 日期
        try:
            account = get_account_dict()
            account_str = str(account)
            if len(account_str) > 500:
                account_str = account_str[:500] + "... [truncated]"
            context_parts.append(f"Current account: {account_str}")
            current_date = get_date_str()
            context_parts.append(f"Current date: {current_date}")
        except Exception as e:
            print(f"Error getting account/date info: {e}")
            context_parts.append(f"Failed to get account/date info: {e}")

        # 上一 cycle 的输出
        if self.cycle_records:
            last_record = self.cycle_records[-1]
            if last_record.miner_output:
                context_parts.append(f"Previous miner agent output: {last_record.miner_output}")
            if last_record.screener_output:
                context_parts.append(f"Previous screener agent output: {last_record.screener_output}")

        return "\n".join(context_parts) if context_parts else ""

    def _build_screener_context(self) -> str:
        """Screener 上下文：本 cycle miner 输出 + 上一 cycle screener/trader 输出。"""
        context_parts = []

        try:
            account = get_account_dict()
            account_str = str(account)
            if len(account_str) > 500:
                account_str = account_str[:500] + "... [truncated]"
            context_parts.append(f"Current account: {account_str}")
            current_date = get_date_str()
            context_parts.append(f"Current date: {current_date}")
        except Exception as e:
            print(f"Error getting account/date info: {e}")
            context_parts.append(f"Failed to get account/date info: {e}")

        if not self.cycle_records:
            return "\n".join(context_parts) if context_parts else ""

        last_record = self.cycle_records[-1]
        if last_record.miner_output:
            context_parts.append(f"Miner agent output from current cycle: {last_record.miner_output}")

        if len(self.cycle_records) >= 2:
            prev_record = self.cycle_records[-2]
            if prev_record.screener_output:
                context_parts.append(f"Previous screener agent output: {prev_record.screener_output}")
            if prev_record.trader_output:
                context_parts.append(f"Previous trader agent output: {prev_record.trader_output}")

        return "\n\n".join(context_parts) if context_parts else ""

    def _build_trader_context(self) -> str:
        """Trader 上下文：本 cycle screener 输出 + 上一 cycle trader 输出。"""
        context_parts = []

        try:
            account = get_account_dict()
            account_str = str(account)
            if len(account_str) > 500:
                account_str = account_str[:500] + "... [truncated]"
            context_parts.append(f"Current account: {account_str}")
            current_date = get_date_str()
            context_parts.append(f"Current date: {current_date}")
        except Exception as e:
            print(f"Error getting account/date info: {e}")
            context_parts.append(f"Failed to get account/date info: {e}")

        if not self.cycle_records:
            return "\n".join(context_parts) if context_parts else ""

        last_record = self.cycle_records[-1]
        if last_record.screener_output:
            context_parts.append(f"Screener agent output from current cycle: {last_record.screener_output}")

        if len(self.cycle_records) >= 2:
            prev_record = self.cycle_records[-2]
            if prev_record.trader_output:
                context_parts.append(f"Previous trader agent output: {prev_record.trader_output}")

        return "\n\n".join(context_parts) if context_parts else ""

    # ── 单个 cycle ───────────────────────────

    def _run_single_cycle(self, cycle: int, is_resume_cycle: bool = False) -> bool:
        """执行一次完整 cycle：Miner -> Screener -> Trader。

        返回 False 表示应当立即停止整个工作流。
        """
        print("\n" + "█" * 60)
        if is_resume_cycle:
            print(f"🔄 RESUME CYCLE {cycle}/{self.max_cycles}")
        else:
            print(f"🔄 CYCLE {cycle}/{self.max_cycles}")
        print("█" * 60)

        record = CycleRecord(cycle=cycle)

        # ── 1. Miner：因子发现 ──
        miner_context = self._build_miner_context()
        miner_result = self._run_agent_phase_with_resume(
            self.miner_agent,
            self.last_miner_input if is_resume_cycle else None,
            miner_context,
            "miner",
            max_iterations=100,
        )
        record.miner_output = miner_result.get("output_text", "")
        print(f"\n--- 🔄 Cycle {cycle} Miner Output ---")
        print(f"{record.miner_output}")
        self._log_workflow_entry(cycle, "miner", miner_result)

        if self._should_terminate(miner_result):
            return False

        # 先把 miner 输出入栈，让 Screener 能看到
        self.cycle_records.append(record)

        # ── 2. Screener：选因子、组装 ensemble ──
        screener_context = self._build_screener_context()
        screener_result = self._run_agent_phase_with_resume(
            self.screener_agent,
            self.last_screener_input if is_resume_cycle else None,
            screener_context,
            "screener",
            max_iterations=100,
        )
        record.screener_output = screener_result.get("output_text", "")
        print(f"\n--- 🔄 Cycle {cycle} Screener Output ---")
        print(f"{record.screener_output}")
        self._log_workflow_entry(cycle, "screener", screener_result)

        if self._should_terminate(screener_result):
            return False

        # 更新栈顶记录的 screener 输出
        self.cycle_records[-1] = record

        # ── 3. Trader：写策略 + step / backtest ──
        trader_context = self._build_trader_context()
        trader_result = self._run_agent_phase_with_resume(
            self.trader_agent,
            self.last_trader_input if is_resume_cycle else None,
            trader_context,
            "trader",
            max_iterations=100,
        )
        record.trader_output = trader_result.get("output_text", "")
        print(f"\n--- 🔄 Cycle {cycle} Trader Output ---")
        print(f"{record.trader_output}")
        self._log_workflow_entry(cycle, "trader", trader_result)

        if self._should_terminate(trader_result):
            return False

        self.cycle_records[-1] = record
        print(f"\n💾 Cycle {cycle} completed")
        return True

    # ── 主入口 ───────────────────────────

    def run(self) -> Dict[str, Any]:
        """启动整个工作流。

        流程:
          1. 准备 workspace
          2. （resume 模式）恢复上次的 Agent 输入与 workflow 状态
          3. 构造三个 Agent
          4. 从 last_complete_cycle+1 开始跑剩余 cycle
        """
        try:
            # ── 1. 准备 workspace ──
            self.workspace_path = self._get_session_workspace()
            self._setup_workspace()

            # ── 2. resume 数据（必须在 Agent init 之前做） ──
            if self.resume:
                self._load_resume_inputs()
                last_complete_cycle = self._load_previous_workflow_state()
            else:
                last_complete_cycle = None

            # ── 3. 构造 Agent（这一步会重置 log 文件） ──
            self.miner_agent = self._create_miner_agent()
            self.screener_agent = self._create_screener_agent()
            self.trader_agent = self._create_trader_agent()

            # ── 4. resume 模式：先用一个特殊 cycle 续上历史 ──
            if self.resume and last_complete_cycle is not None:
                print("\n" + "=" * 60)
                print(f"🚀 RESUMING WORKFLOW from cycle {last_complete_cycle + 1} (max {self.max_cycles} cycles total)")
                print("=" * 60)
                next_cycle = last_complete_cycle + 1
                should_continue = self._run_single_cycle(next_cycle, is_resume_cycle=True)
                if not should_continue:
                    print("Workflow terminated during resume cycle.")
                    return {
                        "success": True,
                        "total_cycles": len(self.cycle_records),
                        "cycle_records": [asdict(r) for r in self.cycle_records],
                    }
                current_cycle = next_cycle
            else:
                if self.resume:
                    print("\nNo previous workflow state found. Starting fresh.")
                print("\n" + "=" * 60)
                print(f"🚀 STARTING NEW WORKFLOW (max {self.max_cycles} cycles)")
                print("=" * 60)
                current_cycle = 0

            # ── 5. 跑剩余 cycle ──
            cycle = current_cycle
            while cycle < self.max_cycles:
                cycle += 1
                # 仅紧接 resume cycle 之后的那个 cycle 仍按 resume 处理（保护历史）
                is_resume = (self.resume and cycle == current_cycle + 1 and current_cycle > 0)
                should_continue = self._run_single_cycle(cycle, is_resume_cycle=is_resume)
                if not should_continue:
                    break

            # ── 收尾 ──
            print("\n" + "=" * 60)
            print("🎯 WORKFLOW COMPLETED")
            print("=" * 60)
            print(f"Total cycles: {len(self.cycle_records)}")
            print(f"✅ Workflow log saved to {self.log_path}")

            return {
                "success": True,
                "total_cycles": len(self.cycle_records),
                "cycle_records": [asdict(r) for r in self.cycle_records],
            }

        except FileNotFoundError as e:
            print(f"Error: {e}")
            print("\nPlease ensure the session exists in sandbox directory.")
            return {"success": False, "error": str(e)}
        except Exception as e:
            print(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}


# ════════════════════════════════════════════════════════════════════════════════
#   命令行入口
# ════════════════════════════════════════════════════════════════════════════════

def parse_arguments():
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="Run quantitative trading workflow with Miner, Screener, and Trader agents"
    )
    parser.add_argument(
        "session_id",
        type=str,
        help="Session identifier for the workspace",
    )
    parser.add_argument(
        "--max-cycles", "-m",
        type=int,
        default=300,
        help="Maximum number of workflow cycles to run (default: 300)",
    )
    parser.add_argument(
        "--resume", "-r",
        action="store_true",
        help="Resume from previous workflow state using logs",
    )
    return parser.parse_args()


def main():
    """CLI 入口。"""
    args = parse_arguments()

    print(f"Starting workflow with:")
    print(f"  Session ID: {args.session_id}")
    print(f"  Max cycles: {args.max_cycles}")
    print(f"  Resume mode: {args.resume}")

    launcher = Launcher(
        session_id=args.session_id,
        max_cycles=args.max_cycles,
        resume=args.resume,
    )
    result = launcher.run()

    if not result["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
