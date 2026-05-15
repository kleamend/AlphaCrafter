import os
import sys
import json
import time
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
    TRADER_INSTRUCTION
)
from agent.toolkit import (
    ReadFileTool, WriteFileTool, ShellTool, 
    GetStockDataTool, GetIndexDataTool, StepTool,
    BacktestTool, SearchFactorTool, GetFinancialStatementsTool, GetNewsTool
)
from agent.skills import (
    QuantitativeTradingSkill, 
    FactorMiningSkill,
    FactorScreeningSkill,
    StrategyRegistrationSkill,
    PositionManagementSkill
)

from alphacrafter.sim.utils import finish_check, get_account_dict, get_date_str

load_dotenv()


@dataclass
class CycleRecord:
    """Record of a single cycle's outputs from all agents."""
    cycle: int
    miner_output: str = ""
    screener_output: str = ""
    trader_output: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class Launcher:
    """Orchestrates the iterative workflow of Miner, Screener, and Trader agents."""
    
    def __init__(self, session_id: str, max_cycles: int = 300, resume: bool = False):
        """
        Initialize the launcher with a session ID and maximum cycles.
        
        Args:
            session_id: Session identifier for workspace
            max_cycles: Maximum number of workflow cycles to run
            resume: Whether to resume from previous workflow state
        """
        self.session_id = session_id
        self.max_cycles = max_cycles
        self.resume = resume
        self.workspace_path = None
        
        # Agent instances
        self.miner_agent = None
        self.screener_agent = None
        self.trader_agent = None
        
        # History storage
        self.cycle_records: List[CycleRecord] = []
        
        # Logging
        self.log_path = "../logs/workflow.json"
        self.miner_log_path = "../logs/miner_agent.json"
        self.screener_log_path = "../logs/screener_agent.json"
        self.trader_log_path = "../logs/trader_agent.json"
        
        # Store last inputs for resume mode (loaded before agent initialization)
        self.last_miner_input = None
        self.last_screener_input = None
        self.last_trader_input = None
        
    def _get_session_workspace(self) -> str:
        """Get existing session workspace path."""
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
        """Setup workspace environment."""
        os.chdir(self.workspace_path)
        if self.workspace_path not in sys.path:
            sys.path.insert(0, self.workspace_path)
        
        print(f"\nWorking in: {self.workspace_path}")
        print("\nCurrent workspace contents:")
        for item in os.listdir('.'):
            print(f"  - {item}")
    
    def _load_last_input_from_agent_log(self, agent_log_path: str) -> Optional[List[Dict[str, str]]]:
        """Extract the last input from an agent's log file and convert to simple user message."""
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
        
        # Find the last successful run with input
        for entry in reversed(entries):
            if entry.get('event') == 'run_complete':
                final_state = entry.get('final_state', {})
                if final_state.get('success') and final_state.get('input'):
                    original_input = final_state['input']
                    
                    # Convert the input array to a single user message
                    return self._aggregate_input_to_user_message(original_input)
        
        return None

    def _aggregate_input_to_user_message(self, input_array: List) -> List[Dict[str, str]]:
        """
        Aggregate various input elements (messages, tool calls, tool outputs) 
        into a single user message with the entire conversation context.
        """
        if not input_array:
            return [{"role": "user", "content": ""}]
        
        aggregated_content = "you are resuming from the previous session: " + str(input_array)  # For simplicity, we convert the entire input array to a string.
        
        return [{"role": "user", "content": aggregated_content}]
    
    def _load_previous_workflow_state(self) -> Optional[int]:
        """Load previous workflow state from logs BEFORE agent initialization."""
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
        
        # Group entries by cycle
        cycles = {}
        for entry in entries:
            cycle_num = entry.get('cycle')
            if cycle_num not in cycles:
                cycles[cycle_num] = {'miner': None, 'screener': None, 'trader': None}
            phase = entry.get('phase')
            if phase in cycles[cycle_num]:
                cycles[cycle_num][phase] = entry
        
        # Find the last complete cycle (all three phases completed successfully)
        last_complete_cycle = None
        for cycle_num in sorted(cycles.keys()):
            cycle_data = cycles[cycle_num]
            if (cycle_data['miner'] and cycle_data['miner'].get('success') and
                cycle_data['screener'] and cycle_data['screener'].get('success') and
                cycle_data['trader'] and cycle_data['trader'].get('success')):
                last_complete_cycle = cycle_num
        
        if last_complete_cycle is not None:
            print(f"Found previous workflow state. Last complete cycle: {last_complete_cycle}")
            
            # Reconstruct cycle records
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
        """Load last inputs from agent logs BEFORE agent initialization."""
        if not self.resume:
            return
        
        print("\n" + "="*60)
        print("📂 LOADING RESUME INPUTS FROM LOGS")
        print("="*60)
        
        # Load last inputs from each agent's log
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
    
    def _create_miner_agent(self) -> Agent:
        """Create and configure miner agent for factor discovery."""
        toolkit = [
            ReadFileTool(),
            WriteFileTool(),
            ShellTool(),
            SearchFactorTool(),
        ]
        
        skills = [QuantitativeTradingSkill(), FactorMiningSkill()]
        
        ADDITIONAL_INFO = """
Here are some market index references:

CSI300 (000300.SH) is the CSI 300 Index, a capitalization-weighted stock market index designed to replicate the performance of the top 300 stocks traded on the Shanghai and Shenzhen stock exchanges. It is the primary benchmark for the Chinese A-share market, similar to the S&P 500 in the US. The index covers approximately 60% of the total market capitalization of the A-share market and is widely used for institutional investment benchmarking, index funds, and derivatives such as futures and options.
"""
        
        agent = Agent(
            model_code="gpt-5.3-codex",
            toolkit=toolkit,
            skills=skills,
            instructions=QUANTITATIVE_TRADING_INSTRUCTION_A + "\n\n" + MINER_INSTRUCTION + "\n\n" + ADDITIONAL_INFO,
            config_path="../config/models.json",
            log_file="../logs/miner_agent.json",
            summary_interval=15,
            force_tool_call=False
        )
        
        return agent
    
    def _create_screener_agent(self) -> Agent:
        """Create and configure screener agent for factor selection and ensemble construction."""
        toolkit = [
            ShellTool(),
            GetStockDataTool(),
            GetIndexDataTool(),
            SearchFactorTool(),
            GetFinancialStatementsTool(),
            GetNewsTool()
        ]
        
        skills = [FactorScreeningSkill()]

        ADDITIONAL_INFO = """
Here are some market index references:

CSI300 (000300.SH) is the CSI 300 Index, a capitalization-weighted stock market index designed to replicate the performance of the top 300 stocks traded on the Shanghai and Shenzhen stock exchanges. It is the primary benchmark for the Chinese A-share market, similar to the S&P 500 in the US. The index covers approximately 60% of the total market capitalization of the A-share market and is widely used for institutional investment benchmarking, index funds, and derivatives such as futures and options.
"""
        
        agent = Agent(
            model_code="gpt-5.3-codex",
            toolkit=toolkit,
            skills=skills,
            instructions=QUANTITATIVE_TRADING_INSTRUCTION_A + "\n\n" + SCREENER_INSTRUCTION + "\n\n" + ADDITIONAL_INFO,
            config_path="../config/models.json",
            log_file="../logs/screener_agent.json",
            summary_interval=15,
            force_tool_call=False
        )
        
        return agent
    
    def _create_trader_agent(self) -> Agent:
        """Create and configure trader agent for portfolio execution."""
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
        
        agent = Agent(
            model_code="gpt-5.3-codex",
            toolkit=toolkit,
            skills=skills,
            instructions=QUANTITATIVE_TRADING_INSTRUCTION_A + "\n\n" + TRADER_INSTRUCTION + "\n\n" + ADDITIONAL_INFO,
            config_path="../config/models.json",
            log_file="../logs/trader_agent.json",
            summary_interval=15,
            force_tool_call=False
        )
        
        return agent
    
    def _run_agent_phase(self, agent: Agent, context: str, phase_name: str, max_iterations: int = 100) -> Dict[str, Any]:
        """Run a single agent phase with given context."""
        print(f"\n{'='*60}")
        print(f"🔬 {phase_name.upper()} PHASE")
        print(f"{'='*60}")
        
        input_messages = [{"role": "user", "content": context}] if context else [{"role": "user", "content": ""}]
        
        result = agent.run(
            input_messages, 
            max_iterations=max_iterations, 
            finish_check=finish_check
        )
        
        print(f"\n{'='*60}")
        print(f"🔬 {phase_name.upper()} PHASE COMPLETED")
        print(f"{'='*60}")
        
        return result
    
    def _run_agent_phase_with_resume(self, agent: Agent, last_input: Optional[List[Dict[str, str]]], 
                                      context: str, phase_name: str, max_iterations: int = 100) -> Dict[str, Any]:
        """Run an agent phase, using last_input if in resume mode and available."""
        if self.resume and last_input:
            print(f"\n{'='*60}")
            print(f"🔬 {phase_name.upper()} PHASE - RESUMING FROM LAST INPUT")
            print(f"{'='*60}")
            print(f"Using last input from previous run")
            
            result = agent.run(
                last_input, 
                max_iterations=max_iterations, 
                finish_check=finish_check
            )
            
            print(f"\n{'='*60}")
            print(f"🔬 {phase_name.upper()} PHASE COMPLETED (RESUMED)")
            print(f"{'='*60}")
            
            return result
        else:
            return self._run_agent_phase(agent, context, phase_name, max_iterations)
    
    def _should_terminate(self, result: Dict[str, Any]) -> bool:
        """Determine if workflow should terminate based on result."""
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
        except:
            pass
        
        return False
    
    def _log_workflow_entry(self, cycle: int, phase: str, result: Dict[str, Any]):
        """Append a workflow entry to JSON log file."""
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        
        entries = []
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, 'r', encoding='utf-8') as f:
                    entries = json.load(f)
                    if not isinstance(entries, list):
                        entries = [entries]
            except:
                entries = []
        
        entries.append({
            "cycle": cycle,
            "phase": phase,
            "timestamp": datetime.now().isoformat(),
            "success": result.get("success", False),
            "interrupted": result.get("interrupted", False),
            "output_text": result.get("output_text", "")
        })
        
        with open(self.log_path, 'w', encoding='utf-8') as f:
            json.dump(entries, f, indent=2, ensure_ascii=False, default=str)
    
    def _build_miner_context(self) -> str:
        """Build context for miner agent using previous miner output only."""
        context_parts = []
        
        # Add account and date information
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
        
        # Add previous miner output
        if self.cycle_records:
            last_record = self.cycle_records[-1]
            if last_record.miner_output:
                context_parts.append(f"Previous miner agent output: {last_record.miner_output}")
            if last_record.screener_output:
                context_parts.append(f"Previous screener agent output: {last_record.screener_output}")
        
        return "\n".join(context_parts) if context_parts else ""

    def _build_screener_context(self) -> str:
        """Build context for screener agent using current miner output and previous screener+trader history."""
        context_parts = []
        
        # Add account and date information
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
        
        # Current cycle miner output
        if last_record.miner_output:
            context_parts.append(f"Miner agent output from current cycle: {last_record.miner_output}")
        
        # Previous cycle screener and trader outputs (if they exist)
        if len(self.cycle_records) >= 2:
            prev_record = self.cycle_records[-2]
            if prev_record.screener_output:
                context_parts.append(f"Previous screener agent output: {prev_record.screener_output}")
            if prev_record.trader_output:
                context_parts.append(f"Previous trader agent output: {prev_record.trader_output}")
        
        return "\n\n".join(context_parts) if context_parts else ""

    def _build_trader_context(self) -> str:
        """Build context for trader agent using current screener output and previous trader history."""
        context_parts = []
        
        # Add account and date information
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
        
        # Current cycle screener output
        if last_record.screener_output:
            context_parts.append(f"Screener agent output from current cycle: {last_record.screener_output}")
        
        # Previous cycle trader output
        if len(self.cycle_records) >= 2:
            prev_record = self.cycle_records[-2]
            if prev_record.trader_output:
                context_parts.append(f"Previous trader agent output: {prev_record.trader_output}")
        
        return "\n\n".join(context_parts) if context_parts else ""
    
    def _run_single_cycle(self, cycle: int, is_resume_cycle: bool = False) -> bool:
        """Execute a single cycle of Miner -> Screener -> Trader."""
        print("\n" + "█"*60)
        if is_resume_cycle:
            print(f"🔄 RESUME CYCLE {cycle}/{self.max_cycles}")
        else:
            print(f"🔄 CYCLE {cycle}/{self.max_cycles}")
        print("█"*60)
        
        record = CycleRecord(cycle=cycle)
        
        # Step 1: Run Miner Agent (factor discovery)
        miner_context = self._build_miner_context()
        miner_result = self._run_agent_phase_with_resume(
            self.miner_agent, 
            self.last_miner_input if is_resume_cycle else None,
            miner_context, 
            "miner", 
            max_iterations=100
        )
        record.miner_output = miner_result.get("output_text", "")
        
        print(f"\n--- 🔄 Cycle {cycle} Miner Output ---")
        print(f"{record.miner_output}")
        
        self._log_workflow_entry(cycle, "miner", miner_result)
        
        if self._should_terminate(miner_result):
            return False
        
        # Add record with miner output so screener can access it
        self.cycle_records.append(record)
        
        # Step 2: Run Screener Agent (factor selection and ensemble)
        screener_context = self._build_screener_context()
        screener_result = self._run_agent_phase_with_resume(
            self.screener_agent,
            self.last_screener_input if is_resume_cycle else None,
            screener_context,
            "screener",
            max_iterations=100
        )
        record.screener_output = screener_result.get("output_text", "")
        
        print(f"\n--- 🔄 Cycle {cycle} Screener Output ---")
        print(f"{record.screener_output}")
        
        self._log_workflow_entry(cycle, "screener", screener_result)
        
        if self._should_terminate(screener_result):
            return False
        
        # Update record with screener output
        self.cycle_records[-1] = record
        
        # Step 3: Run Trader Agent (execution)
        trader_context = self._build_trader_context()
        trader_result = self._run_agent_phase_with_resume(
            self.trader_agent,
            self.last_trader_input if is_resume_cycle else None,
            trader_context,
            "trader",
            max_iterations=100
        )
        record.trader_output = trader_result.get("output_text", "")
        
        print(f"\n--- 🔄 Cycle {cycle} Trader Output ---")
        print(f"{record.trader_output}")
        
        self._log_workflow_entry(cycle, "trader", trader_result)
        
        if self._should_terminate(trader_result):
            return False
        
        # Final update with trader output
        self.cycle_records[-1] = record
        
        print(f"\n💾 Cycle {cycle} completed")
        
        return True
    
    def run(self) -> Dict[str, Any]:
        """Run the full iterative workflow."""
        try:
            # Setup workspace
            self.workspace_path = self._get_session_workspace()
            self._setup_workspace()
            
            # IMPORTANT: Load resume inputs BEFORE creating agents
            # This ensures we capture the last inputs before agent initialization
            # might overwrite the log files
            if self.resume:
                self._load_resume_inputs()
                last_complete_cycle = self._load_previous_workflow_state()
            else:
                last_complete_cycle = None
            
            # Create agents (this may initialize/overwrite log files)
            self.miner_agent = self._create_miner_agent()
            self.screener_agent = self._create_screener_agent()
            self.trader_agent = self._create_trader_agent()
            
            # Handle resume mode workflow
            if self.resume and last_complete_cycle is not None:
                print("\n" + "="*60)
                print(f"🚀 RESUMING WORKFLOW from cycle {last_complete_cycle + 1} (max {self.max_cycles} cycles total)")
                print("="*60)
                
                # Run the resume cycle using saved inputs
                next_cycle = last_complete_cycle + 1
                should_continue = self._run_single_cycle(next_cycle, is_resume_cycle=True)
                
                if not should_continue:
                    print("Workflow terminated during resume cycle.")
                    return {
                        "success": True,
                        "total_cycles": len(self.cycle_records),
                        "cycle_records": [asdict(r) for r in self.cycle_records]
                    }
                
                # Continue with normal cycles (without resume inputs) after the first resume cycle
                current_cycle = next_cycle
            else:
                if self.resume:
                    print("\nNo previous workflow state found. Starting fresh.")
                print("\n" + "="*60)
                print(f"🚀 STARTING NEW WORKFLOW (max {self.max_cycles} cycles)")
                print("="*60)
                current_cycle = 0
            
            # Run remaining cycles
            cycle = current_cycle
            while cycle < self.max_cycles:
                cycle += 1
                # After the first cycle (if it was a resume cycle), subsequent cycles use normal mode
                is_resume = (self.resume and cycle == current_cycle + 1 and current_cycle > 0)
                should_continue = self._run_single_cycle(cycle, is_resume_cycle=is_resume)
                if not should_continue:
                    break
            
            # Final summary
            print("\n" + "="*60)
            print("🎯 WORKFLOW COMPLETED")
            print("="*60)
            print(f"Total cycles: {len(self.cycle_records)}")
            print(f"✅ Workflow log saved to {self.log_path}")
            
            return {
                "success": True,
                "total_cycles": len(self.cycle_records),
                "cycle_records": [asdict(r) for r in self.cycle_records]
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


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run quantitative trading workflow with Miner, Screener, and Trader agents"
    )
    parser.add_argument(
        "session_id",
        type=str,
        help="Session identifier for the workspace"
    )
    parser.add_argument(
        "--max-cycles", "-m",
        type=int,
        default=300,
        help="Maximum number of workflow cycles to run (default: 300)"
    )
    parser.add_argument(
        "--resume", "-r",
        action="store_true",
        help="Resume from previous workflow state using logs"
    )
    
    return parser.parse_args()


def main():
    """Main entry point for the workflow."""
    args = parse_arguments()
    
    print(f"Starting workflow with:")
    print(f"  Session ID: {args.session_id}")
    print(f"  Max cycles: {args.max_cycles}")
    print(f"  Resume mode: {args.resume}")
    
    launcher = Launcher(
        session_id=args.session_id,
        max_cycles=args.max_cycles,
        resume=args.resume
    )
    result = launcher.run()
    
    if not result["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()