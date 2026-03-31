"""
Centralized logging configuration for Genesis Engine.
Uses the Rich library for colorful, structured terminal output.
"""
import logging
import os
from datetime import datetime
from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

# Shared console instance used across the entire application
console = Console(
    highlight=False,
    theme=Theme({
        "llm":    "bold cyan",
        "node":   "bold magenta",
        "action": "bold yellow",
        "task":   "bold green",
        "asset":  "bold blue",
    }),
)

logger = logging.getLogger("GenesisEngine.llm")


def setup_logging():
    """Configure Rich logging handler for the entire application."""
    import logging.handlers

    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_dir, f"genesis_{timestamp}.log")

    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.DEBUG)

    console_handler = RichHandler(
        console=console,
        rich_tracebacks=True,
        show_path=False,
        markup=False,
    )
    console_handler.setLevel(logging.INFO)

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            console_handler,
            file_handler
        ],
        force=True,
    )
    # Quiet noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("google.generativeai").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.WARNING)
    logging.getLogger("langgraph").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Structured event helpers — call these directly for key lifecycle events
# ---------------------------------------------------------------------------

def log_llm_start(caller: str, mode: str = "generate"):
    """Log that an LLM call has been initiated."""
    logger.debug("LLM %s call initiated for %s", mode, caller)


def log_llm_done(caller: str, mode: str = "generate", elapsed: float = None):
    """Log the completion of an LLM call along with its duration."""
    if elapsed is not None:
        logger.info("LLM %s call for %s completed in %.1fs", mode, caller, elapsed)
    else:
        logger.info("LLM %s call for %s completed", mode, caller)


def log_node_start(node_name: str, task: str = ""):
    """Print a separator when a LangGraph node starts executing."""
    display_task = (task[:65] + "…") if len(task) > 65 else task
    task_str = f" — [dim]{display_task}[/dim]" if display_task else ""
    console.rule(f"[magenta]{node_name.upper()}[/magenta]{task_str}", style="dim magenta")
    logging.getLogger("GenesisEngine").info(f"NODE START: {node_name} - {task}")


def log_node_done(node_name: str, result: str = ""):
    """Print the completion status of a LangGraph node."""
    result_str = f"  [dim]→ {result}[/dim]" if result else ""
    console.print(f"  ✓  [magenta]{node_name}[/magenta] complete{result_str}")
    logging.getLogger("GenesisEngine").info(f"NODE DONE: {node_name} - {result}")


def log_action_exec(idx: int, total: int, action_type: str, detail: str = ""):
    """Print a single action being executed by the Coder node."""
    detail_str = f"  [dim]{detail}[/dim]" if detail else ""
    console.print(f"    [{idx}/{total}] [yellow]{action_type}[/yellow]{detail_str}")
    logging.getLogger("GenesisEngine").info(f"ACTION EXEC [{idx}/{total}]: {action_type} - {detail}")


def log_task_start(task_desc: str):
    """Print a prominent banner when a new task starts executing."""
    console.rule("[bold green]▶  TASK START[/bold green]", style="green")
    console.print(f"  [bold green]{task_desc}[/bold green]\n")
    logging.getLogger("GenesisEngine").info(f"TASK START: {task_desc}")


def log_task_done(task_desc: str):
    """Print a prominent banner when a task completes successfully."""
    console.print(f"\n  [bold green]✓  TASK DONE:[/bold green]  {task_desc}")
    console.rule(style="dim green")
    logging.getLogger("GenesisEngine").info(f"TASK DONE: {task_desc}")


def log_asset_acquire(asset_type: str, name: str, detail: str = ""):
    """Print when an asset acquisition starts."""
    detail_str = f"  [dim]{detail}[/dim]" if detail else ""
    console.print(f"  🎨 [blue]Acquiring {asset_type}[/blue]: [bold]{name}[/bold]{detail_str}")
    logging.getLogger("GenesisEngine").info(f"ASSET ACQUIRE [{asset_type}]: {name} - {detail}")
