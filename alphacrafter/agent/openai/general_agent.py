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


class InterruptHandler:
    """Context manager for handling interrupts"""
    
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


class Agent:
    """
    Enhanced agent class that handles tool calls through XML tags in system prompt.
    Compatible with older Chat Completions API that doesn't support native tool calling.
    """
    
    def __init__(
        self,
        model_code: str,
        toolkit: List[BaseTool],
        skills: List[BaseSkill] = None,
        instructions: str = "",
        config_path: str = "../config/models.json",
        log_file: str = "../logs/agent.json",
        summary_interval: int = 20,
        force_tool_call: bool = False
    ):
        """
        Initialize the agent.
        
        Args:
            model_code: Model identifier (e.g., "gpt-4o")
            toolkit: List of tool instances inheriting from BaseTool
            skills: List of skill instances inheriting from BaseSkill
            instructions: System instructions template with {skills} and {tools} placeholders
            config_path: Path to the models configuration JSON file
            log_file: Path to log file for metadata (JSON array format)
            summary_interval: Number of iterations between summaries (default: 20)
            force_tool_call: Whether to force tool call on each iteration (default: False)
        """
        self.model_code = model_code
        self.toolkit = toolkit
        self.skills = skills or []
        self.instructions_template = instructions
        self.config_path = config_path
        self.log_file = log_file
        self.summary_interval = summary_interval
        self.force_tool_call = force_tool_call
        
        # Initialize log storage
        self.log_entries = []
        
        # Load model configuration
        self.model_config = self._load_model_config()
        
        # Get producer from config
        self.producer = self.model_config.get("producer", "OpenAI")
        
        # Initialize OpenAI client
        self.client = OpenAI(
            api_key=os.getenv("API_KEY"),
            base_url=os.getenv("API_URL"),
            timeout=1800
        )
        
        # Extract tool information for system prompt
        self.tool_descriptions = self._build_tool_descriptions()
        self.function_map = {tool.get_name(): tool.get_implementation() for tool in toolkit}
        
        # Build instructions message with skills and tools injected
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
            "timestamp": datetime.now().isoformat()
        })
    
    def _load_existing_logs(self) -> List[Dict[str, Any]]:
        """Load existing log entries from file."""
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
        """Append log entry to file (preserves existing entries)."""
        # Load existing logs
        existing_logs = self._load_existing_logs()
        
        # Append new entry
        existing_logs.append(entry)
        
        # Write back to file
        log_dir = Path(self.log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(existing_logs, f, indent=2, ensure_ascii=False, default=str)
    
    def _build_tool_descriptions(self) -> str:
        """Build tool descriptions for system prompt"""
        if not self.toolkit:
            return "No tools available."
        
        tools_text = "Available Tools:\n\n"
        for i, tool in enumerate(self.toolkit, 1):
            tool_desc = tool.get_description(producer=self.producer)
            tools_text += f"{i}. {tool.get_name()}\n"
            tools_text += f"   Description: {str(tool_desc)}\n"
            tools_text += "\n"
        
        # Add tool calling instructions
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

Example:
<tool_call>
{
  "name": "example_tool",
    "arguments": {
        "symbol": "EXAMPLE",
        "number": 5
    }
}

You can include explanatory text before or after the tool call. After you receive the tool response, continue with your task based on the result.
"""
        
        if self.force_tool_call:
            tools_text += "\nIMPORTANT: You MUST make at least one tool call in each response.\n"
        
        return tools_text
    
    def _build_instructions(self) -> str:
        """Build instructions by injecting skills and tools into template"""
        if not self.instructions_template:
            instructions = ""
        else:
            instructions = self.instructions_template
        
        # Format skills information
        if self.skills:
            skills_text = "\n\nAvailable Skills:\n"
            for skill in self.skills:
                skills_text += f"Name: {skill.get_name()}\n"
                skills_text += f"Description: {skill.get_description()}\n"
                skills_text += f"Details: {skill.get_details()}\n"
        else:
            skills_text = "\n\nNo skills available."
        
        # Add tools information
        tools_text = self._build_tool_descriptions()
        
        instructions = instructions + tools_text + skills_text
        
        return instructions
    
    def _parse_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse tool calls from text using XML tags.
        
        Args:
            text: Text that may contain <tool_call> tags
            
        Returns:
            List of parsed tool calls
        """
        tool_calls = []
        
        # Pattern to match <tool_call>...</tool_call> tags
        pattern = r'<tool_call>\s*(.*?)\s*</tool_call>'
        matches = re.findall(pattern, text, re.DOTALL)
        
        for i, match in enumerate(matches):
            try:
                # Try to parse JSON
                tool_data = json.loads(match.strip())
                
                # Validate required fields
                if "name" not in tool_data:
                    print(f"⚠️ Tool call missing 'name' field: {match}")
                    continue
                
                tool_call = {
                    "name": tool_data["name"],
                    "arguments": tool_data.get("arguments", {}),
                    "call_id": f"call_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}"
                }
                
                tool_calls.append(tool_call)
                
            except json.JSONDecodeError as e:
                print(f"⚠️ Failed to parse tool call JSON: {e}")
                print(f"   Raw content: {match}")
                continue
        
        return tool_calls
    
    def _load_model_config(self) -> Dict[str, Any]:
        """Load configuration for the specified model from JSON file."""
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
        """
        Calculate input and output costs based on model configuration.
        Costs are assumed to be per million tokens.
        """
        cost_per_million_input = self.model_config.get("cost", {}).get("input", 0)
        cost_per_million_output = self.model_config.get("cost", {}).get("output", 0)
        
        input_cost = input_tokens * cost_per_million_input / 1_000_000
        output_cost = output_tokens * cost_per_million_output / 1_000_000
        
        return {
            "input_cost": round(input_cost, 8),
            "output_cost": round(output_cost, 8),
            "total_cost": round(input_cost + output_cost, 8)
        }
    
    def _log_metadata(self, result: Dict[str, Any], iteration: int):
        """Log interaction metadata to file as JSON array."""
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
            "interrupted": result.get("interrupted", False)
        }
        
        self._append_log(metadata)
    
    def _summarize(self, current_messages: List[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
        """
        Use the model to summarize what happened in this step.
        
        Args:
            current_messages: The messages list before this step
            
        Returns:
            Tuple containing (summary string, cost information)
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
                    {"role": "user", "content": f"Please summarize the following conversation:\n\n{json.dumps(current_messages, default=str)}"}
                ],
            )
            
            # Extract token usage
            usage = getattr(response, "usage", None)
            input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
            output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
            
            # Calculate costs
            costs = self._calculate_costs(input_tokens, output_tokens)
            
            summary_text = response.choices[0].message.content or ""
            
            # Log memory usage to file
            self._append_log({
                "event": "memory_summary",
                "timestamp": datetime.now().isoformat(),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "input_cost": costs["input_cost"],
                "output_cost": costs["output_cost"],
                "total_cost": costs["total_cost"],
                "summary_length": len(summary_text)
            })
            
            # Print to console
            print(f"📝 Memory summary generated - {output_tokens} tokens, ${costs['total_cost']:.6f}")
            
            return summary_text, costs
            
        except Exception as e:
            print(f"Failed to generate summary: {e}")
            return "Step completed.", {"input_cost": 0, "output_cost": 0, "total_cost": 0}
    
    def get_response(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Call OpenAI Chat Completions API and parse tool calls from response.
        
        Args:
            messages: Message list following Chat Completions format
            
        Returns:
            Dictionary containing response details
        """
        print(f"📤 API Request - {len(messages)} messages")
        
        # Prepare messages with system instruction
        chat_messages = []
        
        print(f"📜 System instructions length: {len(self.instructions)} characters")
        # Add system instruction if provided
        if self.instructions:
            chat_messages.append({"role": "system", "content": self.instructions})
        
        # Add all messages
        for msg in messages:
            chat_messages.append(msg)
        
        # Call Chat Completions API (no tools parameter)
        response = self.client.chat.completions.create(
            model=self.model_code,
            messages=chat_messages,
        )

        # Extract token usage
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        
        # Calculate costs
        costs = self._calculate_costs(input_tokens, output_tokens)
        
        # Extract text content
        output_text = response.choices[0].message.content or ""
        finish_reason = response.choices[0].finish_reason
        
        # Parse tool calls from text
        tool_calls = self._parse_tool_calls(output_text)
        
        # Create assistant message (without tool call tags for cleaner conversation)
        assistant_message = {
            "role": "assistant",
            "content": output_text  # Keep original if cleaning removes everything
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
    
    @contextlib.contextmanager
    def _run_context(self):
        """Context manager for run execution"""
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        start_time = datetime.now()
        
        # Log run start
        self._append_log({
            "event": "run_start",
            "run_id": run_id,
            "timestamp": start_time.isoformat(),
            "model": self.model_code
        })
        
        try:
            yield run_id
        finally:
            # Log run end
            duration = (datetime.now() - start_time).total_seconds()
            self._append_log({
                "event": "run_end",
                "run_id": run_id,
                "duration_seconds": round(duration, 2),
                "timestamp": datetime.now().isoformat()
            })
    
    def run(
        self, 
        initial_messages: List[Dict[str, Any]], 
        max_iterations: int = 100,
        finish_check: Optional[Callable[[], bool]] = None
    ) -> Dict[str, Any]:
        """
        Run the agent with automatic multi-turn tool handling.
        
        Args:
            initial_messages: Initial message list in Chat Completions format
            max_iterations: Maximum number of iterations to prevent infinite loops
            finish_check: Optional function that takes no arguments and returns 
                        True if the run should finish, False to continue
            
        Returns:
            Dictionary containing the final result and summary information
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
                
                # Get response from model
                result, assistant_message = self.get_response(current_messages)
                result["interrupted"] = handler.interrupted
                last_result = result
    
                # Update metadata with iteration
                self._log_metadata(result, iteration)
                
                # Update totals
                total_cost += result["total_cost"]
                all_tool_calls.extend(result["tool_calls"])
                
                # Check finish condition if provided
                if finish_check and finish_check():
                    print("✅ Finish condition met")
                    break
                
                # If no tool calls or interrupted, end the run
                if not result["tool_calls"] or handler.interrupted:
                    if handler.interrupted:
                        print("⏹️ Run interrupted by user")
                    else:
                        print("✅ No more tool calls required - ending run")
                    break
                
                print(f"⚙️ Executing {len(result['tool_calls'])} tool call(s)...")
                
                # Add assistant message to messages
                current_messages.append(assistant_message)
                
                # Execute tool calls and append results
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
                        
                        # Log error metadata
                        self._append_log({
                            "event": "tool_error",
                            "timestamp": datetime.now().isoformat(),
                            "iteration": iteration,
                            "tool": func_name,
                            "error": error_msg
                        })
                        
                        raise ValueError(error_msg)
                    
                    # Execute the tool
                    func = self.function_map[func_name]
                    
                    try:
                        output = func(**arguments)
                        # Convert output to string if it's not already
                        output_str = json.dumps(output, ensure_ascii=False, default=str) if not isinstance(output, str) else output
                        print(f"  ✅ {func_name} output: {output_str[:1000]}...[truncated]")
                        
                        tool_responses.append({
                            "tool_name": func_name,
                            "call_id": call_id,
                            "response": output_str
                        })
                        
                    except Exception as e:
                        output_str = f"Tool execution error: {str(e)}"
                        print(f"  ❌ {func_name} failed: {e}")
                        
                        tool_responses.append({
                            "tool_name": func_name,
                            "call_id": call_id,
                            "response": output_str,
                            "error": True
                        })
                        
                        # Log error metadata
                        self._append_log({
                            "event": "tool_error",
                            "timestamp": datetime.now().isoformat(),
                            "iteration": iteration,
                            "tool": func_name,
                            "error": str(e)
                        })
                
                # Add tool responses as a single tool message in XML format
                if tool_responses:
                    tool_response_text = ""
                    for resp in tool_responses:
                        tool_response_text += f"\n<tool_response>\n"
                        tool_response_text += json.dumps({
                            "name": resp["tool_name"],
                            "call_id": resp["call_id"],
                            "response": resp["response"]
                        }, ensure_ascii=False, indent=2)
                        tool_response_text += f"\n</tool_response>\n"
                    
                    current_messages.append({
                        "role": "user",
                        "content": f"Tool execution results:{tool_response_text}"
                    })
                
                # Generate summary based on interval
                if iteration % self.summary_interval == 0:
                    print(f"📝 Reached {iteration} iterations, generating summary...")
                    
                    summary, memory_costs = self._summarize(current_messages)
                    total_cost += memory_costs["total_cost"]
                    
                    # Log step summary
                    self._append_log({
                        "event": "interval_summary",
                        "timestamp": datetime.now().isoformat(),
                        "iteration": iteration,
                        "summary": summary,
                        "interval": self.summary_interval,
                        "tools_executed_in_interval": [tc["name"] for tc in result["tool_calls"]]
                    })
                    
                    # Add summary as a system message
                    current_messages.append({
                        "role": "system",
                        "content": f"Progress summary after {iteration} iterations: {summary}\n\nContinue with the task."
                    })
                    
                    print(f"📋 Interval summary: {summary[:1000]}...[truncated]")
            
            if iteration >= max_iterations and not handler.interrupted:
                print(f"⚠️ Max iterations ({max_iterations}) reached")
            
            # Final summary
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
            
            # Prepare return value
            final_state = {
                "success": last_result is not None,
                "input": current_messages,
                "output_text": last_result.get("output_text") if last_result else None,
                "interrupted": handler.interrupted
            }
            
            # Log run completion - using the same format as the new code
            self._append_log({
                "event": "run_complete",
                "timestamp": datetime.now().isoformat(),
                "total_iterations": iteration,
                "total_cost": total_cost,
                "total_tool_calls": len(all_tool_calls),
                "tools_used": list(tools_used) if all_tool_calls else [],
                "final_state": final_state
            })

            print(f"🚀 Agent run completed.")
            
            return final_state