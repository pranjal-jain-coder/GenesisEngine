"""
Centralized logging configuration for Genesis Engine.
Uses the Rich library for colorful, structured terminal output.
"""
import logging
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


def setup_logging():
    """Configure Rich logging handler for the entire application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                console=console,
                rich_tracebacks=True,
                show_path=False,
                markup=False,
            )
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
    """Print a visual indicator that an LLM call is starting."""
    icons = {
        "generate":            "🤖",
        "generate_structured": "📋",
        "generate_with_tools": "🛠️ ",
    }
    icon = icons.get(mode, "🤖")
    console.print(f"  {icon} [cyan]{mode}[/cyan]  ←  [dim]{caller}[/dim]")


def log_llm_done(caller: str, mode: str = "generate", elapsed: float = None):
    """Print a visual indicator that an LLM call completed."""
    timing = f"  [dim]({elapsed:.1f}s)[/dim]" if elapsed is not None else ""
    console.print(f"  ✓  [cyan]{mode} done[/cyan]{timing}  ←  [dim]{caller}[/dim]")


def log_node_start(node_name: str, task: str = ""):
    """Print a separator when a LangGraph node starts executing."""
    display_task = (task[:65] + "…") if len(task) > 65 else task
    task_str = f" — [dim]{display_task}[/dim]" if display_task else ""
    console.rule(f"[magenta]{node_name.upper()}[/magenta]{task_str}", style="dim magenta")


def log_node_done(node_name: str, result: str = ""):
    """Print the completion status of a LangGraph node."""
    result_str = f"  [dim]→ {result}[/dim]" if result else ""
    console.print(f"  ✓  [magenta]{node_name}[/magenta] complete{result_str}")


def log_action_exec(idx: int, total: int, action_type: str, detail: str = ""):
    """Print a single action being executed by the Coder node."""
    detail_str = f"  [dim]{detail}[/dim]" if detail else ""
    console.print(f"    [{idx}/{total}] [yellow]{action_type}[/yellow]{detail_str}")


def log_task_start(task_desc: str):
    """Print a prominent banner when a new task starts executing."""
    console.rule("[bold green]▶  TASK START[/bold green]", style="green")
    console.print(f"  [bold green]{task_desc}[/bold green]\n")


def log_task_done(task_desc: str):
    """Print a prominent banner when a task completes successfully."""
    console.print(f"\n  [bold green]✓  TASK DONE:[/bold green]  {task_desc}")
    console.rule(style="dim green")


def log_asset_acquire(asset_type: str, name: str, detail: str = ""):
    """Print when an asset acquisition starts."""
    detail_str = f"  [dim]{detail}[/dim]" if detail else ""
    console.print(f"  🎨 [blue]Acquiring {asset_type}[/blue]: [bold]{name}[/bold]{detail_str}")
